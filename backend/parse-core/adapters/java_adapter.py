import os
import javalang  # type: ignore
from typing import Dict, Any, List, Tuple
from cir.model import TypeDecl, Field, Method, Parameter
from cir.graph import CIRGraph

# ---------------------------------------------------------------------------
# bare-method → synthetic class wrapper
# ---------------------------------------------------------------------------
import re as _re_wrap


def _has_class_declaration(code: str) -> bool:
    """Quick check: does the code contain a class/interface/enum declaration?"""
    return bool(_re_wrap.search(
        r'^\s*(?:public\s+|private\s+|protected\s+|abstract\s+|final\s+)*'
        r'(?:class|interface|enum)\s+\w+',
        code, _re_wrap.MULTILINE,
    ))


def _stem_to_class_name_java(source_file: str | None, fallback: str = "Snippet") -> str:
    if not source_file:
        return fallback
    import os as _os
    stem = _os.path.splitext(_os.path.basename(source_file))[0]
    parts = _re_wrap.sub(r"[-_]", " ", stem)
    parts = _re_wrap.sub(r"([a-z])([A-Z])", r"\1 \2", parts)
    name = "".join(w.capitalize() for w in parts.split())
    return name if name else fallback


def wrap_bare_methods_as_class(
    code: str,
    source_file: str | None = None,
) -> str:
    """
    FIX v2: If code has no class declaration but contains method-like patterns,
    wrap the snippet in a synthetic public class so javalang can parse it.
    Returns code unchanged if it already has a class declaration.
    """
    if _has_class_declaration(code):
        return code

    has_methods = bool(_re_wrap.search(
        r'(?:public|private|protected|static|void|int|String|boolean|double|float|long)'
        r'\s+\w+\s*\(',
        code,
    ))
    if not has_methods:
        return code

    class_name = _stem_to_class_name_java(source_file, fallback="Snippet")

    lines = code.splitlines()
    header: List[str] = []
    body: List[str] = []
    in_body = False
    for line in lines:
        stripped = line.strip()
        if not in_body and (
            stripped.startswith("package ")
            or stripped.startswith("import ")
            or stripped == ""
        ):
            header.append(line)
        else:
            in_body = True
            body.append(line)

    indented = "\n".join("    " + l for l in body)
    header_str = "\n".join(header)
    if header_str:
        header_str += "\n\n"
    return f"{header_str}public class {class_name} {{\n{indented}\n}}"


class JavaAdapter:
    """
    Java → CIRGraph builder.
    Parses one or more Java compilation units, creates nodes for
    classes/fields/methods/parameters, and edges for:
      - HAS_FIELD, HAS_METHOD, PARAM_OF
      - INHERITS, IMPLEMENTS
      - ASSOCIATES, DEPENDS_ON
      - CALLS (ordered, from method bodies)

    Includes:
      - Multi-file (project-level) support
      - Generics & collections (multiplicity heuristics)
      - Constructor detection
      - Modifier flags (static/abstract/final)
      - Safer type resolution for duplicate short names (prefer same package)
      - Association multiplicity carried onto ASSOCIATES edges
      - Ordered call extraction for sequence diagrams
      - Skips invalid Java files during project parsing (collect errors)
    """

    language = "java"

    # ---------------- Helpers ----------------

    COLLECTION_TYPES = {"List", "Set", "Collection", "Map"}

    def _visibility_from_mods(self, mods: set[str] | None) -> str:
        mods = mods or set()
        if "public" in mods:
            return "public"
        if "private" in mods:
            return "private"
        if "protected" in mods:
            return "protected"
        return "package"

    def _flags_from_mods(self, mods: set[str] | None) -> Tuple[bool, bool, bool]:
        """
        Returns (is_static, is_abstract, is_final)
        """
        mods = mods or set()
        return ("static" in mods, "abstract" in mods, "final" in mods)

    def _resolve_type_name_and_multiplicity(self, t) -> Tuple[str, str, None | str]:
        """
        From a javalang Type node, derive:
          - logical_type (e.g. "Item")
          - raw_type (e.g. "List<Item>")
          - multiplicity (e.g. "1", "1..*", "0..*")
        We use simple heuristics for generics and arrays.
        """
        if t is None:
            return "void", "void", None

        base_name = getattr(t, "name", "Object")
        raw_type = base_name
        multiplicity: None | str = None
        logical_type = base_name

        # generics: List<Item>, Set<Order>, Map<K,V>
        args = getattr(t, "arguments", None)
        if args:
            try:
                first_arg = args[0]
                inner_type = getattr(first_arg, "type", first_arg)
                inner_name = getattr(inner_type, "name", None)
                if inner_name:
                    logical_type = inner_name
                    raw_type = f"{base_name}<{inner_name}>"
                    multiplicity = "1..*"  # one-to-many
            except Exception:
                logical_type = base_name
                raw_type = base_name

        # arrays: Type[]
        dims = getattr(t, "dimensions", None)
        if dims:
            multiplicity = multiplicity or "0..*"
            raw_type = f"{raw_type}[]"

        # known collection type but no generic args
        if base_name in self.COLLECTION_TYPES and multiplicity is None:
            multiplicity = "0..*"

        # default multiplicity for single values
        if multiplicity is None and base_name not in self.COLLECTION_TYPES:
            multiplicity = "1"

        return logical_type, raw_type, multiplicity

    # ---------------- Call extraction ----------------

    def _walk_ast_in_order(self, node):
        """
        Pre-order traversal that yields nodes in a stable source-like order.
        """
        if node is None:
            return
        yield node
        children = getattr(node, "children", None)
        if not children:
            return
        for c in children:
            if c is None:
                continue
            if isinstance(c, (list, tuple)):
                for item in c:
                    yield from self._walk_ast_in_order(item)
            else:
                yield from self._walk_ast_in_order(c)

    def _extract_ordered_calls(self, method_or_ctor) -> List[Dict[str, Any]]:
        """
        Extract ordered calls from a method/constructor body.

        Returns list of:
          {
            "qualifier_kind": "none|super|static|new|var",
            "qualifier": str,
            "member": str,
            "order": int
          }
        """
        calls: List[Dict[str, Any]] = []
        body = getattr(method_or_ctor, "body", None)
        if not body:
            return calls

        nodes = body if isinstance(body, list) else [body]
        order = 0

        for stmt in nodes:
            for n in self._walk_ast_in_order(stmt):
                # new ClassName().method()
                if isinstance(n, javalang.tree.ClassCreator):
                    t = getattr(n, "type", None)
                    cname = getattr(t, "name", "") if t else ""
                    if cname:
                        for sel in getattr(n, "selectors", []) or []:
                            if isinstance(sel, javalang.tree.MethodInvocation):
                                calls.append(
                                    {
                                        "qualifier_kind": "new",
                                        "qualifier": cname,
                                        "member": sel.member or "",
                                        "order": order,
                                    }
                                )
                                order += 1

                # obj.method() OR method()
                if isinstance(n, javalang.tree.MethodInvocation):
                    q = n.qualifier or ""
                    kind = "none"
                    if q:
                        kind = "static" if q[:1].isupper() else "var"
                    calls.append(
                        {
                            "qualifier_kind": kind,
                            "qualifier": q,
                            "member": n.member or "",
                            "order": order,
                        }
                    )
                    order += 1

                # super.method()
                if isinstance(n, javalang.tree.SuperMethodInvocation):
                    calls.append(
                        {
                            "qualifier_kind": "super",
                            "qualifier": "super",
                            "member": n.member or "",
                            "order": order,
                        }
                    )
                    order += 1

        return calls

    # ---------------- Parsing entry points ----------------

    def parse_to_ast(self, code: str):
        try:
            return javalang.parse.parse(code)
        except javalang.parser.JavaSyntaxError as e:
            raise ValueError(f"Java syntax error: {e}")
        except Exception as e:
            raise ValueError(f"Failed to parse Java code: {e}")

    def build_cir_graph_for_code(self, code: str, filename: str | None = None) -> CIRGraph:
        """
        Single-compilation-unit helper (for /parse).
        """
        code = wrap_bare_methods_as_class(code, source_file=filename)  # FIX v2
        graph = CIRGraph()
        type_nodes: Dict[str, str] = {}
        units: List[Dict[str, Any]] = []

        self._process_compilation_unit(code, graph, type_nodes, units, source_file=filename)
        self._add_relationship_edges(graph, type_nodes, units)
        return graph

    def build_cir_graph_for_files(self, files: List[str]) -> CIRGraph:
        """
        Multi-file/project-level CIRGraph builder.
        Skips invalid Java files but continues parsing the rest.
        """
        graph = CIRGraph()
        type_nodes: Dict[str, str] = {}
        units: List[Dict[str, Any]] = []

        errors: List[Dict[str, str]] = []

        for path in files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    code = f.read()
                code = wrap_bare_methods_as_class(code, source_file=path)  # FIX v2
                self._process_compilation_unit(code, graph, type_nodes, units, source_file=path)
            except ValueError as e:
                errors.append({"file": path, "error": str(e)})
                continue

        self._add_relationship_edges(graph, type_nodes, units)

        # attach errors so API can return them
        graph.g.graph["parse_errors"] = errors

        return graph

    # ---------------- Core processing ----------------

    def _process_compilation_unit(
        self,
        code: str,
        graph: CIRGraph,
        type_nodes: Dict[str, str],
        units: List[Dict[str, Any]],
        source_file: str | None = None,
    ) -> None:
        tree = self.parse_to_ast(code)
        package_name = getattr(getattr(tree, "package", None), "name", None)

        for t in tree.types:
            short_name = t.name
            full_name = f"{package_name}.{short_name}" if package_name else short_name

            type_id = f"type:{full_name}"
            kind = type(t).__name__.replace("Declaration", "").lower()
            visibility = self._visibility_from_mods(t.modifiers or set())
            _, is_abstract, is_final = self._flags_from_mods(t.modifiers or set())

            type_decl = TypeDecl(
                id=type_id,
                name=short_name,
                kind=kind,
                visibility=visibility,
                package=package_name,
                modifiers=tuple(t.modifiers or []),
                is_abstract=is_abstract,
                is_final=is_final,
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
            }

            if hasattr(t, "extends") and t.extends:
                try:
                    if hasattr(t.extends, "name"):
                        names = [t.extends.name]
                    else:
                        names = [e.name for e in t.extends]
                except Exception:
                    names = []
                unit["extends"] = names

            if hasattr(t, "implements") and t.implements:
                unit["implements"] = [i.name for i in t.implements]

            # ---------- fields ----------
            for field in getattr(t, "fields", []):
                logical_type, raw_type, multiplicity = self._resolve_type_name_and_multiplicity(field.type)
                for decl in field.declarators:
                    field_id = f"field:{full_name}:{decl.name}"
                    visibility_f = self._visibility_from_mods(field.modifiers or set())
                    mods_f = field.modifiers or set()

                    field_node = Field(
                        id=field_id,
                        name=decl.name,
                        type_name=logical_type,
                        raw_type=raw_type,
                        visibility=visibility_f,
                        modifiers=tuple(mods_f),
                        multiplicity=multiplicity,
                    )
                    graph.add_node(field_id, "Field", field_node)
                    graph.add_edge(type_id, field_id, "HAS_FIELD")

                    unit["fields"].append(
                        {
                            "id": field_id,
                            "name": decl.name,
                            "element_type": logical_type,
                            "raw_type": raw_type,
                            "multiplicity": multiplicity,
                        }
                    )

            # ---------- methods ----------
            for method in getattr(t, "methods", []):
                method_id = f"method:{full_name}:{method.name}"
                visibility_m = self._visibility_from_mods(method.modifiers or set())
                mods_m = method.modifiers or set()
                is_static, is_abs, is_final_m = self._flags_from_mods(mods_m)

                logical_ret, raw_ret, _ = self._resolve_type_name_and_multiplicity(method.return_type)

                method_node = Method(
                    id=method_id,
                    name=method.name,
                    return_type=logical_ret,
                    raw_return_type=raw_ret,
                    visibility=visibility_m,
                    modifiers=tuple(mods_m),
                    is_constructor=False,
                    is_static=is_static,
                    is_abstract=is_abs,
                    is_final=is_final_m,
                )
                graph.add_node(method_id, "Method", method_node)
                graph.add_edge(type_id, method_id, "HAS_METHOD")

                param_infos: List[Dict[str, Any]] = []
                for p in method.parameters:
                    p_id = f"param:{full_name}:{method.name}:{p.name}"
                    logical, raw, _ = self._resolve_type_name_and_multiplicity(p.type)
                    param_node = Parameter(
                        id=p_id,
                        name=p.name,
                        type_name=logical,
                        raw_type=raw,
                    )
                    graph.add_node(p_id, "Parameter", param_node)
                    graph.add_edge(p_id, method_id, "PARAM_OF")
                    param_infos.append({"id": p_id, "name": p.name, "type_name": logical})

                extracted = self._extract_ordered_calls(method)
                for c in extracted:
                    unit["calls"].append({"src_method_id": method_id, **c})

                unit["methods"].append(
                    {
                        "id": method_id,
                        "name": method.name,
                        "return_type": logical_ret,
                        "params": param_infos,
                    }
                )

            # ---------- constructors ----------
            for ctor in getattr(t, "constructors", []):
                ctor_id = f"ctor:{full_name}:{ctor.name}"
                visibility_c = self._visibility_from_mods(ctor.modifiers or set())
                mods_c = ctor.modifiers or set()
                is_static, is_abs, is_final_c = self._flags_from_mods(mods_c)

                method_node = Method(
                    id=ctor_id,
                    name=ctor.name,
                    return_type="void",
                    raw_return_type="<constructor>",
                    visibility=visibility_c,
                    modifiers=tuple(mods_c),
                    is_constructor=True,
                    is_static=is_static,
                    is_abstract=is_abs,
                    is_final=is_final_c,
                )
                graph.add_node(ctor_id, "Method", method_node)
                graph.add_edge(type_id, ctor_id, "HAS_METHOD")

                param_infos: List[Dict[str, Any]] = []
                for p in ctor.parameters:
                    p_id = f"param:{full_name}:{ctor.name}:{p.name}"
                    logical, raw, _ = self._resolve_type_name_and_multiplicity(p.type)
                    param_node = Parameter(
                        id=p_id,
                        name=p.name,
                        type_name=logical,
                        raw_type=raw,
                    )
                    graph.add_node(p_id, "Parameter", param_node)
                    graph.add_edge(p_id, ctor_id, "PARAM_OF")
                    param_infos.append({"id": p_id, "name": p.name, "type_name": logical})

                extracted = self._extract_ordered_calls(ctor)
                for c in extracted:
                    unit["calls"].append({"src_method_id": ctor_id, **c})

                unit["methods"].append(
                    {
                        "id": ctor_id,
                        "name": ctor.name,
                        "return_type": "void",
                        "params": param_infos,
                    }
                )

            units.append(unit)

    def _add_relationship_edges(
        self,
        graph: CIRGraph,
        type_nodes: Dict[str, str],
        units: List[Dict[str, Any]],
    ) -> None:
        # full name -> type node id
        full_to_id: Dict[str, str] = dict(type_nodes)

        # short name -> list of candidate ids
        short_to_ids: Dict[str, List[str]] = {}
        # type id -> full name
        id_to_full: Dict[str, str] = {}

        for full_name, nid in type_nodes.items():
            id_to_full[nid] = full_name
            short_name = full_name.split(".")[-1]
            short_to_ids.setdefault(short_name, []).append(nid)

        def _pkg(full_name: str) -> str:
            parts = full_name.split(".")
            return ".".join(parts[:-1]) if len(parts) > 1 else ""

        def resolve_type_name(tname: str, src_id: str) -> str | None:
            if tname in full_to_id:
                return full_to_id[tname]

            candidates = short_to_ids.get(tname)
            if not candidates:
                return None
            if len(candidates) == 1:
                return candidates[0]

            src_full = id_to_full.get(src_id, "")
            src_pkg = _pkg(src_full)

            same_pkg = []
            for cid in candidates:
                c_full = id_to_full.get(cid, "")
                if _pkg(c_full) == src_pkg:
                    same_pkg.append(cid)

            if len(same_pkg) == 1:
                return same_pkg[0]

            return None

        # method lookup: (type_id, method_name) -> method_id
        method_index: Dict[tuple[str, str], str] = {}
        for u in units:
            owner_type_id = u["id"]
            for m in u.get("methods", []):
                mid = m.get("id")
                mname = m.get("name")
                if mid and mname:
                    method_index[(owner_type_id, mname)] = mid

        for u in units:
            src_id = u["id"]

            # ---------- INHERITS / IMPLEMENTS ----------
            for base in u.get("extends", []):
                target = resolve_type_name(base, src_id)
                if target and target != src_id:
                    graph.add_edge(src_id, target, "INHERITS")

            for iface in u.get("implements", []):
                target = resolve_type_name(iface, src_id)
                if target and target != src_id:
                    graph.add_edge(src_id, target, "IMPLEMENTS")

            # ---------- ASSOCIATES ----------
            for f in u.get("fields", []):
                tname = f.get("element_type")
                mult = f.get("multiplicity")
                if not tname:
                    continue
                target = resolve_type_name(tname, src_id)
                if target and target != src_id:
                    graph.add_edge(src_id, target, "ASSOCIATES", multiplicity=mult)

            # ---------- DEPENDS_ON ----------
            for m in u.get("methods", []):
                for p in m.get("params", []):
                    tname = p.get("type_name")
                    if not tname:
                        continue
                    target = resolve_type_name(tname, src_id)
                    if target and target != src_id:
                        graph.add_edge(src_id, target, "DEPENDS_ON")

                rtype = m.get("return_type")
                if rtype:
                    target = resolve_type_name(rtype, src_id)
                    if target and target != src_id:
                        graph.add_edge(src_id, target, "DEPENDS_ON")

            # ---------- CALLS ----------
            field_type_by_name: Dict[str, str] = {}
            for f in u.get("fields", []):
                fname = f.get("name")
                ftype = f.get("element_type")
                if fname and ftype:
                    field_type_by_name[fname] = ftype

            method_param_types: Dict[str, Dict[str, str]] = {}
            for m in u.get("methods", []):
                mid = m.get("id")
                if not mid:
                    continue
                pm: Dict[str, str] = {}
                for p in m.get("params", []):
                    pname = p.get("name")
                    ptype = p.get("type_name")
                    if pname and ptype:
                        pm[pname] = ptype
                method_param_types[mid] = pm

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
                    target_type_id = src_id

                elif qkind in ("static", "new"):
                    tid = resolve_type_name(qual, src_id)
                    if not tid:
                        continue
                    target_type_id = tid

                elif qkind == "var":
                    var_type = field_type_by_name.get(qual)
                    if not var_type:
                        var_type = method_param_types.get(src_method_id, {}).get(qual)
                    if not var_type:
                        continue
                    tid = resolve_type_name(var_type, src_id)
                    if not tid:
                        continue
                    target_type_id = tid

                dst_method_id = method_index.get((target_type_id, member))
                if not dst_method_id:
                    continue

                graph.add_edge(src_method_id, dst_method_id, "CALLS", order=order)
