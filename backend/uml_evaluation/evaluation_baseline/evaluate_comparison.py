# evaluate_comparison.py  (v2)
#
# Side-by-side comparison:
#   Pipeline A — CIR-based  : source → AST → CIR → /parse API → regex UML
#   Pipeline B — Baseline   : source → direct regex (no AST, no CIR)
#
# Ground truth = CIR output from Pipeline A.
#
# Usage:
#   python evaluate_comparison.py              # all 6 challenging samples
#   python evaluate_comparison.py --sample 21  # single sample by prefix

import argparse
import json
import os
import re
import sys
import time
from typing import Dict, List, Set

import requests

PARSE_URL     = "http://127.0.0.1:7070/parse"
UML_REGEX_URL = "http://127.0.0.1:7080/uml/regex"

BASE_DIR    = os.path.dirname(__file__)
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

# Hand-verified ground truth for all 6 samples
SOURCE_TRUTH = {
    # Java
    "21_multiline_declarations.java":        {"classes": 3, "fields": 8,  "methods": 9,  "rels": 3},
    "22_nested_generics_complex.java":        {"classes": 3, "fields": 10, "methods": 10, "rels": 4},
    "23_anonymous_inner_classes.java":        {"classes": 3, "fields": 9,  "methods": 11, "rels": 3},
    # Python (v2 — designed to show clear baseline gap)
    "24_dynamic_fields_outside_init.py":      {"classes": 3, "fields": 12, "methods": 13, "rels": 3},
    "25_dataclass_and_property_fields.py":    {"classes": 3, "fields": 14, "methods": 11, "rels": 4},
    "26_constructor_injection_and_singletons.py": {"classes": 4, "fields": 11, "methods": 14, "rels": 5},
}

sys.path.insert(0, BASE_DIR)
from baseline_regex_java   import parse_java
from baseline_regex_python import parse_python


# ── PlantUML extractor ────────────────────────────────────────────────────────

def extract_from_plantuml(puml: str) -> Dict[str, Set[str]]:
    result = {k: set() for k in
              ["classes","fields","methods","inherits","implements","associates","depends_on"]}
    if not puml:
        return result
    current_class = None
    for line in puml.splitlines():
        s = line.strip()
        m = re.match(r'^(?:abstract\s+)?(?:class|interface|enum)\s+(\w+)', s)
        if m:
            current_class = m.group(1); result["classes"].add(current_class); continue
        if s == "}":
            current_class = None; continue
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


# ── CIR ground truth extractor ────────────────────────────────────────────────

def extract_from_cir(cir: dict) -> Dict[str, Set[str]]:
    gt = {k: set() for k in
          ["classes","fields","methods","inherits","implements","associates","depends_on"]}
    nodes    = cir.get("nodes", [])
    edges    = cir.get("edges", [])
    node_map = {n["id"]: n for n in nodes}
    type_names: Dict[str, str] = {}
    for node in nodes:
        if node.get("kind") == "TypeDecl":
            name = (node.get("attrs") or {}).get("name", node["id"])
            type_names[node["id"]] = name
            gt["classes"].add(name)
    for edge in edges:
        etype = edge.get("type","")
        src, dst = edge.get("src",""), edge.get("dst","")
        if etype == "HAS_FIELD" and src in type_names:
            fn = (node_map.get(dst,{}).get("attrs") or {}).get("name","")
            if fn: gt["fields"].add(f"{type_names[src]}.{fn}")
        elif etype == "HAS_METHOD" and src in type_names:
            mn     = node_map.get(dst,{})
            mname  = (mn.get("attrs") or {}).get("name","")
            is_ctor= (mn.get("attrs") or {}).get("is_constructor", False)
            if mname and not is_ctor:
                gt["methods"].add(f"{type_names[src]}.{mname}")
        elif etype == "INHERITS"   and src in type_names and dst in type_names:
            gt["inherits"].add(f"{type_names[src]}->{type_names[dst]}")
        elif etype == "IMPLEMENTS" and src in type_names and dst in type_names:
            gt["implements"].add(f"{type_names[src]}->{type_names[dst]}")
        elif etype == "ASSOCIATES" and src in type_names and dst in type_names:
            gt["associates"].add(f"{type_names[src]}->{type_names[dst]}")
        elif etype == "DEPENDS_ON" and src in type_names and dst in type_names:
            gt["depends_on"].add(f"{type_names[src]}->{type_names[dst]}")
    return gt


# ── Metrics ───────────────────────────────────────────────────────────────────

def pct(a, b): return round(a/b*100, 1) if b else 100.0

def compute(gt, ext):
    cats = ["classes","fields","methods","inherits","implements","associates","depends_on"]
    out  = {}
    ttp = tfp = tfn = 0
    for cat in cats:
        g,e = gt.get(cat,set()), ext.get(cat,set())
        tp,fp,fn = len(g&e), len(e-g), len(g-e)
        ttp+=tp; tfp+=fp; tfn+=fn
        pr=pct(tp,tp+fp); re_=pct(tp,tp+fn)
        out[cat] = {"tp":tp,"fp":fp,"fn":fn,"recall":re_,"precision":pr,
                    "f1":round(2*pr*re_/(pr+re_),1) if pr+re_ else 0.0}
    pr=pct(ttp,ttp+tfp); re_=pct(ttp,ttp+tfn)
    out["overall"] = {"tp":ttp,"fp":tfp,"fn":tfn,"recall":re_,"precision":pr,
                      "f1":round(2*pr*re_/(pr+re_),1) if pr+re_ else 0.0}
    return out

def consistency(a, b):
    inter=union=0
    for cat in set(a)|set(b):
        sa,sb = a.get(cat,set()), b.get(cat,set())
        inter+=len(sa&sb); union+=len(sa|sb)
    return round(inter/union*100,1) if union else 100.0


# ── API helpers ───────────────────────────────────────────────────────────────

def call_parse(code, language, filename):
    r = requests.post(PARSE_URL,
                      json={"code":code,"filename":filename,"language":language},
                      timeout=20)
    r.raise_for_status()
    return r.json()

def call_regex_uml(cir):
    r = requests.post(UML_REGEX_URL,
                      json={"cir":cir,"diagram_type":"class"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Regex UML failed: {data.get('validation_errors')}")
    return data.get("plantuml","")


# ── Single-sample evaluator ───────────────────────────────────────────────────

def evaluate_one(path, lang, fname):
    code   = open(path, encoding="utf-8").read()
    result = {"file": fname, "language": lang, "errors": []}

    # Pipeline A: CIR-based
    print(f"    [A] CIR pipeline ...")
    cir_gt = ext_a = None
    try:
        parse_resp = call_parse(code, lang, fname)
        cir        = parse_resp.get("cir", {})
        cir_gt     = extract_from_cir(cir)
        puml_a     = call_regex_uml(cir)
        ext_a      = extract_from_plantuml(puml_a)
        metrics_a  = compute(cir_gt, ext_a)
        result["pipeline_a"] = metrics_a
        ov = metrics_a["overall"]
        print(f"         recall={ov['recall']}%  precision={ov['precision']}%  f1={ov['f1']}%")
        result["cir_counts"] = {
            "classes": len(cir_gt["classes"]),
            "fields":  len(cir_gt["fields"]),
            "methods": len(cir_gt["methods"]),
            "rels":    sum(len(cir_gt[r]) for r in
                          ["inherits","implements","associates","depends_on"])
        }
        # CIR completeness vs source truth
        st = SOURCE_TRUTH.get(fname)
        if st:
            cc = result["cir_counts"]
            comp_overall = pct(
                min(cc["classes"],st["classes"]) + min(cc["fields"],st["fields"]) +
                min(cc["methods"],st["methods"]) + min(cc["rels"],st["rels"]),
                st["classes"] + st["fields"] + st["methods"] + st["rels"]
            )
            print(f"         CIR completeness vs source: {comp_overall}%  "
                  f"(classes={pct(min(cc['classes'],st['classes']),st['classes'])}%  "
                  f"fields={pct(min(cc['fields'],st['fields']),st['fields'])}%  "
                  f"methods={pct(min(cc['methods'],st['methods']),st['methods'])}%  "
                  f"rels={pct(min(cc['rels'],st['rels']),st['rels'])}%)")
    except Exception as e:
        result["errors"].append(f"pipeline_a: {e}")
        print(f"         ERROR: {e}")

    # Pipeline B: Baseline regex
    print(f"    [B] Baseline regex ...")
    ext_b = None
    try:
        ext_b = parse_java(code) if lang == "java" else parse_python(code)
        if cir_gt:
            metrics_b = compute(cir_gt, ext_b)
            result["pipeline_b"] = metrics_b
            ov = metrics_b["overall"]
            print(f"         recall={ov['recall']}%  precision={ov['precision']}%  f1={ov['f1']}%")
        else:
            print(f"         SKIPPED (no CIR ground truth)")
    except Exception as e:
        result["errors"].append(f"pipeline_b: {e}")
        print(f"         ERROR: {e}")

    if ext_a and ext_b:
        result["cross_consistency"] = consistency(ext_a, ext_b)
        print(f"         consistency (CIR↔Baseline) = {result['cross_consistency']}%")

    # Gap analysis
    if cir_gt and ext_b:
        gaps = {}
        for cat in ["classes","fields","methods","inherits","implements","associates","depends_on"]:
            missed = cir_gt.get(cat,set()) - ext_b.get(cat,set())
            extra  = ext_b.get(cat,set())  - cir_gt.get(cat,set())
            if missed or extra:
                gaps[cat] = {"missed": sorted(missed), "extra": sorted(extra)}
        result["baseline_gaps"] = gaps
        if gaps:
            print(f"         Baseline gaps:")
            for cat, g in gaps.items():
                if g["missed"]:
                    print(f"           {cat} missed: {g['missed']}")
                if g["extra"]:
                    print(f"           {cat} extra:  {g['extra']}")

    return result


# ── Summary ───────────────────────────────────────────────────────────────────

def avg(results, key_path):
    vals = []
    for r in results:
        obj = r
        for k in key_path:
            if not isinstance(obj,dict) or k not in obj: obj=None; break
            obj = obj[k]
        if obj is not None: vals.append(obj)
    return round(sum(vals)/len(vals),1) if vals else 0.0

def print_summary(all_results):
    print("\n" + "═"*76)
    print("  COMPARISON SUMMARY: CIR-Based Pipeline (A) vs Baseline Regex (B)")
    print("═"*76)

    metrics = [
        ("Overall Recall",    ["pipeline_a","overall","recall"],    ["pipeline_b","overall","recall"]),
        ("Overall Precision", ["pipeline_a","overall","precision"], ["pipeline_b","overall","precision"]),
        ("F1 Score",          ["pipeline_a","overall","f1"],        ["pipeline_b","overall","f1"]),
        ("Class Recall",      ["pipeline_a","classes","recall"],    ["pipeline_b","classes","recall"]),
        ("Field Recall",      ["pipeline_a","fields","recall"],     ["pipeline_b","fields","recall"]),
        ("Method Recall",     ["pipeline_a","methods","recall"],    ["pipeline_b","methods","recall"]),
    ]

    print(f"\n  {'Metric':<32} {'CIR Pipeline (A)':>18}   {'Baseline (B)':>14}   {'Gap':>8}")
    print(f"  {'─'*32} {'─'*18}   {'─'*14}   {'─'*8}")
    for label, ak, bk in metrics:
        av  = avg(all_results, ak)
        bv  = avg(all_results, bk)
        gap = round(av-bv, 1)
        gs  = f"+{gap}%" if gap > 0 else f"{gap}%"
        win = "✅ A wins" if gap > 2 else ("≈ tie" if abs(gap)<=2 else "⚠️  B wins")
        print(f"  {label:<32} {av:>17.1f}%   {bv:>13.1f}%   {gs:>6}  {win}")

    print(f"\n  Relationship Accuracy (most sensitive to CIR advantage):")
    for cat in ["inherits","implements","associates","depends_on"]:
        av = avg(all_results, ["pipeline_a",cat,"recall"])
        bv = avg(all_results, ["pipeline_b",cat,"recall"])
        gap = round(av-bv,1)
        gs = f"+{gap}%" if gap > 0 else f"{gap}%"
        print(f"    {cat:<28} A={av:>6.1f}%   B={bv:>6.1f}%   gap={gs}")

    cc_vals = [r["cross_consistency"] for r in all_results if "cross_consistency" in r]
    if cc_vals:
        print(f"\n  Cross-method consistency (A↔B)   {round(sum(cc_vals)/len(cc_vals),1):>6.1f}%")

    print(f"\n  Per-Sample F1 Breakdown:")
    print(f"  {'File':<48} {'A (CIR)':>8}   {'B (Base)':>8}   {'Gap':>6}")
    print(f"  {'─'*48} {'─'*8}   {'─'*8}   {'─'*6}")
    for r in all_results:
        af1 = r.get("pipeline_a",{}).get("overall",{}).get("f1","ERR")
        bf1 = r.get("pipeline_b",{}).get("overall",{}).get("f1","ERR")
        gs  = f"+{round(af1-bf1,1)}" if isinstance(af1,float) and isinstance(bf1,float) else "N/A"
        print(f"  {r['file']:<48} {str(af1):>8}   {str(bf1):>8}   {gs:>6}")

    print(f"\n  Samples: {len(all_results)}  |  Errors: {sum(len(r.get('errors',[])) for r in all_results)}")

    oa = avg(all_results, ["pipeline_a","overall","f1"])
    ob = avg(all_results, ["pipeline_b","overall","f1"])
    print(f"\n{'═'*76}")
    print(f"  KEY FINDING:")
    print(f"  CIR-based pipeline F1  : {oa}%")
    print(f"  Baseline regex F1      : {ob}%")
    print(f"  Improvement from CIR   : +{round(oa-ob,1)}%")
    print("═"*76)


# ── Entry point ───────────────────────────────────────────────────────────────

def load_samples(filter_prefix=None):
    samples = []
    for lang, ext in [("java",".java"),("python",".py")]:
        folder = os.path.join(SAMPLES_DIR, lang)
        if not os.path.exists(folder): continue
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith(ext): continue
            if filter_prefix and not fname.startswith(filter_prefix): continue
            samples.append((os.path.join(folder, fname), lang, fname))
    return samples

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", default=None)
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    samples = load_samples(args.sample)
    if not samples:
        print("No samples found."); return

    print(f"\nComparing CIR Pipeline (A) vs Baseline Regex (B) — {len(samples)} sample(s)\n")
    all_results = []

    for path, lang, fname in samples:
        print(f"[{lang.upper()}] {fname}")
        t0 = time.time()
        try:
            result = evaluate_one(path, lang, fname)
        except Exception as e:
            result = {"file": fname, "language": lang, "errors": [str(e)]}
            print(f"  FATAL: {e}")
        result["elapsed_s"] = round(time.time()-t0, 1)
        all_results.append(result)
        print(f"    done in {result['elapsed_s']}s\n")

    print_summary(all_results)

    out = os.path.join(RESULTS_DIR, "comparison_results.json")
    with open(out,"w") as f:
        json.dump(all_results, f, indent=2, default=list)
    print(f"\nResults → {out}\n")

if __name__ == "__main__":
    main()