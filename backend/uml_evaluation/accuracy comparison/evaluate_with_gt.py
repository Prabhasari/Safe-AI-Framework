# evaluate_with_gt.py
#
# Scores regex AND AI independently against hand-verified ground truth.
# This gives you SEPARATE accuracy numbers for each method per diagram type.
#
# Usage:
#   python evaluate_with_gt.py           # all 3 samples, all 5 diagram types
#   python evaluate_with_gt.py --sample 05
#   python evaluate_with_gt.py --type sequence

import argparse
import importlib.util
import json
import os
import re
import sys
import time
from typing import Dict, Set

import requests

PARSE_URL     = "http://127.0.0.1:7070/parse"
UML_REGEX_URL = "http://127.0.0.1:7080/uml/regex"
UML_AI_URL    = "http://127.0.0.1:7081/uml/ai"

BASE_DIR    = os.path.dirname(__file__)
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
GT_DIR      = BASE_DIR  # ground truth files are in same folder

DIAGRAM_TYPES = ["class", "package", "sequence", "component", "activity"]

# Maps sample prefix → ground truth module filename
GT_FILES = {
    "05": "ground_truth_05",
    "09": "ground_truth_09",
    "10": "ground_truth_10",
    "11": "ground_truth_11",
    "12": "ground_truth_12",
    "13": "ground_truth_13",
}


# ══════════════════════════════════════════════════════════════════════════════
#  Load ground truth module dynamically
# ══════════════════════════════════════════════════════════════════════════════

def load_gt(prefix: str):
    module_name = GT_FILES.get(prefix)
    if not module_name:
        return None
    path = os.path.join(GT_DIR, f"{module_name}.py")
    if not os.path.exists(path):
        return None
    spec   = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_gt_for_type(gt_module, dtype: str) -> Dict[str, Set[str]]:
    """Convert ground truth module data into comparable sets."""
    result = {}

    if dtype == "class":
        gt = getattr(gt_module, "CLASS_GT", {})
        result["classes"]    = set(gt.get("classes", set()))
        result["fields"]     = set(gt.get("fields", set()))
        result["methods"]    = set(gt.get("methods", set()))
        result["inherits"]   = set()
        result["implements"] = set()
        result["associates"] = set()
        result["depends_on"] = set()
        for rel_type, src, dst in gt.get("relationships", set()):
            result[rel_type].add(f"{src}->{dst}")

    elif dtype == "package":
        gt = getattr(gt_module, "PACKAGE_GT", {})
        result["packages"]     = set(gt.get("packages", set()))
        result["members"]      = set(gt.get("members", set()))
        result["dependencies"] = set(gt.get("dependencies", set()))

    elif dtype == "sequence":
        gt = getattr(gt_module, "SEQUENCE_GT", {})
        result["participants"] = set(gt.get("participants", set()))
        result["messages"]     = set(gt.get("key_messages", set()))

    elif dtype == "component":
        gt = getattr(gt_module, "COMPONENT_GT", {})
        result["components"]  = set(gt.get("components", set()))
        result["interfaces"]  = set(gt.get("interfaces", set()))
        result["connections"] = set(gt.get("connections", set()))

    elif dtype == "activity":
        gt = getattr(gt_module, "ACTIVITY_GT", {})
        result["actions"]    = set(gt.get("actions", set()))
        result["decisions"]  = set(gt.get("decisions", set()))
        result["swimlanes"]  = set(gt.get("swimlanes", set()))

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  PlantUML extractors (same as evaluate_diagram_types.py)
# ══════════════════════════════════════════════════════════════════════════════

def extract_class(puml: str) -> Dict[str, Set[str]]:
    result = {k: set() for k in
              ["classes","fields","methods","inherits","implements","associates","depends_on"]}
    if not puml: return result
    current_class = None
    for line in puml.splitlines():
        s = line.strip()
        m = re.match(r'^(?:abstract\s+)?(?:class|interface|enum)\s+(\w[\w.]*)', s)
        if m:
            current_class = m.group(1).split(".")[-1]
            result["classes"].add(current_class); continue
        if s == "}": current_class = None; continue
        if current_class:
            if re.match(r'^[+\-#~]', s) and "(" not in s and ":" in s:
                fm = re.match(r'^[+\-#~]\s*(?:\{.*?\}\s*)?(\w+)\s*:', s)
                if fm: result["fields"].add(f"{current_class}.{fm.group(1)}")
                continue
            if re.match(r'^[+\-#~]', s) and "(" in s:
                mm = re.match(r'^[+\-#~]\s*(?:\{.*?\}\s*)?(\w+)\s*\(', s)
                if mm: result["methods"].add(f"{current_class}.{mm.group(1)}")
                continue
        if re.match(r'^(\w+)\s*--\|>\s*(\w+)', s):
            m = re.match(r'^(\w+)\s*--\|>\s*(\w+)', s)
            result["inherits"].add(f"{m.group(1)}->{m.group(2)}")
        elif re.match(r'^(\w+)\s*\.\.\|>\s*(\w+)', s):
            m = re.match(r'^(\w+)\s*\.\.\|>\s*(\w+)', s)
            result["implements"].add(f"{m.group(1)}->{m.group(2)}")
        elif re.match(r'^(\w+)\s*-->\s*(?:"[^"]*"\s*)?(\w+)', s):
            m = re.match(r'^(\w+)\s*-->\s*(?:"[^"]*"\s*)?(\w+)', s)
            result["associates"].add(f"{m.group(1)}->{m.group(2)}")
        elif re.match(r'^(\w+)\s*\.\.\>\s*(\w+)', s):
            m = re.match(r'^(\w+)\s*\.\.\>\s*(\w+)', s)
            result["depends_on"].add(f"{m.group(1)}->{m.group(2)}")
    return result


def extract_package(puml: str) -> Dict[str, Set[str]]:
    result = {"packages": set(), "members": set(), "dependencies": set()}
    if not puml: return result
    # Build alias->name map first (e.g. [Student] as type_Student)
    alias_map = {}
    for line in puml.splitlines():
        s = line.strip()
        am = re.match(r'^\[([^\]]+)\]\s+as\s+(\w+)', s)
        if am:
            alias_map[am.group(2)] = am.group(1).strip()
    current_pkg = None
    pkg_depth = 0
    for line in puml.splitlines():
        s = line.strip()
        pm = re.match(r'^package\s+"?([^"{\s]+)"?\s*(?:<<\w+>>\s*)?\{?', s)
        if pm:
            current_pkg = pm.group(1)
            result["packages"].add(current_pkg)
            pkg_depth += 1
            continue
        if "{" in s and current_pkg and not pm:
            pkg_depth += s.count("{")
        if "}" in s and current_pkg:
            pkg_depth -= s.count("}")
            if pkg_depth <= 0:
                current_pkg = None; pkg_depth = 0
            continue
        if current_pkg:
            # Handle: class X, interface X, enum X
            tm = re.match(r'^(?:class|interface|enum)\s+(\w+)', s)
            if tm: result["members"].add(tm.group(1)); continue
            # Handle: [ClassName] or [ClassName] as alias
            bm = re.match(r'^\[([^\]]+)\]', s)
            if bm: result["members"].add(bm.group(1).strip()); continue
        # Dependencies: resolve aliases to real names
        dm = re.match(r'^(\w+)\s*(?:-->|\.\.>|\.\.|\|>)\s*(\w+)', s)
        if dm:
            src = alias_map.get(dm.group(1), dm.group(1))
            dst = alias_map.get(dm.group(2), dm.group(2))
            # Strip "I_type_" or "type_" prefixes added by regex generator
            src = re.sub(r'^(?:I_)?type_', '', src)
            dst = re.sub(r'^(?:I_)?type_', '', dst)
            result["dependencies"].add(f"{src}->{dst}")
    return result


def extract_sequence(puml: str) -> Dict[str, Set[str]]:
    result = {"participants": set(), "messages": set()}
    if not puml: return result
    aliases = {}
    for line in puml.splitlines():
        s = line.strip()
        pm = re.match(
            r'^(?:actor|boundary|control|entity|database|participant)\s+'
            r'"?([^"]+)"?\s+as\s+(\w+)', s)
        if pm:
            name, alias = pm.group(1).strip(), pm.group(2).strip()
            aliases[alias] = name; result["participants"].add(name); continue
        pm2 = re.match(r'^(?:actor|boundary|control|entity|database|participant)\s+(\w+)', s)
        if pm2:
            name = pm2.group(1)
            aliases[name] = name; result["participants"].add(name); continue
        mm = re.match(r'^(\w+)\s*-+>+\s*(\w+)\s*:\s*(.+)', s)
        if mm:
            src   = aliases.get(mm.group(1), mm.group(1))
            dst   = aliases.get(mm.group(2), mm.group(2))
            label = mm.group(3).strip()
            method = re.match(r'(\w+)\s*[\(:]?', label)
            if method:
                result["messages"].add(f"{src}->{dst}:{method.group(1)}")
    return result


def extract_component(puml: str) -> Dict[str, Set[str]]:
    result = {"components": set(), "interfaces": set(), "connections": set()}
    if not puml: return result
    # Build alias->name map: [Foo] as type_Foo  or  () "Foo" as I_type_Foo
    alias_map = {}
    for line in puml.splitlines():
        s = line.strip()
        # [ComponentName] as alias
        cm = re.match(r'^\[([^\]]+)\]\s+as\s+(\w+)', s)
        if cm:
            name = cm.group(1).strip()
            alias_map[cm.group(2)] = name
            result["components"].add(name)
            continue
        # () "InterfaceName" as alias
        im = re.match(r'^\(\)\s+"?([^"]+)"?\s+as\s+(\w+)', s)
        if im:
            name = im.group(1).strip()
            alias_map[im.group(2)] = name
            result["interfaces"].add(name)
            continue
        # Plain [ComponentName] without alias
        cm2 = re.match(r'^\[([^\]]+)\](?!\s+as)', s)
        if cm2:
            result["components"].add(cm2.group(1).strip())
            continue
    # Second pass for connections — resolve aliases
    for line in puml.splitlines():
        s = line.strip()
        conn = re.match(r'^(\w+)\s*-->\s*(\w+)', s)
        if conn:
            src = alias_map.get(conn.group(1), conn.group(1))
            dst = alias_map.get(conn.group(2), conn.group(2))
            # Strip lollipop interface prefix to get base component name
            src_base = re.sub(r'^(?:I_)?type_', '', src)
            dst_base = re.sub(r'^(?:I_)?type_', '', dst)
            result["connections"].add(f"{src_base}->{dst_base}")
    return result


def extract_activity(puml: str) -> Dict[str, Set[str]]:
    result = {"actions": set(), "decisions": set(), "swimlanes": set()}
    if not puml: return result
    for line in puml.splitlines():
        s = line.strip()
        # Swimlane: |LaneName|
        sl = re.match(r'^\|([^|]+)\|', s)
        if sl: result["swimlanes"].add(sl.group(1).strip()); continue
        # Action: :Some action;
        am = re.match(r'^:(.+);$', s)
        if am:
            label  = am.group(1).strip()
            method = re.match(r'(?:\w+\.)?(\w+)\s*[\(:]?', label)
            if method and method.group(1) not in ('if','else','endif','fork','end'):
                result["actions"].add(method.group(1))
            continue
        # Decision: if (...) then
        dm = re.match(r'^if\s+\((.+?)\??\)', s)
        if dm: result["decisions"].add(dm.group(1).strip()); continue
        # repeat while (...) — treat loop condition as decision
        rw = re.match(r'^repeat\s+while\s+\((.+?)\??\)', s)
        if rw: result["decisions"].add(rw.group(1).strip()); continue
        # while (...) is (yes/no) — alternate syntax
        wh = re.match(r'while\s+\((.+?)\??\)', s)
        if wh: result["decisions"].add(wh.group(1).strip())
    return result


EXTRACTORS = {
    "class":     extract_class,
    "package":   extract_package,
    "sequence":  extract_sequence,
    "component": extract_component,
    "activity":  extract_activity,
}


# ══════════════════════════════════════════════════════════════════════════════
#  Fuzzy matching helpers
#  Because AI may use "get_student" while GT has "getStudent" etc.
# ══════════════════════════════════════════════════════════════════════════════

def normalize(s: str) -> str:
    """Lowercase, remove underscores and spaces for fuzzy comparison."""
    return re.sub(r'[_\s]', '', s.lower())

def fuzzy_match(extracted: Set[str], ground_truth: Set[str]) -> tuple:
    """
    Match extracted elements against GT using normalized comparison.
    Returns (tp, fp, fn) counts.
    """
    gt_norm  = {normalize(g): g for g in ground_truth}
    ext_norm = {normalize(e): e for e in extracted}

    matched_gt  = set()
    matched_ext = set()

    for en, ev in ext_norm.items():
        # Try exact normalized match first
        if en in gt_norm:
            matched_gt.add(gt_norm[en])
            matched_ext.add(ev)
            continue
        # Try substring match (e.g. "StudentController" matches "Controller")
        for gn, gv in gt_norm.items():
            if (en in gn or gn in en) and gv not in matched_gt:
                matched_gt.add(gv)
                matched_ext.add(ev)
                break

    tp = len(matched_gt)
    fp = len(extracted) - len(matched_ext)
    fn = len(ground_truth) - len(matched_gt)
    return tp, fp, fn


# ══════════════════════════════════════════════════════════════════════════════
#  Metrics
# ══════════════════════════════════════════════════════════════════════════════

def pct(a, b): return round(a/b*100, 1) if b else 100.0

def scores(tp, fp, fn):
    pr  = pct(tp, tp+fp)
    re_ = pct(tp, tp+fn)
    f1  = round(2*pr*re_/(pr+re_), 1) if pr+re_ else 0.0
    return {"tp":tp, "fp":fp, "fn":fn, "precision":pr, "recall":re_, "f1":f1}

def compute_against_gt(gt: Dict[str,Set], extracted: Dict[str,Set], fuzzy=True) -> dict:
    out = {}
    ttp = tfp = tfn = 0
    for cat in gt:
        g = gt.get(cat, set())
        e = extracted.get(cat, set())
        if not g:  # skip empty GT categories
            continue
        if fuzzy:
            tp, fp, fn = fuzzy_match(e, g)
        else:
            tp, fp, fn = len(g&e), len(e-g), len(g-e)
        ttp+=tp; tfp+=fp; tfn+=fn
        out[cat] = scores(tp, fp, fn)
    out["overall"] = scores(ttp, tfp, tfn)
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  API helpers
# ══════════════════════════════════════════════════════════════════════════════

def call_parse(code, language, filename):
    r = requests.post(PARSE_URL,
                      json={"code":code,"filename":filename,"language":language},
                      timeout=20)
    r.raise_for_status()
    return r.json()

def call_regex(cir, dtype):
    r = requests.post(UML_REGEX_URL, json={"cir":cir,"diagram_type":dtype}, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"): raise RuntimeError(str(data.get("validation_errors")))
    return data.get("plantuml","")

def call_ai(cir, dtype):
    try:
        r = requests.post(UML_AI_URL, json={"cir":cir,"diagram_type":dtype}, timeout=120)
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"HTTP {r.status_code} — AI service error (diagram may be too large): {e}")
    data = r.json()
    if data.get("error"): raise RuntimeError(data["error"])
    return data.get("plantuml","")


# ══════════════════════════════════════════════════════════════════════════════
#  Single sample evaluator
# ══════════════════════════════════════════════════════════════════════════════

def evaluate_one(path, lang, fname, prefix, dtype_filter, debug=False):
    code   = open(path, encoding="utf-8").read()
    result = {"file":fname, "language":lang, "errors":{}, "diagrams":{}}

    gt_module = load_gt(prefix)
    if not gt_module:
        print(f"    No ground truth found for prefix {prefix}")
        return result

    try:
        cir = call_parse(code, lang, fname).get("cir", {})
        if debug:
            import json as _json
            calls = cir.get("calls", [])
            print(f"\n  ── CIR CALLS ({len(calls)} entries) ──")
            for c in calls[:30]:
                print(f"    {c}")
            if len(calls) > 30:
                print(f"    ... and {len(calls)-30} more")
            print()
    except Exception as e:
        result["errors"]["parse"] = str(e)
        print(f"    PARSE ERROR: {e}")
        return result

    for dtype in dtype_filter:
        extractor = EXTRACTORS[dtype]
        gt        = get_gt_for_type(gt_module, dtype)
        dr        = {"regex":{}, "ai":{}, "errors":[]}

        # Regex
        try:
            regex_puml = call_regex(cir, dtype)
            if debug:
                print(f"\n  ── RAW REGEX {dtype.upper()} ──")
                print(regex_puml)
                print()
            regex_ext  = extractor(regex_puml)
            dr["regex"] = compute_against_gt(gt, regex_ext)
            ov = dr["regex"]["overall"]
            print(f"    [{dtype:<10}]  "
                  f"REGEX  recall={ov['recall']:5.1f}%  "
                  f"precision={ov['precision']:5.1f}%  "
                  f"f1={ov['f1']:5.1f}%")
        except Exception as e:
            dr["errors"].append(f"regex: {e}")
            print(f"    [{dtype:<10}]  REGEX  ERROR: {e}")

        # AI
        try:
            ai_puml = call_ai(cir, dtype)
            if debug:
                print(f"\n  ── RAW AI {dtype.upper()} ──")
                print(ai_puml)
                print()
            ai_ext  = extractor(ai_puml)
            dr["ai"] = compute_against_gt(gt, ai_ext)
            ov = dr["ai"]["overall"]
            print(f"    [{dtype:<10}]  "
                  f"AI     recall={ov['recall']:5.1f}%  "
                  f"precision={ov['precision']:5.1f}%  "
                  f"f1={ov['f1']:5.1f}%")
        except Exception as e:
            dr["errors"].append(f"ai: {e}")
            print(f"    [{dtype:<10}]  AI     ERROR: {e}")

        result["diagrams"][dtype] = dr

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  Summary
# ══════════════════════════════════════════════════════════════════════════════

def avg(results, key_path):
    vals = []
    for r in results:
        obj = r
        for k in key_path:
            if not isinstance(obj,dict) or k not in obj: obj=None; break
            obj=obj[k]
        if obj is not None: vals.append(obj)
    return round(sum(vals)/len(vals),1) if vals else None

def print_summary(all_results, diagram_types):
    print("\n" + "═"*80)
    print("  REGEX vs AI ACCURACY — AGAINST HAND-VERIFIED GROUND TRUTH")
    print("  (Fuzzy matching applied: normalized names, substring matching)")
    print("═"*80)

    print(f"\n  {'Diagram Type':<14} {'REGEX Recall':>13} {'REGEX F1':>10} {'AI Recall':>11} {'AI F1':>8} {'Winner':>10}")
    print(f"  {'─'*14} {'─'*13} {'─'*10} {'─'*11} {'─'*8} {'─'*10}")

    for dtype in diagram_types:
        rr = avg(all_results, ["diagrams",dtype,"regex","overall","recall"])
        rf = avg(all_results, ["diagrams",dtype,"regex","overall","f1"])
        ar = avg(all_results, ["diagrams",dtype,"ai","overall","recall"])
        af = avg(all_results, ["diagrams",dtype,"ai","overall","f1"])

        if rf is None and af is None:
            print(f"  {dtype:<14} {'N/A':>13} {'N/A':>10} {'N/A':>11} {'N/A':>8}")
            continue

        rr_s = f"{rr}%" if rr is not None else "N/A"
        rf_s = f"{rf}%" if rf is not None else "N/A"
        ar_s = f"{ar}%" if ar is not None else "N/A"
        af_s = f"{af}%" if af is not None else "N/A"

        if rf is not None and af is not None:
            gap = round(rf - af, 1)
            if   gap >  5: winner = "Regex ✅"
            elif gap < -5: winner = "AI ✅"
            else:          winner = "≈ Tie"
        else:
            winner = "N/A"

        print(f"  {dtype:<14} {rr_s:>13} {rf_s:>10} {ar_s:>11} {af_s:>8} {winner:>10}")

    # Per diagram type element breakdown
    element_keys = {
        "class":     ["classes","fields","methods","implements","associates","depends_on"],
        "package":   ["packages","members","dependencies"],
        "sequence":  ["participants","messages"],
        "component": ["components","interfaces","connections"],
        "activity":  ["actions","decisions","swimlanes"],
    }

    for dtype in diagram_types:
        keys = element_keys.get(dtype, [])
        print(f"\n  {dtype.upper()} DIAGRAM — Element breakdown:")
        print(f"  {'Element':<20} {'Regex Recall':>13} {'Regex F1':>10} {'AI Recall':>11} {'AI F1':>8}")
        print(f"  {'─'*20} {'─'*13} {'─'*10} {'─'*11} {'─'*8}")
        for key in keys:
            rr = avg(all_results, ["diagrams",dtype,"regex",key,"recall"])
            rf = avg(all_results, ["diagrams",dtype,"regex",key,"f1"])
            ar = avg(all_results, ["diagrams",dtype,"ai",key,"recall"])
            af = avg(all_results, ["diagrams",dtype,"ai",key,"f1"])
            rr_s = f"{rr}%" if rr is not None else "N/A"
            rf_s = f"{rf}%" if rf is not None else "N/A"
            ar_s = f"{ar}%" if ar is not None else "N/A"
            af_s = f"{af}%" if af is not None else "N/A"
            print(f"  {key:<20} {rr_s:>13} {rf_s:>10} {ar_s:>11} {af_s:>8}")

    print(f"\n  Samples evaluated: {len(all_results)}")
    print("═"*80)
    print("\n  NOTE: Ground truth was hand-verified for samples 05, 09, 10.")
    print("  Fuzzy matching used to handle naming variations between methods.")
    print("  See ground_truth_05/09/10.py to inspect or correct GT definitions.")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

def load_samples(filter_prefix=None):
    samples = []
    for lang, ext in [("java",".java"),("python",".py")]:
        folder = os.path.join(SAMPLES_DIR, lang)
        if not os.path.exists(folder): continue
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith(ext): continue
            m = re.match(r'^(\d+)', fname)
            if not m: continue
            prefix = m.group(1).zfill(2)
            if prefix not in GT_FILES: continue
            if filter_prefix and prefix != filter_prefix.zfill(2): continue
            samples.append((os.path.join(folder,fname), lang, fname, prefix))
    return samples

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", default=None, help="Sample prefix e.g. '05'")
    parser.add_argument("--type",   default=None, help="Diagram type e.g. 'sequence'")
    parser.add_argument("--debug",  action="store_true",
                        help="Print raw PlantUML output for inspection")
    args = parser.parse_args()

    dtype_filter = [args.type] if args.type else DIAGRAM_TYPES
    os.makedirs(RESULTS_DIR, exist_ok=True)

    samples = load_samples(args.sample)
    if not samples:
        print("No samples with ground truth found.")
        print(f"Looking for prefixes: {list(GT_FILES.keys())}")
        return

    print(f"\nEvaluating {len(samples)} sample(s) × {len(dtype_filter)} diagram type(s)\n")
    all_results = []

    for path, lang, fname, prefix in samples:
        print(f"[{lang.upper()}] {fname}")
        t0 = time.time()
        try:
            result = evaluate_one(path, lang, fname, prefix, dtype_filter,
                                  debug=args.debug)
        except Exception as e:
            result = {"file":fname,"language":lang,"errors":{"fatal":str(e)},"diagrams":{}}
            print(f"  FATAL: {e}")
        result["elapsed_s"] = round(time.time()-t0, 1)
        all_results.append(result)
        print(f"    done in {result['elapsed_s']}s\n")

    print_summary(all_results, dtype_filter)

    out = os.path.join(RESULTS_DIR, "gt_comparison_results.json")
    with open(out,"w") as f:
        json.dump(all_results, f, indent=2, default=list)
    print(f"Results → {out}\n")

if __name__ == "__main__":
    main()