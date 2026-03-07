# evaluate.py
# Three-layer evaluation:
#   Layer 1 — CIR Completeness : how much of the source code did /parse capture?
#   Layer 2 — Regex Fidelity   : does the regex diagram faithfully represent the CIR?
#   Layer 3 — AI Accuracy      : does the AI diagram faithfully represent the CIR?
#
# Usage:
#   python evaluate.py            # all 20 samples, all layers
#   python evaluate.py --no-ai   # skip AI (Layer 3)
#   python evaluate.py --sample 11

import argparse, json, os, re, time
from typing import Dict, List, Optional, Set, Tuple
import requests

PARSE_URL     = "http://127.0.0.1:7070/parse"
UML_REGEX_URL = "http://127.0.0.1:7080/uml/regex"
UML_AI_URL    = "http://127.0.0.1:7081/uml/ai"

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "samples")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# ─────────────────────────────────────────────────────────────────
#  LAYER 1: Hand-crafted source-code ground truth
#  These counts were verified manually by reading each file.
#  CIR completeness = what /parse captured vs what is actually in source.
# ─────────────────────────────────────────────────────────────────
SOURCE_TRUTH = {
    # ── Original 10 samples ──────────────────────────────────────
    "01_student_baseline.java":      {"classes": 2, "fields": 5,  "methods": 5,  "rels": 0},
    "02_student_inheritance.java":   {"classes": 3, "fields": 7,  "methods": 9,  "rels": 2},
    "03_student_interface.java":     {"classes": 3, "fields": 4,  "methods": 8,  "rels": 2},
    "04_student_association.java":   {"classes": 2, "fields": 6,  "methods": 7,  "rels": 2},
    "05_student_layered_system.java":{"classes": 7, "fields": 18, "methods": 22, "rels": 8},
    "06_student_baseline.py":        {"classes": 2, "fields": 5,  "methods": 6,  "rels": 0},
    "07_student_inheritance.py":     {"classes": 4, "fields": 9,  "methods": 11, "rels": 3},
    "08_student_association.py":     {"classes": 2, "fields": 6,  "methods": 7,  "rels": 2},
    "09_student_layered_system.py":  {"classes": 6, "fields": 18, "methods": 20, "rels": 7},
    "10_student_grade_report.py":    {"classes": 5, "fields": 18, "methods": 18, "rels": 6},
    # ── Hard samples ─────────────────────────────────────────────
    # Java
    "11_messy_ai_style.java":        {"classes": 3, "fields": 8,  "methods": 10, "rels": 2},
    "12_complex_generics.java":      {"classes": 3, "fields": 9,  "methods": 11, "rels": 3},
    "13_deep_inheritance.java":      {"classes": 5, "fields": 13, "methods": 15, "rels": 5},
    "14_ambiguous_incomplete.java":  {"classes": 3, "fields": 9,  "methods": 11, "rels": 2},
    "15_multi_interface_web.java":   {"classes": 5, "fields": 11, "methods": 16, "rels": 7},
    # Python
    "16_messy_ai_style.py":          {"classes": 3, "fields": 9,  "methods": 10, "rels": 2},
    "17_complex_generics.py":        {"classes": 3, "fields": 10, "methods": 12, "rels": 3},
    "18_deep_inheritance.py":        {"classes": 5, "fields": 14, "methods": 15, "rels": 5},
    "19_ambiguous_incomplete.py":    {"classes": 3, "fields": 10, "methods": 11, "rels": 2},
    "20_stress_test.py":             {"classes": 6, "fields": 22, "methods": 22, "rels": 10},
}


# ─────────────────────────────────────────────────────────────────
#  PlantUML element extractor
# ─────────────────────────────────────────────────────────────────

def extract_from_plantuml(puml: str) -> Dict[str, Set[str]]:
    result = {"classes": set(), "fields": set(), "methods": set(),
              "inherits": set(), "implements": set(),
              "associates": set(), "depends_on": set()}
    if not puml:
        return result

    current_class = None
    for line in puml.splitlines():
        s = line.strip()

        m = re.match(r'^(?:abstract\s+)?(?:class|interface|enum)\s+(\w+)', s)
        if m:
            current_class = m.group(1)
            result["classes"].add(current_class)
            continue
        if s == "}":
            current_class = None
            continue

        if current_class:
            if re.match(r'^[+\-#~]', s) and "(" not in s and ":" in s:
                fm = re.match(r'^[+\-#~]\s*(?:\{.*?\}\s*)?(\w+)\s*:', s)
                if fm:
                    result["fields"].add(f"{current_class}.{fm.group(1)}")
                continue
            if re.match(r'^[+\-#~]', s) and "(" in s:
                mm = re.match(r'^[+\-#~]\s*(?:\{.*?\}\s*)?(\w+)\s*\(', s)
                if mm:
                    result["methods"].add(f"{current_class}.{mm.group(1)}")
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


# ─────────────────────────────────────────────────────────────────
#  CIR ground truth extractor
# ─────────────────────────────────────────────────────────────────

def extract_from_cir(cir: dict) -> Dict[str, Set[str]]:
    gt = {"classes": set(), "fields": set(), "methods": set(),
          "inherits": set(), "implements": set(),
          "associates": set(), "depends_on": set()}

    nodes = cir.get("nodes", [])
    edges = cir.get("edges", [])
    node_map = {n["id"]: n for n in nodes}
    type_names: Dict[str, str] = {}

    for node in nodes:
        if node.get("kind") == "TypeDecl":
            name = (node.get("attrs") or {}).get("name", node["id"])
            type_names[node["id"]] = name
            gt["classes"].add(name)

    for edge in edges:
        etype = edge.get("type", "")
        src, dst = edge.get("src", ""), edge.get("dst", "")

        if etype == "HAS_FIELD" and src in type_names:
            fn = (node_map.get(dst, {}).get("attrs") or {}).get("name", "")
            if fn:
                gt["fields"].add(f"{type_names[src]}.{fn}")
        elif etype == "HAS_METHOD" and src in type_names:
            mn = node_map.get(dst, {})
            mname = (mn.get("attrs") or {}).get("name", "")
            is_ctor = (mn.get("attrs") or {}).get("is_constructor", False)
            if mname and not is_ctor:
                gt["methods"].add(f"{type_names[src]}.{mname}")
        elif etype == "INHERITS" and src in type_names and dst in type_names:
            gt["inherits"].add(f"{type_names[src]}->{type_names[dst]}")
        elif etype == "IMPLEMENTS" and src in type_names and dst in type_names:
            gt["implements"].add(f"{type_names[src]}->{type_names[dst]}")
        elif etype == "ASSOCIATES" and src in type_names and dst in type_names:
            gt["associates"].add(f"{type_names[src]}->{type_names[dst]}")
        elif etype == "DEPENDS_ON" and src in type_names and dst in type_names:
            gt["depends_on"].add(f"{type_names[src]}->{type_names[dst]}")

    return gt


# ─────────────────────────────────────────────────────────────────
#  Metrics
# ─────────────────────────────────────────────────────────────────

def pct(a: int, b: int) -> float:
    return round(a / b * 100, 1) if b else 100.0

def compute(gt: Dict[str, Set[str]], ext: Dict[str, Set[str]]) -> dict:
    cats = ["classes", "fields", "methods",
            "inherits", "implements", "associates", "depends_on"]
    out = {}
    ttp = tfp = tfn = 0
    for cat in cats:
        g, e = gt.get(cat, set()), ext.get(cat, set())
        tp, fp, fn = len(g & e), len(e - g), len(g - e)
        ttp += tp; tfp += fp; tfn += fn
        prec = pct(tp, tp + fp)
        rec  = pct(tp, tp + fn)
        f1   = round(2*prec*rec/(prec+rec), 1) if prec+rec else 0.0
        out[cat] = {"tp": tp, "fp": fp, "fn": fn,
                    "recall": rec, "precision": prec, "f1": f1}
    prec = pct(ttp, ttp + tfp)
    rec  = pct(ttp, ttp + tfn)
    out["overall"] = {"tp": ttp, "fp": tfp, "fn": tfn,
                      "recall": rec, "precision": prec,
                      "f1": round(2*prec*rec/(prec+rec), 1) if prec+rec else 0.0}
    return out

def consistency(a: Dict[str, Set[str]], b: Dict[str, Set[str]]) -> float:
    inter = union = 0
    for cat in set(a) | set(b):
        sa, sb = a.get(cat, set()), b.get(cat, set())
        inter += len(sa & sb); union += len(sa | sb)
    return round(inter / union * 100, 1) if union else 100.0

def cir_completeness(cir_counts: dict, source_truth: dict) -> dict:
    """
    Layer 1: compares CIR element counts against hand-verified source truth.
    Returns recall per category (what fraction of source elements did /parse capture).
    """
    result = {}
    total_captured = total_expected = 0
    for key in ["classes", "fields", "methods", "rels"]:
        captured = cir_counts.get(key, 0)
        expected = source_truth.get(key, 0)
        total_captured += captured
        total_expected += expected
        result[key] = pct(min(captured, expected), expected)
    result["overall"] = pct(min(total_captured, total_expected), total_expected)
    return result


# ─────────────────────────────────────────────────────────────────
#  API calls
# ─────────────────────────────────────────────────────────────────

def call_parse(code, language, filename):
    r = requests.post(PARSE_URL,
                      json={"code": code, "filename": filename, "language": language},
                      timeout=20)
    r.raise_for_status()
    return r.json()

def call_regex(cir):
    r = requests.post(UML_REGEX_URL,
                      json={"cir": cir, "diagram_type": "class"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Regex failed: {data.get('validation_errors')}")
    return data.get("plantuml", "")

def call_ai(cir):
    r = requests.post(UML_AI_URL,
                      json={"cir": cir, "diagram_type": "class"}, timeout=45)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data.get("plantuml", "")


# ─────────────────────────────────────────────────────────────────
#  Single sample evaluator
# ─────────────────────────────────────────────────────────────────

def evaluate_one(path, lang, fname, run_ai):
    code   = open(path, encoding="utf-8").read()
    result = {"file": fname, "language": lang, "errors": []}
    source = SOURCE_TRUTH.get(fname)

    # ── Layer 1: Parse → CIR ────────────────────────────────────
    print(f"    [L1] parsing ...")
    parse_resp = call_parse(code, lang, fname)
    cir = parse_resp.get("cir", {})
    cir_gt = extract_from_cir(cir)

    cir_counts = {
        "classes": len(cir_gt["classes"]),
        "fields":  len(cir_gt["fields"]),
        "methods": len(cir_gt["methods"]),
        "rels":    sum(len(cir_gt[r]) for r in
                       ["inherits", "implements", "associates", "depends_on"])
    }
    result["cir_counts"] = cir_counts
    print(f"         CIR: {cir_counts['classes']} classes  "
          f"{cir_counts['fields']} fields  "
          f"{cir_counts['methods']} methods  "
          f"{cir_counts['rels']} rels")

    if source:
        comp = cir_completeness(cir_counts, source)
        result["cir_completeness"] = comp
        print(f"         CIR completeness vs source: {comp['overall']}%  "
              f"(classes={comp['classes']}%  fields={comp['fields']}%  "
              f"methods={comp['methods']}%  rels={comp['rels']}%)")
    else:
        print(f"         [no source truth entry for {fname}]")

    regex_ext = ai_ext = None

    # ── Layer 2: Regex UML (vs CIR ground truth) ─────────────────
    print(f"    [L2] regex UML ...")
    try:
        regex_puml = call_regex(cir)
        regex_ext  = extract_from_plantuml(regex_puml)
        result["regex"] = compute(cir_gt, regex_ext)
        r = result["regex"]["overall"]
        print(f"         recall={r['recall']}%  "
              f"precision={r['precision']}%  f1={r['f1']}%")
    except Exception as e:
        result["errors"].append(f"regex: {e}")
        print(f"         ERROR: {e}")

    # ── Layer 3: AI UML (vs CIR ground truth) ────────────────────
    if run_ai:
        print(f"    [L3] AI UML ...")
        try:
            ai_puml = call_ai(cir)
            ai_ext  = extract_from_plantuml(ai_puml)
            result["ai"] = compute(cir_gt, ai_ext)
            r = result["ai"]["overall"]
            print(f"         recall={r['recall']}%  "
                  f"precision={r['precision']}%  f1={r['f1']}%")
        except Exception as e:
            result["errors"].append(f"ai: {e}")
            print(f"         ERROR: {e}")

    if regex_ext and ai_ext:
        result["cross_consistency"] = consistency(regex_ext, ai_ext)
        print(f"         consistency (regex↔AI) = {result['cross_consistency']}%")

    return result


# ─────────────────────────────────────────────────────────────────
#  Summary printer
# ─────────────────────────────────────────────────────────────────

def avg(results, key_path):
    vals = []
    for r in results:
        obj = r
        for k in key_path:
            if not isinstance(obj, dict) or k not in obj:
                obj = None; break
            obj = obj[k]
        if obj is not None:
            vals.append(obj)
    return round(sum(vals) / len(vals), 1) if vals else 0.0

def print_summary(all_results, run_ai):
    print("\n" + "═"*72)
    print("  THREE-LAYER EVALUATION SUMMARY")
    print("═"*72)

    # Layer 1
    print("\n  LAYER 1 — CIR Completeness (source code → CIR)")
    print(f"  {'Metric':<30} {'Average':>10}")
    print(f"  {'─'*30} {'─'*10}")
    for label, key in [("Classes captured",  ["cir_completeness","classes"]),
                        ("Fields captured",   ["cir_completeness","fields"]),
                        ("Methods captured",  ["cir_completeness","methods"]),
                        ("Relations captured",["cir_completeness","rels"]),
                        ("OVERALL",           ["cir_completeness","overall"])]:
        v = avg(all_results, key)
        bar = "█" * int(v/5) + "░" * (20 - int(v/5))
        flag = "✅" if v >= 90 else ("⚠️ " if v >= 70 else "❌")
        print(f"  {label:<30} {v:>6.1f}%  {bar} {flag}")

    # Layer 2 + 3
    print(f"\n  LAYER 2 & 3 — Diagram Accuracy (CIR → PlantUML)")
    print(f"  {'Metric':<30} {'Regex':>10}    {'AI':>10}")
    print(f"  {'─'*30} {'─'*10}    {'─'*10}")

    metrics = [
        ("Overall Recall",    ["regex","overall","recall"],    ["ai","overall","recall"]),
        ("Overall Precision", ["regex","overall","precision"], ["ai","overall","precision"]),
        ("F1 Score",          ["regex","overall","f1"],        ["ai","overall","f1"]),
        ("Class Recall",      ["regex","classes","recall"],    ["ai","classes","recall"]),
        ("Field Recall",      ["regex","fields","recall"],     ["ai","fields","recall"]),
        ("Method Recall",     ["regex","methods","recall"],    ["ai","methods","recall"]),
    ]
    for label, rk, ak in metrics:
        rv = avg(all_results, rk)
        av = avg(all_results, ak) if run_ai else None
        ai_str = f"{av:>9.1f}%" if av is not None else "       N/A"
        winner = ""
        if av is not None:
            if   av > rv + 2:  winner = "  ← AI wins"
            elif rv > av + 2:  winner = "  ← Regex wins"
            else:              winner = "  ≈ tie"
        print(f"  {label:<30} {rv:>9.1f}%   {ai_str}{winner}")

    # Relationship accuracy separately
    print(f"\n  Relationship Accuracy (most revealing metric):")
    rel_cats = ["inherits", "implements", "associates", "depends_on"]
    for cat in rel_cats:
        rv = avg(all_results, ["regex", cat, "recall"])
        av = avg(all_results, ["ai",    cat, "recall"]) if run_ai else None
        ai_str = f"{av:>9.1f}%" if av is not None else "       N/A"
        print(f"    {cat:<26} {rv:>9.1f}%   {ai_str}")

    cc_vals = [r["cross_consistency"] for r in all_results if "cross_consistency" in r]
    if cc_vals:
        cc = round(sum(cc_vals)/len(cc_vals), 1)
        print(f"\n  Cross-Method Consistency       {cc:>9.1f}%")

    # Error and coverage
    valid = [r for r in all_results if not r.get("errors")]
    print(f"\n  Samples run : {len(all_results)}")
    print(f"  Successful  : {len(valid)}")
    print(f"  Errors      : {sum(len(r.get('errors',[])) for r in all_results)}")
    print("═"*72)


# ─────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────

def load_samples(filter_prefix=None):
    samples = []
    for lang, ext in [("java", ".java"), ("python", ".py")]:
        folder = os.path.join(SAMPLES_DIR, lang)
        if not os.path.exists(folder):
            continue
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith(ext):
                continue
            if filter_prefix and not fname.startswith(filter_prefix):
                continue
            samples.append((os.path.join(folder, fname), lang, fname))
    return samples

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-ai",  action="store_true")
    parser.add_argument("--sample", default=None)
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    samples = load_samples(args.sample)
    if not samples:
        print(f"No samples found (filter: {args.sample})")
        return

    print(f"\nRunning {len(samples)} sample(s)  |  AI: {'ON' if not args.no_ai else 'OFF'}\n")
    all_results = []

    for path, lang, fname in samples:
        print(f"[{lang.upper()}] {fname}")
        t0 = time.time()
        try:
            result = evaluate_one(path, lang, fname, run_ai=not args.no_ai)
        except Exception as e:
            result = {"file": fname, "language": lang, "errors": [str(e)]}
            print(f"  FATAL: {e}")
        result["elapsed_s"] = round(time.time() - t0, 1)
        all_results.append(result)
        print(f"    done in {result['elapsed_s']}s\n")

    print_summary(all_results, run_ai=not args.no_ai)

    out = os.path.join(RESULTS_DIR, "eval_results.json")
    with open(out, "w") as f:
        json.dump(all_results, f, indent=2, default=list)
    print(f"\nResults saved → {out}\n")

if __name__ == "__main__":
    main()