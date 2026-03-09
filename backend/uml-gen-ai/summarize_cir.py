# backend/uml-gen-ai/summarize_cir.py
"""
CIR  →  deterministic LLM context string.

Supports the node schema produced by python_adapter.py and JavaAdapter:

  TypeDecl  attrs: name, kind, package, visibility, is_abstract, is_final, modifiers
  Field     attrs: name, type_name, raw_type, visibility, multiplicity, modifiers
  Method    attrs: name, return_type, raw_return_type, visibility,
                   is_constructor, is_static, is_abstract, modifiers
  Parameter attrs: name, type_name, raw_type

Edges used:
  HAS_FIELD     TypeDecl → Field
  HAS_METHOD    TypeDecl → Method
  PARAM_OF      Parameter → Method      (reverse: method is dst)
  INHERITS      TypeDecl → TypeDecl
  IMPLEMENTS    TypeDecl → TypeDecl
  ASSOCIATES    TypeDecl → TypeDecl
  DEPENDS_ON    TypeDecl → TypeDecl
  CALLS         Method   → Method       (ordered by 'order' attr)
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, Set, Tuple

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _s(x: Any) -> str:
    if x is None:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()


def _bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, str):
        return x.lower() in ("true", "1", "yes")
    return bool(x)


_VIS_SYMBOL: Dict[str, str] = {
    "public":    "+",
    "protected": "#",
    "private":   "-",
    "package":   "~",
    "":          "+",
}


def _vis_symbol(vis: str) -> str:
    return _VIS_SYMBOL.get(vis.lower().strip(), "+")


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _clean_type(raw: str) -> str:
    if not raw:
        return "void"
    base = raw.split("[")[0].split("<")[0]
    if "." in base:
        short = base.rsplit(".", 1)[1]
        raw = raw[len(base) - len(short):]
    return raw


def _clean_type_short(raw: str) -> str:
    if not raw:
        return ""
    t = re.sub(r"<.*?>", "", raw)
    if "." in t:
        t = t.rsplit(".", 1)[1]
    return t.strip()


# ─────────────────────────────────────────────────────────────────────────────
#  Edge map builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_edge_maps(
    edges: List[Dict[str, Any]],
) -> Tuple[DefaultDict[str, List[Tuple[str, str]]], DefaultDict[str, List[Tuple[str, str]]]]:
    outgoing: DefaultDict[str, List[Tuple[str, str]]] = defaultdict(list)
    incoming: DefaultDict[str, List[Tuple[str, str]]] = defaultdict(list)
    for e in edges or []:
        src   = _s(e.get("src"))
        dst   = _s(e.get("dst"))
        etype = _s(e.get("type"))
        if src and dst and etype:
            outgoing[src].append((etype, dst))
            incoming[dst].append((etype, src))
    return outgoing, incoming


# ─────────────────────────────────────────────────────────────────────────────
#  Attribute reader
# ─────────────────────────────────────────────────────────────────────────────

def _get(node: Dict[str, Any], *keys: str, default: str = "") -> str:
    attrs = node.get("attrs") or {}
    for k in keys:
        v = node.get(k) or attrs.get(k)
        if v is not None:
            s = _s(v)
            if s:
                return s
    return default


def _get_bool(node: Dict[str, Any], *keys: str) -> bool:
    attrs = node.get("attrs") or {}
    for k in keys:
        v = node.get(k)
        if v is None:
            v = attrs.get(k)
        if v is not None:
            return _bool(v)
    return False


def _get_mods(node: Dict[str, Any]) -> Tuple[str, ...]:
    attrs = node.get("attrs") or {}
    for k in ("modifiers",):
        v = node.get(k) or attrs.get(k)
        if v:
            if isinstance(v, (list, tuple)):
                return tuple(_s(m) for m in v if _s(m))
            if isinstance(v, str) and v.strip():
                return (v.strip(),)
    return ()


# ─────────────────────────────────────────────────────────────────────────────
#  Architecture layer ordering
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
#  Infrastructure noise filter  (shared with uml_rules.py logic)
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
#  Model / POJO detection
# ─────────────────────────────────────────────────────────────────────────────

_MODEL_PKG_KW     = {"model", "entity", "domain", "dto", "vo", "bean", "pojo"}
_BEHAVIOUR_PKG_KW = {"util", "utils", "helper", "helpers", "service", "services",
                     "manager", "managers", "dao", "repository", "config"}
_BEHAVIOUR_SFXS   = ("util", "utils", "helper", "helpers", "service", "manager",
                     "dao", "repo", "repository", "config", "factory")
_TRIVIAL_PFXS     = ("get", "set", "is", "has")
_TRIVIAL_NAMES    = {"tostring", "hashcode", "equals", "clone", "compareto"}


def _is_pure_model(name: str, pkg: str, methods: List[Dict[str, Any]]) -> bool:
    nm  = (name or "").lower()
    pkg = (pkg  or "").lower()
    if any(kw in pkg for kw in _BEHAVIOUR_PKG_KW):
        return False
    if any(nm.endswith(sfx) for sfx in _BEHAVIOUR_SFXS):
        return False
    if any(kw in pkg or kw in nm for kw in _MODEL_PKG_KW):
        return True
    ms = [m for m in methods if not m.get("is_constructor") and not _is_dunder(m.get("name", ""))]
    if not ms:
        return False
    non_trivial = [m for m in ms
                   if not any(m.get("name", "").startswith(p) for p in _TRIVIAL_PFXS)
                   and m.get("name", "").lower() not in _TRIVIAL_NAMES]
    return len(non_trivial) == 0


# ─────────────────────────────────────────────────────────────────────────────
#  Diagram-specific summarizers
# ─────────────────────────────────────────────────────────────────────────────

def _summarize_package(
    type_info: Dict[str, Any],
    type_names: Dict[str, str],
    edges: List[Dict[str, Any]],
) -> str:
    from collections import defaultdict as _dd
    lines = ["PACKAGE DIAGRAM CONTEXT", ""]

    pkg_to_types: Dict[str, list] = _dd(list)
    for type_id, tnode in type_info.items():
        tname = type_names[type_id]
        pkg   = _get(tnode, "package", default="(default)")
        attrs = tnode.get("attrs") or tnode
        kind  = (attrs.get("kind") or "class").lower()
        pkg_to_types[pkg].append((tname, kind))

    lines.append("PACKAGES (full FQN label, type keyword + name only, NO bodies, NO brackets):")
    lines.append("")
    for pkg in sorted(pkg_to_types.keys()):
        label = "(default)" if pkg == "(default)" else pkg
        lines.append(f'package "{label}" {{')
        for tname, kind in sorted(pkg_to_types[pkg], key=lambda x: x[0]):
            if kind == "interface":
                lines.append(f"  interface {tname}")
            elif kind in ("abstract class", "abstract"):
                lines.append(f"  abstract class {tname}")
            elif kind == "enum":
                lines.append(f"  enum {tname}")
            else:
                lines.append(f"  class {tname}")
        lines.append("}")
        lines.append("")

    lines.append("RELATIONSHIP ARROWS (ALL go after all package blocks, never inside):")
    lines.append("  --|>  inheritance    ..|>  implementation    -->  association    ..>  dependency")
    lines.append("")

    seen: set = set()
    type_name_map = {tid: type_names[tid] for tid in type_info}
    for e in edges:
        etype = _s(e.get("type"))
        src   = _s(e.get("src"))
        dst   = _s(e.get("dst"))
        if src not in type_info or dst not in type_info:
            continue
        sn, dn = type_name_map[src], type_name_map[dst]
        key = (sn, dn, etype)
        if key in seen:
            continue
        seen.add(key)
        if etype == "INHERITS":
            lines.append(f"{sn} --|> {dn}")
        elif etype == "IMPLEMENTS":
            lines.append(f"{sn} ..|> {dn}")
        elif etype == "ASSOCIATES":
            lines.append(f"{sn} --> {dn}")
        elif etype == "DEPENDS_ON":
            lines.append(f"{sn} ..> {dn}")

    return "\n".join(lines)


def _summarize_component(
    type_info: Dict[str, Any],
    type_names: Dict[str, str],
    edges: List[Dict[str, Any]],
    outgoing: Any,
    nodes_by_id: Dict[str, Any],
) -> str:
    import re as _re
    from collections import defaultdict as _dd

    _STEREO_MAP = [
        ("controller", "<<Controller>>"), ("resource",   "<<Controller>>"),
        ("endpoint",   "<<Controller>>"), ("rest",       "<<Controller>>"),
        ("handler",    "<<Controller>>"), ("service",    "<<Service>>"),
        ("manager",    "<<Service>>"),    ("facade",     "<<Service>>"),
        ("repository", "<<Repository>>"), ("dao",        "<<Repository>>"),
        ("repo",       "<<Repository>>"), ("database",   "<<Database>>"),
        ("db",         "<<Database>>"),   ("model",      "<<Model>>"),
        ("entity",     "<<Model>>"),      ("domain",     "<<Model>>"),
        ("dto",        "<<DTO>>"),        ("util",       "<<Utility>>"),
        ("helper",     "<<Utility>>"),    ("config",     "<<Config>>"),
        ("security",   "<<Security>>"),   ("filter",     "<<Security>>"),
    ]

    def _stereo(pkg: str, name: str) -> str:
        combined = (pkg + " " + name).lower()
        for kw, s in _STEREO_MAP:
            if kw in combined:
                return s
        return ""

    def _arrow_label(dst_pkg: str, dst_name: str) -> str:
        combined = (dst_pkg + " " + dst_name).lower()
        if "database" in combined or "db" in combined:
            return "queries"
        if "model" in combined or "entity" in combined or "dto" in combined:
            return "maps"
        if "dao" in combined or "repository" in combined or "repo" in combined:
            return "delegates"
        return "uses"

    def _alias(tid: str) -> str:
        return "t_" + _re.sub(r"[^a-zA-Z0-9]", "_", type_names.get(tid, tid))

    def _ialias(tid: str) -> str:
        return "I_t_" + _re.sub(r"[^a-zA-Z0-9]", "_", type_names.get(tid, tid))

    called: set = set()
    dep_edges = []
    for e in edges:
        etype = _s(e.get("type"))
        src   = _s(e.get("src"))
        dst   = _s(e.get("dst"))
        if src in type_info and dst in type_info and src != dst:
            if etype in ("ASSOCIATES", "DEPENDS_ON"):
                dep_edges.append((src, dst))
                called.add(dst)

    all_pkgs = list({
        _get(t, "package", default="(default)")
        for t in type_info.values()
        if _get(t, "package", default="(default)") != "(default)"
    })
    root = ""
    if len(all_pkgs) > 1:
        parts = [p.split(".") for p in all_pkgs]
        common = []
        for segs in zip(*parts):
            if len(set(segs)) == 1:
                common.append(segs[0])
            else:
                break
        root = ".".join(common)

    def _short(pkg: str) -> str:
        if pkg == "(default)":
            return "(root)"
        if root and pkg.startswith(root):
            rel = pkg[len(root):].lstrip(".")
            return rel if rel else "(root)"
        return pkg.rsplit(".", 1)[-1]

    pkg_to_tids: Dict[str, list] = _dd(list)
    for tid in type_info:
        pkg = _get(type_info[tid], "package", default="(default)")
        pkg_to_tids[pkg].append(tid)

    lines = ["COMPONENT DIAGRAM CONTEXT", ""]
    lines.append(f"ROOT PACKAGE (full FQN): {root or '(default)'}")
    lines.append("")
    lines.append("COMPONENTS — each class becomes [ClassName] as alias:")
    lines.append("  - Components depended-on by others get a lollipop: () 'ClassName' as I_alias + alias - I_alias")
    lines.append("")

    if root:
        lines.append(f'package "{root}" {{')
    for pkg in sorted(pkg_to_tids.keys()):
        short = _short(pkg)
        tids = sorted(pkg_to_tids[pkg], key=lambda t: type_names.get(t, t))
        is_root_level = short in ("(root)", "(default)")
        indent = "  " if root else ""
        stereos = [_stereo(pkg, type_names.get(t, "")) for t in tids if _stereo(pkg, type_names.get(t, ""))]
        pkg_stereo = stereos[0] if stereos else ""
        if not is_root_level:
            stereo_str = f" {pkg_stereo}" if pkg_stereo else ""
            lines.append(f'{indent}package "{short}"{stereo_str} {{')
            inner = indent + "  "
        else:
            inner = indent
        for tid in tids:
            nm = type_names[tid]
            a  = _alias(tid)
            ia = _ialias(tid)
            lines.append(f"{inner}[{nm}] as {a}")
            if tid in called:
                lines.append(f'{inner}() "{nm}" as {ia}')
                lines.append(f"{inner}{a} - {ia}")
        if not is_root_level:
            lines.append(f"{indent}}}")
        lines.append("")
    if root:
        lines.append("}")
        lines.append("")

    lines.append("DEPENDENCY ARROWS (after closing root package }, target lollipop alias I_alias):")
    seen: set = set()
    for src, dst in dep_edges:
        pair = (_alias(src), _ialias(dst) if dst in called else _alias(dst))
        if pair in seen:
            continue
        seen.add(pair)
        dst_pkg  = _get(type_info[dst], "package", default="")
        dst_name = type_names[dst]
        label = _arrow_label(dst_pkg, dst_name)
        lines.append(f"{_alias(src)} --> {_ialias(dst) if dst in called else _alias(dst)} : {label}")

    return "\n".join(lines)


def _summarize_activity(
    type_info: Dict[str, Any],
    type_names: Dict[str, str],
    nodes_by_id: Dict[str, Any],
    edges: List[Dict[str, Any]],
    outgoing: DefaultDict[str, List[Tuple[str, str]]],
) -> str:
    """
    Build a rich activity-diagram context for the LLM.

    Key fix vs original:
      _is_infrastructure_noise() types (DatabaseUtil, PasswordUtil, ConfigUtil,
      LoggerUtil, *Config, *Util, *Helper …) are now excluded from active_types
      AND from the call chain.  Previously these stayed in active_types and their
      CALLS edges (layer=60-70) dominated the sorted chain because the App/Main
      class (layer=55 default) called them first, producing a shallow 5-7 node
      diagram that completely missed the real business logic.

    With noise excluded, LibraryService (layer=20), BookDAO/MemberDAO/LoanDAO
    (layer=30) etc. become the active types and their rich CALLS chains fill
    the diagram correctly.
    """

    # ── Index methods ──────────────────────────────────────────────────────
    method_owner: Dict[str, str] = {}
    methods_by_type: Dict[str, List[Dict[str, Any]]] = {t: [] for t in type_info}
    method_attrs: Dict[str, Dict[str, Any]] = {}

    for e in edges:
        if e.get("type") == "HAS_METHOD":
            src, dst = e.get("src"), e.get("dst")
            if src in type_info and dst in nodes_by_id:
                ma = dict(nodes_by_id[dst].get("attrs", {}))
                ma["_id"] = dst
                methods_by_type.setdefault(src, []).append(ma)
                method_owner[dst] = src
                method_attrs[dst] = ma

    # ── Index parameters ───────────────────────────────────────────────────
    params_by_method: Dict[str, List[Dict[str, Any]]] = {}
    for e in edges:
        if e.get("type") == "PARAM_OF":
            pid, mid = e.get("src"), e.get("dst")
            if pid and mid:
                pn = nodes_by_id.get(pid)
                if pn and pn.get("kind") == "Parameter":
                    params_by_method.setdefault(mid, []).append(pn.get("attrs", {}))

    # ── Index CALLS edges ──────────────────────────────────────────────────
    calls_raw: List[Dict[str, Any]] = []
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
        calls_raw.append({"src": src_m, "dst": dst_m, "order": order})

    calls_raw.sort(key=lambda x: x.get("order", 0))

    # ── Exclusion: pure model types AND infrastructure noise ───────────────
    #
    # FIX: The original only excluded _is_pure_model(). This left DatabaseUtil
    # (layer=40), PasswordUtil, ConfigUtil (layer=70) in active_types. The
    # App/Main class (layer=55 default) calls them first in the CALLS chain,
    # so their 5-7 methods dominated the entire diagram output. The real
    # business logic (LibraryService layer=20, BookDAO layer=30 etc.) never
    # appeared because their CALLS edges came later in the sort.
    #
    # Now we exclude infrastructure noise types from active_types AND filter
    # them from both src and dst positions in the call chain — exactly as the
    # sequence and component diagram generators already do.
    excluded: Set[str] = set()
    for tid, attrs in type_info.items():
        nm  = _get(attrs, "name",    default="")
        pkg = _get(attrs, "package", default="")
        ms  = methods_by_type.get(tid, [])
        if _is_pure_model(nm, pkg, ms) or _is_infrastructure_noise(nm, pkg):
            excluded.add(tid)

    active_types = {t: a for t, a in type_info.items() if t not in excluded}

    # If everything got excluded (tiny utility-only project), fall back gracefully
    if not active_types:
        active_types = {t: a for t, a in type_info.items()
                        if not _is_pure_model(
                            _get(a, "name", default=""),
                            _get(a, "package", default=""),
                            methods_by_type.get(t, []),
                        )}
    if not active_types:
        active_types = dict(type_info)

    def _participant_lane(tid: str) -> str:
        a   = type_info[tid]
        nm  = (_get(a, "name",    default="") or "").lower()
        pkg = (_get(a, "package", default="") or "").lower()
        combined = nm + " " + pkg
        if any(k in combined for k in ("controller", "resource", "endpoint", "rest", "handler")):
            return "Controller"
        if any(k in combined for k in ("service", "manager", "interactor", "usecase", "business", "facade")):
            return "Service"
        if any(k in combined for k in ("dao", "repository", "repo", "persistence", "store", "gateway")):
            return "Repository"
        if any(k in combined for k in ("database", "db")):
            return "Database"
        if any(k in combined for k in ("util", "helper", "config")):
            return "Utility"
        return "System"

    def _is_list_return(mid: str) -> bool:
        ma = method_attrs.get(mid, {})
        rt = (ma.get("raw_return_type") or ma.get("return_type") or "").lower()
        return any(k in rt for k in ("list", "collection", "set", "iterable", "[]", "array"))

    def _is_bool_return(mid: str) -> bool:
        ma = method_attrs.get(mid, {})
        rt = _clean_type_short(ma.get("raw_return_type") or ma.get("return_type") or "")
        return rt.lower() in ("boolean", "bool")

    def _is_optional_return(mid: str) -> bool:
        ma = method_attrs.get(mid, {})
        rt = (ma.get("raw_return_type") or ma.get("return_type") or "").lower()
        return "optional" in rt

    def _is_guard(mid: str) -> bool:
        ma   = method_attrs.get(mid, {})
        name = (ma.get("name") or "").lower()
        _GUARD_PFXS = ("validate", "check", "verify", "ensure", "assert",
                       "exists", "existsby", "is", "has", "can", "allow")
        if _is_bool_return(mid) or _is_optional_return(mid):
            return True
        return any(name.startswith(p) for p in _GUARD_PFXS)

    def _fmt_params(mid: str, max_p: int = 3) -> str:
        params = params_by_method.get(mid, [])[:max_p]
        parts: List[str] = []
        for p in params:
            pn = p.get("name", "")
            pt = _clean_type_short(p.get("raw_type") or p.get("type_name") or "")
            if pn and pt:
                parts.append(f"{pn}: {pt}")
            elif pn:
                parts.append(pn)
        suffix = ", ..." if len(params_by_method.get(mid, [])) > max_p else ""
        return ", ".join(parts) + suffix

    def _fmt_return(mid: str) -> str:
        ma = method_attrs.get(mid, {})
        rt = _clean_type_short(ma.get("raw_return_type") or ma.get("return_type") or "void")
        return rt or "void"

    def _guard_label(mid: str) -> str:
        ma   = method_attrs.get(mid, {})
        name = ma.get("name") or ""
        nl   = name.lower()

        if _is_optional_return(mid):
            subject = re.sub(
                r"^(?:findBy|getBy|loadBy|fetchBy|searchBy|find|get|load|fetch|lookup|query|retrieve)",
                "", name
            ).strip()
            if subject:
                # FIX: preserve acronyms (ISBN, ID, URL) before camelCase split
                # Step 1: collapse consecutive uppercase sequences into title-case
                subject = re.sub(r'([A-Z]{2,})', lambda m: m.group(1).title(), subject)
                # Step 2: now split camelCase normally
                subject = re.sub(r"([A-Z])", lambda m: " " + m.group(1), subject).strip().lower()
            else:
                subject = "result"
            return f"{subject} found?"

        prefix_map = [
            ("existsby", "exists?"), ("exists", "exists?"),
            ("validateby", "valid?"), ("validate", "valid?"),
            ("verifyby", "valid?"), ("verify", "valid?"),
            ("checkby", "correct?"), ("check", "correct?"),
            ("ensure", "satisfied?"), ("has", "?"), ("is", "?"),
            ("can", "?"), ("allow", " allowed?"),
        ]
        for prefix, suffix in prefix_map:
            if nl.startswith(prefix):
                subject = name[len(prefix):]
                if not subject:
                    subject = name
                # FIX: same acronym-preserving split
                subject = re.sub(r'([A-Z]{2,})', lambda m: m.group(1).title(), subject)
                subject = re.sub(r"([A-Z])", lambda m: " " + m.group(1), subject).strip().lower()
                return f"{subject}{suffix}"

        subject = re.sub(r'([A-Z]{2,})', lambda m: m.group(1).title(), name)
        subject = re.sub(r"([A-Z])", lambda m: " " + m.group(1), subject).strip().lower()
        return f"{subject}?"

    # ── Build ordered call chain ───────────────────────────────────────────
    src_layer_info: Dict[str, Tuple[int, int]] = {}
    calls_by_src: Dict[str, List[Dict[str, Any]]] = {}
    for c in calls_raw:
        src_m = c["src"]
        src_t = method_owner.get(src_m)
        if not src_t or src_t not in active_types:
            continue
        ma = method_attrs.get(src_m, {})
        if ma.get("visibility", "public") == "private":
            continue
        nm = ma.get("name", "")
        if nm.startswith("_") and not nm.startswith("__"):
            continue
        layer = _layer_order(
            _get(type_info[src_t], "name", default=""),
            _get(type_info[src_t], "package", default=""),
        )
        calls_by_src.setdefault(src_m, []).append(c)
        prev = src_layer_info.get(src_m, (layer, c["order"]))
        src_layer_info[src_m] = (prev[0], min(prev[1], c["order"]))

    sorted_callers = sorted(src_layer_info.keys(), key=lambda m: src_layer_info[m])

    # Dedup: (src_type_id, dst_method_id) — each caller type emits each dst method once
    # Also apply per-caller cap (8) and global repeat cap (3) matching uml_rules.py fix
    MAX_PER_CALLER  = 8
    MAX_GLOBAL_REPS = 3

    per_caller_emitted: Set[Tuple[str, str]] = set()
    per_caller_count:   Dict[str, int]       = {}
    global_count:       Dict[str, int]       = {}
    ordered_calls: List[Dict[str, Any]] = []

    for src_m in sorted_callers:
        src_t = method_owner.get(src_m, "")
        for c in sorted(calls_by_src.get(src_m, []), key=lambda x: x["order"]):
            dst_m = c["dst"]
            dst_t = method_owner.get(dst_m)
            # FIX: skip dst methods whose owner is infrastructure noise
            if not dst_t or dst_t not in active_types:
                continue
            dst_ma = method_attrs.get(dst_m, {})
            if dst_ma.get("visibility", "public") == "private":
                continue
            dst_nm = dst_ma.get("name", "")
            if dst_nm.startswith("_") and not dst_nm.startswith("__"):
                continue

            key = (src_t, dst_m)
            if key in per_caller_emitted:
                continue
            per_caller_emitted.add(key)

            if per_caller_count.get(src_t, 0) >= MAX_PER_CALLER:
                continue
            per_caller_count[src_t] = per_caller_count.get(src_t, 0) + 1

            if global_count.get(dst_m, 0) >= MAX_GLOBAL_REPS:
                continue
            global_count[dst_m] = global_count.get(dst_m, 0) + 1

            ordered_calls.append({
                "src_method": src_m,
                "dst_method": dst_m,
                "src_type":   src_t,
                "dst_type":   dst_t,
            })

    # ── Build context text ─────────────────────────────────────────────────
    lines: List[str] = ["ACTIVITY DIAGRAM CONTEXT", ""]

    sorted_tids = sorted(
        active_types.keys(),
        key=lambda t: _layer_order(
            _get(type_info[t], "name", default=""),
            _get(type_info[t], "package", default=""),
        ),
    )

    lines.append("ARCHITECTURAL COMPONENTS (swimlane classification):")
    for tid in sorted_tids:
        nm   = _get(type_info[tid], "name",    default=tid)
        pkg  = _get(type_info[tid], "package", default="(default)")
        lane = _participant_lane(tid)
        lines.append(f"  [{nm}]  lane={lane}  package={pkg}")
    lines.append("")

    if ordered_calls:
        lines.append("ORDERED METHOD CALL CHAIN (follow this sequence for the flow):")
        lines.append("  Format: CallerType → CallerMethod  calls  CalleeType.calleeMethod(params) : ReturnType")
        lines.append("  Hint:   [GUARD]  = decision diamond (if/else)    [LOOP] = repeat while    [ACTION] = plain step")
        lines.append("")
        for i, c in enumerate(ordered_calls, 1):
            src_t  = c["src_type"]
            dst_t  = c["dst_type"]
            src_nm = _get(type_info.get(src_t, {}), "name", default=src_t)
            dst_nm = _get(type_info.get(dst_t, {}), "name", default=dst_t)
            src_ma = method_attrs.get(c["src_method"], {})
            dst_ma = method_attrs.get(c["dst_method"], {})
            src_mname = src_ma.get("name", "?")
            dst_mname = dst_ma.get("name", "?")
            params    = _fmt_params(c["dst_method"])
            ret       = _fmt_return(c["dst_method"])
            mid       = c["dst_method"]

            hint = "[ACTION]"
            if _is_list_return(mid):
                hint = "[LOOP]  → use: repeat / repeat while (more items?) is (yes) -> no;"
            elif _is_guard(mid):
                guard_q = _guard_label(mid)
                hint = f'[GUARD] → use: if ({guard_q}) then (yes) ... else (no) ... endif'

            lines.append(f"  {i:2}. {src_nm}.{src_mname}  →  {dst_nm}.{dst_mname}({params}) : {ret}")
            lines.append(f"       {hint}")

        lines.append("")
        lines.append("SWIMLANE ORDER (top-to-bottom, same as call chain above):")
        seen_lanes: List[str] = []
        for c in ordered_calls:
            lane = _participant_lane(c["dst_type"])
            if lane not in seen_lanes:
                seen_lanes.append(lane)
        for lane in seen_lanes:
            lines.append(f"  |{lane}|")

    else:
        lines.append("NO CALL CHAIN DATA — emit flat method listing per swimlane:")
        lines.append("")
        for tid in sorted_tids:
            nm   = _get(type_info[tid], "name", default=tid)
            lane = _participant_lane(tid)
            ms   = [m for m in methods_by_type.get(tid, [])
                    if not m.get("is_constructor")
                    and not _is_dunder(m.get("name", ""))
                    and m.get("visibility", "public") != "private"
                    and not any(m.get("name", "").startswith(p) for p in _TRIVIAL_PFXS)
                    and m.get("name", "").lower() not in _TRIVIAL_NAMES]
            if not ms:
                continue
            lines.append(f"  LANE |{lane}| — type: {nm}")
            for m in ms[:6]:
                mname  = m.get("name", "?")
                mid    = m.get("_id", "")
                params = _fmt_params(mid)
                ret    = _fmt_return(mid)
                hint   = ""
                if _is_list_return(mid):
                    hint = "  [LOOP]"
                elif _is_guard(mid):
                    hint = f"  [GUARD → if ({_guard_label(mid)}) then (yes) ... else (no) ... endif]"
                lines.append(f"    :   {nm}.{mname}({params}) : {ret}{hint}")
            lines.append("")

    lines.append("")
    lines.append("CRITICAL RULES FOR ACTIVITY DIAGRAM GENERATION:")
    lines.append("  1. start and stop are REQUIRED.")
    lines.append("  2. NEVER mix swimlane markers (|Lane|) with if/repeat/fork blocks.")
    lines.append("     MODE A: swimlanes only, NO if/repeat/fork anywhere.")
    lines.append("     MODE B: if/repeat/fork only, NO swimlane markers anywhere.")
    lines.append("  3. Action labels must NOT contain < > or | — replace with ( ) and /.")
    lines.append("  4. Use 'ClassName.methodName(params)' format in :action; labels.")
    lines.append("  5. Guards wrap calls annotated [GUARD]; loops wrap calls annotated [LOOP].")
    lines.append("  6. Follow the call chain order above for the diagram flow.")
    lines.append("  7. Do NOT use 'lane' keyword — it does not exist in PlantUML.")
    lines.append("  8. Do NOT emit @startuml twice.")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Main public function
# ─────────────────────────────────────────────────────────────────────────────

def summarize_cir_for_llm(cir: Dict[str, Any], diagram_type: str) -> str:
    nodes: List[Dict[str, Any]] = cir.get("nodes", []) or []
    edges: List[Dict[str, Any]] = cir.get("edges", []) or []

    nodes_by_id: Dict[str, Dict[str, Any]] = {
        _s(n.get("id")): n for n in nodes if _s(n.get("id"))
    }

    outgoing, incoming = _build_edge_maps(edges)

    type_info:  Dict[str, Dict[str, Any]] = {}
    type_names: Dict[str, str]            = {}

    for n in nodes:
        if n.get("kind") != "TypeDecl":
            continue
        nid = _s(n.get("id"))
        if not nid:
            continue
        type_info[nid]  = n
        type_names[nid] = _get(n, "name") or nid

    dt = diagram_type.lower().strip()
    is_class_diagram     = dt in ("class", "class diagram", "class_diagram")
    is_package_diagram   = dt in ("package", "package diagram")
    is_component_diagram = dt in ("component", "component diagram")
    is_activity_diagram  = dt in ("activity", "activity diagram")

    if is_package_diagram:
        return _summarize_package(type_info, type_names, edges)

    if is_component_diagram:
        return _summarize_component(type_info, type_names, edges, outgoing, nodes_by_id)

    if is_activity_diagram:
        return _summarize_activity(type_info, type_names, nodes_by_id, edges, outgoing)

    # ── Class / Sequence diagrams ─────────────────────────────────────────────
    fields_by_type:  DefaultDict[str, List[str]] = defaultdict(list)
    methods_by_type: DefaultDict[str, List[str]] = defaultdict(list)

    params_for_method: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    if is_class_diagram:
        for n in nodes:
            if n.get("kind") != "Parameter":
                continue
            nid = _s(n.get("id"))
            if not nid:
                continue
            for etype, dst in outgoing.get(nid, []):
                if etype == "PARAM_OF":
                    params_for_method[dst].append(n)

    if is_class_diagram:
        for type_id in type_info:
            for etype, field_id in outgoing.get(type_id, []):
                if etype != "HAS_FIELD":
                    continue
                fn = nodes_by_id.get(field_id)
                if not fn:
                    continue

                fname      = _get(fn, "name")
                raw_type   = _get(fn, "raw_type", "type_name", default="Any")
                vis        = _get(fn, "visibility", default="public")
                mult       = _get(fn, "multiplicity")
                mods       = _get_mods(fn)
                is_static  = _get_bool(fn, "is_static") or "static" in mods

                if not fname:
                    continue

                sym = _vis_symbol(vis)
                mod_parts: List[str] = []
                if is_static:
                    mod_parts.append("{static}")
                mod_prefix = " ".join(mod_parts)
                if mod_prefix:
                    mod_prefix += " "

                display_type = _clean_type(raw_type) or "Any"
                mult_suffix = ""
                if mult and mult not in ("1", ""):
                    mult_suffix = f"  [{mult}]"

                fields_by_type[type_id].append(
                    f"{sym}{mod_prefix}{fname} : {display_type}{mult_suffix}"
                )

            for etype, method_id in outgoing.get(type_id, []):
                if etype != "HAS_METHOD":
                    continue
                mn = nodes_by_id.get(method_id)
                if not mn:
                    continue

                mname       = _get(mn, "name")
                return_type = _get(mn, "raw_return_type", "return_type", default="void")
                vis         = _get(mn, "visibility", default="public")
                is_ctor     = _get_bool(mn, "is_constructor")
                is_static   = _get_bool(mn, "is_static")
                is_abstract = _get_bool(mn, "is_abstract")
                mods        = _get_mods(mn)

                if not mname or is_ctor:
                    continue

                sym = _vis_symbol(vis)
                mod_parts = []
                if is_abstract or "abstract" in mods:
                    mod_parts.append("{abstract}")
                if is_static or "static" in mods:
                    mod_parts.append("{static}")
                mod_prefix = " ".join(mod_parts)
                if mod_prefix:
                    mod_prefix += " "

                param_nodes = params_for_method.get(method_id, [])
                param_strs: List[str] = []
                for pn in param_nodes:
                    pname = _get(pn, "name")
                    ptype = _get(pn, "raw_type", "type_name", default="Any")
                    if pname and ptype:
                        param_strs.append(f"{pname}: {_clean_type(ptype)}")
                    elif pname:
                        param_strs.append(pname)

                param_sig = ", ".join(param_strs)
                ret_display = _clean_type(return_type) or "void"

                methods_by_type[type_id].append(
                    f"{sym}{mod_prefix}{mname}({param_sig}) : {ret_display}"
                )

    MAX_FIELDS  = 15
    MAX_METHODS = 18

    rels: List[str] = []
    for e in edges:
        src   = _s(e.get("src"))
        dst   = _s(e.get("dst"))
        etype = _s(e.get("type"))
        if not src or not dst or not etype:
            continue
        if src not in type_names or dst not in type_names:
            continue
        rels.append(f"- {etype}: {type_names[src]} -> {type_names[dst]}")

    lines: List[str] = []
    lines.append("CIR SUMMARY")
    lines.append(f"DIAGRAM_TYPE: {diagram_type}")
    lines.append("")
    lines.append("TYPES:")

    sorted_types = sorted(
        type_info.items(),
        key=lambda kv: (
            _get(kv[1], "package", default=""),
            type_names.get(kv[0], kv[0]),
        ),
    )

    for type_id, tnode in sorted_types:
        tname    = type_names[type_id]
        pkg      = _get(tnode, "package", default="(default)")
        kind     = _get(tnode, "kind", default="class").lower()
        is_abs   = _get_bool(tnode, "is_abstract")
        is_final = _get_bool(tnode, "is_final")

        modifiers: List[str] = []
        if is_abs:
            modifiers.append("abstract")
        if is_final:
            modifiers.append("final")
        mod_str = f" [{', '.join(modifiers)}]" if modifiers else ""

        lines.append(f"- {tname} (kind: {kind}{mod_str}, package: {pkg})")

        if is_class_diagram:
            flds  = fields_by_type.get(type_id,  [])[:MAX_FIELDS]
            mths  = methods_by_type.get(type_id, [])[:MAX_METHODS]

            if flds:
                lines.append("  FIELDS:")
                for f in flds:
                    lines.append(f"    - {f}")

            if mths:
                lines.append("  METHODS:")
                for m in mths:
                    lines.append(f"    - {m}")

    lines.append("")
    lines.append("RELATIONSHIPS (etype: A -> B):")
    for r in rels[:250]:
        lines.append(r)

    return "\n".join(lines)