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

# ──────────────────────────────────────────────────────────────────────────────
#  Architecture layer ordering
#  Lower number = higher in the call stack (client-side / entry point)
# ──────────────────────────────────────────────────────────────────────────────
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
    """Return architectural layer order for a type. Lower = earlier caller."""
    combined = (type_name + " " + (package or "")).lower()
    best = 55  # default: middle
    for keyword, order in _LAYER_ORDER.items():
        if keyword in combined:
            if order < best:
                best = order
    return best


# ──────────────────────────────────────────────────────────────────────────────
#  Low-level CIR helpers
# ──────────────────────────────────────────────────────────────────────────────

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


def _clean_type_for_display(raw_type: str) -> str:
    if not raw_type:
        return "void"
    t = re.sub(r"<.*?>", "<>", raw_type)
    if "." in t:
        t = t.split(".")[-1]
    return t


def _clean_type_short(raw_type: str) -> str:
    """Strip generics entirely, just keep base name."""
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


# ──────────────────────────────────────────────────────────────────────────────
#  Infrastructure-noise filter
# ──────────────────────────────────────────────────────────────────────────────

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

    lines: List[str] = ["@startuml",
                        "skinparam classAttributeIconSize 0",
                        "set namespaceSeparator ."]

    for type_id, t in type_nodes.items():
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
    type_name_by_id = {tid: attrs.get("name", tid) for tid, attrs in type_nodes.items()}

    for e in edges:
        src, dst, etype = e.get("src"), e.get("dst"), e.get("type")
        if not src or not dst or not etype:
            continue
        if src not in type_nodes or dst not in type_nodes:
            continue
        sn, dn = type_name_by_id[src], type_name_by_id[dst]
        if etype == "INHERITS":
            relation_lines.add(f"{sn} --|> {dn}")
        elif etype == "IMPLEMENTS":
            relation_lines.add(f"{sn} ..|> {dn}")
        elif etype == "ASSOCIATES":
            mult = (e.get("attrs") or {}).get("multiplicity")
            if mult and mult not in ("1", ""):
                relation_lines.add(f'{sn} --> "{mult}" {dn}')
            else:
                relation_lines.add(f"{sn} --> {dn}")
        elif etype == "DEPENDS_ON":
            relation_lines.add(f"{sn} ..> {dn}")

    for rel in sorted(relation_lines):
        lines.append(rel)

    lines.append("@enduml")
    return "\n".join(lines)


def generate_plantuml_from_cir(cir: Dict[str, Any]) -> str:
    return generate_class_diagram(cir)


# ══════════════════════════════════════════════════════════════════════════════
#  PACKAGE DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════

def generate_package_diagram(cir: Dict[str, Any]) -> str:
    nodes_by_id, edges = _index_cir(cir)

    type_nodes: Dict[str, Dict[str, Any]] = {}
    for nid, n in nodes_by_id.items():
        if n.get("kind") == "TypeDecl":
            type_nodes[nid] = n.get("attrs", {})

    package_to_types: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
    for tid, attrs in type_nodes.items():
        pkg = attrs.get("package") or "(default)"
        package_to_types.setdefault(pkg, []).append((tid, attrs))

    type_to_package: Dict[str, str] = {
        tid: (attrs.get("package") or "(default)")
        for tid, attrs in type_nodes.items()
    }

    out: List[str] = [
        "@startuml",
        "",
        "' Package diagram — shows physical namespace organisation",
        "' Classifier names only inside packages (no kind keywords, no members)",
        "' Arrows represent inter-package dependencies aggregated from type relationships",
        "",
        "skinparam packageStyle         folder",
        "skinparam classAttributeIconSize 0",
        "skinparam shadowing            false",
        "",
        "skinparam package {",
        "  FontStyle        Bold",
        "  FontSize         12",
        "}",
        "",
    ]

    sorted_pkgs = sorted(
        package_to_types.keys(),
        key=lambda p: (0 if p == "(default)" else 1, p)
    )

    type_name_by_id: Dict[str, str] = {}

    for pkg in sorted_pkgs:
        members = sorted(package_to_types[pkg], key=lambda x: x[1].get("name", ""))
        label = "(default)" if pkg == "(default)" else pkg

        out.append(f'package "{label}" {{')
        for tid, attrs in members:
            name = attrs.get("name", "UnknownType")
            type_name_by_id[tid] = name
            out.append(f'  [{name}]')
        out.append("}")
        out.append("")

    package_deps: Set[Tuple[str, str]] = set()

    for e in edges:
        src, dst, etype = e.get("src"), e.get("dst"), e.get("type")
        if not src or not dst or not etype:
            continue
        if src not in type_nodes or dst not in type_nodes:
            continue
        if etype not in ("ASSOCIATES", "DEPENDS_ON"):
            continue
        src_pkg = type_to_package.get(src)
        dst_pkg = type_to_package.get(dst)
        if src_pkg and dst_pkg and src_pkg != dst_pkg:
            package_deps.add((src_pkg, dst_pkg))

    if package_deps:
        out.append("' Inter-package dependencies")
        for src_pkg, dst_pkg in sorted(package_deps):
            src_label = "(default)" if src_pkg == "(default)" else src_pkg
            dst_label = "(default)" if dst_pkg == "(default)" else dst_pkg
            out.append(f'"{src_label}" ..> "{dst_label}"')

    out.append("")
    out.append("@enduml")
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════════════════
#  SEQUENCE DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════

def generate_sequence_diagram(cir: Dict[str, Any]) -> str:
    nodes_by_id, edges = _index_cir(cir)

    type_attrs: Dict[str, Dict[str, Any]] = {}
    for nid, n in nodes_by_id.items():
        if n.get("kind") == "TypeDecl":
            type_attrs[nid] = n.get("attrs", {})

    if not type_attrs:
        return '@startuml\nnote "No types found in CIR." as N1\n@enduml'

    methods_by_type: Dict[str, List[Dict[str, Any]]] = {t: [] for t in type_attrs}
    method_owner: Dict[str, str] = {}
    for e in edges:
        if e.get("type") == "HAS_METHOD":
            src, dst = e.get("src"), e.get("dst")
            if src in type_attrs and dst in nodes_by_id:
                ma = dict(nodes_by_id[dst].get("attrs", {}))
                ma["_id"] = dst
                methods_by_type[src].append(ma)
                method_owner[dst] = src

    params_by_method: Dict[str, List[Dict[str, Any]]] = {}
    for e in edges:
        if e.get("type") == "PARAM_OF":
            pid, mid = e.get("src"), e.get("dst")
            if pid and mid:
                pnode = nodes_by_id.get(pid)
                if pnode and pnode.get("kind") == "Parameter":
                    params_by_method.setdefault(mid, []).append(pnode.get("attrs", {}))

    method_name_by_id: Dict[str, str] = {}
    for nid, n in nodes_by_id.items():
        if n.get("kind") == "Method":
            method_name_by_id[nid] = n.get("attrs", {}).get("name", "")

    calls_by_src: Dict[str, List[Dict[str, Any]]] = {}
    for e in edges:
        if e.get("type") != "CALLS":
            continue
        src_m, dst_m = e.get("src"), e.get("dst")
        if not src_m or not dst_m:
            continue
        if _is_dunder(method_name_by_id.get(dst_m, "")):
            continue
        order = (e.get("attrs") or {}).get("order", 0)
        calls_by_src.setdefault(src_m, []).append({"dst": dst_m, "order": order})

    associates: Dict[str, List[str]] = {t: [] for t in type_attrs}
    for e in edges:
        if e.get("type") not in ("ASSOCIATES", "DEPENDS_ON"):
            continue
        src, dst = e.get("src"), e.get("dst")
        if src in type_attrs and dst in type_attrs and src != dst:
            if dst not in associates[src]:
                associates[src].append(dst)

    _MODEL_PKG_KW  = {"model", "entity", "domain", "dto", "vo", "bean", "pojo"}
    _TRIVIAL_PFXS  = ("get", "set", "is", "has")
    _TRIVIAL_NAMES = {"tostring", "hashcode", "equals", "clone", "compareto"}

    def _is_model(tid: str) -> bool:
        a   = type_attrs[tid]
        pkg = (a.get("package") or "").lower()
        nm  = (a.get("name")    or "").lower()
        if any(kw in pkg or kw in nm for kw in _MODEL_PKG_KW):
            return True
        ms = [m for m in methods_by_type.get(tid, [])
              if not m.get("is_constructor") and not _is_dunder(m.get("name", ""))]
        if not ms:
            return False
        non_trivial = [m for m in ms
                       if not any(m.get("name", "").startswith(p) for p in _TRIVIAL_PFXS)
                       and m.get("name", "").lower() not in _TRIVIAL_NAMES]
        return len(non_trivial) == 0

    model_types: Set[str] = {t for t in type_attrs if _is_model(t)}
    noise_types: Set[str] = {
        t for t in type_attrs
        if _is_infrastructure_noise(
            type_attrs[t].get("name", ""),
            type_attrs[t].get("package", ""),
        )
    }
    excluded_types: Set[str] = model_types | noise_types

    def layer(tid: str) -> int:
        a = type_attrs[tid]
        return _layer_order(a.get("name", ""), a.get("package", ""))

    incoming: Dict[str, int] = {t: 0 for t in type_attrs}
    for deps in associates.values():
        for d in deps:
            incoming[d] = incoming.get(d, 0) + 1

    def build_chain(start: str, visited: Set[str]) -> List[str]:
        chain = [start]
        visited = visited | {start}
        hops = sorted(
            [d for d in associates.get(start, []) if d not in visited and d not in excluded_types],
            key=layer,
        )
        for hop in hops:
            chain.extend(build_chain(hop, visited | {hop}))
        return chain

    non_model    = [t for t in type_attrs if t not in excluded_types]
    sorted_types = sorted(non_model, key=lambda t: (incoming.get(t, 0), layer(t), type_attrs[t].get("name", "")))

    covered: Set[str] = set()
    chains:  List[List[str]] = []
    for candidate in sorted_types:
        if candidate in covered:
            continue
        chain = build_chain(candidate, set())
        if chain:
            chains.append(chain)
            covered.update(chain)

    seen: Set[str] = set()
    ordered: List[str] = []
    for chain in sorted(chains, key=lambda c: layer(c[0]) if c else 99):
        for tid in chain:
            if tid not in seen:
                seen.add(tid)
                ordered.append(tid)
    for tid in sorted(non_model, key=layer):
        if tid not in seen:
            ordered.append(tid)

    def _participant_keyword(tid: str) -> str:
        a   = type_attrs[tid]
        nm  = (a.get("name")    or "").lower()
        pkg = (a.get("package") or "").lower()
        combined = nm + " " + pkg
        if any(k in combined for k in ("controller", "resource", "endpoint", "rest", "handler", "boundary", "api")):
            return "boundary"
        if any(k in combined for k in ("service", "manager", "interactor", "usecase", "business", "facade")):
            return "control"
        if any(k in combined for k in ("dao", "repository", "repo", "database", "db", "persistence", "store", "gateway")):
            return "database"
        return "participant"

    entry_controllers: List[str] = []
    for tid in ordered:
        if _participant_keyword(tid) == "boundary":
            is_called_internally = any(
                method_owner.get(e.get("dst")) == tid
                for e in edges
                if e.get("type") == "CALLS"
                and method_owner.get(e.get("src")) != tid
                and method_owner.get(e.get("src")) in seen
                and method_owner.get(e.get("src")) not in excluded_types
            )
            if not is_called_internally:
                entry_controllers.append(tid)

    _SKIP_PFXS = ("get", "set", "is", "has")

    def useful_methods(type_id: str, max_count: int = 4) -> List[Dict[str, Any]]:
        result = []
        for m in methods_by_type.get(type_id, []):
            n = m.get("name", "")
            if _is_dunder(n) or m.get("is_constructor"):
                continue
            if m.get("visibility", "public") == "private":
                continue
            if any(n.startswith(p) for p in _SKIP_PFXS) and len(n) <= 12:
                continue
            if n.lower() in _TRIVIAL_NAMES:
                continue
            result.append(m)
        if not result:
            for m in methods_by_type.get(type_id, []):
                n = m.get("name", "")
                if not m.get("is_constructor") and not _is_dunder(n):
                    if m.get("visibility", "public") != "private":
                        result.append(m)
                        if len(result) >= 2:
                            break
        return result[:max_count]

    def _safe_type(raw: str) -> str:
        t = _clean_type_short(raw or "")
        return t.replace("[]", "").strip()

    def fmt_call(method: Dict[str, Any]) -> str:
        name   = method.get("name", "call")
        mid    = method.get("_id", "")
        params = params_by_method.get(mid, [])[:3]
        parts  = []
        for p in params:
            pn = p.get("name", "")
            pt = _safe_type(p.get("raw_type") or p.get("type_name") or "")
            if pn and pt:
                parts.append(pn + ": " + pt)
            elif pn:
                parts.append(pn)
        suffix = ", ..." if len(params_by_method.get(mid, [])) > 3 else ""
        return name + "(" + ", ".join(parts) + suffix + ")"

    def fmt_ret(method: Dict[str, Any]) -> Optional[str]:
        rt = _safe_type(method.get("raw_return_type") or method.get("return_type") or "")
        if not rt or rt.lower() in ("void", "none", "unit"):
            return None
        if rt == "ResponseEntity":
            return "HTTP Response"
        if rt.lower() in ("boolean", "bool"):
            return "boolean"
        if rt.lower() in ("string", "str"):
            return "String"
        return rt

    def _is_list_return(method: Dict[str, Any]) -> bool:
        rt = (method.get("raw_return_type") or method.get("return_type") or "").lower()
        return any(k in rt for k in ("list", "collection", "set", "iterable", "[]", "array"))

    def _is_bool_return(method: Dict[str, Any]) -> bool:
        rt = _safe_type(method.get("raw_return_type") or method.get("return_type") or "")
        return rt.lower() in ("boolean", "bool")

    out: List[str] = [
        "@startuml",
        "",
        "skinparam sequenceArrowThickness 2",
        "skinparam roundcorner 5",
        "skinparam maxmessagesize 250",
        "skinparam responseMessageBelowArrow true",
        "skinparam shadowing false",
        "",
        "autoactivate on",
        "",
    ]

    if not ordered:
        out.append('note "No architectural participants found in CIR." as N1')
        out.append("@enduml")
        return "\n".join(out)

    boundary_names: List[str] = [
        type_attrs[tid].get("name", tid)
        for tid in ordered
        if _participant_keyword(tid) == "boundary"
    ]

    out.append('actor "Client" as Client')
    for tid in ordered:
        nm      = type_attrs[tid].get("name", tid)
        keyword = _participant_keyword(tid)
        out.append(f'{keyword} "{nm}" as {nm}')
    out.append("")

    for ctrl_name in boundary_names:
        out.append(f"Client -> {ctrl_name} : HTTP Request")
        out.append(f"{ctrl_name} --> Client : HTTP Response")
    if boundary_names:
        out.append("")

    has_arrows   = False
    shown:       Set[Tuple[str, str, str]] = set()
    using_calls  = bool(calls_by_src)

    if using_calls:
        call_triples: List[Tuple[int, str, str, Dict[str, Any]]] = []
        for src_m, call_list in calls_by_src.items():
            s_tid = method_owner.get(src_m)
            if not s_tid or s_tid in excluded_types or s_tid not in seen:
                continue
            s_name = type_attrs[s_tid].get("name", s_tid)
            for call in call_list:
                dst_m = call.get("dst")
                if not dst_m:
                    continue
                d_tid = method_owner.get(dst_m)
                if not d_tid or d_tid in excluded_types or d_tid not in seen:
                    continue
                d_name = type_attrs[d_tid].get("name", d_tid)
                dst_nm = method_name_by_id.get(dst_m, "")
                if not dst_nm or _is_dunder(dst_nm) or s_name == d_name:
                    continue
                mn = nodes_by_id.get(dst_m)
                if mn:
                    dummy        = dict(mn.get("attrs", {}))
                    dummy["_id"] = dst_m
                else:
                    dummy = {"name": dst_nm, "_id": dst_m}
                order = call.get("order", 0)
                call_triples.append((order, s_name, d_name, dummy))

        call_triples.sort(key=lambda x: x[0])
        for _, s_name, d_name, dummy in call_triples:
            dst_nm = dummy.get("name", "call")
            key = (s_name, d_name, dst_nm)
            if key in shown:
                continue
            shown.add(key)
            cl      = fmt_call(dummy)
            rl      = fmt_ret(dummy)
            is_list = _is_list_return(dummy)
            is_bool = _is_bool_return(dummy)
            has_arrows = True

            if is_list:
                out.append("loop for each item")
                out.append("  " + s_name + " -> " + d_name + " : " + cl)
                out.append("  " + d_name + " --> " + s_name + " : " + (rl or "void"))
                out.append("end")
            elif is_bool:
                out.append("opt if successful")
                out.append("  " + s_name + " -> " + d_name + " : " + cl)
                out.append("  " + d_name + " --> " + s_name + " : boolean")
                out.append("end")
            else:
                out.append(s_name + " -> " + d_name + " : " + cl)
                out.append(d_name + " --> " + s_name + " : " + (rl or "void"))
        if has_arrows:
            out.append("")

    else:
        first_declared = (
            type_attrs[ordered[0]].get("name", ordered[0]) if ordered else ""
        )
        if first_declared:
            out.append(f'note over {first_declared}')
            out.append('  Messages inferred from class associations')
            out.append('  (no CALLS data in CIR — diagram is approximate)')
            out.append('end note')
            out.append("")

        assoc_pairs: Set[Tuple[str, str]] = set()
        for src, dests in associates.items():
            for dst in dests:
                if src not in excluded_types and dst not in excluded_types:
                    assoc_pairs.add((src, dst))

        emitted: Set[Tuple[str, str]] = set()
        for i in range(len(ordered) - 1):
            c_tid  = ordered[i]
            c_name = type_attrs[c_tid].get("name", c_tid)
            callees = [
                tid for tid in ordered[i + 1:]
                if (c_tid, tid) in assoc_pairs and (c_tid, tid) not in emitted
            ]
            if not callees:
                continue

            for e_tid in callees:
                e_name  = type_attrs[e_tid].get("name", e_tid)
                emitted.add((c_tid, e_tid))
                methods = useful_methods(e_tid, max_count=4)

                if not methods:
                    out.append(c_name + " -> " + e_name + " : request()")
                    out.append(e_name + " --> " + c_name + " : void")
                    has_arrows = True
                    out.append("")
                    continue

                has_arrows = True
                for m in methods:
                    cl      = fmt_call(m)
                    rl      = fmt_ret(m)
                    is_list = _is_list_return(m)
                    is_bool = _is_bool_return(m)
                    shown.add((c_name, e_name, m.get("name", "")))

                    if is_list:
                        out.append("loop for each item")
                        out.append("  " + c_name + " -> " + e_name + " : " + cl)
                        out.append("  " + e_name + " --> " + c_name + " : " + (rl or "void"))
                        out.append("end")
                    elif is_bool:
                        out.append("opt if successful")
                        out.append("  " + c_name + " -> " + e_name + " : " + cl)
                        out.append("  " + e_name + " --> " + c_name + " : boolean")
                        out.append("end")
                    else:
                        out.append(c_name + " -> " + e_name + " : " + cl)
                        out.append(e_name + " --> " + c_name + " : " + (rl or "void"))

                out.append("")

    if not has_arrows:
        first_p = type_attrs[ordered[0]].get("name", ordered[0]) if ordered else "Client"
        out.append(f"note over {first_p}")
        out.append("  No direct method call chains detected.")
        out.append("end note")

    out.append("@enduml")
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════════════════
#  COMPONENT DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════

def generate_component_diagram(cir: Dict[str, Any]) -> str:
    nodes_by_id, edges = _index_cir(cir)

    type_nodes:  Dict[str, Dict[str, Any]] = {}
    package_of:  Dict[str, str] = {}

    for nid, n in nodes_by_id.items():
        if n.get("kind") != "TypeDecl":
            continue
        attrs = n.get("attrs", {})
        nm  = attrs.get("name",    "") or ""
        pkg = attrs.get("package", "") or ""
        if _is_infrastructure_noise(nm, pkg):
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
        combined = (pkg + " " + name).lower()
        for kw, stereo in _LAYERS:
            if kw in combined:
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

    pkg_to_types: Dict[str, List[str]] = {}
    for tid in type_nodes:
        pkg = package_of[tid]
        pkg_to_types.setdefault(pkg, []).append(tid)

    all_pkgs = [p for p in pkg_to_types if p != "(default)"]
    root_prefix = ""
    if len(all_pkgs) > 1:
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
    for src, dst, _ in dep_edges:
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
        label = _arrow_label(package_of[dst_id], type_nodes[dst_id].get("name", ""))
        out.append(f"{src_alias} --> {dst_alias} : {label}")

    out.append("")
    out.append("@enduml")
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════════════════
#  ACTIVITY DIAGRAM
#
#  Shows: method-level control flow derived from CALLS edges (primary source),
#         with a heuristic fallback when no CALLS data is present.
#
#  PlantUML constructs used:
#    - |Swimlane|                                   (one lane per architectural type)
#    - start / stop
#    - :action;                                     (action node)
#    - if (...) then (yes) / else (no) / endif      (boolean-return guard)
#    - repeat / repeat while (...)                  (collection-return loop)
#    - note right / note left                       (parameter hints on decisions)
#
#  Message source priority:
#    1. PRIMARY  — CALLS edges: actual runtime method invocations in call order.
#    2. FALLBACK — method listing heuristic when no CALLS data exists in CIR.
#
#  Does NOT show: fields, inheritance, package structure, interface lollipops.
# ══════════════════════════════════════════════════════════════════════════════

def generate_activity_diagram(cir: Dict[str, Any]) -> str:
    """
    Generate a PlantUML activity diagram from a CIR graph.

    Design decisions for PlantUML compatibility:
    ─────────────────────────────────────────────
    PRIMARY path (CALLS edges present):
      • Uses NO swimlanes. Swimlane switches inside if/repeat blocks crash the
        PlantUML swimlane renderer, and cross-type call chains almost always
        cross lane boundaries inside structured blocks.
      • Instead, action labels are prefixed with the owning type name so the
        reader can still see which component handles each step.
      • boolean-return → if/endif decision diamond
      • collection-return → repeat/repeat while (one-line form, always safe)
      • Deduplicates (src_method, dst_method) pairs.

    FALLBACK path (no CALLS data):
      • Uses swimlanes — one per active type. Each type's methods are listed
        sequentially inside its own lane, so lane boundaries never appear
        inside a structured block.
      • Same boolean / collection heuristics applied.

    Exclusions (both paths):
      • Pure model/POJO types (Student, User) — no behaviour.
      • Util/service/dao types are KEPT (DatabaseUtil, BCryptUtil are actors).
    """
    nodes_by_id, edges = _index_cir(cir)

    # ── 1. Index TypeDecl nodes ─────────────────────────────────────────────
    type_attrs: Dict[str, Dict[str, Any]] = {}
    for nid, n in nodes_by_id.items():
        if n.get("kind") == "TypeDecl":
            type_attrs[nid] = n.get("attrs", {})

    if not type_attrs:
        return "@startuml\nstart\n:No types found in CIR.;\nstop\n@enduml"

    # ── 2. Methods per type + method ownership ──────────────────────────────
    methods_by_type: Dict[str, List[Dict[str, Any]]] = {t: [] for t in type_attrs}
    method_owner: Dict[str, str] = {}
    method_attrs_by_id: Dict[str, Dict[str, Any]] = {}

    for e in edges:
        if e.get("type") == "HAS_METHOD":
            src, dst = e.get("src"), e.get("dst")
            if src in type_attrs and dst in nodes_by_id:
                ma = dict(nodes_by_id[dst].get("attrs", {}))
                ma["_id"] = dst
                methods_by_type[src].append(ma)
                method_owner[dst] = src
                method_attrs_by_id[dst] = ma

    # ── 3. Parameters per method ────────────────────────────────────────────
    params_by_method: Dict[str, List[Dict[str, Any]]] = {}
    for e in edges:
        if e.get("type") == "PARAM_OF":
            pid, mid = e.get("src"), e.get("dst")
            if pid and mid:
                pn = nodes_by_id.get(pid)
                if pn and pn.get("kind") == "Parameter":
                    params_by_method.setdefault(mid, []).append(pn.get("attrs", {}))

    # ── 4. CALLS edges ──────────────────────────────────────────────────────
    calls_by_src: Dict[str, List[Dict[str, Any]]] = {}
    for e in edges:
        if e.get("type") != "CALLS":
            continue
        src_m, dst_m = e.get("src"), e.get("dst")
        if not src_m or not dst_m:
            continue
        dst_nm = (nodes_by_id.get(dst_m) or {}).get("attrs", {}).get("name", "")
        if _is_dunder(dst_nm):
            continue
        order = (e.get("attrs") or {}).get("order", 0)
        calls_by_src.setdefault(src_m, []).append({"dst": dst_m, "order": order})

    for src_m in calls_by_src:
        calls_by_src[src_m].sort(key=lambda x: x.get("order", 0))

    # ── 5. Exclusion: pure model/POJO types only ────────────────────────────
    _MODEL_PKG_KW     = {"model", "entity", "domain", "dto", "vo", "bean", "pojo"}
    _BEHAVIOUR_PKG_KW = {"util", "utils", "helper", "helpers", "service", "services",
                         "manager", "managers", "dao", "repository", "config"}
    _BEHAVIOUR_SFXS   = ("util", "utils", "helper", "helpers", "service", "manager",
                         "dao", "repo", "repository", "config", "factory")
    _TRIVIAL_PFXS     = ("get", "set", "is", "has")
    _TRIVIAL_NAMES    = {"tostring", "hashcode", "equals", "clone", "compareto"}

    def _is_pure_model(tid: str) -> bool:
        a   = type_attrs[tid]
        pkg = (a.get("package") or "").lower()
        nm  = (a.get("name")    or "").lower()
        if any(kw in pkg for kw in _BEHAVIOUR_PKG_KW):
            return False
        if any(nm.endswith(sfx) for sfx in _BEHAVIOUR_SFXS):
            return False
        if any(kw in pkg or kw in nm for kw in _MODEL_PKG_KW):
            return True
        ms = [m for m in methods_by_type.get(tid, [])
              if not m.get("is_constructor") and not _is_dunder(m.get("name", ""))]
        if not ms:
            return False
        non_trivial = [m for m in ms
                       if not any(m.get("name", "").startswith(p) for p in _TRIVIAL_PFXS)
                       and m.get("name", "").lower() not in _TRIVIAL_NAMES]
        return len(non_trivial) == 0

    excluded: Set[str] = {t for t in type_attrs if _is_pure_model(t)}
    active_types = {t: a for t, a in type_attrs.items() if t not in excluded}
    if not active_types:
        active_types = dict(type_attrs)

    sorted_type_ids: List[str] = sorted(
        active_types.keys(),
        key=lambda t: _layer_order(
            active_types[t].get("name", ""),
            active_types[t].get("package", ""),
        ),
    )

    # ── 6. Format helpers ────────────────────────────────────────────────────

    def _safe_label(text: str) -> str:
        """Escape chars that break PlantUML labels: <, >, |"""
        return text.replace("<", "(").replace(">", ")").replace("|", "/")

    def _fmt_action(method_id: str, method_name: str, owner_name: str) -> str:
        params = params_by_method.get(method_id, [])[:2]
        parts: List[str] = []
        for p in params:
            pn = p.get("name", "")
            pt = _clean_type_short(p.get("raw_type") or p.get("type_name") or "")
            if pn and pt:
                parts.append(f"{pn}: {pt}")
            elif pn:
                parts.append(pn)
        suffix = ", ..." if len(params_by_method.get(method_id, [])) > 2 else ""
        raw = f"{owner_name}.{method_name}({', '.join(parts)}{suffix})"
        return _safe_label(raw)

    def _is_list_ret(mid: str) -> bool:
        ma = method_attrs_by_id.get(mid) or {}
        rt = (ma.get("raw_return_type") or ma.get("return_type") or "").lower()
        return any(k in rt for k in ("list", "collection", "set", "iterable", "[]", "array"))

    def _is_bool_ret(mid: str) -> bool:
        ma = method_attrs_by_id.get(mid) or {}
        rt = _clean_type_short(ma.get("raw_return_type") or ma.get("return_type") or "")
        return rt.lower() in ("boolean", "bool")

    # ── 7. Gather active call triples, grouped by caller layer ─────────────
    #
    # Problem with a flat sort-by-order: every caller method resets `order`
    # from 0, so calls from AccountService.createAccount (order 0,1,2…) and
    # AccountService.deposit (order 0,1,2…) interleave arbitrarily when merged
    # into one list and sorted by order value alone.
    #
    # Fix: group callers by their owning type's architectural layer, then sort
    # each group's calls by their local order.  This gives a coherent top-down
    # flow: Controller methods first, Service methods next, Repository last.
    #
    # Within a type, caller methods are sorted by the first order value of any
    # call they make (i.e. the method that fires earliest in the file).

    # Map src_method → (layer, earliest_order) for sorting
    src_layer: Dict[str, Tuple[int, int]] = {}
    for src_m, call_list in calls_by_src.items():
        src_type = method_owner.get(src_m)
        if not src_type or src_type not in active_types:
            continue
        # Skip private callers — Python _ prefix or CIR visibility=private
        src_attrs = method_attrs_by_id.get(src_m) or {}
        src_nm    = src_attrs.get("name", "")
        src_vis   = src_attrs.get("visibility", "public")
        if src_vis == "private":
            continue
        if src_nm.startswith("_") and not src_nm.startswith("__"):
            continue
        layer = _layer_order(
            active_types[src_type].get("name", ""),
            active_types[src_type].get("package", ""),
        )
        earliest = min((c.get("order", 0) for c in call_list), default=0)
        src_layer[src_m] = (layer, earliest)

    # Sort callers: by layer first, then earliest call order
    sorted_callers = sorted(src_layer.keys(), key=lambda m: src_layer[m])

    # Build ordered flat list: for each caller, append its dst calls in order
    all_calls: List[Tuple[int, str, str]] = []
    for src_m in sorted_callers:
        for call in sorted(calls_by_src[src_m], key=lambda c: c.get("order", 0)):
            dst_m = call.get("dst")
            if not dst_m:
                continue
            dst_type = method_owner.get(dst_m)
            if not dst_type or dst_type not in active_types:
                continue
            # Skip private destination methods — either by CIR visibility field
            # or by Python convention (_name prefix means private/internal).
            dst_attrs = method_attrs_by_id.get(dst_m) or {}
            dst_vis   = dst_attrs.get("visibility", "public")
            dst_nm    = dst_attrs.get("name", "")
            if dst_vis == "private":
                continue
            # Python: single underscore prefix = private/protected
            if dst_nm.startswith("_") and not dst_nm.startswith("__"):
                continue
            all_calls.append((src_layer[src_m][0], src_m, dst_m))

    use_primary = bool(all_calls)

    # ── 8. Skinparam header (no swimlane params if using primary/no-lane mode)
    out: List[str] = [
        "@startuml",
        "",
        "skinparam shadowing               false",
        "",
        "start",
        "",
    ]

    if use_primary:
        # ── PRIMARY PATH ─────────────────────────────────────────────────────
        # Emits action nodes with heuristic branching inferred from:
        #   • method name prefixes  (validate/check/exists/verify → guard)
        #   • return type           (Optional/boolean → guard, List → loop)
        #   • call position         (first call in a chain is often a lookup/guard)
        #
        # Branching rules (applied per dst method):
        #   GUARD   — name starts with validate/check/exists/verify/is/has/can/ensure
        #             OR returns boolean/Optional/bool
        #             → if (condition) then (yes) … else (no) :handle error; endif
        #   LOOP    — returns List/Collection/Set/Iterable/array
        #             → repeat … repeat while (more items?) is (yes) -> no;
        #   ACTION  — everything else → plain :action; node
        #
        # Dedup on dst_m: each called method appears at most once.

        # ── helper classifiers ──────────────────────────────────────────────
        _GUARD_PFXS = ("validate", "check", "verify", "ensure", "assert",
                       "exists", "existsby", "is", "has", "can", "allow")
        _FIND_PFXS  = ("find", "get", "load", "fetch", "lookup", "query",
                       "retrieve", "read", "search")

        def _is_guard(mid: str) -> bool:
            """
            Returns True when the method acts as a decision gate:
              - name prefix signals validation / existence check
              - OR returns boolean / Boolean
              - OR returns Optional (findBy… that may come back empty)
            """
            ma    = method_attrs_by_id.get(mid) or {}
            name  = (ma.get("name") or "").lower()
            rt    = _clean_type_short(
                        ma.get("raw_return_type") or ma.get("return_type") or ""
                    ).lower()
            # boolean return always a guard
            if rt in ("boolean", "bool"):
                return True
            # Optional return → potential null path
            if "optional" in rt:
                return True
            # Explicit guard prefix
            if any(name.startswith(p) for p in _GUARD_PFXS):
                return True
            return False

        def _is_loop(mid: str) -> bool:
            ma = method_attrs_by_id.get(mid) or {}
            rt = (ma.get("raw_return_type") or ma.get("return_type") or "").lower()
            return any(k in rt for k in
                       ("list", "collection", "set", "iterable", "[]", "array"))

        def _guard_label(dst_mname: str, mid: str) -> str:
            """Human-readable condition label for the diamond."""
            ma   = method_attrs_by_id.get(mid) or {}
            name = dst_mname  # preserve original casing for regex
            rt   = _clean_type_short(
                       ma.get("raw_return_type") or ma.get("return_type") or ""
                   ).lower()

            if "optional" in rt:
                # findByUsername → "username found?"
                # findByAccountNumber → "accountNumber found?"
                subject = re.sub(
                    r"^(?:findBy|getBy|loadBy|fetchBy|searchBy|"
                    r"find|get|load|fetch|lookup|query|retrieve)",
                    "", name
                ).strip()
                if subject:
                    # split camelCase: AccountNumber → Account Number
                    subject = re.sub(r"([A-Z])", lambda m: " " + m.group(1), subject).strip().lower()
                else:
                    subject = "result"
                return f"{subject} found?"

            # boolean methods: existsByUsername → "username exists?"
            #                  validateInput   → "input valid?"
            #                  checkPassword   → "password correct?"
            #                  isActive        → "active?"
            nl = name.lower()
            # Determine suffix first, then strip prefix keeping remainder
            if nl.startswith("existsby"):
                subject = name[len("existsBy"):]
                suffix  = " exists?"
            elif nl.startswith("exists"):
                subject = name[len("exists"):]
                suffix  = " exists?"
            elif nl.startswith("validateby"):
                subject = name[len("validateBy"):]
                suffix  = " valid?"
            elif nl.startswith("validate"):
                subject = name[len("validate"):]
                suffix  = " valid?"
            elif nl.startswith("verifyby"):
                subject = name[len("verifyBy"):]
                suffix  = " valid?"
            elif nl.startswith("verify"):
                subject = name[len("verify"):]
                suffix  = " valid?"
            elif nl.startswith("checkby"):
                subject = name[len("checkBy"):]
                suffix  = " correct?"
            elif nl.startswith("check"):
                subject = name[len("check"):]
                suffix  = " correct?"
            elif nl.startswith("ensure"):
                subject = name[len("ensure"):]
                suffix  = " satisfied?"
            elif nl.startswith("has"):
                subject = name[len("has"):]
                suffix  = "?"
            elif nl.startswith("is"):
                subject = name[len("is"):]
                suffix  = "?"
            elif nl.startswith("can"):
                subject = name[len("can"):]
                suffix  = "?"
            elif nl.startswith("allow"):
                subject = name[len("allow"):]
                suffix  = " allowed?"
            else:
                subject = name
                suffix  = "?"

            if not subject:
                subject = name
            # camelCase → space-separated lowercase words
            subject = re.sub(r"([A-Z])", lambda m: " " + m.group(1), subject).strip().lower()
            return f"{subject}{suffix}"

        # ── emit loop ───────────────────────────────────────────────────────
        emitted: Set[str] = set()

        for _, src_m, dst_m in all_calls:
            if dst_m in emitted:
                continue
            emitted.add(dst_m)

            dst_type  = method_owner.get(dst_m, "")
            dst_name  = (type_attrs.get(dst_type) or {}).get("name", dst_type)
            dst_mname = (nodes_by_id.get(dst_m) or {}).get("attrs", {}).get("name", "")

            if not dst_mname or _is_dunder(dst_mname):
                continue

            action = _fmt_action(dst_m, dst_mname, dst_name)

            if _is_loop(dst_m):
                # Collection return → process-each loop
                out.append("repeat")
                out.append(f"  :{action};")
                out.append("repeat while (more items?) is (yes) -> no;")

            elif _is_guard(dst_m):
                # Guard / validation → decision diamond
                cond = _safe_label(_guard_label(dst_mname, dst_m))
                out.append(f"if ({cond}) then (yes)")
                out.append(f"  :{action};")
                out.append("else (no)")
                out.append("  :handle error / return;")
                out.append("endif")

            else:
                out.append(f":{action};")

    else:
        # ── FALLBACK PATH ────────────────────────────────────────────────────
        # Swimlanes are safe here because each type's methods stay inside
        # their own lane — no structured blocks cross lane boundaries.
        pass  # no extra skinparams needed for fallback swimlane path

        out.append(":Approximate flow - no call chain data available;")
        out.append("")

        any_emitted = False
        for type_id in sorted_type_ids:
            type_name = active_types[type_id].get("name", type_id)
            lane_name = re.sub(r"[^\w ]", "", type_name).strip() or "System"

            type_methods = [
                m for m in methods_by_type.get(type_id, [])
                if not m.get("is_constructor")
                and not _is_dunder(m.get("name", ""))
                and m.get("visibility", "public") != "private"
                and not any(m.get("name", "").startswith(p) for p in _TRIVIAL_PFXS)
                and m.get("name", "").lower() not in _TRIVIAL_NAMES
            ]
            if not type_methods:
                continue

            out.append(f"|{lane_name}|")
            any_emitted = True

            for m in type_methods[:6]:
                mname  = m.get("name", "method")
                mid    = m.get("_id", "")
                action = _fmt_action(mid, mname, type_name)

                out.append(f":{action};")

        if not any_emitted:
            out.append("|System|")
            out.append(":No public methods found;")

    out.append("")
    out.append("stop")
    out.append("")
    out.append("@enduml")
    return "\n".join(out)