# # uml-gen-regex/uml_rules.py
# from __future__ import annotations

# import re
# from typing import Dict, Any, List, Set


# # Map CIR visibility to PlantUML symbols
# VISIBILITY_MAP = {
#     "public": "+",
#     "private": "-",
#     "protected": "#",
#     "package": "~",
# }


# def _index_cir(cir: Dict[str, Any]):
#     """
#     Helper: index nodes and edges from CIR debug JSON.
#     cir format:
#     {
#       "nodes": [ { "id": "...", "kind": "TypeDecl", "attrs": {...} }, ... ],
#       "edges": [ { "src": "...", "dst": "...", "type": "HAS_FIELD" }, ... ]
#     }
#     """
#     nodes_by_id: Dict[str, Dict[str, Any]] = {n["id"]: n for n in cir.get("nodes", [])}
#     edges: List[Dict[str, Any]] = cir.get("edges", [])
#     return nodes_by_id, edges


# def _extract_types_and_members(nodes_by_id: Dict[str, Dict[str, Any]],
#                                edges: List[Dict[str, Any]]):
#     """
#     Build convenient indexes:
#       - type_nodes: only TypeDecl nodes
#       - fields_by_type: type_id -> [field attrs]
#       - methods_by_type: type_id -> [method attrs]
#     """
#     type_nodes: Dict[str, Dict[str, Any]] = {}
#     fields_by_type: Dict[str, List[Dict[str, Any]]] = {}
#     methods_by_type: Dict[str, List[Dict[str, Any]]] = {}

#     # collect all TypeDecl nodes
#     for nid, n in nodes_by_id.items():
#         if n["kind"] == "TypeDecl":
#             type_nodes[nid] = n["attrs"]
#             fields_by_type.setdefault(nid, [])
#             methods_by_type.setdefault(nid, [])

#     # Using HAS_FIELD / HAS_METHOD edges, attach fields/methods to classes
#     for e in edges:
#         src = e["src"]
#         dst = e["dst"]
#         etype = e["type"]

#         if etype == "HAS_FIELD" and src in type_nodes:
#             field_node = nodes_by_id[dst]
#             fields_by_type[src].append(field_node["attrs"])

#         if etype == "HAS_METHOD" and src in type_nodes:
#             method_node = nodes_by_id[dst]
#             methods_by_type[src].append(method_node["attrs"])

#     return type_nodes, fields_by_type, methods_by_type


# def _clean_type_for_display(raw_type: str) -> str:
#     """
#     Regex-style helper:
#       - Strip full generics: List<Item> -> List<Item>
#       - Optionally, collapse package names: com.example.Person -> Person
#     You already have type_name in CIR, but this shows the 'regex-style' idea.
#     """
#     if not raw_type:
#         return "void"

#     t = raw_type

#     # remove generic content (keep base) -> List<Item> -> List<>
#     # (If you don't want this, you can change this logic)
#     t = re.sub(r"<.*?>", "<>", t)

#     # shorten fully qualified names: com.example.Person -> Person
#     if "." in t:
#         t = t.split(".")[-1]

#     return t


# def generate_plantuml_from_cir(cir: Dict[str, Any]) -> str:
#     """
#     Main entry point:
#       CIR JSON ({nodes, edges}) -> PlantUML class diagram text.
#     Rule-based, deterministic, with light regex post-processing.
#     """
#     nodes_by_id, edges = _index_cir(cir)

#     type_nodes, fields_by_type, methods_by_type = _extract_types_and_members(
#         nodes_by_id, edges
#     )

#     lines: List[str] = []
#     lines.append("@startuml")
#     lines.append("set namespaceSeparator .")

#     # ---------- Class / interface / enum blocks ----------
#     for type_id, t in type_nodes.items():
#         kind = t.get("kind", "class")  # we don't store kind here, so default
#         # but you *do* have 'kind' on the node kind itself; attrs has: name, package, etc.
#         name = t.get("name", "UnknownType")

#         # If you want to infer kind from attrs, you can add a flag in CIR later.
#         # For now, we treat all as 'class'.
#         header = f"class {name} {{"
#         lines.append(header)

#         # --- fields ---
#         for f in fields_by_type.get(type_id, []):
#             vis = f.get("visibility", "package")
#             vis_symbol = VISIBILITY_MAP.get(vis, "~")

#             field_name = f.get("name", "field")
#             type_name = f.get("type_name") or f.get("raw_type") or "Object"
#             raw_type = f.get("raw_type") or type_name
#             multiplicity = f.get("multiplicity")

#             # regex-style cleanup of raw type for display
#             display_type = _clean_type_for_display(raw_type)

#             if multiplicity and multiplicity not in ("1", ""):
#                 display_type = f"{display_type} [{multiplicity}]"

#             lines.append(f"  {vis_symbol} {field_name} : {display_type}")

#         # --- methods ---
#         for m in methods_by_type.get(type_id, []):
#             vis = m.get("visibility", "package")
#             vis_symbol = VISIBILITY_MAP.get(vis, "~")

#             method_name = m.get("name", "method")
#             is_ctor = m.get("is_constructor", False)

#             # annotate constructors
#             if is_ctor:
#                 display_name = f"<<create>> {method_name}"
#             else:
#                 display_name = method_name

#             return_type = m.get("return_type", "void")
#             raw_ret = m.get("raw_return_type") or return_type

#             display_ret = _clean_type_for_display(raw_ret)

#             # (simple version – we don't print params yet to keep diagram clean)
#             lines.append(f"  {vis_symbol} {display_name}() : {display_ret}")

#         lines.append("}")  # end class

#     # ---------- Relationships ----------
#     relation_set: Set[tuple[str, str, str]] = set()

#     # Build a map: type_id -> display name
#     type_name_by_id = {tid: attrs.get("name", tid) for tid, attrs in type_nodes.items()}

#     for e in edges:
#         src = e["src"]
#         dst = e["dst"]
#         etype = e["type"]

#         if src not in type_nodes or dst not in type_nodes:
#             continue  # only class-to-class relationships

#         src_name = type_name_by_id[src]
#         dst_name = type_name_by_id[dst]

#         if etype == "INHERITS":
#             relation_set.add((src_name, dst_name, "--|>"))
#         elif etype == "IMPLEMENTS":
#             relation_set.add((src_name, dst_name, "..|>"))
#         elif etype == "ASSOCIATES":
#             relation_set.add((src_name, dst_name, "-->"))
#         elif etype == "DEPENDS_ON":
#             relation_set.add((src_name, dst_name, "..>"))

#     for src_name, dst_name, arrow in sorted(relation_set):
#         lines.append(f"{src_name} {arrow} {dst_name}")

#     lines.append("@enduml")
#     return "\n".join(lines)



from __future__ import annotations

import re
from typing import Dict, Any, List, Set


# Map CIR visibility to PlantUML symbols
VISIBILITY_MAP = {
    "public": "+",
    "private": "-",
    "protected": "#",
    "package": "~",
}


def _index_cir(cir: Dict[str, Any]):
    """
    Helper: index nodes and edges from CIR debug JSON.
    cir format:
    {
      "nodes": [ { "id": "...", "kind": "TypeDecl", "attrs": {...} }, ... ],
      "edges": [ { "src": "...", "dst": "...", "type": "HAS_FIELD" }, ... ]
    }
    """
    nodes_by_id: Dict[str, Dict[str, Any]] = {n["id"]: n for n in cir.get("nodes", [])}
    edges: List[Dict[str, Any]] = cir.get("edges", [])
    return nodes_by_id, edges


def _extract_types_and_members(nodes_by_id: Dict[str, Dict[str, Any]],
                               edges: List[Dict[str, Any]]):
    """
    Build convenient indexes:
      - type_nodes: only TypeDecl nodes
      - fields_by_type: type_id -> [field attrs]
      - methods_by_type: type_id -> [method attrs]
    """
    type_nodes: Dict[str, Dict[str, Any]] = {}
    fields_by_type: Dict[str, List[Dict[str, Any]]] = {}
    methods_by_type: Dict[str, List[Dict[str, Any]]] = {}

    # collect all TypeDecl nodes
    for nid, n in nodes_by_id.items():
        if n["kind"] == "TypeDecl":
            type_nodes[nid] = n["attrs"]
            fields_by_type.setdefault(nid, [])
            methods_by_type.setdefault(nid, [])

    # Using HAS_FIELD / HAS_METHOD edges, attach fields/methods to classes
    for e in edges:
        src = e["src"]
        dst = e["dst"]
        etype = e["type"]

        if etype == "HAS_FIELD" and src in type_nodes:
            field_node = nodes_by_id[dst]
            fields_by_type[src].append(field_node["attrs"])

        if etype == "HAS_METHOD" and src in type_nodes:
            method_node = nodes_by_id[dst]
            methods_by_type[src].append(method_node["attrs"])

    return type_nodes, fields_by_type, methods_by_type


def _clean_type_for_display(raw_type: str) -> str:
    """
    Regex-style helper:
      - Simplify generics: java.util.List<com.example.Item> -> List<>
      - Shorten fully qualified names: com.example.Person -> Person
    """
    if not raw_type:
        return "void"

    t = raw_type

    # remove generic content (keep base) -> List<Item> -> List<>
    t = re.sub(r"<.*?>", "<>", t)

    # shorten fully qualified names: com.example.Person -> Person
    if "." in t:
        t = t.split(".")[-1]

    return t


# ======================================================================
#  CLASS DIAGRAM GENERATION (existing behaviour)
# ======================================================================

def generate_class_diagram(cir: Dict[str, Any]) -> str:
    """
    CIR JSON ({nodes, edges}) -> PlantUML class diagram text.
    Rule-based, deterministic, with light regex post-processing.
    """
    nodes_by_id, edges = _index_cir(cir)
    type_nodes, fields_by_type, methods_by_type = _extract_types_and_members(
        nodes_by_id, edges
    )

    lines: List[str] = []
    lines.append("@startuml")
    lines.append("set namespaceSeparator .")

    # ---------- Class / interface / enum blocks ----------
    for type_id, t in type_nodes.items():
        name = t.get("name", "UnknownType")

        # For now we treat everything as 'class'. You can extend later using a 'kind' flag.
        header = f"class {name} {{"
        lines.append(header)

        # --- fields ---
        for f in fields_by_type.get(type_id, []):
            vis = f.get("visibility", "package")
            vis_symbol = VISIBILITY_MAP.get(vis, "~")

            field_name = f.get("name", "field")
            type_name = f.get("type_name") or f.get("raw_type") or "Object"
            raw_type = f.get("raw_type") or type_name
            multiplicity = f.get("multiplicity")

            # regex-style cleanup of raw type for display
            display_type = _clean_type_for_display(raw_type)

            if multiplicity and multiplicity not in ("1", ""):
                display_type = f"{display_type} [{multiplicity}]"

            lines.append(f"  {vis_symbol} {field_name} : {display_type}")

        # --- methods ---
        for m in methods_by_type.get(type_id, []):
            vis = m.get("visibility", "package")
            vis_symbol = VISIBILITY_MAP.get(vis, "~")

            method_name = m.get("name", "method")
            is_ctor = m.get("is_constructor", False)

            # annotate constructors
            if is_ctor:
                display_name = f"<<create>> {method_name}"
            else:
                display_name = method_name

            return_type = m.get("return_type", "void")
            raw_ret = m.get("raw_return_type") or return_type
            display_ret = _clean_type_for_display(raw_ret)

            # (simple version – no param list for now)
            lines.append(f"  {vis_symbol} {display_name}() : {display_ret}")

        lines.append("}")  # end class

    # ---------- Relationships (class-level) ----------
    relation_set: Set[tuple[str, str, str]] = set()

    # Build a map: type_id -> display name
    type_name_by_id = {tid: attrs.get("name", tid) for tid, attrs in type_nodes.items()}

    for e in edges:
        src = e["src"]
        dst = e["dst"]
        etype = e["type"]

        if src not in type_nodes or dst not in type_nodes:
            continue  # only class-to-class relationships

        src_name = type_name_by_id[src]
        dst_name = type_name_by_id[dst]

        if etype == "INHERITS":
            relation_set.add((src_name, dst_name, "--|>"))
        elif etype == "IMPLEMENTS":
            relation_set.add((src_name, dst_name, "..|>"))
        elif etype == "ASSOCIATES":
            relation_set.add((src_name, dst_name, "-->"))
        elif etype == "DEPENDS_ON":
            relation_set.add((src_name, dst_name, "..>"))

    for src_name, dst_name, arrow in sorted(relation_set):
        lines.append(f"{src_name} {arrow} {dst_name}")

    lines.append("@enduml")
    return "\n".join(lines)


# Backwards-compatible wrapper (old name)
def generate_plantuml_from_cir(cir: Dict[str, Any]) -> str:
    """
    Default: class diagram (for backward compatibility).
    """
    return generate_class_diagram(cir)


# ======================================================================
#  PACKAGE DIAGRAM GENERATION (NEW)
# ======================================================================

def generate_package_diagram(cir: Dict[str, Any]) -> str:
    """
    CIR JSON ({nodes, edges}) -> PlantUML package-based class diagram.
    Groups classes by package and shows them inside package blocks.
    Relationships remain at class level (arrows between classes).
    """
    nodes_by_id, edges = _index_cir(cir)

    # Collect type nodes
    type_nodes: Dict[str, Dict[str, Any]] = {}
    for nid, n in nodes_by_id.items():
        if n["kind"] == "TypeDecl":
            type_nodes[nid] = n["attrs"]

    # Group types by package
    package_to_types: Dict[str, List[Dict[str, Any]]] = {}
    for tid, attrs in type_nodes.items():
        pkg = attrs.get("package") or "(default)"
        package_to_types.setdefault(pkg, []).append(attrs)

    lines: List[str] = []
    lines.append("@startuml")
    lines.append("set namespaceSeparator .")

    # ---------- Package blocks ----------
    for pkg, types in package_to_types.items():
        # Use quotes in case package name has dots
        if pkg == "(default)":
            # optional: don't wrap default package in a block, or do a generic one
            for t in types:
                name = t.get("name", "UnknownType")
                lines.append(f"class {name}")
        else:
            lines.append(f'package "{pkg}" {{')
            for t in types:
                name = t.get("name", "UnknownType")
                lines.append(f"  class {name}")
            lines.append("}")  # end package

    # ---------- Relationships (class-level) ----------
    relation_set: Set[tuple[str, str, str]] = set()
    type_name_by_id = {tid: attrs.get("name", tid) for tid, attrs in type_nodes.items()}

    for e in edges:
        src = e["src"]
        dst = e["dst"]
        etype = e["type"]

        if src not in type_nodes or dst not in type_nodes:
            continue

        src_name = type_name_by_id[src]
        dst_name = type_name_by_id[dst]

        if etype == "INHERITS":
            relation_set.add((src_name, dst_name, "--|>"))
        elif etype == "IMPLEMENTS":
            relation_set.add((src_name, dst_name, "..|>"))
        elif etype == "ASSOCIATES":
            relation_set.add((src_name, dst_name, "-->"))
        elif etype == "DEPENDS_ON":
            relation_set.add((src_name, dst_name, "..>"))

    for src_name, dst_name, arrow in sorted(relation_set):
        lines.append(f"{src_name} {arrow} {dst_name}")

    lines.append("@enduml")
    return "\n".join(lines)
