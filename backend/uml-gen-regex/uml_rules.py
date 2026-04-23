from __future__ import annotations

import re
from typing import Dict, Any, List, Set, Optional, Tuple

# Map CIR visibility to PlantUML symbols
VISIBILITY_MAP = {
    "public": "+",
    "private": "-",
    "protected": "#",
    "package": "~",
}

_LAYER_ORDER: Dict[str, int] = {
    "client":      5,
    "controller":  10,
    "resource":    10,
    "endpoint":    10,
    "rest":        10,
    "handler":     12,
    "api":         15,
    "service":     20,
    "manager":     22,
    "facade":      22,
    "business":    22,
    "interactor":  22,
    "usecase":     22,
    "repository":  30,
    "repo":        30,
    "dao":         30,
    "persistence": 32,
    "store":       32,
    "data":        35,
    "gateway":     38,
    "database":    40,
    "db":          40,
    "entity":      45,
    "model":       50,
    "domain":      50,
    "util":        60,
    "helper":      60,
    "config":      70,
    "security":    75,
    "filter":      74,
    "middleware":  73,
}


def _layer_order(type_name: str, package: str) -> int:
    combined = (type_name + " " + (package or "")).lower()
    best = 55
    for keyword, order in _LAYER_ORDER.items():
        if keyword in combined:
            if order < best:
                best = order
    return best


def _index_cir(cir: Dict[str, Any]):
    nodes_by_id: Dict[str, Dict[str, Any]] = {
        n["id"]: n for n in cir.get("nodes", [])
    }
    edges: List[Dict[str, Any]] = cir.get("edges", [])
    return nodes_by_id, edges


def _extract_types_and_members(
    nodes_by_id: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, Any]],
):
    type_nodes: Dict[str, Dict[str, Any]] = {}
    fields_by_type: Dict[str, List[Dict[str, Any]]] = {}
    methods_by_type: Dict[str, List[Dict[str, Any]]] = {}

    for nid, n in nodes_by_id.items():
        if n.get("kind") == "TypeDecl":
            type_nodes[nid] = n.get("attrs", {})
            fields_by_type.setdefault(nid, [])
            methods_by_type.setdefault(nid, [])

    for e in edges:
        src, dst, etype = e.get("src"), e.get("dst"), e.get("type")
        if not src or not dst:
            continue
        if etype == "HAS_FIELD" and src in type_nodes and dst in nodes_by_id:
            fa = dict(nodes_by_id[dst].get("attrs", {}))
            fa["_id"] = dst
            fields_by_type[src].append(fa)
        if etype == "HAS_METHOD" and src in type_nodes and dst in nodes_by_id:
            ma = dict(nodes_by_id[dst].get("attrs", {}))
            ma["_id"] = dst
            methods_by_type[src].append(ma)

    return type_nodes, fields_by_type, methods_by_type


def _index_params_by_method(
    nodes_by_id: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    method_to_params: Dict[str, List[Dict[str, Any]]] = {}
    for e in edges:
        if e.get("type") != "PARAM_OF":
            continue
        param_id, method_id = e.get("src"), e.get("dst")
        if not param_id or not method_id:
            continue
        pnode = nodes_by_id.get(param_id)
        if pnode and pnode.get("kind") == "Parameter":
            method_to_params.setdefault(method_id, []).append(
                pnode.get("attrs", {})
            )
    return method_to_params


def _index_method_owners(
    methods_by_type: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, str]:
    method_owner_by_id: Dict[str, str] = {}
    for type_id, methods in methods_by_type.items():
        for method in methods:
            method_id = method.get("_id")
            if method_id:
                method_owner_by_id[method_id] = type_id
    return method_owner_by_id


def _collect_type_dependency_pairs_from_calls(
    edges: List[Dict[str, Any]],
    method_owner_by_id: Dict[str, str],
) -> Set[Tuple[str, str]]:
    dependency_pairs: Set[Tuple[str, str]] = set()
    for edge in edges:
        if edge.get("type") != "CALLS":
            continue
        src_method_id = edge.get("src")
        dst_method_id = edge.get("dst")
        if not src_method_id or not dst_method_id:
            continue
        src_type_id = method_owner_by_id.get(src_method_id)
        dst_type_id = method_owner_by_id.get(dst_method_id)
        if not src_type_id or not dst_type_id or src_type_id == dst_type_id:
            continue
        dependency_pairs.add((src_type_id, dst_type_id))
    return dependency_pairs


def _clean_type_for_display(raw_type: str) -> str:
    if not raw_type:
        return "void"
    t = re.sub(r"<.*?>", "<>", raw_type)
    if "." in t:
        t = t.split(".")[-1]
    return t


def _clean_type_short(raw_type: str) -> str:
    if not raw_type:
        return ""
    t = re.sub(r"<.*?>", "", raw_type)
    if "." in t:
        t = t.rsplit(".", 1)[1]
    return t.strip()


def _format_mods(obj: Dict[str, Any]) -> str:
    mods = obj.get("modifiers") or ()
    if isinstance(mods, str):
        mods = (mods,)
    if isinstance(mods, set):
        mods = tuple(mods)
    out: List[str] = []
    if "static" in mods or obj.get("is_static"):
        out.append("{static}")
    if "abstract" in mods or obj.get("is_abstract"):
        out.append("{abstract}")
    return " ".join(out)


def _is_dunder(name: str) -> bool:
    return bool(name) and name.startswith("__") and name.endswith("__")


def _safe_sequence_label(method_name: str) -> str:
    if method_name == "__init__":
        return "<<create>>"
    if _is_dunder(method_name):
        safe = method_name.replace("__", "~__", 1)
        safe = safe[::-1].replace("__", "~__", 1)[::-1]
        return f"{safe}()"
    return f"{method_name}()"


_NOISE_NAME_SUFFIXES: Tuple[str, ...] = (
    "exception", "error",
    "logger",
    "util", "utils",
    "helper", "helpers",
    "config", "configuration",
    "filter",
    "framework",
    "application", "main",
)

_NOISE_NAME_CONTAINS: Tuple[str, ...] = (
    "logger",
    "logutil",
    "filterchain",
)

_NOISE_PKG_SEGMENTS: Tuple[str, ...] = (
    "exception", "exceptions",
    "error",     "errors",
    "util",      "utils",
    "helper",    "helpers",
    "log",       "logger",   "logging",
    "config",    "configuration",
    "filter",    "filters",
    "framework",
)


def _is_infrastructure_noise(name: str, package: str) -> bool:
    nm   = (name    or "").lower()
    pkg  = (package or "").lower()
    segs = set(pkg.replace("-", ".").split("."))

    if any(nm.endswith(sfx) for sfx in _NOISE_NAME_SUFFIXES):
        return True
    if any(kw in nm for kw in _NOISE_NAME_CONTAINS):
        return True
    if segs & set(_NOISE_PKG_SEGMENTS):
        return True

    return False

# ══════════════════════════════════════════════════════════════════════════════
#  CLASS DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════

def generate_class_diagram(cir: Dict[str, Any]) -> str:
    nodes_by_id, edges = _index_cir(cir)
    type_nodes, fields_by_type, methods_by_type = _extract_types_and_members(
        nodes_by_id, edges
    )
    params_by_method = _index_params_by_method(nodes_by_id, edges)
    method_owner_by_id = _index_method_owners(methods_by_type)

    def _has_main_entry_method(type_id: str) -> bool:
        for m in methods_by_type.get(type_id, []):
            method_name = str(m.get("name") or "").strip().lower()
            if method_name != "main":
                continue

            modifiers = {str(x).lower() for x in (m.get("modifiers") or ())}
            is_static = bool(m.get("is_static")) or ("static" in modifiers)
            if not is_static:
                continue

            raw_ret = str(m.get("raw_return_type") or m.get("return_type") or "").strip().lower()
            if raw_ret not in ("", "void", "java.lang.void"):
                continue

            return True
        return False

    def _is_class_diagram_noise(type_name: str) -> bool:
        n = (type_name or "").strip().lower()
        if n == "bcrypt":
            return True
        if n == "config":
            return True
        return False

    # Remove entry-point types (Main/Application/Bootstrap or static-main app classes)
    # from class diagrams.
    diagram_type_nodes: Dict[str, Dict[str, Any]] = {}
    for type_id, attrs in type_nodes.items():
        type_name = attrs.get("name", type_id)
        if _is_entry_or_demo_type(type_name, methods_by_type.get(type_id, [])) or _has_main_entry_method(type_id):
            continue
        if _is_class_diagram_noise(type_name):
            continue
        diagram_type_nodes[type_id] = attrs

    lines: List[str] = ["@startuml",
                        "skinparam classAttributeIconSize 0",
                        "set namespaceSeparator ."]

    for type_id, t in diagram_type_nodes.items():
        name = t.get("name", "UnknownType")
        kind = (t.get("kind") or "class").lower()
        if kind not in ("class", "interface", "enum"):
            kind = "class"

        class_mods = _format_mods(t)
        header = f"{kind} {name} {class_mods} {{" if class_mods else f"{kind} {name} {{"
        lines.append(header)

        for f in fields_by_type.get(type_id, []):
            vis_symbol = VISIBILITY_MAP.get(f.get("visibility", "package"), "~")
            field_name = f.get("name", "field")
            raw_type = f.get("raw_type") or f.get("type_name") or "Object"
            display_type = _clean_type_for_display(raw_type)
            multiplicity = f.get("multiplicity")
            if multiplicity and multiplicity not in ("1", ""):
                display_type = f"{display_type} [{multiplicity}]"
            f_mods = _format_mods(f)
            mods_prefix = f"{f_mods} " if f_mods else ""
            lines.append(f"  {vis_symbol} {mods_prefix}{field_name} : {display_type}")

        for m in methods_by_type.get(type_id, []):
            if m.get("is_constructor"):
                continue
            vis_symbol = VISIBILITY_MAP.get(m.get("visibility", "package"), "~")
            method_name = m.get("name", "method")
            m_mods = _format_mods(m)
            mods_prefix = f"{m_mods} " if m_mods else ""
            method_node_id = m.get("_id")
            params = params_by_method.get(method_node_id, []) if method_node_id else []
            param_parts = [
                f"{p.get('name','p')}: {_clean_type_for_display(p.get('raw_type') or p.get('type_name') or 'Object')}"
                for p in params
            ]
            param_str = ", ".join(param_parts)
            raw_ret = m.get("raw_return_type") or m.get("return_type", "void")
            display_ret = _clean_type_for_display(raw_ret)
            lines.append(f"  {vis_symbol} {mods_prefix}{method_name}({param_str}) : {display_ret}")

        lines.append("}")

    relation_lines: Set[str] = set()
    type_name_by_id = {tid: attrs.get("name", tid) for tid, attrs in diagram_type_nodes.items()}

    # Classify ASSOCIATES pairs into composition / aggregation / association.
    # Heuristics:
    # - composition: at least one backing field is final and there is no DEPENDS_ON
    #   evidence for the same pair (constructor/method usage usually means plain association)
    # - aggregation: backing field looks collection-like (multiplicity many or container raw type)
    # - association: fallback
    def _field_targets_type(field: Dict[str, Any], target_name: str) -> bool:
        element_type = str(field.get("type_name") or field.get("element_type") or "").strip()
        if not element_type or not target_name:
            return False
        if element_type == target_name:
            return True
        if element_type.endswith(f".{target_name}"):
            return True
        return False

    def _classify_association_pair(src_type_id: str, dst_type_id: str) -> str:
        target_name = str(type_name_by_id.get(dst_type_id, ""))
        if not target_name:
            return "association"

        candidates = [
            f for f in fields_by_type.get(src_type_id, [])
            if _field_targets_type(f, target_name)
        ]
        if not candidates:
            return "association"

        for f in candidates:
            modifiers = {str(m).lower() for m in (f.get("modifiers") or ())}
            if "final" in modifiers:
                return "composition"

        for f in candidates:
            mult = str(f.get("multiplicity") or "").strip()
            raw = str(f.get("raw_type") or "").lower()
            if mult in {"0..*", "1..*", "*"}:
                return "aggregation"
            if any(k in raw for k in ("list<", "set<", "map<", "collection<", "[]")):
                return "aggregation"

        return "association"

    depends_pairs: Set[Tuple[str, str]] = set()
    for e in edges:
        src, dst, etype = e.get("src"), e.get("dst"), e.get("type")
        if etype != "DEPENDS_ON":
            continue
        if not src or not dst:
            continue
        if src not in diagram_type_nodes or dst not in diagram_type_nodes:
            continue
        depends_pairs.add((src, dst))

    association_style_by_pair: Dict[Tuple[str, str], str] = {}
    for e in edges:
        src, dst, etype = e.get("src"), e.get("dst"), e.get("type")
        if etype != "ASSOCIATES":
            continue
        if not src or not dst:
            continue
        if src not in diagram_type_nodes or dst not in diagram_type_nodes:
            continue
        pair = (src, dst)
        style = _classify_association_pair(src, dst)
        if style == "composition" and (src, dst) in depends_pairs:
            style = "association"
        previous = association_style_by_pair.get(pair)
        if previous == "composition":
            continue
        if previous == "aggregation" and style == "association":
            continue
        association_style_by_pair[pair] = style

    explicit_relation_pairs: Set[Tuple[str, str]] = set()
    for e in edges:
        src, dst, etype = e.get("src"), e.get("dst"), e.get("type")
        if not src or not dst or not etype:
            continue
        if src not in diagram_type_nodes or dst not in diagram_type_nodes:
            continue
        if etype in ("INHERITS", "IMPLEMENTS", "ASSOCIATES", "DEPENDS_ON"):
            explicit_relation_pairs.add((src, dst))

    # Precompute ASSOCIATES pairs so DEPENDS_ON can be suppressed for the same endpoints.
    associate_pairs: Set[Tuple[str, str]] = set()
    for e in edges:
        src, dst, etype = e.get("src"), e.get("dst"), e.get("type")
        if etype != "ASSOCIATES":
            continue
        if not src or not dst:
            continue
        if src not in diagram_type_nodes or dst not in diagram_type_nodes:
            continue
        associate_pairs.add((src, dst))

    for e in edges:
        src, dst, etype = e.get("src"), e.get("dst"), e.get("type")
        if not src or not dst or not etype:
            continue
        if src not in diagram_type_nodes or dst not in diagram_type_nodes:
            continue
        sn, dn = type_name_by_id[src], type_name_by_id[dst]
        if etype == "INHERITS":
            relation_lines.add(f"{sn} --|> {dn}")
        elif etype == "IMPLEMENTS":
            relation_lines.add(f"{sn} ..|> {dn}")
        elif etype == "ASSOCIATES":
            style = association_style_by_pair.get((src, dst), "association")
            mult = (e.get("attrs") or {}).get("multiplicity")
            if style == "composition":
                if mult and mult not in ("1", ""):
                    relation_lines.add(f'{sn} *-- "{mult}" {dn}')
                else:
                    relation_lines.add(f"{sn} *-- {dn}")
            elif style == "aggregation":
                if mult and mult not in ("1", ""):
                    relation_lines.add(f'{sn} o-- "{mult}" {dn}')
                else:
                    relation_lines.add(f"{sn} o-- {dn}")
            else:
                if mult and mult not in ("1", ""):
                    relation_lines.add(f'{sn} --> "{mult}" {dn}')
                else:
                    relation_lines.add(f"{sn} --> {dn}")
        elif etype == "DEPENDS_ON":
            if (src, dst) in associate_pairs:
                continue
            relation_lines.add(f"{sn} ..> {dn}")

    for src_type_id, dst_type_id in _collect_type_dependency_pairs_from_calls(edges, method_owner_by_id):
        if src_type_id not in diagram_type_nodes or dst_type_id not in diagram_type_nodes:
            continue
        if (src_type_id, dst_type_id) in explicit_relation_pairs:
            continue
        relation_lines.add(f"{type_name_by_id[src_type_id]} ..> {type_name_by_id[dst_type_id]}")

    for rel in sorted(relation_lines):
        lines.append(rel)

    lines.append("@enduml")
    return "\n".join(lines)

# ══════════════════════════════════════════════════════════════════════════════
#  PACKAGE DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════

def _package_display_name(package: Optional[str]) -> str:
    package_name = (package or "").strip()
    return package_name if package_name else "(default)"


def _infer_package_from_type_name(type_name: str) -> str:
    name = (type_name or "").lower()

    if any(k in name for k in ("app", "main", "application", "bootstrap")):
        return "application"
    if any(k in name for k in ("controller", "resource", "endpoint", "api", "handler")):
        return "api"
    if any(k in name for k in ("service", "manager", "facade", "usecase", "interactor")):
        return "service"
    if any(k in name for k in ("repository", "repo", "dao", "store", "database")):
        return "repository"
    if any(k in name for k in ("hasher", "auth", "security", "crypto", "encrypt", "token")):
        return "security"
    if any(k in name for k in ("entity", "model", "dto", "vo", "record", "user", "student", "account")):
        return "model"
    if any(k in name for k in ("util", "helper", "common", "shared", "config")):
        return "common"

    return "default"


def _render_type_declaration(attrs: Dict[str, Any]) -> str:
    name = attrs.get("name", "UnknownType")
    kind = (attrs.get("kind") or "class").lower()

    if kind == "interface":
        return f"interface {name}"
    if kind == "enum":
        return f"enum {name}"
    if attrs.get("is_abstract") or kind == "abstract class":
        return f"abstract class {name}"
    return f"class {name}"

# Skip common entry/demo wrapper classes in generated single-file snippets.
def _is_entry_or_demo_type(name: str, methods: Optional[List[Dict[str, Any]]] = None) -> bool:
    n = (name or "").lower()

    if any(k in n for k in (
        "main", "application", "bootstrap", "app", "demo", "example", "sample", "runner", "cli", "program"
    )):
        return True

    # Strong signal: Java entry point method.
    for m in methods or []:
        if (m.get("name") or "").lower() == "main":
            return True

    return False


def generate_package_diagram(cir: Dict[str, Any]) -> str:
    nodes_by_id, edges = _index_cir(cir)
    _, fields_by_type, methods_by_type = _extract_types_and_members(nodes_by_id, edges)
    params_by_method = _index_params_by_method(nodes_by_id, edges)
    method_owner_by_id = _index_method_owners(methods_by_type)

    # Best-practice defaults for readable architecture diagrams.
    show_isolated_packages = False
    infer_missing_dependencies = True

    type_nodes: Dict[str, Dict[str, Any]] = {}
    for nid, n in nodes_by_id.items():
        if n.get("kind") == "TypeDecl":
            type_nodes[nid] = n.get("attrs", {})

    lines: List[str] = [
        "@startuml",
        "skinparam packageStyle         folder",
        "skinparam classAttributeIconSize 0",
        "skinparam shadowing            false",
        "skinparam package {",
        "  FontStyle        Bold",
        "  FontSize         12",
        "}",
    ]

    package_to_types: Dict[str, List[str]] = {}
    package_by_type_id: Dict[str, str] = {}
    type_name_by_id: Dict[str, str] = {}

    explicit_package_values: List[str] = [
        str((attrs.get("package") or "")).strip()
        for attrs in type_nodes.values()
        if str((attrs.get("package") or "")).strip()
    ]
    has_explicit_package = bool(explicit_package_values)
    unique_explicit_packages = set(explicit_package_values)

    def _looks_synthetic_single_package(pkg: str) -> bool:
        p = (pkg or "").strip()
        if not p:
            return False
        pl = p.lower()

        # Typical synthetic wrappers from snippet/single-file parsing.
        if pl in {"main", "__main__", "snippet", "module", "script", "app"}:
            return True

        # Java-like real packages are usually dotted lowercase identifiers.
        # If dotted, treat as explicit/real package.
        if "." in p:
            return False

        # Single CamelCase token is usually synthetic for our parser path.
        return p[:1].isupper()

    for type_id, attrs in type_nodes.items():
        type_name = attrs.get("name", type_id)
        has_main_entry_method = any(
            str(m.get("name") or "").strip().lower() == "main"
            for m in methods_by_type.get(type_id, [])
        )

        package_name = _package_display_name(attrs.get("package"))

        # If every parsed type lands in one explicit module/package (e.g., single-file
        # Python snippets often become "Main"), switch to role-based grouping to keep
        # package diagrams architectural and avoid one giant package with no arrows.
        should_force_inferred_grouping = (
            has_explicit_package
            and len(unique_explicit_packages) == 1
            and _looks_synthetic_single_package(next(iter(unique_explicit_packages)))
        )
        if should_force_inferred_grouping or (not has_explicit_package and package_name == "(default)"):
            if has_main_entry_method:
                package_name = "application"
            else:
                inferred = _infer_package_from_type_name(type_name)
                if inferred and inferred != "default":
                    package_name = inferred
        package_to_types.setdefault(package_name, []).append(_render_type_declaration(attrs))
        package_by_type_id[type_id] = package_name
        type_name_by_id[type_id] = type_name

    type_ids_by_short_name: Dict[str, List[str]] = {}
    for tid, tname in type_name_by_id.items():
        key = _clean_type_short(tname).lower() or str(tname).lower()
        type_ids_by_short_name.setdefault(key, []).append(tid)

    def _resolve_target_type_id(raw_type: str, src_type_id: str) -> Optional[str]:
        short = _clean_type_short(raw_type).lower()
        if not short:
            return None

        candidates = type_ids_by_short_name.get(short, [])
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        src_pkg = package_by_type_id.get(src_type_id)
        same_pkg = [tid for tid in candidates if package_by_type_id.get(tid) == src_pkg]
        if len(same_pkg) == 1:
            return same_pkg[0]

        return sorted(candidates)[0]

    package_dependency_pairs: Set[Tuple[str, str]] = set()

    def _add_package_dependency(src_type_id: str, dst_type_id: str) -> None:
        src_pkg = package_by_type_id.get(src_type_id)
        dst_pkg = package_by_type_id.get(dst_type_id)
        if not src_pkg or not dst_pkg or src_pkg == dst_pkg:
            return
        package_dependency_pairs.add((src_pkg, dst_pkg))

    for e in edges:
        src, dst, etype = e.get("src"), e.get("dst"), e.get("type")
        if not src or not dst or not etype:
            continue
        if src not in package_by_type_id or dst not in package_by_type_id:
            continue
        if etype in ("DEPENDS_ON", "ASSOCIATES", "INHERITS", "IMPLEMENTS"):
            _add_package_dependency(src, dst)

    if infer_missing_dependencies:
        for src_type_id in package_by_type_id.keys():
            for f in fields_by_type.get(src_type_id, []):
                raw_t = str(f.get("raw_type") or f.get("type_name") or "")
                dst_type_id = _resolve_target_type_id(raw_t, src_type_id)
                if dst_type_id and dst_type_id != src_type_id:
                    _add_package_dependency(src_type_id, dst_type_id)

            for m in methods_by_type.get(src_type_id, []):
                raw_ret = str(m.get("raw_return_type") or m.get("return_type") or "")
                dst_type_id = _resolve_target_type_id(raw_ret, src_type_id)
                if dst_type_id and dst_type_id != src_type_id:
                    _add_package_dependency(src_type_id, dst_type_id)

                method_id = m.get("_id")
                if not method_id:
                    continue

                for p in params_by_method.get(method_id, []):
                    raw_p = str(p.get("raw_type") or p.get("type_name") or "")
                    dst_type_id = _resolve_target_type_id(raw_p, src_type_id)
                    if dst_type_id and dst_type_id != src_type_id:
                        _add_package_dependency(src_type_id, dst_type_id)

    for src_type_id, dst_type_id in _collect_type_dependency_pairs_from_calls(edges, method_owner_by_id):
        if src_type_id in package_by_type_id and dst_type_id in package_by_type_id:
            _add_package_dependency(src_type_id, dst_type_id)

    if not show_isolated_packages and package_dependency_pairs:
        involved_packages: Set[str] = {
            pkg for src_pkg, dst_pkg in package_dependency_pairs for pkg in (src_pkg, dst_pkg)
        }
        package_to_types = {
            pkg: decls
            for pkg, decls in package_to_types.items()
            if pkg in involved_packages
        }

    if package_to_types:
        lines.append("")

    for package_name in sorted(package_to_types.keys()):
        lines.append(f'package "{package_name}" {{')
        for type_decl in sorted(package_to_types[package_name]):
            lines.append(f"  {type_decl}")
        lines.append("}")
        lines.append("")

    for src_pkg, dst_pkg in sorted(package_dependency_pairs):
        if src_pkg not in package_to_types or dst_pkg not in package_to_types:
            continue
        lines.append(f'"{src_pkg}" ..> "{dst_pkg}" : depends')

    lines.append("@enduml")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  SEQUENCE DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════

def generate_sequence_diagram(cir: Dict[str, Any]) -> str:
    nodes_by_id, edges = _index_cir(cir)
    type_nodes, _, methods_by_type = _extract_types_and_members(nodes_by_id, edges)

    method_attrs_by_id: Dict[str, Dict[str, Any]] = {}
    owner_type_by_method_id: Dict[str, str] = {}
    for type_id, methods in methods_by_type.items():
        for method in methods:
            method_id = str(method.get("_id") or "").strip()
            if not method_id:
                continue
            method_attrs_by_id[method_id] = method
            owner_type_by_method_id[method_id] = type_id

    type_name_by_id: Dict[str, str] = {
        tid: str(attrs.get("name") or tid) for tid, attrs in type_nodes.items()
    }
    type_package_by_id: Dict[str, str] = {
        tid: str(attrs.get("package") or "") for tid, attrs in type_nodes.items()
    }

    call_edges: List[Tuple[int, str, str]] = []
    incoming_method_count: Dict[str, int] = {}
    outgoing_by_method: Dict[str, List[Tuple[int, str]]] = {}

    for edge in edges:
        if edge.get("type") != "CALLS":
            continue
        src_method_id = str(edge.get("src") or "").strip()
        dst_method_id = str(edge.get("dst") or "").strip()
        if src_method_id not in method_attrs_by_id or dst_method_id not in method_attrs_by_id:
            continue

        order = int((edge.get("attrs") or {}).get("order", 0))
        call_edges.append((order, src_method_id, dst_method_id))
        incoming_method_count[dst_method_id] = incoming_method_count.get(dst_method_id, 0) + 1
        outgoing_by_method.setdefault(src_method_id, []).append((order, dst_method_id))

    for src_method_id in list(outgoing_by_method.keys()):
        outgoing_by_method[src_method_id].sort(key=lambda x: (x[0], x[1]))

    def _participant_alias(type_id: str) -> str:
        return "P_" + re.sub(r"[^a-zA-Z0-9_]", "_", type_id)

    def _method_priority(method_id: str) -> Tuple[int, int, int, str, str]:
        attrs = method_attrs_by_id.get(method_id, {})
        owner_id = owner_type_by_method_id.get(method_id, "")
        type_name = str(type_name_by_id.get(owner_id, ""))
        type_pkg = str(type_package_by_id.get(owner_id, ""))
        method_name = str(attrs.get("name") or "")
        incoming_rank = 1 if incoming_method_count.get(method_id, 0) > 0 else 0
        noise_rank = 1 if _is_infrastructure_noise(type_name, type_pkg) else 0
        layer_rank = _layer_order(type_name, type_pkg)
        return (incoming_rank, noise_rank, layer_rank, type_name, method_name)

    lines: List[str] = [
        "@startuml",
        "skinparam shadowing false",
        "skinparam sequenceMessageAlign center",
        "autonumber",
    ]

    if call_edges:
        entry_methods = sorted(outgoing_by_method.keys(), key=_method_priority)
        entry_method_id = entry_methods[0]

        chain: List[Tuple[str, str]] = []
        visited_calls: Set[Tuple[str, str]] = set()
        cursor = entry_method_id
        max_steps = 40

        while len(chain) < max_steps:
            next_candidates = outgoing_by_method.get(cursor, [])
            next_method_id: Optional[str] = None
            for _, dst_method_id in next_candidates:
                pair = (cursor, dst_method_id)
                if pair in visited_calls:
                    continue
                next_method_id = dst_method_id
                break

            if not next_method_id:
                break

            chain.append((cursor, next_method_id))
            visited_calls.add((cursor, next_method_id))
            cursor = next_method_id

        if not chain:
            ordered_edges = sorted(call_edges, key=lambda x: (x[0], x[1], x[2]))
            chain = [(src, dst) for _, src, dst in ordered_edges[:20]]

        participant_order: List[str] = []
        seen_participants: Set[str] = set()

        for src_method_id, dst_method_id in chain:
            src_type_id = owner_type_by_method_id.get(src_method_id, "")
            dst_type_id = owner_type_by_method_id.get(dst_method_id, "")
            for type_id in (src_type_id, dst_type_id):
                if not type_id or type_id in seen_participants:
                    continue
                seen_participants.add(type_id)
                participant_order.append(type_id)

        for type_id in participant_order:
            display = type_name_by_id.get(type_id, type_id)
            lines.append(f'participant "{display}" as {_participant_alias(type_id)}')

        if participant_order:
            lines.append("")

        for src_method_id, dst_method_id in chain:
            src_type_id = owner_type_by_method_id.get(src_method_id, "")
            dst_type_id = owner_type_by_method_id.get(dst_method_id, "")
            if not src_type_id or not dst_type_id:
                continue

            dst_method_name = str(method_attrs_by_id.get(dst_method_id, {}).get("name") or "call")
            msg = _safe_sequence_label(dst_method_name)
            src_alias = _participant_alias(src_type_id)
            dst_alias = _participant_alias(dst_type_id)

            lines.append(f"{src_alias} -> {dst_alias} : {msg}")

    else:
        # Fallback: create high-level interaction flow from type dependencies.
        type_ids: List[str] = []
        for tid, attrs in type_nodes.items():
            t_name = str(attrs.get("name") or "")
            t_pkg = str(attrs.get("package") or "")
            if _is_entry_or_demo_type(t_name, methods_by_type.get(tid, [])):
                continue
            if _is_infrastructure_noise(t_name, t_pkg):
                continue
            type_ids.append(tid)

        type_ids.sort(key=lambda tid: _layer_order(type_name_by_id.get(tid, ""), type_package_by_id.get(tid, "")))

        relation_pairs: List[Tuple[str, str]] = []
        for edge in edges:
            etype = str(edge.get("type") or "")
            if etype not in {"DEPENDS_ON", "ASSOCIATES"}:
                continue
            src = str(edge.get("src") or "").strip()
            dst = str(edge.get("dst") or "").strip()
            if src in type_nodes and dst in type_nodes and src != dst:
                if src in type_ids and dst in type_ids:
                    relation_pairs.append((src, dst))

        seen_rel: Set[Tuple[str, str]] = set()
        compact_pairs: List[Tuple[str, str]] = []
        for src, dst in relation_pairs:
            if (src, dst) in seen_rel:
                continue
            seen_rel.add((src, dst))
            compact_pairs.append((src, dst))

        if not compact_pairs and len(type_ids) >= 2:
            for i in range(0, min(len(type_ids) - 1, 8)):
                compact_pairs.append((type_ids[i], type_ids[i + 1]))

        participants: List[str] = []
        seen_participants = set()
        for src, dst in compact_pairs:
            if src not in seen_participants:
                participants.append(src)
                seen_participants.add(src)
            if dst not in seen_participants:
                participants.append(dst)
                seen_participants.add(dst)

        if not participants and type_ids:
            participants = [type_ids[0]]

        for type_id in participants:
            display = type_name_by_id.get(type_id, type_id)
            lines.append(f'participant "{display}" as {_participant_alias(type_id)}')

        if participants:
            lines.append("")

        if compact_pairs:
            for src, dst in compact_pairs[:20]:
                lines.append(
                    f"{_participant_alias(src)} -> {_participant_alias(dst)} : uses()"
                )
        elif participants:
            p = _participant_alias(participants[0])
            lines.append(f"{p} -> {p} : process()")

    lines.append("@enduml")
    return "\n".join(lines)




# ══════════════════════════════════════════════════════════════════════════════
#  COMPONENT DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════

def generate_component_diagram(cir: Dict[str, Any]) -> str:
    nodes_by_id, edges = _index_cir(cir)
    _, _, methods_by_type = _extract_types_and_members(nodes_by_id, edges)
    method_owner_by_id = _index_method_owners(methods_by_type)

    type_nodes:  Dict[str, Dict[str, Any]] = {}
    package_of:  Dict[str, str] = {}

    def _is_component_noise(type_name: str, methods: Optional[List[Dict[str, Any]]]) -> bool:
        n = (type_name or "").lower()
        if _is_entry_or_demo_type(type_name, methods):
            return True
        # Drop low-level crypto placeholder/helper types from architecture view.
        if n in {"bcrypt"}:
            return True
        return False

    for nid, n in nodes_by_id.items():
        if n.get("kind") != "TypeDecl":
            continue
        attrs = n.get("attrs", {})
        nm  = attrs.get("name",    "") or ""
        pkg = attrs.get("package", "") or ""
        if _is_component_noise(nm, methods_by_type.get(nid, [])):
            continue
        type_nodes[nid] = attrs
        package_of[nid] = pkg or "(default)"

    dep_edges: List[Tuple[str, str, str]] = []
    for e in edges:
        src, dst, etype = e.get("src"), e.get("dst"), e.get("type")
        if src and dst and etype and src != dst:
            if src in type_nodes and dst in type_nodes:
                if etype in ("ASSOCIATES", "DEPENDS_ON"):
                    dep_edges.append((src, dst, etype))

    for src_type_id, dst_type_id in _collect_type_dependency_pairs_from_calls(edges, method_owner_by_id):
        if src_type_id in type_nodes and dst_type_id in type_nodes:
            dep_edges.append((src_type_id, dst_type_id, "CALLS"))

    if dep_edges:
        involved: Set[str] = {tid for s, d, _ in dep_edges for tid in (s, d)}
        type_nodes = {tid: attrs for tid, attrs in type_nodes.items() if tid in involved}
        package_of = {tid: pkg for tid, pkg in package_of.items() if tid in involved}

    _LAYERS: List[Tuple[str, str]] = [
        ("controller", "<<Controller>>"),
        ("resource",   "<<Controller>>"),
        ("endpoint",   "<<Controller>>"),
        ("rest",       "<<Controller>>"),
        ("handler",    "<<Controller>>"),
        ("service",    "<<Service>>"),
        ("manager",    "<<Service>>"),
        ("facade",     "<<Service>>"),
        ("repository", "<<Repository>>"),
        ("dao",        "<<Repository>>"),
        ("repo",       "<<Repository>>"),
        ("database",   "<<Database>>"),
        ("db",         "<<Database>>"),
        ("model",      "<<Model>>"),
        ("entity",     "<<Model>>"),
        ("domain",     "<<Model>>"),
        ("dto",        "<<DTO>>"),
        ("util",       "<<Utility>>"),
        ("helper",     "<<Utility>>"),
        ("config",     "<<Config>>"),
        ("security",   "<<Security>>"),
        ("filter",     "<<Security>>"),
        ("middleware", "<<Middleware>>"),
    ]

    def _layer_stereo(pkg: str, name: str) -> Optional[str]:
        pkg_l = (pkg or "").lower()
        for kw, stereo in _LAYERS:
            if kw in pkg_l:
                return stereo

        name_l = (name or "").lower()
        for kw, stereo in _LAYERS:
            if kw in name_l:
                return stereo
        return None

    def _arrow_label(dst_pkg: str, dst_name: str) -> str:
        combined = (dst_pkg + " " + dst_name).lower()
        if "database" in combined or "db" in combined:     return "queries"
        if "model" in combined or "entity" in combined:    return "maps"
        if "dao" in combined or "repository" in combined or "repo" in combined: return "delegates"
        if "util" in combined or "helper" in combined:     return "uses"
        return "uses"

    def _alias(tid: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_]", "_", tid)

    def _iface_alias(tid: str) -> str:
        return "I_" + re.sub(r"[^a-zA-Z0-9_]", "_", tid)

    explicit_pkgs = {p for p in package_of.values() if p and p != "(default)"}

    root_prefix = ""
    if len(explicit_pkgs) == 1:
        root_prefix = next(iter(explicit_pkgs))
    elif len(explicit_pkgs) > 1:
        parts_list = [p.split(".") for p in explicit_pkgs]
        common: List[str] = []
        for segs in zip(*parts_list):
            if len(set(segs)) == 1:
                common.append(segs[0])
            else:
                break
        root_prefix = ".".join(common)

    def _inferred_component_group(type_name: str) -> str:
        name = (type_name or "").lower()
        if any(k in name for k in ("repository", "repo", "dao", "store")):
            return "repository"
        if any(k in name for k in ("database", "db", "connection")):
            return "database"
        if any(k in name for k in ("service", "manager", "facade", "interactor", "usecase")):
            return "service"
        if any(k in name for k in ("util", "helper", "common", "shared")):
            return "util"
        if any(k in name for k in ("model", "entity", "domain", "dto", "record", "vo", "student", "user")):
            return "model"
        if any(k in name for k in ("security", "auth", "hasher", "crypto", "token", "encrypt")):
            return "security"
        if any(k in name for k in ("controller", "resource", "endpoint", "api", "handler", "rest")):
            return "api"
        return "(root)"

    effective_package_of: Dict[str, str] = {}
    for tid, attrs in type_nodes.items():
        raw_pkg = package_of.get(tid, "(default)")
        name = str(attrs.get("name", ""))

        if raw_pkg == "(default)":
            grp = _inferred_component_group(name)
            effective_package_of[tid] = grp if grp != "(root)" else "(default)"
            continue

        if root_prefix and raw_pkg == root_prefix:
            grp = _inferred_component_group(name)
            if grp != "(root)":
                effective_package_of[tid] = f"{root_prefix}.{grp}"
                continue

        effective_package_of[tid] = raw_pkg

    pkg_to_types: Dict[str, List[str]] = {}
    for tid in type_nodes:
        pkg_to_types.setdefault(effective_package_of[tid], []).append(tid)

    all_pkgs = [p for p in pkg_to_types if p != "(default)"]

    if not root_prefix and len(all_pkgs) > 1:
        parts_list = [p.split(".") for p in all_pkgs]
        common: List[str] = []
        for segs in zip(*parts_list):
            if len(set(segs)) == 1:
                common.append(segs[0])
            else:
                break
        root_prefix = ".".join(common)

    def _short_pkg(pkg: str) -> str:
        if pkg == "(default)":
            return "(default)"
        if root_prefix and pkg.startswith(root_prefix):
            rel = pkg[len(root_prefix):].lstrip(".")
            return rel if rel else "(root)"
        return pkg.rsplit(".", 1)[-1]

    called_types: Set[str] = set()
    for _, dst, _ in dep_edges:
        called_types.add(dst)

    out: List[str] = [
        "@startuml",
        "",
        "' Component diagram — shows architectural components and their interfaces",
        "' Notched-rectangle = component   Circle (lollipop) = provided interface",
        "' Only ASSOCIATES and DEPENDS_ON edges are shown (no classifier relationships)",
        "",
        "skinparam componentStyle      uml2",
        "skinparam defaultTextAlignment center",
        "skinparam shadowing           false",
        "left to right direction",
        "",
        "skinparam package {",
        "  FontStyle        Bold",
        "}",
        "",
    ]

    use_root = bool(root_prefix) and len(all_pkgs) > 1
    indent = ""
    if use_root:
        out.append(f'package "{root_prefix}" {{')
        indent = "  "

    def _pkg_sort(pkg: str) -> Tuple[int, str]:
        s = _short_pkg(pkg)
        if s in ("(root)", "(default)"):
            return (0, "")
        return (1 + _layer_order("", s), s)

    for pkg in sorted(pkg_to_types.keys(), key=_pkg_sort):
        tids  = sorted(pkg_to_types[pkg], key=lambda t: type_nodes[t].get("name", ""))
        short = _short_pkg(pkg)

        stereo_counts: Dict[str, int] = {}
        for tid in tids:
            s = _layer_stereo(pkg, type_nodes[tid].get("name", ""))
            if s:
                stereo_counts[s] = stereo_counts.get(s, 0) + 1
        pkg_stereo = max(stereo_counts, key=stereo_counts.get) if stereo_counts else None

        is_root_level = short in ("(root)", "(default)")

        if not is_root_level:
            s_str = f" {pkg_stereo}" if pkg_stereo else ""
            out.append(f'{indent}package "{short}"{s_str} {{')
            inner = indent + "  "
        else:
            inner = indent

        for tid in tids:
            attrs  = type_nodes[tid]
            nm     = attrs.get("name", "UnknownType")
            alias  = _alias(tid)
            ialias = _iface_alias(tid)

            out.append(f'{inner}[{nm}] as {alias}')

            if tid in called_types:
                out.append(f'{inner}() "{nm}" as {ialias}')
                out.append(f'{inner}{alias} - {ialias}')

        if not is_root_level:
            out.append(f'{indent}}}')
        out.append("")

    if use_root:
        out.append("}")
        out.append("")

    arrow_set: Set[Tuple[str, str]] = set()
    for src_id, dst_id, etype in dep_edges:
        src_alias = _alias(src_id)
        dst_alias = _iface_alias(dst_id) if dst_id in called_types else _alias(dst_id)
        pair = (src_alias, dst_alias)
        if pair in arrow_set:
            continue
        arrow_set.add(pair)
        label = _arrow_label(effective_package_of[dst_id], type_nodes[dst_id].get("name", ""))
        out.append(f"{src_alias} --> {dst_alias} : {label}")

    out.append("")
    out.append("@enduml")
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════════════════
#  ACTIVITY DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════

def _is_boolean_return_type(raw_type: str) -> bool:
    t = (raw_type or "").strip().lower()
    return t in {"bool", "boolean"}


def _is_collection_return_type(raw_type: str) -> bool:
    t = (raw_type or "").strip().lower()
    if not t:
        return False
    return any(k in t for k in ("list", "set", "collection", "iterable", "array", "[]"))


def _activity_action_label(type_name: str, method_name: str) -> str:
    tn = (type_name or "UnknownType").strip()
    mn = (method_name or "method").strip()
    return f"{tn}.{mn}()"


def _is_void_return_type(raw_type: str) -> bool:
    return (raw_type or "").strip().lower() in {"", "void", "none", "null"}


def _is_scalar_return_type(raw_type: str) -> bool:
    t = (raw_type or "").strip().lower()
    t = re.sub(r"<.*?>", "", t)
    primitives = {
        "int", "integer", "long", "short", "byte",
        "float", "double", "decimal", "number",
        "char", "character", "string", "str",
        "uuid",
    }
    return t in primitives


def _is_lookup_like_method(method_name: str, raw_ret: str) -> bool:
    n = (method_name or "").strip().lower()
    if _is_void_return_type(raw_ret) or _is_boolean_return_type(raw_ret) or _is_collection_return_type(raw_ret):
        return False
    if _is_scalar_return_type(raw_ret):
        return False
    if n.startswith("get") and not n.startswith("getall"):
        return True
    return any(k in n for k in ("find", "fetch", "lookup", "load", "read"))


def _is_boolean_guard_method(method_name: str, raw_ret: str) -> bool:
    n = (method_name or "").strip().lower()
    if _is_boolean_return_type(raw_ret):
        return True
    return any(n.startswith(p) for p in ("is", "has", "can", "should", "verify", "validate", "check"))


def _is_collection_iteration_method(method_name: str, raw_ret: str) -> bool:
    n = (method_name or "").strip().lower()
    if _is_collection_return_type(raw_ret):
        return True
    return any(k in n for k in ("list", "all", "findall", "getall"))


def _collection_item_label(raw_type: str) -> str:
    t = (raw_type or "").strip()
    m = re.search(r"<\s*([A-Za-z_][A-Za-z0-9_]*)\s*>", t)
    if m:
        return m.group(1)
    if "[]" in t:
        base = t.replace("[]", "").strip()
        return base or "item"
    return "item"


def _lookup_found_means_failure(entry_method_name: str) -> bool:
    n = (entry_method_name or "").strip().lower()
    return any(k in n for k in ("register", "create", "add", "signup", "enroll"))


def _failure_label_for_entry(entry_method_name: str, return_type: str) -> str:
    name = (entry_method_name or "operation").strip()
    if _is_boolean_return_type(return_type):
        return f"{name} failed (return false)"
    if _is_void_return_type(return_type):
        return f"{name} aborted"
    return f"{name} failed (return null)"


def generate_activity_diagram(cir: Dict[str, Any]) -> str:
    nodes_by_id, edges = _index_cir(cir)
    type_nodes, _, methods_by_type = _extract_types_and_members(nodes_by_id, edges)

    # Build method indexes and owner lookups.
    method_attrs_by_id: Dict[str, Dict[str, Any]] = {}
    owner_type_by_method_id: Dict[str, str] = {}
    type_name_by_id: Dict[str, str] = {
        tid: str(attrs.get("name") or tid) for tid, attrs in type_nodes.items()
    }

    for type_id, methods in methods_by_type.items():
        for m in methods:
            mid = str(m.get("_id") or "").strip()
            if not mid:
                continue
            method_attrs_by_id[mid] = m
            owner_type_by_method_id[mid] = type_id

    outgoing_by_method: Dict[str, List[Tuple[int, str]]] = {}
    incoming_count: Dict[str, int] = {}
    for e in edges:
        if e.get("type") != "CALLS":
            continue
        src = str(e.get("src") or "").strip()
        dst = str(e.get("dst") or "").strip()
        if src not in method_attrs_by_id or dst not in method_attrs_by_id:
            continue
        order = int((e.get("attrs") or {}).get("order", 0))
        outgoing_by_method.setdefault(src, []).append((order, dst))
        incoming_count[dst] = incoming_count.get(dst, 0) + 1

    for src in list(outgoing_by_method.keys()):
        outgoing_by_method[src].sort(key=lambda x: (x[0], x[1]))

    method_candidates = [mid for mid in outgoing_by_method.keys() if mid in method_attrs_by_id]

    def _method_priority(mid: str) -> Tuple[int, int, int, str, str]:
        m = method_attrs_by_id[mid]
        type_id = owner_type_by_method_id.get(mid, "")
        t_attrs = type_nodes.get(type_id, {})
        type_name = str(t_attrs.get("name") or "")
        type_pkg = str(t_attrs.get("package") or "")
        method_name = str(m.get("name") or "")

        # Prefer root-like orchestrator methods:
        # - no incoming calls
        # - not demo/entry wrappers
        # - higher-level architectural layers
        incoming = incoming_count.get(mid, 0)
        is_demo = _is_entry_or_demo_type(type_name, methods_by_type.get(type_id, []))

        method_rank = 5
        name_l = method_name.lower()
        if name_l in {"start", "run", "execute", "process", "handle", "main"}:
            method_rank = 0
        elif any(k in name_l for k in ("login", "register", "create", "update", "delete", "get", "list")):
            method_rank = 1

        return (
            1 if incoming > 0 else 0,
            1 if is_demo else 0,
            _layer_order(type_name, type_pkg),
            method_rank,
            f"{type_name}.{method_name}",
        )

    ordered_methods = sorted(method_candidates, key=_method_priority)

    lines: List[str] = [
        "@startuml",
        "skinparam shadowing false",
        "skinparam activityBorderColor #000000",
        "skinparam activityBackgroundColor #ffffff",
        "skinparam activityFontColor #000000",
        "skinparam activityFontSize 13",
        "skinparam ActivityDiamondBorderColor #000000",
        "skinparam ActivityDiamondBackgroundColor #ffffff",
        "skinparam ActivityDiamondFontColor #000000",
        "start",
    ]

    if not ordered_methods:
        # Fallback when CALLS are missing in CIR.
        fallback_method: Optional[Tuple[str, Dict[str, Any], str]] = None
        for type_id, methods in methods_by_type.items():
            t_attrs = type_nodes.get(type_id, {})
            type_name = str(t_attrs.get("name") or "")
            if _is_entry_or_demo_type(type_name, methods):
                continue
            for m in methods:
                if m.get("is_constructor"):
                    continue
                name = str(m.get("name") or "")
                if not name or _is_dunder(name):
                    continue
                fallback_method = (type_id, m, type_name)
                break
            if fallback_method:
                break

        if fallback_method:
            _, m, type_name = fallback_method
            lines.append(f":{_activity_action_label(type_name, str(m.get('name') or 'method'))};")
        else:
            lines.append(":Execute workflow;")

        lines.append("stop")
        lines.append("@enduml")
        return "\n".join(lines)

    entry_method_id = ordered_methods[0]

    # Walk the dominant ordered CALLS chain.
    chain: List[str] = [entry_method_id]
    visited: Set[str] = {entry_method_id}
    cursor = entry_method_id
    max_steps = 25
    while len(chain) < max_steps:
        next_candidates = outgoing_by_method.get(cursor, [])
        next_id: Optional[str] = None
        for _, dst in next_candidates:
            if dst not in visited:
                next_id = dst
                break
        if not next_id:
            break
        chain.append(next_id)
        visited.add(next_id)
        cursor = next_id

    entry_method = method_attrs_by_id.get(entry_method_id, {})
    entry_method_name = str(entry_method.get("name") or "operation")
    entry_return_type = str(entry_method.get("raw_return_type") or entry_method.get("return_type") or "")

    used_lookup_branch = False
    used_boolean_branch = False
    used_collection_loop = False

    for mid in chain:
        m = method_attrs_by_id.get(mid, {})
        type_id = owner_type_by_method_id.get(mid, "")
        type_name = type_name_by_id.get(type_id, "UnknownType")
        method_name = str(m.get("name") or "method")
        raw_ret = str(m.get("raw_return_type") or m.get("return_type") or "")
        action_label = _activity_action_label(type_name, method_name)

        lines.append(f":{action_label};")

        if not used_lookup_branch and _is_lookup_like_method(method_name, raw_ret):
            if _lookup_found_means_failure(entry_method_name):
                lines.append(f"if ({action_label} returned value?) then (exists)")
                lines.append(f"  :{_failure_label_for_entry(entry_method_name, entry_return_type)};")
                lines.append("  stop")
                lines.append("else (not found)")
                lines.append("  :Proceed with registration;")
                lines.append("endif")
            else:
                lines.append(f"if ({action_label} returned value?) then (found)")
                lines.append("  :Proceed with retrieved entity;")
                lines.append("else (not found)")
                lines.append(f"  :{_failure_label_for_entry(entry_method_name, entry_return_type)};")
                lines.append("  stop")
                lines.append("endif")
            used_lookup_branch = True
            continue

        if not used_boolean_branch and _is_boolean_guard_method(method_name, raw_ret):
            lines.append(f"if ({action_label} is true?) then (yes)")
            lines.append(f"  :{entry_method_name} check passed;")
            lines.append("else (no)")
            lines.append(f"  :{_failure_label_for_entry(entry_method_name, entry_return_type)};")
            lines.append("  stop")
            lines.append("endif")
            used_boolean_branch = True
            continue

        if not used_collection_loop and _is_collection_iteration_method(method_name, raw_ret):
            item_label = _collection_item_label(raw_ret)
            lines.append(f"while ({action_label} has more items?) is (yes)")
            lines.append(f"  :Process {item_label};")
            lines.append("endwhile (no)")
            used_collection_loop = True

    if not used_lookup_branch and not used_boolean_branch and len(chain) >= 2:
        # Fallback decision when we only have linear calls but no clear semantic guard.
        guard_mid = chain[1]
        guard_m = method_attrs_by_id.get(guard_mid, {})
        guard_tid = owner_type_by_method_id.get(guard_mid, "")
        guard_type_name = type_name_by_id.get(guard_tid, "UnknownType")
        guard_label = _activity_action_label(guard_type_name, str(guard_m.get("name") or "method"))
        lines.append(f"if ({guard_label} succeeded?) then (yes)")
        lines.append(f"  :{entry_method_name} continues;")
        lines.append("else (no)")
        lines.append(f"  :{_failure_label_for_entry(entry_method_name, entry_return_type)};")
        lines.append("  stop")
        lines.append("endif")

    lines.append("stop")
    lines.append("@enduml")
    return "\n".join(lines)


def generate_plantuml_from_cir(cir: Dict[str, Any]) -> str:
    return generate_class_diagram(cir)

