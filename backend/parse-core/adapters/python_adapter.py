"""
backend/parse-core/adapters/python_adapter.py

Python → CIRGraph builder.

Parses one or more Python source files using the built-in `ast` module,
creates nodes for classes / fields / methods / parameters, and edges for:

  - HAS_FIELD, HAS_METHOD, PARAM_OF
  - INHERITS, IMPLEMENTS  (ABC subclasses treated as IMPLEMENTS)
  - ASSOCIATES, DEPENDS_ON
  - CALLS  (ordered, from method bodies)

Features:
  - Multi-file (project-level) support with cross-file resolution
  - Annotated assignments (PEP 526):  name: Type = value
  - Instance assignments in __init__:  self.x = ...  /  self.x: Type = ...
  - Generic / collection multiplicity heuristics (List[], Optional[], Dict[], ...)
  - @dataclass field detection
  - Abstract class detection (ABC, abc.ABC, abstractmethod)
  - Modifier flags (is_static via @staticmethod/@classmethod, is_abstract)
  - Ordered CALLS extraction for sequence diagrams
  - Module-level singleton variable resolution (e.g. db_manager = DatabaseManager())
  - Skips invalid files during project parsing and collects errors
"""

from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from cir.model import TypeDecl, Field, Method, Parameter
from cir.graph import CIRGraph
import textwrap as _textwrap

# ---------------------------------------------------------------------------
# bare-function → pseudo-class wrapper
# ---------------------------------------------------------------------------

def _has_top_level_classes(tree: ast.Module) -> bool:
    """Return True if the module has at least one top-level ClassDef."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            return True
    return False


def _top_level_functions_list(tree: ast.Module) -> List:
    """Return all top-level (Async)FunctionDef nodes."""
    funcs = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(node)
    return funcs


def _stem_to_class_name_py(source_file: Optional[str], fallback: str = "Module") -> str:
    if not source_file:
        return fallback
    stem = os.path.splitext(os.path.basename(source_file))[0]
    parts = re.sub(r"[-_]", " ", stem)
    parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", parts)
    name = "".join(w.capitalize() for w in parts.split())
    return name if name else fallback


def wrap_bare_functions_as_class(
    code: str,
    source_file: Optional[str] = None,
) -> str:
    """
    FIX v2: If code has top-level function defs but NO class defs, wrap
    everything in a synthetic class so the adapter produces a real CIR.
    The class name comes from the filename stem (auth.py -> Auth).
    Returns code unchanged if classes already exist or code is unparseable.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code

    if _has_top_level_classes(tree):
        return code

    funcs = _top_level_functions_list(tree)
    if not funcs:
        return code

    class_name = _stem_to_class_name_py(source_file, fallback="Module")
    lines = code.splitlines()
    first_func_lineno = min(f.lineno for f in funcs)
    header_lines = lines[: first_func_lineno - 1]

    func_blocks: List[str] = []
    for func in sorted(funcs, key=lambda f: f.lineno):
        block = "\n".join(lines[func.lineno - 1 : func.end_lineno])
        func_blocks.append(_textwrap.indent(block, "    "))

    wrapped = "\n".join(header_lines)
    if wrapped:
        wrapped += "\n\n"
    wrapped += f"class {class_name}:\n"
    wrapped += "    def __init__(self):\n        pass\n\n"
    wrapped += "\n\n".join(func_blocks)
    return wrapped


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

language = "python"

_PRIMITIVE_TYPES = {
    "str", "int", "float", "bool", "bytes", "complex",
    "None", "NoneType", "Any", "object",
}

# Collection-like generics that imply one-to-many
_COLLECTION_PREFIXES = (
    "List[", "list[",
    "Set[", "set[",
    "FrozenSet[", "frozenset[",
    "Sequence[",
    "MutableSequence[",
    "Deque[",
    "Tuple[",
    "tuple[",
)

# Mapping-like generics → no single inner type worth following
_DICT_PREFIXES = (
    "Dict[", "dict[",
    "Mapping[",
    "MutableMapping[",
    "DefaultDict[",
    "OrderedDict[",
    "ChainMap[",
)

# Optional / Union wrappers
_OPTIONAL_PREFIXES = (
    "Optional[",
    "Union[",
)


# ---------------------------------------------------------------------------
# FIX A: Package extraction — derive a clean logical package name from filepath
# ---------------------------------------------------------------------------

def _extract_package(filepath: Optional[str]) -> str:
    """
    Derive a clean logical package name from a Python source file path.

    Priority:
      1. If the file lives inside a proper Python package (has __init__.py
         siblings), walk up to find the package root and return the dotted
         package path.
      2. Otherwise return just the file's stem (filename without .py),
         converted to a clean identifier.
      3. Fall back to "(default)".

    Never returns a full absolute path, so temp-file paths such as
    C:\\Users\\HP\\AppData\\Local\\Temp\\tmpdzvzkxsr\\Main are reduced to
    just "Main" (or "(default)" when the stem looks like a random hash).
    """
    if not filepath:
        return "(default)"

    filepath = os.path.normpath(filepath)
    stem = os.path.splitext(os.path.basename(filepath))[0]

    # Walk upward collecting package segments while __init__.py exists
    segments = []
    current_dir = os.path.dirname(filepath)
    for _ in range(10):  # max 10 levels
        if os.path.isfile(os.path.join(current_dir, "__init__.py")):
            segments.insert(0, os.path.basename(current_dir))
            current_dir = os.path.dirname(current_dir)
        else:
            break

    if segments:
        return ".".join(segments)

    # No package structure — use just the stem, cleaned up
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", stem).strip("_")
    if not clean or len(clean) < 2:
        return "(default)"

    # If the stem looks like a temp hash (all lowercase letters+digits, no
    # underscores or uppercase letters, 8+ chars) treat it as a temp artifact
    if re.match(r"^[a-z0-9]{8,}$", clean) and not re.search(r"[_A-Z]", stem):
        return "(default)"

    return clean


# ---------------------------------------------------------------------------
# Helpers: annotation → (logical_type, raw_type, multiplicity)
# ---------------------------------------------------------------------------

def _resolve_annotation(annotation: Optional[ast.expr]) -> Tuple[str, str, Optional[str]]:
    if annotation is None:
        return "Any", "Any", None
    try:
        raw = ast.unparse(annotation)
    except Exception:
        return "Any", "Any", None
    return _resolve_annotation_str(raw)


def _resolve_annotation_str(raw: str) -> Tuple[str, str, Optional[str]]:
    s = raw.strip()

    for prefix in _DICT_PREFIXES:
        if s.startswith(prefix) and s.endswith("]"):
            return "Any", s, "0..*"

    if s.startswith("Optional[") and s.endswith("]"):
        inner = s[len("Optional["):-1].strip()
        logical = inner.split("[")[0].split(".")[-1]
        return logical, s, "0..1"

    if s.startswith("Union[") and s.endswith("]"):
        inner_csv = s[len("Union["):-1].strip()
        parts = [p.strip() for p in inner_csv.split(",")]
        non_none = [p for p in parts if p not in ("None", "NoneType", "type[None]")]
        if non_none:
            logical = non_none[0].split("[")[0].split(".")[-1]
            return logical, s, "0..1"
        return "None", s, "0..1"

    for prefix in _COLLECTION_PREFIXES:
        if s.startswith(prefix) and s.endswith("]"):
            inner = s[len(prefix):-1].strip()
            inner_base = inner.split(",")[0].strip()
            logical = inner_base.split("[")[0].split(".")[-1]
            return logical, s, "1..*"

    logical = s.split("[")[0].split(".")[-1]
    return logical, s, "1"


# ---------------------------------------------------------------------------
# Helpers: visibility from leading underscores (Python convention)
# ---------------------------------------------------------------------------

def _visibility_from_name(name: str) -> str:
    if name.startswith("__") and not name.endswith("__"):
        return "private"
    if name.startswith("_") and not name.startswith("__"):
        return "protected"
    return "public"


# ---------------------------------------------------------------------------
# Helpers: is method abstract / static / classmethod
# ---------------------------------------------------------------------------

def _method_flags(func: ast.FunctionDef | ast.AsyncFunctionDef) -> Tuple[bool, bool, bool]:
    is_static = False
    is_abstract = False
    is_classmethod = False
    for dec in func.decorator_list:
        if isinstance(dec, ast.Name):
            if dec.id == "staticmethod":
                is_static = True
            elif dec.id == "classmethod":
                is_classmethod = True
            elif dec.id == "abstractmethod":
                is_abstract = True
        elif isinstance(dec, ast.Attribute):
            if dec.attr == "abstractmethod":
                is_abstract = True
    return is_static, is_abstract, is_classmethod


def _class_flags(node: ast.ClassDef) -> Tuple[bool, bool]:
    is_abstract = False
    is_dataclass = False
    for base in node.bases:
        bname = ast.unparse(base) if hasattr(ast, "unparse") else ""
        if bname in ("ABC", "abc.ABC"):
            is_abstract = True
    for dec in node.decorator_list:
        dname = ""
        if isinstance(dec, ast.Name):
            dname = dec.id
        elif isinstance(dec, ast.Attribute):
            dname = dec.attr
        elif isinstance(dec, ast.Call):
            func = dec.func
            dname = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else "")
        if dname == "dataclass":
            is_dataclass = True
    return is_abstract, is_dataclass


def _is_abc_interface(node: ast.ClassDef) -> bool:
    is_abstract, _ = _class_flags(node)
    if not is_abstract:
        return False
    methods = [
        n for n in node.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not n.name.startswith("_")
    ]
    if not methods:
        return False
    return all(_method_flags(m)[1] for m in methods)


def _extract_module_vars(tree: ast.Module) -> Dict[str, str]:
    """
    Scan module-level statements for singleton/instance assignments of the form:
        var_name = ClassName()
        var_name = module.ClassName()

    Returns a dict mapping variable name → class name, e.g.:
        {"db_manager": "DatabaseManager", "sms_service": "StudentManagementService"}

    This enables resolution of CALLS like `db_manager.insert(...)` where
    db_manager is not a self-field or parameter but a module-level singleton.
    """
    module_vars: Dict[str, str] = {}

    for node in ast.iter_child_nodes(tree):
        # Only look at top-level assignments (not inside classes or functions)
        if not isinstance(node, ast.Assign):
            continue

        # RHS must be a constructor call: ClassName() or module.ClassName()
        if not isinstance(node.value, ast.Call):
            continue

        func = node.value.func
        if isinstance(func, ast.Name):
            class_name = func.id
        elif isinstance(func, ast.Attribute):
            class_name = func.attr  # e.g. module.ClassName → "ClassName"
        else:
            continue

        # Only capture if the class name looks like a class (PascalCase)
        if not class_name or not class_name[0].isupper():
            continue

        for target in node.targets:
            if isinstance(target, ast.Name):
                module_vars[target.id] = class_name

    return module_vars


# ---------------------------------------------------------------------------
# CALLS extraction
# ---------------------------------------------------------------------------

def _extract_ordered_calls(func: ast.FunctionDef | ast.AsyncFunctionDef) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    order_counter = [0]

    class CallVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            func_node = node.func

            if isinstance(func_node, ast.Attribute):
                value = func_node.value
                member = func_node.attr

                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "super":
                    calls.append({
                        "qualifier_kind": "super",
                        "qualifier": "super",
                        "member": member,
                        "order": order_counter[0],
                    })
                    order_counter[0] += 1

                elif isinstance(value, ast.Name) and value.id == "self":
                    calls.append({
                        "qualifier_kind": "self",
                        "qualifier": "self",
                        "member": member,
                        "order": order_counter[0],
                    })
                    order_counter[0] += 1

                elif isinstance(value, ast.Name) and value.id == "cls":
                    calls.append({
                        "qualifier_kind": "cls",
                        "qualifier": "cls",
                        "member": member,
                        "order": order_counter[0],
                    })
                    order_counter[0] += 1

                # FIX: handle self.field.method() — two-level attribute access
                # Pattern: self.user_repo.find_by_username(...)
                #   → qualifier_kind=field, qualifier=user_repo, member=find_by_username
                elif (isinstance(value, ast.Attribute)
                      and isinstance(value.value, ast.Name)
                      and value.value.id == "self"):
                    field_name = value.attr
                    calls.append({
                        "qualifier_kind": "field",
                        "qualifier": field_name,
                        "member": member,
                        "order": order_counter[0],
                    })
                    order_counter[0] += 1

                elif isinstance(value, ast.Name):
                    name = value.id
                    kind = "var" if name[:1].islower() else "static"
                    calls.append({
                        "qualifier_kind": kind,
                        "qualifier": name,
                        "member": member,
                        "order": order_counter[0],
                    })
                    order_counter[0] += 1

            elif isinstance(func_node, ast.Name):
                name = func_node.id
                kind = "new" if name[:1].isupper() else "none"
                calls.append({
                    "qualifier_kind": kind,
                    "qualifier": name,
                    "member": name,
                    "order": order_counter[0],
                })
                order_counter[0] += 1

            self.generic_visit(node)

    CallVisitor().visit(func)
    return calls


# ---------------------------------------------------------------------------
# Self-assignment field extraction (from __init__ body)
# ---------------------------------------------------------------------------

def _extract_init_self_fields(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> List[Dict[str, Any]]:
    """
    Extract self.x = ... assignments from __init__ and determine their types.

    FIX v2: build a param_type_map from __init__ parameter annotations so that
    patterns like:
        def __init__(self, repo: UserRepository):
            self.repo = repo          # ← type inferred as UserRepository
    produce Field.type_name = 'UserRepository' instead of 'Any'.
    This enables CALLS and ASSOCIATES edge resolution for dependency-injected
    collaborators, which is the dominant pattern in Python service classes.
    """
    # Build param name → annotated type from __init__ signature
    param_type_map: Dict[str, str] = {}
    for arg in func.args.args:
        if arg.arg in ("self", "cls") or arg.annotation is None:
            continue
        logical, _, _ = _resolve_annotation(arg.annotation)
        if logical and logical not in ("Any", "None", "object"):
            param_type_map[arg.arg] = logical

    fields: List[Dict[str, Any]] = []
    seen: set = set()

    for stmt in ast.walk(func):
        if isinstance(stmt, ast.AnnAssign):
            target = stmt.target
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                name = target.attr
                if name not in seen:
                    seen.add(name)
                    logical, raw, mult = _resolve_annotation(stmt.annotation)
                    fields.append({
                        "name": name,
                        "type_name": logical,
                        "raw_type": raw,
                        "multiplicity": mult,
                    })

        elif isinstance(stmt, ast.Assign):
            for tgt in stmt.targets:
                if (
                    isinstance(tgt, ast.Attribute)
                    and isinstance(tgt.value, ast.Name)
                    and tgt.value.id == "self"
                ):
                    name = tgt.attr
                    if name not in seen:
                        seen.add(name)
                        # FIX: if RHS is a plain name that matches an annotated
                        # __init__ param, use that param's type instead of Any
                        logical, raw, mult = _infer_rhs_type(stmt.value)
                        if (logical in ("Any",) and isinstance(stmt.value, ast.Name)
                                and stmt.value.id in param_type_map):
                            resolved = param_type_map[stmt.value.id]
                            logical = resolved
                            raw = resolved
                            mult = mult or "1"
                        fields.append({
                            "name": name,
                            "type_name": logical,
                            "raw_type": raw,
                            "multiplicity": mult,
                        })

    return fields


def _infer_rhs_type(value: ast.expr) -> Tuple[str, str, Optional[str]]:
    if isinstance(value, ast.Constant):
        t = type(value.value).__name__
        return t, t, "1"
    if isinstance(value, (ast.List, ast.ListComp)):
        return "list", "list", "0..*"
    if isinstance(value, (ast.Set, ast.SetComp)):
        return "set", "set", "0..*"
    if isinstance(value, (ast.Dict, ast.DictComp)):
        return "dict", "dict", "0..*"
    if isinstance(value, ast.Call):
        if isinstance(value.func, ast.Name):
            name = value.func.id
            return name, name, "1"
        if isinstance(value.func, ast.Attribute):
            attr = value.func.attr
            return attr, attr, "1"
    if isinstance(value, ast.Name) and value.id == "None":
        return "None", "None", "0..1"
    return "Any", "Any", None


# ---------------------------------------------------------------------------
# Main adapter class
# ---------------------------------------------------------------------------

class PythonAdapter:
    """
    Python → CIRGraph builder.

    Public API (mirrors JavaAdapter):
      parse_to_ast(code)                        → ast.Module
      build_cir_graph_for_code(code, filename)  → CIRGraph
      build_cir_graph_for_files(files)          → CIRGraph  (multi-file / project)
    """

    language = "python"

    def parse_to_ast(self, code: str) -> ast.Module:
        try:
            return ast.parse(code)
        except SyntaxError as e:
            raise ValueError(f"Python syntax error: {e}")
        except Exception as e:
            raise ValueError(f"Failed to parse Python code: {e}")

    def build_cir_graph_for_code(
        self,
        code: str,
        filename: Optional[str] = None,
    ) -> CIRGraph:
        code = wrap_bare_functions_as_class(code, source_file=filename)  # FIX v2
        graph = CIRGraph()
        type_nodes: Dict[str, str] = {}
        units: List[Dict[str, Any]] = []
        self._process_module(code, graph, type_nodes, units, source_file=filename)
        self._add_relationship_edges(graph, type_nodes, units)
        return graph

    def build_cir_graph_for_files(self, files: List[str]) -> CIRGraph:
        graph = CIRGraph()
        type_nodes: Dict[str, str] = {}
        units: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []

        all_module_vars: Dict[str, str] = {}
        for path in files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    code = f.read()
                code = wrap_bare_functions_as_class(code, source_file=path)  # FIX v2
                tree = self.parse_to_ast(code)
                all_module_vars.update(_extract_module_vars(tree))
            except Exception:
                pass  # errors will be caught in the main loop below

        for path in files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    code = f.read()
                code = wrap_bare_functions_as_class(code, source_file=path)  # FIX v2
                self._process_module(
                    code, graph, type_nodes, units,
                    source_file=path,
                    project_module_vars=all_module_vars,
                )
            except ValueError as e:
                errors.append({"file": path, "error": str(e)})
            except Exception as e:
                errors.append({"file": path, "error": f"Unexpected: {type(e).__name__}: {e}"})

        self._add_relationship_edges(graph, type_nodes, units)
        graph.g.graph["parse_errors"] = errors
        return graph

    def _process_module(
        self,
        code: str,
        graph: CIRGraph,
        type_nodes: Dict[str, str],
        units: List[Dict[str, Any]],
        source_file: Optional[str] = None,
        project_module_vars: Optional[Dict[str, str]] = None,
    ) -> None:
        tree = self.parse_to_ast(code)

        module_name: Optional[str] = None
        if source_file:
            rel = source_file.replace(os.sep, "/")
            if rel.endswith(".py"):
                rel = rel[:-3]
            module_name = rel.replace("/", ".")

        local_vars = _extract_module_vars(tree)
        if project_module_vars is not None:
            module_vars = {**local_vars, **project_module_vars}
        else:
            module_vars = local_vars

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if _is_nested_in_class(node, tree):
                continue
            self._process_class(
                node,
                graph,
                type_nodes,
                units,
                module_name=module_name,
                source_file=source_file,
                module_vars=module_vars,
            )

    def _process_class(
        self,
        node: ast.ClassDef,
        graph: CIRGraph,
        type_nodes: Dict[str, str],
        units: List[Dict[str, Any]],
        module_name: Optional[str],
        source_file: Optional[str],
        module_vars: Optional[Dict[str, str]] = None,
    ) -> None:
        short_name = node.name
        full_name = f"{module_name}.{short_name}" if module_name else short_name

        is_abstract_class, is_dataclass = _class_flags(node)
        is_interface_like = _is_abc_interface(node)

        kind = "interface" if is_interface_like else "class"

        type_id = f"type:{full_name}"

        # FIX A: derive a clean logical package name from source_file rather
        # than using the raw module_name (which may contain a full temp path).
        package = _extract_package(source_file)

        type_decl = TypeDecl(
            id=type_id,
            name=short_name,
            kind=kind,
            visibility="public",
            package=package,
            modifiers=("abstract",) if is_abstract_class else (),
            is_abstract=is_abstract_class,
            is_final=False,
        )
        graph.add_node(type_id, "TypeDecl", type_decl)
        type_nodes[full_name] = type_id

        unit: Dict[str, Any] = {
            "id": type_id,
            "short_name": short_name,
            "full_name": full_name,
            "fields": [],
            "methods": [],
            "extends": [],
            "implements": [],
            "calls": [],
            "source_file": source_file,
            "module_vars": module_vars or {},
        }

        # ---- Bases ----
        for base in node.bases:
            try:
                bname = ast.unparse(base).strip()
            except Exception:
                continue
            if bname in ("object", ""):
                continue
            short_bname = bname.split(".")[-1]
            if short_bname in ("ABC",):
                unit["implements"].append(short_bname)
            else:
                unit["extends"].append(short_bname)

        # ---- Class-level annotated attributes ----
        class_fields_seen: set = set()
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign):
                target = stmt.target
                if not isinstance(target, ast.Name):
                    continue
                fname = target.id
                class_fields_seen.add(fname)

                logical, raw, mult = _resolve_annotation(stmt.annotation)
                vis = _visibility_from_name(fname)
                field_id = f"field:{full_name}:{fname}"

                field_node = Field(
                    id=field_id,
                    name=fname,
                    type_name=logical,
                    raw_type=raw,
                    visibility=vis,
                    modifiers=(),
                    multiplicity=mult,
                )
                graph.add_node(field_id, "Field", field_node)
                graph.add_edge(type_id, field_id, "HAS_FIELD")

                unit["fields"].append({
                    "id": field_id,
                    "name": fname,
                    "element_type": logical,
                    "raw_type": raw,
                    "multiplicity": mult,
                })

        # ---- Methods ----
        for stmt in node.body:
            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            func = stmt
            mname = func.name
            is_static, is_abs, is_classmethod = _method_flags(func)
            is_constructor = (mname == "__init__")
            vis_m = _visibility_from_name(mname)

            logical_ret, raw_ret, _ = _resolve_annotation(func.returns)

            method_id = f"method:{full_name}:{mname}"

            mods: Tuple[str, ...] = ()
            if is_static:
                mods = (*mods, "static")
            if is_classmethod:
                mods = (*mods, "classmethod")
            if is_abs:
                mods = (*mods, "abstract")

            method_node = Method(
                id=method_id,
                name=mname,
                return_type=logical_ret,
                raw_return_type=raw_ret,
                visibility=vis_m,
                modifiers=mods,
                is_constructor=is_constructor,
                is_static=is_static,
                is_abstract=is_abs,
                is_final=False,
            )
            graph.add_node(method_id, "Method", method_node)
            graph.add_edge(type_id, method_id, "HAS_METHOD")

            # Parameters (skip 'self' and 'cls')
            param_infos: List[Dict[str, Any]] = []
            for arg in func.args.args:
                if arg.arg in ("self", "cls"):
                    continue
                p_id = f"param:{full_name}:{mname}:{arg.arg}"
                logical_p, raw_p, _ = _resolve_annotation(arg.annotation)
                param_node = Parameter(
                    id=p_id,
                    name=arg.arg,
                    type_name=logical_p,
                    raw_type=raw_p,
                )
                graph.add_node(p_id, "Parameter", param_node)
                graph.add_edge(p_id, method_id, "PARAM_OF")
                param_infos.append({"id": p_id, "name": arg.arg, "type_name": logical_p})

            # Ordered CALLS
            extracted = _extract_ordered_calls(func)
            for c in extracted:
                unit["calls"].append({"src_method_id": method_id, **c})

            unit["methods"].append({
                "id": method_id,
                "name": mname,
                "return_type": logical_ret,
                "params": param_infos,
                "is_constructor": is_constructor,
            })

            # __init__ self-assignments
            if is_constructor:
                for finfo in _extract_init_self_fields(func):
                    fname = finfo["name"]
                    if fname in class_fields_seen:
                        continue
                    class_fields_seen.add(fname)

                    field_id = f"field:{full_name}:{fname}"
                    vis_f = _visibility_from_name(fname)

                    field_node = Field(
                        id=field_id,
                        name=fname,
                        type_name=finfo["type_name"],
                        raw_type=finfo["raw_type"],
                        visibility=vis_f,
                        modifiers=(),
                        multiplicity=finfo["multiplicity"],
                    )
                    graph.add_node(field_id, "Field", field_node)
                    graph.add_edge(type_id, field_id, "HAS_FIELD")

                    unit["fields"].append({
                        "id": field_id,
                        "name": fname,
                        "element_type": finfo["type_name"],
                        "raw_type": finfo["raw_type"],
                        "multiplicity": finfo["multiplicity"],
                    })

        units.append(unit)

    def _add_relationship_edges(
        self,
        graph: CIRGraph,
        type_nodes: Dict[str, str],
        units: List[Dict[str, Any]],
    ) -> None:
        full_to_id: Dict[str, str] = dict(type_nodes)
        short_to_ids: Dict[str, List[str]] = {}
        id_to_full: Dict[str, str] = {}

        for full_name, nid in type_nodes.items():
            id_to_full[nid] = full_name
            short_name = full_name.split(".")[-1]
            short_to_ids.setdefault(short_name, []).append(nid)

        def _pkg(full: str) -> str:
            parts = full.split(".")
            return ".".join(parts[:-1]) if len(parts) > 1 else ""

        def resolve_type(tname: str, src_id: str) -> Optional[str]:
            if tname in full_to_id:
                return full_to_id[tname]
            candidates = short_to_ids.get(tname)
            if not candidates:
                return None
            if len(candidates) == 1:
                return candidates[0]
            src_full = id_to_full.get(src_id, "")
            src_pkg = _pkg(src_full)
            same_pkg = [c for c in candidates if _pkg(id_to_full.get(c, "")) == src_pkg]
            return same_pkg[0] if len(same_pkg) == 1 else None

        method_index: Dict[Tuple[str, str], str] = {}
        for u in units:
            owner_type_id = u["id"]
            for m in u.get("methods", []):
                mid = m.get("id")
                mname = m.get("name")
                if mid and mname:
                    method_index[(owner_type_id, mname)] = mid

        for u in units:
            src_id = u["id"]

            # INHERITS / IMPLEMENTS
            for base_name in u.get("extends", []):
                target = resolve_type(base_name, src_id)
                if target and target != src_id:
                    graph.add_edge(src_id, target, "INHERITS")

            for iface_name in u.get("implements", []):
                target = resolve_type(iface_name, src_id)
                if target and target != src_id:
                    graph.add_edge(src_id, target, "IMPLEMENTS")

            # ASSOCIATES
            for f in u.get("fields", []):
                tname = f.get("element_type")
                mult = f.get("multiplicity")
                if not tname or tname in _PRIMITIVE_TYPES:
                    continue
                target = resolve_type(tname, src_id)
                if target and target != src_id:
                    graph.add_edge(src_id, target, "ASSOCIATES", multiplicity=mult)

            # DEPENDS_ON
            for m in u.get("methods", []):
                for p in m.get("params", []):
                    tname = p.get("type_name")
                    if not tname or tname in _PRIMITIVE_TYPES:
                        continue
                    target = resolve_type(tname, src_id)
                    if target and target != src_id:
                        graph.add_edge(src_id, target, "DEPENDS_ON")
                rtype = m.get("return_type")
                if rtype and rtype not in _PRIMITIVE_TYPES:
                    target = resolve_type(rtype, src_id)
                    if target and target != src_id:
                        graph.add_edge(src_id, target, "DEPENDS_ON")

            # CALLS
            field_type_by_name: Dict[str, str] = {
                f["name"]: f["element_type"]
                for f in u.get("fields", [])
                if f.get("name") and f.get("element_type")
            }

            module_vars: Dict[str, str] = u.get("module_vars", {})

            method_param_types: Dict[str, Dict[str, str]] = {}
            for m in u.get("methods", []):
                mid = m.get("id")
                if not mid:
                    continue
                method_param_types[mid] = {
                    p["name"]: p["type_name"]
                    for p in m.get("params", [])
                    if p.get("name") and p.get("type_name")
                }

            for c in u.get("calls", []):
                src_method_id = c.get("src_method_id")
                qkind = c.get("qualifier_kind")
                qual = (c.get("qualifier") or "").strip()
                member = (c.get("member") or "").strip()
                order = c.get("order", 0)

                if not src_method_id or not member:
                    continue

                target_type_id = src_id

                if qkind == "super":
                    extends = u.get("extends", [])
                    if extends:
                        t = resolve_type(extends[0], src_id)
                        if t:
                            target_type_id = t

                elif qkind in ("static", "new"):
                    t = resolve_type(qual, src_id)
                    if not t:
                        continue
                    target_type_id = t

                elif qkind in ("var", "field"):
                    # Resolution priority:
                    #   1. self-fields:  self.repo = SomeClass()  OR  self.repo.method()
                    #   2. method parameters
                    #   3. module-level singleton variables
                    var_type = field_type_by_name.get(qual)
                    if not var_type:
                        var_type = method_param_types.get(src_method_id, {}).get(qual)
                    if not var_type:
                        var_type = module_vars.get(qual)
                    if not var_type:
                        continue
                    t = resolve_type(var_type, src_id)
                    if not t:
                        continue
                    target_type_id = t

                elif qkind in ("self", "cls"):
                    target_type_id = src_id

                dst_method_id = method_index.get((target_type_id, member))
                if not dst_method_id:
                    continue

                graph.add_edge(src_method_id, dst_method_id, "CALLS", order=order)


# ---------------------------------------------------------------------------
# Utility: detect if an AST ClassDef is nested inside another class
# ---------------------------------------------------------------------------

def _is_nested_in_class(target: ast.ClassDef, tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if node is target:
            continue
        if isinstance(node, ast.ClassDef):
            for child in ast.walk(node):
                if child is target and child is not node:
                    return True
    return False