# evaluate_diagram_types.py
#
# Compares Regex vs AI diagram generation across all 5 diagram types:
#   class, package, sequence, component, activity
#
# For each diagram type, a different PlantUML extractor is used because
# each diagram type has different syntax and meaningful elements to compare.
#
# Scoring approach per diagram type:
#   class     → classes, fields, methods, relationships
#   package   → packages, classes-in-packages, inter-package dependencies
#   sequence  → participants, messages (method calls between participants)
#   component → components, interfaces (lollipops), connections
#   activity  → actions, decisions, swimlanes
#
# Usage:
#   python evaluate_diagram_types.py                    # all 20 samples, all 5 types
#   python evaluate_diagram_types.py --type class       # single diagram type
#   python evaluate_diagram_types.py --sample 05        # single sample
#   python evaluate_diagram_types.py --type sequence --sample 05

import argparse
import json
import os
import re
import time
from typing import Dict, List, Set, Tuple

import requests

# ── Service URLs ──────────────────────────────────────────────────────────────
PARSE_URL     = "http://127.0.0.1:7070/parse"
UML_REGEX_URL = "http://127.0.0.1:7080/uml/regex"
UML_AI_URL    = "http://127.0.0.1:7081/uml/ai"

BASE_DIR    = os.path.dirname(__file__)
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

DIAGRAM_TYPES = ["class", "package", "sequence", "component", "activity"]


# ══════════════════════════════════════════════════════════════════════════════
#  Per-diagram-type PlantUML extractors
#  Each returns a dict of sets representing the meaningful elements
#  that can be compared between regex and AI outputs.
# ══════════════════════════════════════════════════════════════════════════════

def extract_class(puml: str) -> Dict[str, Set[str]]:
    """Extract classes, fields, methods, relationships from class diagram."""
    result = {k: set() for k in
              ["classes","fields","methods","inherits","implements","associates","depends_on"]}
    if not puml:
        return result
    current_class = None
    for line in puml.splitlines():
        s = line.strip()
        m = re.match(r'^(?:abstract\s+)?(?:class|interface|enum)\s+(\w[\w.]*)', s)
        if m:
            current_class = m.group(1).split(".")[-1]  # short name
            result["classes"].add(current_class)
            continue
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


def extract_package(puml: str) -> Dict[str, Set[str]]:
    """Extract packages, type memberships, and inter-package dependencies."""
    result = {"packages": set(), "members": set(), "dependencies": set()}
    if not puml:
        return result
    current_pkg = None
    for line in puml.splitlines():
        s = line.strip()
        # Package declaration: package "com.example.service" {
        pm = re.match(r'^package\s+"?([^"{\s]+)"?\s*(?:<<\w+>>\s*)?\{?', s)
        if pm:
            current_pkg = pm.group(1)
            result["packages"].add(current_pkg)
            continue
        if s == "}" and current_pkg:
            current_pkg = None
            continue
        # Type inside package: class Foo  or  interface Bar
        if current_pkg:
            tm = re.match(r'^(?:class|interface|enum)\s+(\w+)', s)
            if tm:
                result["members"].add(f"{current_pkg}::{tm.group(1)}")
                continue
        # Dependency arrows outside packages
        dm = re.match(r'^(\w+)\s*(?:-->|\.\.>|--|\.\.|<--)\s*(\w+)', s)
        if dm:
            result["dependencies"].add(f"{dm.group(1)}->{dm.group(2)}")
    return result


def extract_sequence(puml: str) -> Dict[str, Set[str]]:
    """Extract participants and messages from sequence diagram."""
    result = {"participants": set(), "messages": set()}
    if not puml:
        return result
    participant_aliases = {}  # alias -> name
    for line in puml.splitlines():
        s = line.strip()
        # Participant declarations: actor "Client" as C  or  boundary Controller as Ctrl
        pm = re.match(
            r'^(?:actor|boundary|control|entity|database|participant)\s+'
            r'"?([^"]+)"?\s+as\s+(\w+)', s)
        if pm:
            name, alias = pm.group(1).strip(), pm.group(2).strip()
            participant_aliases[alias] = name
            result["participants"].add(name)
            continue
        # Also plain: participant Foo
        pm2 = re.match(r'^(?:actor|boundary|control|entity|database|participant)\s+(\w+)', s)
        if pm2:
            name = pm2.group(1)
            participant_aliases[name] = name
            result["participants"].add(name)
            continue
        # Messages: A -> B : label  or  A --> B : label
        mm = re.match(r'^(\w+)\s*-+>+\s*(\w+)\s*:\s*(.+)', s)
        if mm:
            src   = participant_aliases.get(mm.group(1), mm.group(1))
            dst   = participant_aliases.get(mm.group(2), mm.group(2))
            label = mm.group(3).strip()
            # Normalize label: extract method name only (ignore params)
            method = re.match(r'(\w+)\s*[\(:]?', label)
            if method:
                result["messages"].add(f"{src}->{dst}:{method.group(1)}")
    return result


def extract_component(puml: str) -> Dict[str, Set[str]]:
    """Extract components, interfaces (lollipops), and connections."""
    result = {"components": set(), "interfaces": set(), "connections": set()}
    if not puml:
        return result
    for line in puml.splitlines():
        s = line.strip()
        # Component: [StudentController] as t_Ctrl  or  [Foo]
        cm = re.match(r'^\[([^\]]+)\](?:\s+as\s+(\w+))?', s)
        if cm:
            name = cm.group(1).strip()
            result["components"].add(name)
            continue
        # Lollipop interface: () "InterfaceName" as I_alias
        im = re.match(r'^\(\)\s+"?([^"]+)"?\s+as\s+(\w+)', s)
        if im:
            result["interfaces"].add(im.group(1).strip())
            continue
        # Connection arrows: alias --> I_alias : label
        conn = re.match(r'^(\w+)\s*-->\s*(\w+)(?:\s*:\s*(.+))?', s)
        if conn:
            result["connections"].add(f"{conn.group(1)}->{conn.group(2)}")
    return result


def extract_activity(puml: str) -> Dict[str, Set[str]]:
    """Extract actions, decisions, and swimlanes from activity diagram."""
    result = {"actions": set(), "decisions": set(), "swimlanes": set()}
    if not puml:
        return result
    for line in puml.splitlines():
        s = line.strip()
        # Swimlane: |LaneName|
        sl = re.match(r'^\|([^|]+)\|', s)
        if sl:
            result["swimlanes"].add(sl.group(1).strip())
            continue
        # Action: :Some action;
        am = re.match(r'^:(.+);$', s)
        if am:
            label = am.group(1).strip()
            # Normalize: extract method name if present (ClassName.method(...))
            method = re.match(r'(?:\w+\.)?(\w+)\s*[\(:]?', label)
            if method and method.group(1) not in ('if','else','endif','fork','end'):
                result["actions"].add(method.group(1))
            continue
        # Decision diamond: if (condition?) then
        dm = re.match(r'^if\s+\((.+?)\??\)', s)
        if dm:
            result["decisions"].add(dm.group(1).strip())
    return result


EXTRACTORS = {
    "class":     extract_class,
    "package":   extract_package,
    "sequence":  extract_sequence,
    "component": extract_component,
    "activity":  extract_activity,
}


# ══════════════════════════════════════════════════════════════════════════════
#  Metrics
# ══════════════════════════════════════════════════════════════════════════════

def pct(a, b): return round(a/b*100, 1) if b else 100.0

def compute(gt: Dict[str,Set], pred: Dict[str,Set]) -> dict:
    ttp = tfp = tfn = 0
    out = {}
    for cat in gt:
        g, p = gt.get(cat, set()), pred.get(cat, set())
        tp, fp, fn = len(g&p), len(p-g), len(g-p)
        ttp+=tp; tfp+=fp; tfn+=fn
        pr=pct(tp,tp+fp); re_=pct(tp,tp+fn)
        out[cat] = {"tp":tp,"fp":fp,"fn":fn,"recall":re_,"precision":pr,
                    "f1":round(2*pr*re_/(pr+re_),1) if pr+re_ else 0.0}
    pr=pct(ttp,ttp+tfp); re_=pct(ttp,ttp+tfn)
    out["overall"] = {"tp":ttp,"fp":tfp,"fn":tfn,"recall":re_,"precision":pr,
                      "f1":round(2*pr*re_/(pr+re_),1) if pr+re_ else 0.0}
    return out

def consistency(a: Dict[str,Set], b: Dict[str,Set]) -> float:
    inter=union=0
    for cat in set(a)|set(b):
        sa,sb = a.get(cat,set()), b.get(cat,set())
        inter+=len(sa&sb); union+=len(sa|sb)
    return round(inter/union*100,1) if union else 100.0


# ══════════════════════════════════════════════════════════════════════════════
#  API helpers
# ══════════════════════════════════════════════════════════════════════════════

def call_parse(code, language, filename):
    r = requests.post(PARSE_URL,
                      json={"code":code,"filename":filename,"language":language},
                      timeout=20)
    r.raise_for_status()
    return r.json()

def call_regex(cir, diagram_type):
    r = requests.post(UML_REGEX_URL,
                      json={"cir":cir,"diagram_type":diagram_type}, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Regex failed: {data.get('validation_errors')}")
    return data.get("plantuml","")

def call_ai(cir, diagram_type):
    r = requests.post(UML_AI_URL,
                      json={"cir":cir,"diagram_type":diagram_type}, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data.get("plantuml","")


# ══════════════════════════════════════════════════════════════════════════════
#  Single sample evaluator
# ══════════════════════════════════════════════════════════════════════════════

def evaluate_one(path, lang, fname, diagram_types_to_run):
    code   = open(path, encoding="utf-8").read()
    result = {"file": fname, "language": lang, "errors": [], "diagrams": {}}

    # Parse once to get CIR
    try:
        parse_resp = call_parse(code, lang, fname)
        cir = parse_resp.get("cir", {})
    except Exception as e:
        result["errors"].append(f"parse: {e}")
        print(f"    PARSE ERROR: {e}")
        return result

    # For each diagram type
    for dtype in diagram_types_to_run:
        extractor = EXTRACTORS[dtype]
        dr = {"regex": None, "ai": None, "consistency": None, "errors": []}

        # Regex
        try:
            regex_puml = call_regex(cir, dtype)
            regex_ext  = extractor(regex_puml)
            dr["regex_raw"] = regex_puml
        except Exception as e:
            dr["errors"].append(f"regex: {e}")
            regex_ext = None

        # AI
        try:
            ai_puml = call_ai(cir, dtype)
            ai_ext  = extractor(ai_puml)
            dr["ai_raw"] = ai_puml
        except Exception as e:
            dr["errors"].append(f"ai: {e}")
            ai_ext = None

        # Compare regex vs AI using regex output as reference ground truth
        # (Both are generating from the same CIR, so regex acts as the
        # deterministic reference — AI is evaluated against what regex found)
        if regex_ext and ai_ext:
            dr["regex_vs_ai"] = compute(regex_ext, ai_ext)
            dr["consistency"] = consistency(regex_ext, ai_ext)

            ov = dr["regex_vs_ai"]["overall"]
            cons = dr["consistency"]
            print(f"    [{dtype:<10}] "
                  f"AI recall={ov['recall']}%  "
                  f"AI precision={ov['precision']}%  "
                  f"AI f1={ov['f1']}%  "
                  f"consistency={cons}%")
        else:
            if regex_ext is None:
                print(f"    [{dtype:<10}] regex FAILED")
            if ai_ext is None:
                print(f"    [{dtype:<10}] AI FAILED")

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
            if not isinstance(obj, dict) or k not in obj:
                obj = None; break
            obj = obj[k]
        if obj is not None:
            vals.append(obj)
    return round(sum(vals)/len(vals), 1) if vals else None

def print_summary(all_results, diagram_types):
    print("\n" + "═"*76)
    print("  REGEX vs AI COMPARISON — ALL DIAGRAM TYPES")
    print("  (AI metrics measured against regex as deterministic reference)")
    print("═"*76)

    # Per diagram type summary
    print(f"\n  {'Diagram Type':<14} {'AI Recall':>11} {'AI Precision':>14} {'AI F1':>8} {'Consistency':>13}")
    print(f"  {'─'*14} {'─'*11} {'─'*14} {'─'*8} {'─'*13}")

    type_summaries = {}
    for dtype in diagram_types:
        recall = avg(all_results, ["diagrams", dtype, "regex_vs_ai", "overall", "recall"])
        prec   = avg(all_results, ["diagrams", dtype, "regex_vs_ai", "overall", "precision"])
        f1     = avg(all_results, ["diagrams", dtype, "regex_vs_ai", "overall", "f1"])
        cons   = avg(all_results, ["diagrams", dtype, "consistency"])

        type_summaries[dtype] = {"recall":recall,"precision":prec,"f1":f1,"consistency":cons}

        r_str    = f"{recall}%"    if recall is not None    else "N/A"
        p_str    = f"{prec}%"      if prec is not None      else "N/A"
        f1_str   = f"{f1}%"        if f1 is not None        else "N/A"
        cons_str = f"{cons}%"      if cons is not None      else "N/A"

        # Flag whether AI matches regex well or not
        flag = ""
        if f1 is not None:
            if f1 >= 95:   flag = "✅ strong agreement"
            elif f1 >= 80: flag = "⚠️  moderate agreement"
            else:          flag = "❌ significant divergence"

        print(f"  {dtype:<14} {r_str:>11} {p_str:>14} {f1_str:>8} {cons_str:>13}  {flag}")

    # Element-level breakdown per diagram type
    element_keys = {
        "class":     ["classes","fields","methods","inherits","implements","associates","depends_on"],
        "package":   ["packages","members","dependencies"],
        "sequence":  ["participants","messages"],
        "component": ["components","interfaces","connections"],
        "activity":  ["actions","decisions","swimlanes"],
    }

    for dtype in diagram_types:
        keys = element_keys.get(dtype, [])
        if not keys:
            continue
        print(f"\n  {dtype.upper()} DIAGRAM — Element-level AI accuracy vs Regex:")
        print(f"  {'Element':<20} {'AI Recall':>11} {'AI F1':>8}")
        print(f"  {'─'*20} {'─'*11} {'─'*8}")
        for key in keys:
            rec = avg(all_results, ["diagrams", dtype, "regex_vs_ai", key, "recall"])
            f1  = avg(all_results, ["diagrams", dtype, "regex_vs_ai", key, "f1"])
            r_s = f"{rec}%" if rec is not None else "N/A"
            f_s = f"{f1}%"  if f1  is not None else "N/A"
            print(f"  {key:<20} {r_s:>11} {f_s:>8}")

    # Per-sample breakdown for class diagram (most detailed)
    print(f"\n  PER-SAMPLE CLASS DIAGRAM — AI F1 vs Regex reference:")
    print(f"  {'File':<42} {'AI F1':>8} {'Consistency':>13}")
    print(f"  {'─'*42} {'─'*8} {'─'*13}")
    for r in all_results:
        f1   = r.get("diagrams",{}).get("class",{}).get("regex_vs_ai",{}).get("overall",{}).get("f1","N/A")
        cons = r.get("diagrams",{}).get("class",{}).get("consistency","N/A")
        print(f"  {r['file']:<42} {str(f1):>8}%  {str(cons):>12}%")

    # Key findings
    print(f"\n{'═'*76}")
    print(f"  KEY FINDINGS:")
    for dtype in diagram_types:
        s = type_summaries[dtype]
        if s["f1"] is not None:
            if s["f1"] >= 95:
                insight = "regex and AI are largely interchangeable"
            elif s["f1"] >= 80:
                insight = "AI shows moderate divergence from regex — semantic differences"
            else:
                insight = "AI diverges significantly — AI adds/infers elements regex cannot"
            print(f"  {dtype:<12}: AI F1={s['f1']}%  → {insight}")
    print("═"*76)

    # Overall recommendation
    all_f1s = [type_summaries[d]["f1"] for d in diagram_types if type_summaries[d]["f1"] is not None]
    if all_f1s:
        overall = round(sum(all_f1s)/len(all_f1s), 1)
        print(f"\n  Average AI-Regex agreement across all diagram types: {overall}%")
        if overall >= 95:
            print("  → Both methods produce very consistent results across diagram types.")
            print("    Dual-mode value: validation and fallback rather than complementary outputs.")
        elif overall >= 80:
            print("  → Methods agree on structure but diverge on semantic elements.")
            print("    Dual-mode value: regex for precision, AI for richer semantic diagrams.")
        else:
            print("  → Methods produce meaningfully different outputs.")
            print("    Dual-mode value: each method captures elements the other misses.")
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
            if filter_prefix and not fname.startswith(filter_prefix): continue
            samples.append((os.path.join(folder, fname), lang, fname))
    return samples

def main():
    parser = argparse.ArgumentParser(
        description="Compare regex vs AI across all 5 UML diagram types"
    )
    parser.add_argument("--type",   default=None,
                        help="Single diagram type to run (class/package/sequence/component/activity)")
    parser.add_argument("--sample", default=None,
                        help="Filter samples by prefix (e.g. '05')")
    args = parser.parse_args()

    diagram_types = [args.type] if args.type else DIAGRAM_TYPES

    # Validate
    for dt in diagram_types:
        if dt not in DIAGRAM_TYPES:
            print(f"Unknown diagram type '{dt}'. Choose from: {DIAGRAM_TYPES}")
            return

    os.makedirs(RESULTS_DIR, exist_ok=True)
    samples = load_samples(args.sample)
    if not samples:
        print("No samples found."); return

    print(f"\nRegex vs AI — {len(samples)} sample(s) × {len(diagram_types)} diagram type(s)\n")

    all_results = []
    for path, lang, fname in samples:
        print(f"[{lang.upper()}] {fname}")
        t0 = time.time()
        try:
            result = evaluate_one(path, lang, fname, diagram_types)
        except Exception as e:
            result = {"file":fname,"language":lang,"errors":[str(e)],"diagrams":{}}
            print(f"  FATAL: {e}")
        result["elapsed_s"] = round(time.time()-t0, 1)
        all_results.append(result)
        print(f"    done in {result['elapsed_s']}s\n")

    print_summary(all_results, diagram_types)

    out = os.path.join(RESULTS_DIR, "diagram_type_comparison.json")
    with open(out, "w") as f:
        json.dump(all_results, f, indent=2, default=list)
    print(f"Results → {out}\n")

if __name__ == "__main__":
    main()