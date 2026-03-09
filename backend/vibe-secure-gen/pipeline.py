# backend/vibe-secure-gen/pipeline.py

"""
Pipeline stages:
  1. Prompt sanitization & enhancement
  2. LLM code generation
  3. Semgrep SAST scan + autofix
  4. LLM fix for remaining SAST issues
  5. DAST — calls dast-service on :7095
  6. LLM re-fix for critical DAST findings
  7. UML generation
"""

from typing import Dict, Any

from stages.prompt           import enhance_prompt
from stages.prompt_firewall  import sanitize_prompt
from stages.llm              import stream_code
from stages.semgrep_smart_fix import run_semgrep_smart_fix
from stages.llm_fix          import fix_with_llm
from stages.dast_client      import call_dast_service      # ← calls :7095
from stages.uml_pipeline     import run_uml_pipeline_over_blob


# ─────────────────────────────────────────────────────────────────────────────
#  Terminal pretty-print helpers
# ─────────────────────────────────────────────────────────────────────────────

_W = 80  # box width

def _box_line(text: str, width: int = _W) -> str:
    padded = f"  {text}"
    return f"║{padded:<{width - 2}}║"

def _divider(char: str = "─", width: int = _W) -> str:
    return "  " + char * (width - 4)

def _print_prompt_box(label: str, content: str) -> None:
    """Print a titled box with wrapped content."""
    bar = "═" * (_W - 2)
    print(f"\n╔{bar}╗")
    print(_box_line(f"  {label}"))
    print(f"╠{bar}╣")
    # Print content lines, wrapping long lines
    for raw_line in content.splitlines():
        # Wrap at width - 4 chars
        while len(raw_line) > _W - 4:
            print(_box_line(raw_line[:_W - 4]))
            raw_line = raw_line[_W - 4:]
        print(_box_line(raw_line))
    print(f"╚{bar}╝")


SEV_ICON = {
    "CRITICAL": "🔴",
    "ERROR":    "🔴",
    "HIGH":     "🟠",
    "WARNING":  "🟡",
    "MEDIUM":   "🟡",
    "LOW":      "🔵",
    "INFO":     "⚪",
}

SEV_ORDER = {"CRITICAL": 0, "ERROR": 0, "HIGH": 1, "WARNING": 2, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def _print_sast_findings(findings: list, title: str = "SAST Findings") -> None:
    """Print a detailed, formatted table of SAST findings."""
    if not findings:
        print(f"   ✔ No findings to display")
        return

    # Sort by severity
    sorted_findings = sorted(
        findings,
        key=lambda f: SEV_ORDER.get(f.get("severity", "INFO").upper(), 99)
    )

    bar = "═" * (_W - 2)
    thin = "─" * (_W - 2)
    print(f"\n╔{bar}╗")
    header = f"  {title}  ({len(findings)} total)"
    print(f"║{header:<{_W - 2}}║")
    print(f"╠{bar}╣")

    # Severity summary
    sev_counts: Dict[str, int] = {}
    for f in findings:
        s = f.get("severity", "INFO").upper()
        sev_counts[s] = sev_counts.get(s, 0) + 1

    summary_parts = []
    for sev in ["CRITICAL", "ERROR", "HIGH", "MEDIUM", "WARNING", "LOW", "INFO"]:
        if sev in sev_counts:
            icon = SEV_ICON.get(sev, "⚪")
            summary_parts.append(f"{icon} {sev}: {sev_counts[sev]}")
    summary_line = "  " + "   ".join(summary_parts)
    print(f"║{summary_line:<{_W - 2}}║")
    print(f"╠{bar}╣")

    for i, finding in enumerate(sorted_findings, 1):
        sev      = (finding.get("severity") or "INFO").upper()
        icon     = SEV_ICON.get(sev, "⚪")
        check_id = finding.get("check_id") or "unknown"
        message  = finding.get("message") or "No description"
        path     = finding.get("path") or ""
        line_no  = (finding.get("start") or {}).get("line")
        metadata = finding.get("metadata") or {}
        owasp    = metadata.get("owasp") or finding.get("owasp") or ""
        cwe      = metadata.get("cwe")  or finding.get("cwe")  or ""
        has_fix  = finding.get("has_autofix", False)

        # Finding header
        idx_line = f"  #{i}  {icon} {sev:<8}  {check_id}"
        print(f"║{idx_line:<{_W - 2}}║")

        # File + line
        if path:
            loc = path
            if line_no:
                loc += f"  :  line {line_no}"
            loc_line = f"      📄 {loc}"
            print(f"║{loc_line:<{_W - 2}}║")

        # Message (wrap if long)
        msg_prefix = "      💬 "
        full_msg   = msg_prefix + message
        while len(full_msg) > _W - 4:
            print(f"║{full_msg[:_W - 4]:<{_W - 2}}║")
            full_msg = "         " + full_msg[_W - 4:]
        print(f"║{full_msg:<{_W - 2}}║")

        # OWASP / CWE / autofix tags
        tags = []
        if owasp:
            tags.append(f"OWASP: {owasp}")
        if cwe:
            tags.append(f"CWE: {cwe}")
        if has_fix:
            tags.append("🔧 auto-fixable")
        if tags:
            tag_line = "      🏷  " + "   │   ".join(tags)
            print(f"║{tag_line:<{_W - 2}}║")

        # Separator between findings (not after last)
        if i < len(sorted_findings):
            sep = f"  {thin}"
            print(f"║{'  ' + '·' * (_W - 4):<{_W - 2}}║")

    print(f"╚{bar}╝")


# ─────────────────────────────────────────────────────────────────────────────
#  Pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def run_pipeline(prompt: str) -> Dict[str, Any]:

    print("=" * _W)
    print("🔒 SECURE CODE GENERATION PIPELINE")
    print("=" * _W)

    # ── Stage 1: Prompt ───────────────────────────────────────────────────
    print("\n📝 Stage 1: Processing prompt...")
    safe_prompt     = sanitize_prompt(prompt or "")
    enhanced        = enhance_prompt(safe_prompt)
    hardened_prompt = enhanced["text"]
    policy_version  = enhanced.get("policy_version", "v1")

    # ── Show the original user prompt ────────────────────────────────────
    _print_prompt_box("USER PROMPT (original)", safe_prompt)

    # ── Show the full enhanced / hardened prompt ──────────────────────────
    _print_prompt_box("ENHANCED PROMPT (sent to LLM)", hardened_prompt)

    print(f"\n   Policy version : {policy_version}")
    print(f"   Original length : {len(safe_prompt)} chars")
    print(f"   Enhanced length : {len(hardened_prompt)} chars")

    # ── Stage 2: LLM generation ───────────────────────────────────────────
    print("\n🤖 Stage 2: Generating code with LLM...")
    parts = []
    async for chunk in stream_code(hardened_prompt):
        if chunk:
            parts.append(chunk)

    original_code = "".join(parts).strip() or "// empty"
    print(f"   ✔ Generated {len(original_code)} characters")

    # ── Stage 3: Semgrep SAST ─────────────────────────────────────────────
    print("\n🔍 Stage 3: Static analysis (Semgrep)...")
    semgrep_result = run_semgrep_smart_fix(original_code)

    if not semgrep_result.get("ok"):
        print(f"   ❌ Semgrep failed: {semgrep_result.get('error')}")
        return {
            "code":          original_code,
            "original_code": original_code,
            "report": {
                "policy_version": policy_version,
                "semgrep_error":  semgrep_result.get("error"),
                "dast":           {"ok": False, "error": "Skipped — Semgrep failed"},
                "uml":            {"ok": False, "error": "Skipped — Semgrep failed"},
            },
            "decision": "CODE_ONLY",
        }

    current_code  = semgrep_result.get("code", original_code)
    semgrep_fixed = semgrep_result.get("fixes_applied", 0)

    # ── Detailed SAST findings output ─────────────────────────────────────
    findings_before = semgrep_result.get("findings_before", 0)
    cat             = semgrep_result.get("categorized_findings", {})
    all_initial     = (
        cat.get("initially_auto_fixable", []) +
        cat.get("initially_manual_only", [])
    )
    # Fallback: if categorized list is empty but count > 0, note it
    if findings_before > 0:
        if all_initial:
            _print_sast_findings(all_initial, title="SAST — Initial Findings")
        else:
            print(f"   ⚠️  {findings_before} finding(s) detected (detail not available at this stage)")
    else:
        print(f"   ✔ No SAST vulnerabilities found")

    # ── Post-fix findings (if any remain) ─────────────────────────────────
    remaining_after_semgrep = cat.get("still_remaining", [])
    if semgrep_fixed > 0:
        print(f"\n   🔧 Semgrep auto-fixed {semgrep_fixed} issue(s)")
        if remaining_after_semgrep:
            _print_sast_findings(remaining_after_semgrep, title="SAST — Remaining After Semgrep Autofix")
        else:
            print(f"   ✔ All issues resolved by Semgrep autofix")

    # ── Stage 4: LLM SAST fix ─────────────────────────────────────────────
    llm_fix_result = None
    remaining_sast = cat.get("remaining_needs_llm", [])

    if remaining_sast:
        critical_sast = [
            f for f in remaining_sast
            if f.get("severity", "").upper() in ("CRITICAL", "HIGH", "ERROR")
        ]
        issues_to_fix = critical_sast if critical_sast else remaining_sast[:10]

        if 0 < len(issues_to_fix) <= 10:
            print(f"\n🤖 Stage 4: LLM fixing {len(issues_to_fix)} SAST issue(s)...")
            _print_sast_findings(issues_to_fix, title="SAST — Issues Sent to LLM Fix")
            llm_fix_result = await fix_with_llm(current_code, issues_to_fix)
            if llm_fix_result.get("fixed"):
                current_code = llm_fix_result["code"]
                print(f"   ✔ LLM fixed {llm_fix_result['fixes_applied']} SAST issues")
                # Show what remains after LLM fix
                issues_after_llm = llm_fix_result.get("issues_after", 0)
                if issues_after_llm > 0:
                    print(f"   ⚠️  {issues_after_llm} issue(s) still remaining after LLM fix")
            else:
                print(f"   ⚠️  LLM SAST fix unsuccessful: {llm_fix_result.get('error')}")
        elif len(issues_to_fix) > 10:
            print(f"\n⚠️  Stage 4: too many SAST issues ({len(remaining_sast)}) — skipping LLM")
            llm_fix_result = {
                "fixed": False, "attempted": False,
                "reason": f"Too many issues ({len(remaining_sast)}) — manual review needed",
            }
    else:
        print("\n✔ Stage 4: No remaining SAST issues")

    # ── Stage 5: DAST ─────────────────────────────────────────────────────
    print("\n🔬 Stage 5: Dynamic Analysis (DAST) via :7095...")

    lang_hint = ""
    langs_detected = semgrep_result.get("languages", [])
    if langs_detected:
        lang_hint = langs_detected[0]

    dast_result   = call_dast_service(current_code, language_hint=lang_hint)
    dast_findings = dast_result.get("findings", [])
    dast_summary  = dast_result.get("summary", {})

    print(
        f"   {'✔' if not dast_findings else '⚠️ '} DAST: "
        f"{len(dast_findings)} finding(s)  "
        f"[CRITICAL={dast_summary.get('critical', 0)} "
        f"HIGH={dast_summary.get('high', 0)} "
        f"MEDIUM={dast_summary.get('medium', 0)}]"
    )
    print(
        f"   🐳 Docker: "
        f"{'active' if dast_result.get('docker_available') else 'unavailable (pattern scan only)'}"
    )

    # ── Stage 6: LLM re-fix for critical DAST findings ────────────────────
    dast_llm_result = None
    critical_dast   = [
        f for f in dast_findings
        if f.get("severity", "").upper() in ("CRITICAL", "HIGH")
    ]

    if critical_dast:
        print(f"\n🤖 Stage 6: LLM re-fixing {len(critical_dast)} critical DAST finding(s)...")
        dast_llm_result = await fix_with_llm(current_code, critical_dast, max_attempts=2)
        if dast_llm_result.get("fixed"):
            current_code = dast_llm_result["code"]
            print(f"   ✔ DAST LLM fixed {dast_llm_result['fixes_applied']} issue(s)")
        else:
            print(f"   ⚠️  DAST LLM re-fix unsuccessful: {dast_llm_result.get('error')}")
    else:
        print("\n✔ Stage 6: No critical DAST findings — LLM re-fix skipped")

    # ── Stage 7: UML ──────────────────────────────────────────────────────
    print("\n📊 Stage 7: Generating UML diagrams...")
    uml_report = run_uml_pipeline_over_blob(current_code)

    # ── Totals ────────────────────────────────────────────────────────────
    sast_fixed  = semgrep_fixed
    sast_fixed += llm_fix_result.get("fixes_applied", 0) if llm_fix_result and llm_fix_result.get("fixed") else 0
    dast_fixed  = dast_llm_result.get("fixes_applied", 0) if dast_llm_result and dast_llm_result.get("fixed") else 0
    total_fixes = sast_fixed + dast_fixed

    initial_issues = semgrep_result.get("findings_before", 0)
    final_sast     = semgrep_result.get("findings_after", 0)
    if llm_fix_result and llm_fix_result.get("fixed"):
        final_sast = llm_fix_result.get("issues_after", final_sast)

    final_dast = dast_summary.get("total", 0)
    if dast_llm_result and dast_llm_result.get("fixed"):
        final_dast = dast_llm_result.get("issues_after", final_dast)

    print("\n" + "=" * _W)
    print("✔ PIPELINE COMPLETE")
    print("=" * _W)
    print(f"   SAST initial   : {initial_issues}")
    print(f"   Semgrep fixed  : {semgrep_fixed}")
    if llm_fix_result and llm_fix_result.get("fixed"):
        print(f"   LLM SAST fixed : {llm_fix_result.get('fixes_applied', 0)}")
    print(f"   DAST findings  : {dast_summary.get('total', 0)}")
    if dast_llm_result and dast_llm_result.get("fixed"):
        print(f"   DAST LLM fixed : {dast_llm_result.get('fixes_applied', 0)}")
    print(f"   Total fixes    : {total_fixes}")
    print("=" * _W + "\n")

    if total_fixes > 0:
        decision = "CODE_FIXED"
    elif dast_summary.get("total", 0) > 0:
        decision = "CODE_WITH_DAST_WARNINGS"
    else:
        decision = "CODE_ONLY"

    return {
        "code":          current_code,
        "original_code": original_code,
        "report": {
            "policy_version":           policy_version,
            "prompt_after_enhancement": hardened_prompt,

            "semgrep": {
                "ok":                   semgrep_result.get("ok", False),
                "initial_findings":     initial_issues,
                "final_findings":       final_sast,
                "autofix_applied":      semgrep_result.get("autofix_applied", False),
                "fixes_applied":        semgrep_fixed,
                "auto_fixable_count":   semgrep_result.get("auto_fixable_count", 0),
                "manual_only_count":    semgrep_result.get("manual_only_count", 0),
                "packs":                semgrep_result.get("packs", []),
                "languages":            semgrep_result.get("languages", []),
                "file_count":           semgrep_result.get("file_count", 0),
                "categorized_findings": semgrep_result.get("categorized_findings", {}),
            },

            "llm_fix": llm_fix_result,

            "dast": {
                "ok":                dast_result.get("ok", False),
                "docker_available":  dast_result.get("docker_available", False),
                "findings":          dast_findings,
                "pattern_findings":  dast_result.get("pattern_findings", []),
                "runtime_findings":  dast_result.get("runtime_findings", []),
                "execution_results": dast_result.get("execution_results", []),
                "languages":         dast_result.get("languages", []),
                "summary":           dast_summary,
            },

            "dast_llm_fix": dast_llm_result,
            "uml":          uml_report,

            "total_fixes_applied": total_fixes,
            "fix_summary": {
                "initial_issues":    initial_issues,
                "semgrep_fixed":     semgrep_fixed,
                "llm_fixed":         llm_fix_result.get("fixes_applied", 0) if llm_fix_result and llm_fix_result.get("fixed") else 0,
                "dast_findings":     dast_summary.get("total", 0),
                "dast_fixed":        dast_fixed,
                "remaining_issues":  final_sast,
                "dast_remaining":    final_dast,
                "fix_rate_percent":  round(
                    (total_fixes / initial_issues * 100) if initial_issues > 0 else 100, 1
                ),
            },
        },
        "decision": decision,
    }