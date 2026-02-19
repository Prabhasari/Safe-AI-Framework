# backend/uml-gen-ai/summarize_cir.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple, DefaultDict, Set, Optional
from collections import defaultdict
import re


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    s = str(x)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_getter_setter(method_name: str) -> bool:
    if not method_name:
        return False
    return (
        (method_name.startswith("get") and len(method_name) > 3)
        or (method_name.startswith("set") and len(method_name) > 3)
        or (method_name.startswith("is") and len(method_name) > 2)
    )


def _looks_like_logger(field_name: str, field_type: str) -> bool:
    n = (field_name or "").lower()
    t = (field_type or "").lower()
    return (
        "logger" in n
        or n == "log"
        or "org.slf4j" in t
        or t.endswith("logger")
        or t.endswith("log")
    )


def _resolve_owner_from_candidates(candidates: List[Any], type_names: Dict[str, str]) -> str:
    """
    Given a list of candidate owner references, return a TypeDecl node id if possible.
    """
    cands = [_safe_str(c) for c in candidates if c is not None]
    cands = [c for c in cands if c]

    # 1) direct id match
    for c in cands:
        if c in type_names:
            return c

    # 2) convert FQN -> "type:FQN"
    for c in cands:
        if c.startswith("type:") and c in type_names:
            return c
        type_id = f"type:{c}"
        if type_id in type_names:
            return type_id

    # 3) name match (class name only)
    for c in cands:
        for tid, tname in type_names.items():
            if tname == c:
                return tid

    return ""


def _resolve_owner(node: Dict[str, Any], type_names: Dict[str, str]) -> str:
    """
    Try multiple common owner keys from BOTH:
      - node top-level
      - node.attrs
    """
    attrs: Dict[str, Any] = node.get("attrs") or {}

    candidates = [
        # top-level possibilities
        node.get("owner"),
        node.get("ownerId"),
        node.get("parent"),
        node.get("parentId"),
        node.get("declaringType"),
        node.get("declaringTypeId"),
        node.get("typeId"),
        node.get("container"),
        node.get("containerId"),
        node.get("classId"),
        node.get("class"),
        node.get("inType"),
        # attrs possibilities
        attrs.get("owner"),
        attrs.get("ownerId"),
        attrs.get("declaringType"),
        attrs.get("declaring_type"),
        attrs.get("declaringTypeId"),
        attrs.get("parent"),
        attrs.get("parentId"),
        attrs.get("typeId"),
        attrs.get("type"),
        attrs.get("container"),
        attrs.get("containerId"),
        attrs.get("classId"),
        attrs.get("class"),
        attrs.get("inType"),
    ]

    return _resolve_owner_from_candidates(candidates, type_names)


def _build_edge_maps(edges: List[Dict[str, Any]]) -> Tuple[DefaultDict[str, List[Tuple[str, str]]], DefaultDict[str, List[Tuple[str, str]]]]:
    """
    Returns:
      outgoing[src] = [(etype, dst), ...]
      incoming[dst] = [(etype, src), ...]
    """
    outgoing: DefaultDict[str, List[Tuple[str, str]]] = defaultdict(list)
    incoming: DefaultDict[str, List[Tuple[str, str]]] = defaultdict(list)

    for e in edges or []:
        src = e.get("src")
        dst = e.get("dst")
        etype = e.get("type")
        if not src or not dst or not etype:
            continue
        src = _safe_str(src)
        dst = _safe_str(dst)
        etype = _safe_str(etype)
        if not src or not dst or not etype:
            continue
        outgoing[src].append((etype, dst))
        incoming[dst].append((etype, src))

    return outgoing, incoming


def _guess_owner_from_edges(
    member_id: str,
    incoming: DefaultDict[str, List[Tuple[str, str]]],
    type_names: Dict[str, str],
) -> str:
    """
    If member has no owner key, sometimes there is an edge:
      TypeDecl -(DECLARES|HAS_FIELD|HAS_METHOD|CONTAINS)-> Member
    We look at incoming edges of the member and choose a TypeDecl src.
    """
    for etype, src in incoming.get(member_id, []):
        if src in type_names:
            # accept only plausible containment edge types; if unknown, still allow as fallback
            if etype.upper() in {"DECLARES", "CONTAINS", "HAS_FIELD", "HAS_METHOD", "HAS_MEMBER", "OWNS"}:
                return src

    # fallback: any incoming from a TypeDecl
    for _, src in incoming.get(member_id, []):
        if src in type_names:
            return src

    return ""


def _collect_method_params(
    method_node_id: str,
    nodes_by_id: Dict[str, Dict[str, Any]],
    outgoing: DefaultDict[str, List[Tuple[str, str]]],
    incoming: DefaultDict[str, List[Tuple[str, str]]],
) -> List[str]:
    """
    Try to collect parameters for a method node using:
      - method.attrs.params / method.attrs.parameters
      - edges Method -> Parameter (or Parameter -> Method)
      - Parameter nodes attrs {name,type}
    Returns list like ["id: int", "name: String"]
    """
    m = nodes_by_id.get(method_node_id) or {}
    attrs = m.get("attrs") or {}

    # 1) direct params list
    params = attrs.get("params") or attrs.get("parameters")
    if isinstance(params, list) and params:
        out: List[str] = []
        for p in params[:10]:
            if isinstance(p, dict):
                pn = _safe_str(p.get("name"))
                pt = _safe_str(p.get("type"))
                if pn and pt:
                    out.append(f"{pn}: {pt}")
                elif pt:
                    out.append(pt)
                elif pn:
                    out.append(pn)
            else:
                s = _safe_str(p)
                if s:
                    out.append(s)
        return out

    # 2) edge-based parameter nodes
    param_ids: List[str] = []

    # outgoing edges from method to something
    for etype, dst in outgoing.get(method_node_id, []):
        if etype.upper() in {"HAS_PARAM", "PARAM", "HAS_PARAMETER", "DECLARES_PARAM", "CONTAINS"}:
            param_ids.append(dst)

    # incoming edges into method from something
    for etype, src in incoming.get(method_node_id, []):
        if etype.upper() in {"HAS_PARAM", "PARAM", "HAS_PARAMETER", "DECLARES_PARAM"}:
            param_ids.append(src)

    # de-dup preserving order
    seen: Set[str] = set()
    param_ids = [pid for pid in param_ids if not (pid in seen or seen.add(pid))]

    rendered: List[str] = []
    for pid in param_ids[:10]:
        pn = nodes_by_id.get(pid)
        if not pn:
            continue
        if pn.get("kind") not in ("Parameter", "Param", "MethodParam"):
            continue
        pattrs = pn.get("attrs") or {}
        name = _safe_str(pattrs.get("name"))
        ptype = _safe_str(pattrs.get("type")) or _safe_str(pattrs.get("paramType"))
        if name and ptype:
            rendered.append(f"{name}: {ptype}")
        elif ptype:
            rendered.append(ptype)
        elif name:
            rendered.append(name)

    return rendered


def summarize_cir_for_llm(cir: Dict[str, Any], diagram_type: str) -> str:
    """
    CIR -> deterministic LLM summary.

    Supports:
      - TypeDecl nodes
      - Field / Method / Parameter nodes (your CIR)
      - FieldDecl / MethodDecl alternative schema
    Also tries owner via:
      - explicit keys (top-level + attrs)
      - containment edges (TypeDecl -> Field/Method)
    """
    nodes: List[Dict[str, Any]] = cir.get("nodes", []) or []
    edges: List[Dict[str, Any]] = cir.get("edges", []) or []

    nodes_by_id: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        nid = _safe_str(n.get("id"))
        if nid:
            nodes_by_id[nid] = n

    outgoing, incoming = _build_edge_maps(edges)

    # -----------------------------
    # 1) Index types
    # -----------------------------
    type_names: Dict[str, str] = {}
    packages: Dict[str, str] = {}

    for n in nodes:
        if n.get("kind") != "TypeDecl":
            continue
        nid = _safe_str(n.get("id"))
        attrs = n.get("attrs") or {}
        if not nid:
            continue
        type_names[nid] = _safe_str(attrs.get("name", nid)) or nid
        packages[nid] = _safe_str(attrs.get("package")) or "(default)"

    include_members = diagram_type.lower() in ("class", "class diagram", "class_diagram")

    # -----------------------------
    # 2) Collect members
    # -----------------------------
    fields_by_type: DefaultDict[str, List[str]] = defaultdict(list)
    methods_by_type: DefaultDict[str, List[str]] = defaultdict(list)

    if include_members:
        for n in nodes:
            kind = n.get("kind")
            nid = _safe_str(n.get("id"))
            attrs = n.get("attrs") or {}

            # Support both schemas
            is_field = kind in ("FieldDecl", "Field")
            is_method = kind in ("MethodDecl", "Method")

            if not (is_field or is_method):
                continue

            # 2.1 owner from keys
            owner = _resolve_owner(n, type_names)

            # 2.2 owner fallback: edges
            if not owner and nid:
                owner = _guess_owner_from_edges(nid, incoming, type_names)

            if not owner:
                continue

            if is_field:
                fname = _safe_str(attrs.get("name"))
                ftype = _safe_str(attrs.get("type")) or _safe_str(attrs.get("fieldType"))
                vis = _safe_str(attrs.get("visibility"))  # public/private/protected (if available)
                static_flag = bool(attrs.get("static"))
                final_flag = bool(attrs.get("final"))

                if not fname:
                    continue
                if _looks_like_logger(fname, ftype):
                    continue

                mods: List[str] = []
                if vis:
                    mods.append(vis)
                if static_flag:
                    mods.append("static")
                if final_flag:
                    mods.append("final")

                mod_str = " ".join(mods).strip()
                if mod_str:
                    mod_str += " "

                if ftype:
                    fields_by_type[owner].append(f"{mod_str}{fname}: {ftype}")
                else:
                    fields_by_type[owner].append(f"{mod_str}{fname}")

            if is_method:
                mname = _safe_str(attrs.get("name"))
                if not mname:
                    continue
                if _is_getter_setter(mname):
                    continue

                vis = _safe_str(attrs.get("visibility"))
                static_flag = bool(attrs.get("static"))
                rtype = _safe_str(attrs.get("returnType")) or _safe_str(attrs.get("type"))
                sig = _safe_str(attrs.get("signature"))

                mods: List[str] = []
                if vis:
                    mods.append(vis)
                if static_flag:
                    mods.append("static")
                mod_str = " ".join(mods).strip()
                if mod_str:
                    mod_str += " "

                if sig:
                    methods_by_type[owner].append(f"{mod_str}{sig}")
                else:
                    params_rendered = _collect_method_params(nid, nodes_by_id, outgoing, incoming) if nid else []
                    param_str = ", ".join(params_rendered)
                    if rtype:
                        methods_by_type[owner].append(f"{mod_str}{mname}({param_str}): {rtype}")
                    else:
                        methods_by_type[owner].append(f"{mod_str}{mname}({param_str})")

    # caps to keep prompt small
    MAX_FIELDS_PER_TYPE = 12
    MAX_METHODS_PER_TYPE = 14

    # -----------------------------
    # 3) Relationships between types
    # -----------------------------
    rels: List[Tuple[str, str, str]] = []
    for e in edges:
        src = _safe_str(e.get("src"))
        dst = _safe_str(e.get("dst"))
        etype = _safe_str(e.get("type"))
        if not src or not dst or not etype:
            continue
        if src not in type_names or dst not in type_names:
            continue
        rels.append((etype, type_names[src], type_names[dst]))

    rels = rels[:250]

    # -----------------------------
    # 4) Compose summary
    # -----------------------------
    lines: List[str] = []
    lines.append("CIR SUMMARY")
    lines.append(f"DIAGRAM_TYPE: {diagram_type}")
    lines.append("")
    lines.append("TYPES:")

    type_items = sorted(type_names.items(), key=lambda kv: (packages.get(kv[0], ""), kv[1]))
    for tid, name in type_items:
        pkg = packages.get(tid, "(default)")
        lines.append(f"- {name} (package: {pkg})")

        if include_members:
            flds = (fields_by_type.get(tid, []) or [])[:MAX_FIELDS_PER_TYPE]
            mths = (methods_by_type.get(tid, []) or [])[:MAX_METHODS_PER_TYPE]

            if flds:
                lines.append("  FIELDS:")
                for f in flds:
                    lines.append(f"  - {f}")
            if mths:
                lines.append("  METHODS:")
                for m in mths:
                    lines.append(f"  - {m}")

    lines.append("")
    lines.append("RELATIONSHIPS (etype: src -> dst):")
    for etype, src_name, dst_name in rels:
        lines.append(f"- {etype}: {src_name} -> {dst_name}")

    return "\n".join(lines)
