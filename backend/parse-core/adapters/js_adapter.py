"""
backend/parse-core/adapters/js_adapter.py

JavaScript / TypeScript → CIRGraph builder.  v3

What's new in v3
----------------
Option B: Module-level function extraction
  Files that contain NO ES6 classes (e.g. Express route files, functional
  model files, utility modules) are now handled by extracting every exported
  function and grouping them into a single pseudo-class named after the file.

  Examples
  --------
  models/userModel.js   → class  UserModel
    methods: createUser, findUserByUsername, findUserById

  utils/security.js     → class  Security
    methods: hashPassword, comparePassword, generateToken, verifyToken

  routes/authRoutes.js  → class  AuthRoutes
    methods: register (POST /register), login (POST /login)

  server.js             → class  Server  (skipped if < 2 exports)

  Import-resolution also builds CALLS / DEPENDS_ON edges between modules:
    authRoutes.js imports { createUser } from userModel.js
    → AuthRoutes CALLS UserModel.createUser

v2 fixes (retained)
-------------------
  1. Fields restricted to constructor this.x = ... assignments only
  2. _module_to_package() strips temp dirs → clean package names
  3. CALLS edges handle this.fieldName.method() two-hop chains
  4. Esprima fields from PropertyDefinition only
"""

from __future__ import annotations

import re
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from cir.model import TypeDecl, Field, Method, Parameter
from cir.graph import CIRGraph

# ── Try to import esprima ─────────────────────────────────────────────────
try:
    import esprima          # type: ignore
    _ESPRIMA_OK = True
except ImportError:
    _ESPRIMA_OK = False

# ── Primitives / built-ins ────────────────────────────────────────────────
_JS_PRIMITIVES: Set[str] = {
    "string", "number", "boolean", "null", "undefined", "void", "any",
    "never", "unknown", "object", "symbol", "bigint",
    "String", "Number", "Boolean", "Object", "Array", "Function",
    "Date", "RegExp", "Error", "Map", "Set", "WeakMap", "WeakSet",
    "Promise", "Iterable", "Iterator", "Generator",
    "Router", "Request", "Response", "NextFunction",   # Express noise
    "Pool", "Client",                                   # pg noise
}

_COLLECTION_PREFIXES = (
    "Array<", "array<", "Set<", "set<",
    "Map<",   "map<",   "List<", "list<",
    "ReadonlyArray<", "Iterable<",
)

_SKIP_NAMES: Set[str] = {
    "constructor", "if", "else", "for", "while", "switch", "return",
    "const", "let", "var", "class", "function", "import", "export",
    "new", "delete", "typeof", "instanceof", "in", "of", "try", "catch",
    "finally", "throw", "async", "await", "yield", "super", "this",
    "true", "false", "null", "undefined", "break", "continue", "case",
    "default", "do", "debugger", "with", "void", "static", "extends",
    "implements", "interface", "enum", "abstract", "readonly", "override",
    "public", "private", "protected", "get", "set", "from", "as",
    # Express / Node noise that should never become method names
    "use", "listen", "config", "on", "emit", "pipe",
    "json", "send", "status", "end", "next", "query",
}

# Files that are pure config/static and should not produce pseudo-classes
_SKIP_FILE_STEMS: Set[str] = {
    "server", "app", "index", "main",          # entry points (optional)
    "package", "tsconfig", "jest.config",      # config
    "style", "script",                          # frontend assets
}

# ═══════════════════════════════════════════════════════════════════════════
#  Basic helpers
# ═══════════════════════════════════════════════════════════════════════════

def _visibility_from_name(name: str) -> str:
    if name.startswith("#"):
        return "private"
    if name.startswith("_") and not name.startswith("__"):
        return "protected"
    return "public"


def _resolve_type_and_multiplicity(
    ts_type: Optional[str],
) -> Tuple[str, str, Optional[str]]:
    if not ts_type:
        return "any", "any", None
    raw = ts_type.strip()
    if raw.endswith("[]"):
        inner = raw[:-2].strip()
        logical = inner.split("<")[0].split(".")[-1]
        return logical, raw, "0..*"
    for prefix in _COLLECTION_PREFIXES:
        if raw.startswith(prefix) and raw.endswith(">"):
            inner_csv = raw[len(prefix):-1].strip()
            parts = [p.strip() for p in inner_csv.split(",")]
            if prefix.lower().startswith("map"):
                logical = parts[1].split("<")[0].split(".")[-1] if len(parts) > 1 else "Any"
            else:
                logical = parts[0].split("<")[0].split(".")[-1]
            return logical, raw, "0..*"
    for wrapper in ("Promise<", "Observable<", "Subject<", "Optional<"):
        if raw.startswith(wrapper) and raw.endswith(">"):
            inner = raw[len(wrapper):-1].strip()
            logical = inner.split("<")[0].split(".")[-1]
            return logical, raw, "1"
    logical = raw.split("<")[0].split(".")[-1]
    return logical, raw, "1"


def _format_params_from_esprima(params: List[Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for p in params:
        name = ""
        if p.type == "Identifier":
            name = p.name
        elif p.type == "AssignmentPattern":
            left = p.left
            if hasattr(left, "name"):
                name = left.name
        elif p.type == "RestElement":
            arg = p.argument
            if hasattr(arg, "name"):
                name = "..." + arg.name
        else:
            name = getattr(p, "name", str(p.type))
        if name:
            result.append({"name": name, "type_name": "any", "raw_type": "any"})
    return result


def _walk_esprima(node: Any):
    if node is None:
        return
    yield node
    for key in vars(node) if hasattr(node, "__dict__") else {}:
        child = getattr(node, key, None)
        if child is None:
            continue
        if isinstance(child, list):
            for item in child:
                if item and hasattr(item, "type"):
                    yield from _walk_esprima(item)
        elif hasattr(child, "type"):
            yield from _walk_esprima(child)


def _parse_param_string(param_str: str) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for part in param_str.split(","):
        part = part.strip()
        if not part:
            continue
        part = part.split("=")[0].strip()
        part = re.sub(r'\b(readonly|public|private|protected)\b', "", part).strip()
        if ":" in part:
            pname, ptype = part.split(":", 1)
            pname = pname.strip().lstrip("?").lstrip(".")
            ptype = ptype.strip()
        else:
            pname = part.strip().lstrip("?").lstrip(".")
            ptype = "any"
        if pname:
            logical, raw, _ = _resolve_type_and_multiplicity(ptype)
            result.append({"name": pname, "type_name": logical, "raw_type": raw})
    return result


def _extract_brace_block(text: str, start: int) -> str:
    """Return content between matching braces, starting search from `start`."""
    depth = 0
    i = start
    block_start = -1
    while i < len(text):
        if text[i] == "{":
            depth += 1
            if depth == 1:
                block_start = i + 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[block_start:i] if block_start >= 0 else ""
        i += 1
    return text[block_start:] if block_start >= 0 else ""


# ═══════════════════════════════════════════════════════════════════════════
#  Module-level function extraction  (Option B)
# ═══════════════════════════════════════════════════════════════════════════

# Matches:
#   export const foo = async (params) => { ... }
#   export const foo = (params) => { ... }
#   export async function foo(params) { ... }
#   export function foo(params) { ... }
#   export const foo = async function(params) { ... }
_RE_EXPORT_ARROW = re.compile(
    r'export\s+(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?'
    r'(?:function\s*\*?\s*)?\(([^)]*)\)',
    re.MULTILINE,
)
_RE_EXPORT_FUNC = re.compile(
    r'export\s+(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
    re.MULTILINE,
)
# Named export from object: export { foo, bar }  or  export { foo as bar }
_RE_NAMED_EXPORT = re.compile(
    r'export\s*\{([^}]+)\}',
    re.MULTILINE,
)
# Import: import { foo, bar } from './some/module.js'
_RE_IMPORT = re.compile(
    r'import\s+(?:\*\s+as\s+\w+|\{([^}]*)\}|(\w+))\s+from\s+[\'"]([^\'"]+)[\'"]',
    re.MULTILINE,
)
# Express router method calls:  router.get('/path', handler)
_RE_ROUTER_METHOD = re.compile(
    r'router\.(get|post|put|patch|delete|use)\s*\(\s*[\'"]([^\'"]*)[\'"]',
    re.MULTILINE,
)


def _stem_to_class_name(stem: str) -> str:
    """
    Convert a filename stem to a PascalCase class name.
    e.g. 'userModel' → 'UserModel', 'auth-routes' → 'AuthRoutes'
    """
    # Split on camelCase, dashes, underscores
    parts = re.sub(r'[-_]', ' ', stem)
    parts = re.sub(r'([a-z])([A-Z])', r'\1 \2', parts)
    return "".join(w.capitalize() for w in parts.split())


def _extract_module_imports(code: str) -> Dict[str, List[str]]:
    """
    Return mapping: module_path → [imported_names]
    e.g. { '../models/userModel': ['createUser', 'findUserByUsername'] }
    """
    imports: Dict[str, List[str]] = {}
    for m in _RE_IMPORT.finditer(code):
        named_group = m.group(1)   # { foo, bar }
        default_grp = m.group(2)   # default import
        path        = m.group(3)   # './some/path'

        # Strip .js extension and leading ./
        clean_path = re.sub(r'\.js$', '', path)

        names: List[str] = []
        if named_group:
            for part in named_group.split(","):
                part = part.strip()
                # handle  'foo as bar' → use 'foo' (original export name)
                name = part.split(" as ")[0].strip()
                if name:
                    names.append(name)
        elif default_grp:
            names.append(default_grp)

        if clean_path and names:
            imports.setdefault(clean_path, []).extend(names)

    return imports


def _extract_module_functions(
    code: str,
    module_name: str,
    file_stem: str,
) -> Optional[Dict[str, Any]]:
    """
    Extract all exported functions from a module-style JS file and return
    a single pseudo-class unit dict, or None if nothing meaningful found.
    """
    methods: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    def _add_method(name: str, param_str: str, is_async: bool = False) -> None:
        if name in _SKIP_NAMES or name in seen:
            return
        seen.add(name)
        params = _parse_param_string(param_str)
        methods.append({
            "name": name,
            "return_type": "any",
            "raw_return_type": "any",
            "is_constructor": False,
            "is_static": False,
            "visibility": "public",
            "params": params,
            "is_async": is_async,
        })

    # export const foo = async (...) =>
    for m in _RE_EXPORT_ARROW.finditer(code):
        fname     = m.group(1)
        param_str = m.group(2)
        is_async  = "async" in code[m.start():m.start() + 60]
        _add_method(fname, param_str, is_async)

    # export [async] function foo(...)
    for m in _RE_EXPORT_FUNC.finditer(code):
        fname     = m.group(1)
        param_str = m.group(2)
        is_async  = "async" in code[m.start():m.start() + 30]
        _add_method(fname, param_str, is_async)

    # Express router routes — represent as pseudo-methods named after HTTP verb + path
    router_methods: List[Dict[str, Any]] = []
    router_seen: Set[str] = set()
    for m in _RE_ROUTER_METHOD.finditer(code):
        verb  = m.group(1).upper()
        path  = m.group(2) or "/"
        # e.g.  POST_register,  GET_accounts
        safe_path = re.sub(r'[^a-zA-Z0-9]', '_', path).strip("_") or "root"
        mname = f"{verb}_{safe_path}"
        if mname not in router_seen:
            router_seen.add(mname)
            router_methods.append({
                "name": mname,
                "return_type": "void",
                "raw_return_type": "void",
                "is_constructor": False,
                "is_static": False,
                "visibility": "public",
                "params": [
                    {"name": "req",  "type_name": "any", "raw_type": "any"},
                    {"name": "res",  "type_name": "any", "raw_type": "any"},
                ],
                "is_async": True,
            })

    all_methods = methods + router_methods

    # Need at least one exported function or route to create a pseudo-class
    if not all_methods:
        return None

    class_name = _stem_to_class_name(file_stem)
    full_name  = f"{module_name}.{class_name}" if module_name else class_name

    # Build CALLS from import statements
    # We'll store imports on the unit and resolve them later
    imports = _extract_module_imports(code)

    return {
        "full_name":    full_name,
        "short_name":   class_name,
        "kind":         "class",
        "fields":       [],
        "methods":      all_methods,
        "extends":      [],
        "implements":   [],
        "calls":        [],          # populated during relationship pass
        "_imports":     imports,     # raw import map for relationship resolution
        "_is_module":   True,        # flag: generated from module functions
    }


# ═══════════════════════════════════════════════════════════════════════════
#  CALLS extraction helpers (class-based)
# ═══════════════════════════════════════════════════════════════════════════

def _extract_constructor_fields_from_esprima(body: Any) -> List[Dict[str, Any]]:
    fields: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for n in (_walk_esprima(body) if body else []):
        if not hasattr(n, "type"):
            continue
        if n.type != "AssignmentExpression":
            continue
        left = getattr(n, "left", None)
        if not left or left.type != "MemberExpression":
            continue
        obj  = getattr(left, "object", None)
        prop = getattr(left, "property", None)
        if not obj or not prop:
            continue
        if obj.type != "ThisExpression":
            continue
        fname = getattr(prop, "name", "")
        if not fname or fname in _SKIP_NAMES or fname in seen:
            continue
        seen.add(fname)
        fields.append({
            "name": fname,
            "element_type": "any",
            "raw_type": "any",
            "multiplicity": "1",
            "visibility": _visibility_from_name(fname),
        })
    return fields


def _extract_calls_from_esprima_body(body: Any) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    order = 0
    for n in (_walk_esprima(body) if body else []):
        if not hasattr(n, "type"):
            continue
        if n.type == "NewExpression":
            callee = getattr(n, "callee", None)
            if callee and hasattr(callee, "name") and callee.name:
                calls.append({"qualifier_kind": "new", "qualifier": callee.name,
                               "member": callee.name, "order": order})
                order += 1
        if n.type == "CallExpression":
            callee = getattr(n, "callee", None)
            if not callee:
                continue
            if callee.type == "MemberExpression":
                obj    = getattr(callee, "object",   None)
                prop   = getattr(callee, "property", None)
                member = getattr(prop, "name", "") if prop else ""
                if not member:
                    continue
                if obj and obj.type == "ThisExpression":
                    calls.append({"qualifier_kind": "self",   "qualifier": "this",
                                   "member": member, "order": order})
                    order += 1
                elif obj and obj.type == "MemberExpression":
                    inner_obj  = getattr(obj, "object",   None)
                    inner_prop = getattr(obj, "property", None)
                    field_name = getattr(inner_prop, "name", "") if inner_prop else ""
                    if inner_obj and inner_obj.type == "ThisExpression" and field_name:
                        calls.append({"qualifier_kind": "field", "qualifier": field_name,
                                       "member": member, "order": order})
                        order += 1
                    elif inner_obj and inner_obj.type == "Identifier":
                        q = getattr(inner_obj, "name", "")
                        if q:
                            calls.append({"qualifier_kind": "var", "qualifier": q,
                                           "member": member, "order": order})
                            order += 1
                elif obj and obj.type == "Super":
                    calls.append({"qualifier_kind": "super", "qualifier": "super",
                                   "member": member, "order": order})
                    order += 1
                elif obj and obj.type == "Identifier":
                    q = obj.name or ""
                    kind = "static" if q[:1].isupper() else "var"
                    calls.append({"qualifier_kind": kind, "qualifier": q,
                                   "member": member, "order": order})
                    order += 1
            elif callee.type == "Identifier":
                name = callee.name or ""
                kind = "new" if name[:1].isupper() else "none"
                calls.append({"qualifier_kind": kind, "qualifier": name,
                               "member": name, "order": order})
                order += 1
    return calls


# ═══════════════════════════════════════════════════════════════════════════
#  Regex-based class extractor (fallback / TS supplement)
# ═══════════════════════════════════════════════════════════════════════════

_RE_CLASS = re.compile(
    r'(?:export\s+)?(?:abstract\s+)?(class|interface|enum)\s+(\w+)'
    r'(?:\s+extends\s+([\w,\s<>]+?))?'
    r'(?:\s+implements\s+([\w,\s<>]+?))?'
    r'\s*[{]',
    re.MULTILINE,
)
_RE_CONSTRUCTOR = re.compile(r'\bconstructor\s*\(([^)]*)\)', re.MULTILINE)
_RE_THIS_ASSIGN = re.compile(r'\bthis\.(\w+)\s*=', re.MULTILINE)


def _regex_extract_constructor_fields(constructor_body: str) -> List[Dict[str, Any]]:
    fields: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for m in _RE_THIS_ASSIGN.finditer(constructor_body):
        fname = m.group(1)
        if fname in _SKIP_NAMES or fname in seen:
            continue
        seen.add(fname)
        fields.append({
            "name": fname, "element_type": "any", "raw_type": "any",
            "multiplicity": "1", "visibility": _visibility_from_name(fname),
        })
    return fields


def _regex_extract_classes(
    code: str,
    module_name: Optional[str],
) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []
    for m in _RE_CLASS.finditer(code):
        kind_kw        = m.group(1).lower()
        name           = m.group(2)
        extends_raw    = m.group(3) or ""
        implements_raw = m.group(4) or ""
        full_name      = f"{module_name}.{name}" if module_name else name
        kind           = ("interface" if kind_kw == "interface"
                          else "enum" if kind_kw == "enum" else "class")

        body = _extract_brace_block(code, m.end() - 1)

        # Fields from constructor this.x = only
        fields: List[Dict[str, Any]] = []
        ctor_match = _RE_CONSTRUCTOR.search(body)
        if ctor_match:
            ctor_body = _extract_brace_block(body, ctor_match.end() - 1)
            if not ctor_body:
                ctor_body = body[ctor_match.end():]
            fields = _regex_extract_constructor_fields(ctor_body)

        methods: List[Dict[str, Any]] = []
        method_pattern = re.compile(
            r'(?:(?:public|private|protected|static|abstract|async|override)\s+)*'
            r'(\w+)\s*\(([^)]*)\)\s*(?::\s*([\w<>\[\]|&,\s.]+?))?\s*[{;]',
            re.MULTILINE,
        )
        seen_names: Set[str] = set()
        for mm in method_pattern.finditer(body):
            mname = mm.group(1)
            if mname in _SKIP_NAMES or mname in seen_names:
                continue
            seen_names.add(mname)
            ret_type = (mm.group(3) or "void").strip()
            logical_ret, raw_ret, _ = _resolve_type_and_multiplicity(ret_type)
            methods.append({
                "name": mname, "return_type": logical_ret,
                "raw_return_type": raw_ret,
                "is_constructor": (mname == "constructor"),
                "params": _parse_param_string(mm.group(2)),
            })

        # CALLS from method bodies
        calls: List[Dict[str, Any]] = []
        call_pattern = re.compile(
            r'(?:await\s+)?this\.(\w+)\.(\w+)\s*\(|this\.(\w+)\s*\(',
            re.MULTILINE,
        )
        call_order = 0
        for mm in method_pattern.finditer(body):
            mname = mm.group(1)
            if mname in _SKIP_NAMES:
                continue
            method_id = f"method:{full_name}:{mname}"
            mb_body   = _extract_brace_block(body, mm.end() - 1)
            for cm in call_pattern.finditer(mb_body):
                if cm.group(1) and cm.group(2):
                    calls.append({"src_method_id": method_id, "qualifier_kind": "field",
                                   "qualifier": cm.group(1), "member": cm.group(2),
                                   "order": call_order})
                    call_order += 1
                elif cm.group(3):
                    calls.append({"src_method_id": method_id, "qualifier_kind": "self",
                                   "qualifier": "this", "member": cm.group(3),
                                   "order": call_order})
                    call_order += 1

        extends_list = [e.split("<")[0].strip()
                        for e in re.split(r"[,\s]+", extends_raw.strip())
                        if e.split("<")[0].strip()]
        impl_list = [e.split("<")[0].strip()
                     for e in re.split(r"[,\s]+", implements_raw.strip())
                     if e.split("<")[0].strip()]

        units.append({
            "full_name": full_name, "short_name": name, "kind": kind,
            "fields": fields, "methods": methods,
            "extends": extends_list, "implements": impl_list, "calls": calls,
        })
    return units


# ═══════════════════════════════════════════════════════════════════════════
#  Esprima-based class extractor
# ═══════════════════════════════════════════════════════════════════════════

def _esprima_extract_classes(
    code: str,
    module_name: Optional[str],
) -> List[Dict[str, Any]]:
    try:
        tree = esprima.parseScript(
            code,
            options={"tolerant": True, "jsx": True, "range": False, "loc": False},
        )
    except Exception:
        try:
            tree = esprima.parseModule(code, options={"tolerant": True, "jsx": True})
        except Exception:
            return []

    units: List[Dict[str, Any]] = []

    def _visit(node: Any) -> None:
        if not hasattr(node, "type"):
            return
        if node.type in ("ClassDeclaration", "ClassExpression"):
            _handle_class(node)
        else:
            for key in ("body", "declarations", "expression", "consequent",
                        "alternate", "block", "handler", "finalizer"):
                child = getattr(node, key, None)
                if child is None:
                    continue
                if isinstance(child, list):
                    for item in child:
                        if item and hasattr(item, "type"):
                            _visit(item)
                elif hasattr(child, "type"):
                    _visit(child)
                elif hasattr(child, "body"):
                    for item in (child.body or []):
                        _visit(item)

    def _handle_class(node: Any) -> None:
        id_node   = getattr(node, "id", None)
        name      = id_node.name if id_node and hasattr(id_node, "name") else "AnonymousClass"
        full_name = f"{module_name}.{name}" if module_name else name

        sc = getattr(node, "superClass", None)
        extends_list: List[str] = []
        if sc:
            if hasattr(sc, "name"):
                extends_list.append(sc.name)
            elif hasattr(sc, "property") and hasattr(sc.property, "name"):
                extends_list.append(sc.property.name)

        body_node  = getattr(node, "body", None)
        body_items = (body_node.body or []) if body_node and hasattr(body_node, "body") else []

        fields:  List[Dict[str, Any]] = []
        methods: List[Dict[str, Any]] = []
        calls:   List[Dict[str, Any]] = []
        seen_method_names: Set[str]   = set()
        constructor_func_node         = None

        for item in body_items:
            if not hasattr(item, "type"):
                continue
            if item.type in ("PropertyDefinition", "FieldDefinition",
                             "ClassProperty", "ClassAccessorProperty"):
                key_node = getattr(item, "key", None)
                fname    = getattr(key_node, "name", "") if key_node else ""
                if fname and fname not in _SKIP_NAMES:
                    fields.append({
                        "name": fname, "element_type": "any", "raw_type": "any",
                        "multiplicity": "1",
                        "visibility": _visibility_from_name(fname),
                    })
            elif item.type == "MethodDefinition":
                key_node = getattr(item, "key", None)
                mname    = getattr(key_node, "name", "") if key_node else ""
                if not mname or mname in seen_method_names:
                    continue
                seen_method_names.add(mname)
                is_ctor   = item.kind == "constructor" if hasattr(item, "kind") else (mname == "constructor")
                is_static = bool(getattr(item, "static", False))
                func_node = getattr(item, "value", None)
                params_raw = (func_node.params or []) if func_node and hasattr(func_node, "params") else []
                method_id = f"method:{full_name}:{mname}"
                methods.append({
                    "id": method_id, "name": mname,
                    "return_type": "void" if is_ctor else "any",
                    "raw_return_type": "<constructor>" if is_ctor else "any",
                    "visibility": _visibility_from_name(mname),
                    "is_constructor": is_ctor, "is_static": is_static,
                    "params": _format_params_from_esprima(params_raw),
                })
                if func_node and hasattr(func_node, "body"):
                    if is_ctor:
                        constructor_func_node = func_node
                    for c in _extract_calls_from_esprima_body(func_node.body):
                        calls.append({"src_method_id": method_id, **c})

        if constructor_func_node and hasattr(constructor_func_node, "body"):
            ctor_fields = _extract_constructor_fields_from_esprima(constructor_func_node.body)
            existing = {f["name"] for f in fields}
            for cf in ctor_fields:
                if cf["name"] not in existing:
                    fields.append(cf)

        units.append({
            "full_name": full_name, "short_name": name, "kind": "class",
            "fields": fields, "methods": methods,
            "extends": extends_list, "implements": [], "calls": calls,
        })

    for stmt in (getattr(tree, "body", None) or []):
        if not hasattr(stmt, "type"):
            continue
        if stmt.type in ("ClassDeclaration", "ClassExpression"):
            _handle_class(stmt)
        elif stmt.type in ("ExportNamedDeclaration", "ExportDefaultDeclaration"):
            decl = getattr(stmt, "declaration", None)
            if decl and hasattr(decl, "type"):
                if decl.type in ("ClassDeclaration", "ClassExpression"):
                    _handle_class(decl)

    return units


# ═══════════════════════════════════════════════════════════════════════════
#  TypeScript interface / enum supplement
# ═══════════════════════════════════════════════════════════════════════════

_RE_INTERFACE = re.compile(
    r'(?:export\s+)?interface\s+(\w+)'
    r'(?:\s+extends\s+([\w,\s<>]+?))?'
    r'\s*\{([^}]*)\}',
    re.MULTILINE | re.DOTALL,
)
_RE_ENUM = re.compile(
    r'(?:export\s+)?(?:const\s+)?enum\s+(\w+)\s*\{([^}]*)\}',
    re.MULTILINE | re.DOTALL,
)


def _extract_ts_interfaces_enums(
    code: str,
    module_name: Optional[str],
) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []
    for m in _RE_INTERFACE.finditer(code):
        name      = m.group(1)
        extends   = [e.split("<")[0].strip()
                     for e in re.split(r"[,\s]+", (m.group(2) or "").strip())
                     if e.split("<")[0].strip()]
        full_name = f"{module_name}.{name}" if module_name else name
        body      = m.group(3) or ""
        skip_names = {"new", "readonly", "abstract"}
        methods: List[Dict[str, Any]] = []
        fields:  List[Dict[str, Any]] = []
        for mm in re.finditer(
            r'(\w+)\s*\??\s*\(([^)]*)\)\s*(?::\s*([\w<>\[\]|&,\s.]+?))?(?:\s*;|$)',
            body, re.MULTILINE,
        ):
            mname = mm.group(1)
            if mname in skip_names:
                continue
            ret = (mm.group(3) or "void").strip()
            logical_r, raw_r, _ = _resolve_type_and_multiplicity(ret)
            methods.append({
                "name": mname, "return_type": logical_r, "raw_return_type": raw_r,
                "is_constructor": False, "params": _parse_param_string(mm.group(2)),
            })
        for fm in re.finditer(
            r'(\w+)\s*\??\s*:\s*([\w<>\[\]|&,\s.]+?)\s*(?:;|$)',
            body, re.MULTILINE,
        ):
            fname = fm.group(1)
            if fname in skip_names or "(" in body[fm.start():fm.start() + 60]:
                continue
            logical, raw, mult = _resolve_type_and_multiplicity(fm.group(2).strip())
            fields.append({
                "name": fname, "element_type": logical, "raw_type": raw,
                "multiplicity": mult, "visibility": "public",
            })
        units.append({
            "full_name": full_name, "short_name": name, "kind": "interface",
            "fields": fields, "methods": methods,
            "extends": extends, "implements": [], "calls": [],
        })
    for m in _RE_ENUM.finditer(code):
        name      = m.group(1)
        full_name = f"{module_name}.{name}" if module_name else name
        units.append({
            "full_name": full_name, "short_name": name, "kind": "enum",
            "fields": [], "methods": [], "extends": [], "implements": [], "calls": [],
        })
    return units


# ═══════════════════════════════════════════════════════════════════════════
#  CIRGraph population
# ═══════════════════════════════════════════════════════════════════════════

def _populate_graph(
    graph: CIRGraph,
    type_nodes: Dict[str, str],
    all_units: List[Dict[str, Any]],
    source_file: Optional[str],
) -> None:
    pkg = _module_to_package(source_file)
    for unit in all_units:
        full_name  = unit["full_name"]
        short_name = unit["short_name"]
        kind       = unit.get("kind", "class")
        type_id    = f"type:{full_name}"

        graph.add_node(type_id, "TypeDecl", TypeDecl(
            id=type_id, name=short_name, kind=kind,
            visibility="public", package=pkg, modifiers=(),
            is_abstract=(kind == "interface"), is_final=False,
        ))
        type_nodes[full_name] = type_id

    for unit in all_units:
        full_name = unit["full_name"]
        type_id   = type_nodes.get(full_name)
        if not type_id:
            continue

        for f in unit.get("fields", []):
            fname = f.get("name", "")
            if not fname:
                continue
            field_id = f"field:{full_name}:{fname}"
            graph.add_node(field_id, "Field", Field(
                id=field_id, name=fname,
                type_name=f.get("element_type", "any"),
                raw_type=f.get("raw_type", "any"),
                visibility=f.get("visibility", "public"),
                modifiers=(), multiplicity=f.get("multiplicity"),
            ))
            graph.add_edge(type_id, field_id, "HAS_FIELD")
            f["_id"] = field_id
            f["_type_id"] = type_id

        method_index_local: Dict[str, str] = {}
        for m in unit.get("methods", []):
            mname = m.get("name", "")
            if not mname:
                continue
            method_id = m.get("id") or f"method:{full_name}:{mname}"
            is_ctor   = bool(m.get("is_constructor"))
            is_static = bool(m.get("is_static"))
            graph.add_node(method_id, "Method", Method(
                id=method_id, name=mname,
                return_type=m.get("return_type", "any"),
                raw_return_type=m.get("raw_return_type", "any"),
                visibility=m.get("visibility", "public"),
                modifiers=("static",) if is_static else (),
                is_constructor=is_ctor, is_static=is_static,
                is_abstract=False, is_final=False,
            ))
            graph.add_edge(type_id, method_id, "HAS_METHOD")
            method_index_local[mname] = method_id
            m["_id"] = method_id

            for p in m.get("params", []):
                pname = p.get("name", "")
                if not pname:
                    continue
                p_id = f"param:{full_name}:{mname}:{pname}"
                graph.add_node(p_id, "Parameter", Parameter(
                    id=p_id, name=pname,
                    type_name=p.get("type_name", "any"),
                    raw_type=p.get("raw_type", "any"),
                ))
                graph.add_edge(p_id, method_id, "PARAM_OF")

        unit["_method_index"] = method_index_local


def _add_relationship_edges(
    graph: CIRGraph,
    type_nodes: Dict[str, str],
    all_units: List[Dict[str, Any]],
    file_stem_to_full: Optional[Dict[str, str]] = None,
) -> None:
    """
    Build INHERITS, IMPLEMENTS, ASSOCIATES, DEPENDS_ON, and CALLS edges.
    Also resolves module-level import relationships for pseudo-class units.
    """
    full_to_id: Dict[str, str]         = dict(type_nodes)
    short_to_ids: Dict[str, List[str]] = {}
    id_to_full: Dict[str, str]         = {}

    for full, nid in type_nodes.items():
        id_to_full[nid] = full
        short = full.split(".")[-1]
        short_to_ids.setdefault(short, []).append(nid)

    def resolve(tname: str, src_id: str) -> Optional[str]:
        if tname in full_to_id:
            return full_to_id[tname]
        candidates = short_to_ids.get(tname)
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        src_full = id_to_full.get(src_id, "")
        src_pkg  = ".".join(src_full.split(".")[:-1])
        same_pkg = [c for c in candidates
                    if ".".join(id_to_full.get(c, "").split(".")[:-1]) == src_pkg]
        return same_pkg[0] if len(same_pkg) == 1 else None

    method_global: Dict[Tuple[str, str], str] = {}
    for u in all_units:
        src_id = type_nodes.get(u["full_name"], "")
        for mname, mid in u.get("_method_index", {}).items():
            method_global[(src_id, mname)] = mid

    # Build a map: exported_function_name → (type_id, method_id)
    # Used to resolve import-based CALLS for module-style pseudo-classes
    export_name_to_method: Dict[str, Tuple[str, str]] = {}
    for u in all_units:
        tid = type_nodes.get(u["full_name"], "")
        for m in u.get("methods", []):
            mname = m.get("name", "")
            mid   = m.get("_id", "")
            if mname and mid:
                export_name_to_method[mname] = (tid, mid)

    for u in all_units:
        src_id = type_nodes.get(u["full_name"])
        if not src_id:
            continue

        for base in u.get("extends", []):
            t = resolve(base, src_id)
            if t and t != src_id:
                graph.add_edge(src_id, t, "INHERITS")

        for iface in u.get("implements", []):
            t = resolve(iface, src_id)
            if t and t != src_id:
                graph.add_edge(src_id, t, "IMPLEMENTS")

        for f in u.get("fields", []):
            tname = f.get("element_type")
            if not tname or tname in _JS_PRIMITIVES:
                continue
            t = resolve(tname, src_id)
            if t and t != src_id:
                graph.add_edge(src_id, t, "ASSOCIATES",
                               multiplicity=f.get("multiplicity"))

        for m in u.get("methods", []):
            for p in m.get("params", []):
                tname = p.get("type_name")
                if not tname or tname in _JS_PRIMITIVES:
                    continue
                t = resolve(tname, src_id)
                if t and t != src_id:
                    graph.add_edge(src_id, t, "DEPENDS_ON")
            rtype = m.get("return_type")
            if rtype and rtype not in _JS_PRIMITIVES:
                t = resolve(rtype, src_id)
                if t and t != src_id:
                    graph.add_edge(src_id, t, "DEPENDS_ON")

        # ── CALLS edges ────────────────────────────────────────────────────

        field_type_by_name: Dict[str, str] = {
            f["name"]: f["element_type"]
            for f in u.get("fields", [])
            if f.get("name") and f.get("element_type")
        }

        # 1. Class-based CALLS (this.field.method / super / static)
        for c in u.get("calls", []):
            src_method_id = c.get("src_method_id")
            qkind  = c.get("qualifier_kind", "none")
            qual   = (c.get("qualifier") or "").strip()
            member = (c.get("member")    or "").strip()
            order  = c.get("order", 0)
            if not src_method_id or not member:
                continue

            target_type_id = src_id
            if qkind == "super":
                extends = u.get("extends", [])
                if extends:
                    t = resolve(extends[0], src_id)
                    if t:
                        target_type_id = t
            elif qkind in ("static", "new"):
                t = resolve(qual, src_id)
                if not t:
                    continue
                target_type_id = t
            elif qkind == "field":
                var_type = field_type_by_name.get(qual)
                if not var_type or var_type in _JS_PRIMITIVES:
                    continue
                t = resolve(var_type, src_id)
                if not t:
                    continue
                target_type_id = t
            elif qkind == "var":
                var_type = field_type_by_name.get(qual)
                if not var_type:
                    continue
                t = resolve(var_type, src_id)
                if not t:
                    continue
                target_type_id = t
            elif qkind in ("self", "cls"):
                target_type_id = src_id

            dst_method_id = method_global.get((target_type_id, member))
            if dst_method_id:
                graph.add_edge(src_method_id, dst_method_id, "CALLS", order=order)

        # 2. Module-level import-based CALLS
        #    e.g. authRoutes.js imports { createUser } from userModel.js
        #    → AuthRoutes DEPENDS_ON UserModel
        #    → first method of AuthRoutes CALLS UserModel.createUser
        if u.get("_is_module"):
            imports = u.get("_imports", {})
            for _import_path, imported_names in imports.items():
                # Resolve which type the import path belongs to
                # _import_path might be '../models/userModel' → stem = 'userModel'
                import_stem = _import_path.split("/")[-1]
                import_class_name = _stem_to_class_name(import_stem)
                target_type_id_imp = resolve(import_class_name, src_id)

                if not target_type_id_imp or target_type_id_imp == src_id:
                    continue

                # DEPENDS_ON edge at type level
                graph.add_edge(src_id, target_type_id_imp, "DEPENDS_ON")

                # CALLS edges: map each imported function name to a method
                order_imp = 0
                for fn_name in imported_names:
                    if fn_name in _SKIP_NAMES:
                        continue
                    dst_mid = method_global.get((target_type_id_imp, fn_name))
                    if not dst_mid:
                        continue
                    # Attribute the call to the first method of the caller
                    methods_list = u.get("methods", [])
                    if not methods_list:
                        continue
                    src_mid = methods_list[0].get("_id", "")
                    if src_mid and dst_mid:
                        graph.add_edge(src_mid, dst_mid, "CALLS", order=order_imp)
                        order_imp += 1


# ═══════════════════════════════════════════════════════════════════════════
#  Path / package helpers
# ═══════════════════════════════════════════════════════════════════════════

def _module_to_package(source_file: Optional[str]) -> Optional[str]:
    """
    Convert source file path to dotted package name.
    Strips temp dirs and returns just the filename stem.
    e.g. C:/Users/.../Temp/tmpXXX/models/userModel.js → 'models.userModel'
    but for flat structures → 'userModel'
    """
    if not source_file:
        return None
    rel = source_file.replace("\\", "/")
    # Strip temp directory prefix
    rel = re.sub(r'.*/[Tt]emp/tmp[^/]+/', '', rel)
    rel = re.sub(r'.*/tmp/tmp[^/]+/', '', rel)
    # Strip extension
    for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        if rel.endswith(ext):
            rel = rel[: -len(ext)]
            break
    # Convert path separators to dots but keep subdirectory structure
    # e.g. models/userModel → models.userModel
    return rel.replace("/", ".")


def _file_stem(source_file: str) -> str:
    """Return just the filename without extension."""
    base = os.path.basename(source_file)
    for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        if base.endswith(ext):
            return base[: -len(ext)]
    return base


# ═══════════════════════════════════════════════════════════════════════════
#  Public adapter class
# ═══════════════════════════════════════════════════════════════════════════

class JSAdapter:
    """
    JavaScript / TypeScript → CIRGraph builder.

    Handles both:
      - Class-based JS/TS (ES6 classes)
      - Functional/module-style JS (exported functions → pseudo-classes)

    Public API (mirrors JavaAdapter / PythonAdapter):
      parse_to_ast(code)
      build_cir_graph_for_code(code, filename)
      build_cir_graph_for_files(files)
    """

    language = "javascript"

    def parse_to_ast(self, code: str) -> List[Dict[str, Any]]:
        units: List[Dict[str, Any]] = []
        if _ESPRIMA_OK:
            units.extend(_esprima_extract_classes(code, module_name=None))
        ts_units = _extract_ts_interfaces_enums(code, module_name=None)
        existing = {u["short_name"] for u in units}
        for u in ts_units:
            if u["short_name"] not in existing:
                units.append(u)
        if not units:
            units.extend(_regex_extract_classes(code, module_name=None))
        return units

    def build_cir_graph_for_code(
        self,
        code: str,
        filename: Optional[str] = None,
    ) -> CIRGraph:
        graph      = CIRGraph()
        type_nodes: Dict[str, str]       = {}
        all_units:  List[Dict[str, Any]] = []
        self._process_source(code, graph, type_nodes, all_units,
                             source_file=filename)
        _add_relationship_edges(graph, type_nodes, all_units)
        return graph

    def build_cir_graph_for_files(self, files: List[str]) -> CIRGraph:
        graph      = CIRGraph()
        type_nodes: Dict[str, str]       = {}
        all_units:  List[Dict[str, Any]] = []
        errors:     List[Dict[str, str]] = []

        for path in files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    code = f.read()
                self._process_source(code, graph, type_nodes, all_units,
                                     source_file=path)
            except ValueError as e:
                errors.append({"file": path, "error": str(e)})
            except Exception as e:
                errors.append({"file": path,
                                "error": f"Unexpected: {type(e).__name__}: {e}"})

        _add_relationship_edges(graph, type_nodes, all_units)
        graph.g.graph["parse_errors"] = errors
        return graph

    def _process_source(
        self,
        code: str,
        graph: CIRGraph,
        type_nodes: Dict[str, str],
        all_units: List[Dict[str, Any]],
        source_file: Optional[str] = None,
    ) -> None:
        stem        = _file_stem(source_file) if source_file else ""
        module_name = _module_to_package(source_file)
        units: List[Dict[str, Any]] = []

        # ── Pass 1: ES6 class extraction ──────────────────────────────────
        if _ESPRIMA_OK:
            try:
                units.extend(_esprima_extract_classes(code, module_name))
            except Exception:
                pass

        # ── Pass 2: TypeScript interface/enum supplement ───────────────────
        ts_units = _extract_ts_interfaces_enums(code, module_name)
        existing = {u["short_name"] for u in units}
        for u in ts_units:
            if u["short_name"] not in existing:
                units.append(u)
                existing.add(u["short_name"])

        # ── Pass 3: Pure-regex class fallback ─────────────────────────────
        if not units:
            for u in _regex_extract_classes(code, module_name):
                if u["short_name"] not in existing:
                    units.append(u)
                    existing.add(u["short_name"])

        # ── Pass 4: Module-level function extraction (Option B) ───────────
        # Only runs when NO classes were found (functional-style file)
        if not units and stem and stem not in _SKIP_FILE_STEMS:
            pseudo = _extract_module_functions(code, module_name, stem)
            if pseudo:
                units.append(pseudo)

        if not units:
            return

        _populate_graph(graph, type_nodes, units, source_file)
        all_units.extend(units)