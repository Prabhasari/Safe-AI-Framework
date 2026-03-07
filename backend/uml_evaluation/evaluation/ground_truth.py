# ground_truth.py
# Builds element sets from your CIR JSON so they can be compared
# against PlantUML-extracted sets to compute accuracy metrics.

from typing import Any, Dict, Set


def extract_from_cir(cir: Dict[str, Any]) -> Dict[str, Set[str]]:
    gt = {
        "classes":    set(),
        "fields":     set(),
        "methods":    set(),
        "inherits":   set(),
        "implements": set(),
        "associates": set(),
        "depends_on": set(),
    }

    nodes = cir.get("nodes", [])
    edges = cir.get("edges", [])

    # Build a name lookup: node id → class name
    type_names: Dict[str, str] = {}
    for node in nodes:
        if node.get("kind") == "TypeDecl":
            name = (node.get("attrs") or {}).get("name", node["id"])
            type_names[node["id"]] = name
            gt["classes"].add(name)

    # Walk edges to find fields, methods, and relationships
    node_map = {n["id"]: n for n in nodes}

    for edge in edges:
        etype = edge.get("type", "")
        src   = edge.get("src", "")
        dst   = edge.get("dst", "")

        if etype == "HAS_FIELD" and src in type_names:
            owner      = type_names[src]
            field_node = node_map.get(dst, {})
            fname      = (field_node.get("attrs") or {}).get("name", "")
            if fname:
                gt["fields"].add(f"{owner}.{fname}")

        elif etype == "HAS_METHOD" and src in type_names:
            owner       = type_names[src]
            method_node = node_map.get(dst, {})
            mname       = (method_node.get("attrs") or {}).get("name", "")
            is_ctor     = (method_node.get("attrs") or {}).get("is_constructor", False)
            if mname and not is_ctor:
                gt["methods"].add(f"{owner}.{mname}")

        elif etype == "INHERITS" and src in type_names and dst in type_names:
            gt["inherits"].add(f"{type_names[src]}->{type_names[dst]}")

        elif etype == "IMPLEMENTS" and src in type_names and dst in type_names:
            gt["implements"].add(f"{type_names[src]}->{type_names[dst]}")

        elif etype == "ASSOCIATES" and src in type_names and dst in type_names:
            gt["associates"].add(f"{type_names[src]}->{type_names[dst]}")

        elif etype == "DEPENDS_ON" and src in type_names and dst in type_names:
            gt["depends_on"].add(f"{type_names[src]}->{type_names[dst]}")

    return gt