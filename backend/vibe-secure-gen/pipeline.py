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

from stages.prompt            import enhance_prompt
from stages.prompt_firewall   import sanitize_prompt
from stages.llm               import stream_code
from stages.semgrep_smart_fix import run_semgrep_smart_fix
from stages.llm_fix           import fix_with_llm
from stages.dast_client       import call_dast_service
from stages.uml_pipeline      import run_uml_pipeline_over_blob


# ─────────────────────────────────────────────────────────────────────────────
#  ANSI color constants
# ─────────────────────────────────────────────────────────────────────────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    # Three main colors used throughout
    CYAN    = "\033[96m"   # stage headers / info lines
    GREEN   = "\033[92m"   # success / clean / fixed
    YELLOW  = "\033[93m"   # warnings / partial / DAST findings
    # Supporting colors
    RED     = "\033[91m"   # errors / critical
    MAGENTA = "\033[95m"   # LLM calls
    BLUE    = "\033[94m"   # SAST / Semgrep
    WHITE   = "\033[97m"   # values / numbers


def _c(color: str, text: str) -> str:
    """Wrap text in an ANSI color and reset."""
    return f"{color}{text}{C.RESET}"


# ─────────────────────────────────────────────────────────────────────────────
#  Terminal pretty-print helpers
# ─────────────────────────────────────────────────────────────────────────────

_W = 80

def _box_line(text: str, width: int = _W) -> str:
    padded = f"  {text}"
    # Strip ANSI codes for length calculation
    import re
    clean = re.sub(r"\033\[[0-9;]*m", "", padded)
    pad = width - 2 - len(clean)
    return f"{C.CYAN}║{C.RESET}{padded}{' ' * max(pad, 0)}{C.CYAN}║{C.RESET}"


def _print_prompt_box(label: str, content: str) -> None:
    bar = _c(C.CYAN, "═" * (_W - 2))
    print(f"\n{C.CYAN}╔{C.RESET}{bar}{C.CYAN}╗{C.RESET}")
    lbl_line = f"  {_c(C.CYAN + C.BOLD, label)}"
    import re
    clean = re.sub(r"\033\[[0-9;]*m", "", lbl_line)
    pad = _W - 2 - len(clean)
    print(f"{C.CYAN}║{C.RESET}{lbl_line}{' ' * max(pad, 0)}{C.CYAN}║{C.RESET}")
    print(f"{C.CYAN}╠{C.RESET}{bar}{C.CYAN}╣{C.RESET}")
    for raw_line in content.splitlines():
        while len(raw_line) > _W - 4:
            print(_box_line(_c(C.DIM, raw_line[:_W - 4])))
            raw_line = raw_line[_W - 4:]
        print(_box_line(_c(C.DIM, raw_line)))
    print(f"{C.CYAN}╚{C.RESET}{bar}{C.CYAN}╝{C.RESET}")


def _stage_header(n: int, icon: str, title: str, color: str = C.CYAN) -> None:
    """Print a bold colored stage header line."""
    bar_l = "━" * 4
    tag   = f" STAGE {n} "
    bar_r = "━" * (_W - len(tag) - 6)
    print(f"\n{color}{C.BOLD}{bar_l}{tag}{bar_r}{C.RESET}")
    print(f"  {color}{C.BOLD}{icon}  {title}{C.RESET}")


def _ok(text: str) -> None:
    print(f"   {_c(C.GREEN, '✔')}  {_c(C.GREEN, text)}")


def _warn(text: str) -> None:
    print(f"   {_c(C.YELLOW, '⚠')}  {_c(C.YELLOW, text)}")


def _err(text: str) -> None:
    print(f"   {_c(C.RED, '✘')}  {_c(C.RED, text)}")


def _info(label: str, value: str = "", color: str = C.CYAN) -> None:
    v = f"  {_c(C.WHITE, value)}" if value else ""
    print(f"   {_c(color, '›')}  {_c(color, label)}{v}")


def _kv(label: str, value: str, label_color: str = C.DIM, value_color: str = C.WHITE) -> None:
    print(f"   {_c(label_color, label + ':')}  {_c(value_color, str(value))}")


SEV_ICON = {
    "CRITICAL": "🔴",
    "ERROR":    "🔴",
    "HIGH":     "🟠",
    "WARNING":  "🟡",
    "MEDIUM":   "🟡",
    "LOW":      "🔵",
    "INFO":     "⚪",
}

SEV_COLOR = {
    "CRITICAL": C.RED,
    "ERROR":    C.RED,
    "HIGH":     C.YELLOW,
    "MEDIUM":   C.YELLOW,
    "WARNING":  C.YELLOW,
    "LOW":      C.BLUE,
    "INFO":     C.DIM,
}

SEV_ORDER = {"CRITICAL": 0, "ERROR": 0, "HIGH": 1, "WARNING": 2, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def _print_sast_findings(findings: list, title: str = "SAST Findings") -> None:
    if not findings:
        _ok("No findings to display")
        return

    sorted_findings = sorted(
        findings,
        key=lambda f: SEV_ORDER.get(f.get("severity", "INFO").upper(), 99)
    )

    import re
    bar  = "═" * (_W - 2)
    thin = "─" * (_W - 2)

    print(f"\n{C.BLUE}╔{bar}╗{C.RESET}")
    header = f"  {_c(C.BLUE + C.BOLD, title)}  {_c(C.DIM, f'({len(findings)} total)')}"
    clean  = re.sub(r"\033\[[0-9;]*m", "", header)
    print(f"{C.BLUE}║{C.RESET}{header}{' ' * max(_W - 2 - len(clean), 0)}{C.BLUE}║{C.RESET}")
    print(f"{C.BLUE}╠{bar}╣{C.RESET}")

    # Severity summary
    sev_counts: Dict[str, int] = {}
    for f in findings:
        s = f.get("severity", "INFO").upper()
        sev_counts[s] = sev_counts.get(s, 0) + 1

    parts = []
    for sev in ["CRITICAL", "ERROR", "HIGH", "MEDIUM", "WARNING", "LOW", "INFO"]:
        if sev in sev_counts:
            sc = SEV_COLOR.get(sev, C.DIM)
            parts.append(f"{SEV_ICON.get(sev,'')} {_c(sc + C.BOLD, sev)}{_c(C.DIM, ':')}{_c(C.WHITE, str(sev_counts[sev]))}")
    summary = "  " + "   ".join(parts)
    clean   = re.sub(r"\033\[[0-9;]*m", "", summary)
    print(f"{C.BLUE}║{C.RESET}{summary}{' ' * max(_W - 2 - len(clean), 0)}{C.BLUE}║{C.RESET}")
    print(f"{C.BLUE}╠{bar}╣{C.RESET}")

    for i, finding in enumerate(sorted_findings, 1):
        sev      = (finding.get("severity") or "INFO").upper()
        sc       = SEV_COLOR.get(sev, C.DIM)
        icon     = SEV_ICON.get(sev, "⚪")
        check_id = finding.get("check_id") or "unknown"
        message  = finding.get("message") or "No description"
        path     = finding.get("path") or ""
        line_no  = (finding.get("start") or {}).get("line")
        metadata = finding.get("metadata") or {}
        owasp    = metadata.get("owasp") or finding.get("owasp") or ""
        cwe      = metadata.get("cwe")  or finding.get("cwe")  or ""
        has_fix  = finding.get("has_autofix", False)

        idx_line = f"  #{i}  {icon} {_c(sc + C.BOLD, f'{sev:<8}')}  {_c(C.WHITE, check_id)}"
        clean    = re.sub(r"\033\[[0-9;]*m", "", idx_line)
        print(f"{C.BLUE}║{C.RESET}{idx_line}{' ' * max(_W - 2 - len(clean), 0)}{C.BLUE}║{C.RESET}")

        if path:
            loc      = path + (f"  :  line {line_no}" if line_no else "")
            loc_line = f"      📄 {_c(C.CYAN, loc)}"
            clean    = re.sub(r"\033\[[0-9;]*m", "", loc_line)
            print(f"{C.BLUE}║{C.RESET}{loc_line}{' ' * max(_W - 2 - len(clean), 0)}{C.BLUE}║{C.RESET}")

        msg_prefix = "      ◈ "
        full_msg   = msg_prefix + _c(C.DIM, message)
        clean_msg  = msg_prefix + message
        while len(clean_msg) > _W - 4:
            line_out = msg_prefix + _c(C.DIM, message[:_W - 4 - len(msg_prefix)])
            clean_o  = re.sub(r"\033\[[0-9;]*m", "", line_out)
            print(f"{C.BLUE}║{C.RESET}{line_out}{' ' * max(_W - 2 - len(clean_o), 0)}{C.BLUE}║{C.RESET}")
            message   = message[_W - 4 - len(msg_prefix):]
            clean_msg = msg_prefix + message
            full_msg  = msg_prefix + _c(C.DIM, message)
        clean = re.sub(r"\033\[[0-9;]*m", "", full_msg)
        print(f"{C.BLUE}║{C.RESET}{full_msg}{' ' * max(_W - 2 - len(clean), 0)}{C.BLUE}║{C.RESET}")

        tags = []
        if owasp: tags.append(_c(C.YELLOW, f"OWASP: {owasp}"))
        if cwe:   tags.append(_c(C.DIM,    f"CWE: {cwe}"))
        if has_fix: tags.append(_c(C.GREEN, "🔧 auto-fixable"))
        if tags:
            tag_line = "      🏷  " + "   │   ".join(tags)
            clean    = re.sub(r"\033\[[0-9;]*m", "", tag_line)
            print(f"{C.BLUE}║{C.RESET}{tag_line}{' ' * max(_W - 2 - len(clean), 0)}{C.BLUE}║{C.RESET}")

        if i < len(sorted_findings):
            dots = "  " + "·" * (_W - 4)
            print(f"{C.BLUE}║{C.RESET}{_c(C.DIM, dots)}{' ' * 0}{C.BLUE}║{C.RESET}")

    print(f"{C.BLUE}╚{bar}╝{C.RESET}")


# ─────────────────────────────────────────────────────────────────────────────
#  Pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def run_pipeline(prompt: str) -> Dict[str, Any]:

    bar = _c(C.CYAN, "=" * _W)
    print(f"\n{bar}")
    print(f"{C.CYAN}{C.BOLD}  🔒  SECURE CODE GENERATION PIPELINE{C.RESET}")
    print(bar)

    # ── Stage 1: Prompt ───────────────────────────────────────────────────
    _stage_header(1, "📝", "Prompt Processing", C.CYAN)

    safe_prompt     = sanitize_prompt(prompt or "")
    enhanced        = enhance_prompt(safe_prompt)
    hardened_prompt = enhanced["text"]
    policy_version  = enhanced.get("policy_version", "v1")

    _print_prompt_box("USER PROMPT (original)", safe_prompt)
    _print_prompt_box("ENHANCED PROMPT (sent to LLM)", hardened_prompt)

    print()
    _kv("Policy version",  policy_version,          C.DIM, C.CYAN)
    _kv("Original length", f"{len(safe_prompt)} chars",    C.DIM, C.WHITE)
    _kv("Enhanced length", f"{len(hardened_prompt)} chars", C.DIM, C.GREEN)

    # ── Stage 2: LLM generation ───────────────────────────────────────────
    _stage_header(2, "🤖", "LLM Code Generation", C.MAGENTA)

    parts = []
    async for chunk in stream_code(hardened_prompt):
        if chunk:
            parts.append(chunk)

    original_code = "".join(parts).strip() or "// empty"
    _ok(f"Generated {_c(C.WHITE, str(len(original_code)))} {_c(C.DIM, 'characters')}")

    # ── Stage 3: Semgrep SAST ─────────────────────────────────────────────
    _stage_header(3, "🔍", "Static Analysis  —  Semgrep SAST", C.BLUE)

    semgrep_result = run_semgrep_smart_fix(original_code)

    if not semgrep_result.get("ok"):
        _err(f"Semgrep failed: {semgrep_result.get('error')}")
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

    langs = semgrep_result.get("languages", [])
    packs = semgrep_result.get("packs", [])
    _info("Languages detected", ", ".join(langs) or "unknown", C.CYAN)
    _info("Rule packs",         ", ".join(packs),              C.BLUE)

    findings_before = semgrep_result.get("findings_before", 0)
    cat             = semgrep_result.get("categorized_findings", {})
    all_initial     = (
        cat.get("initially_auto_fixable", []) +
        cat.get("initially_manual_only", [])
    )

    if findings_before > 0:
        if all_initial:
            _print_sast_findings(all_initial, title="SAST — Initial Findings")
        else:
            _warn(f"{findings_before} finding(s) detected  {_c(C.DIM, '(detail not available)')}")
    else:
        _ok("No SAST vulnerabilities found")

    remaining_after_semgrep = cat.get("still_remaining", [])
    if semgrep_fixed > 0:
        _ok(f"Semgrep auto-fixed {_c(C.WHITE, str(semgrep_fixed))} {_c(C.DIM, 'issue(s)')}")
        if remaining_after_semgrep:
            _print_sast_findings(remaining_after_semgrep, title="SAST — Remaining After Semgrep Autofix")
        else:
            _ok("All issues resolved by Semgrep autofix")

    # ── Stage 4: LLM SAST fix ─────────────────────────────────────────────
    _stage_header(4, "🤖", "LLM SAST Fix  (conditional)", C.MAGENTA)

    llm_fix_result = None
    remaining_sast = cat.get("remaining_needs_llm", [])

    if remaining_sast:
        critical_sast = [
            f for f in remaining_sast
            if f.get("severity", "").upper() in ("CRITICAL", "HIGH", "ERROR")
        ]
        issues_to_fix = critical_sast if critical_sast else remaining_sast[:10]

        if 0 < len(issues_to_fix) <= 10:
            _info(f"Fixing {len(issues_to_fix)} SAST issue(s) with LLM...", color=C.MAGENTA)
            _print_sast_findings(issues_to_fix, title="SAST — Issues Sent to LLM Fix")
            llm_fix_result = await fix_with_llm(current_code, issues_to_fix)
            if llm_fix_result.get("fixed"):
                current_code = llm_fix_result["code"]
                _ok(f"LLM fixed {_c(C.WHITE, str(llm_fix_result['fixes_applied']))} {_c(C.DIM, 'SAST issue(s)')}")
                issues_after_llm = llm_fix_result.get("issues_after", 0)
                if issues_after_llm > 0:
                    _warn(f"{issues_after_llm} issue(s) still remaining after LLM fix")
            else:
                _warn(f"LLM SAST fix unsuccessful:  {llm_fix_result.get('error')}")
        elif len(issues_to_fix) > 10:
            _warn(f"Too many SAST issues ({len(remaining_sast)}) — skipping LLM  {_c(C.DIM, '(manual review needed)')}")
            llm_fix_result = {
                "fixed": False, "attempted": False,
                "reason": f"Too many issues ({len(remaining_sast)}) — manual review needed",
            }
    else:
        _ok(f"No remaining SAST issues  {_c(C.DIM, '— LLM fix skipped')}")

    # ── Stage 5: DAST ─────────────────────────────────────────────────────
    _stage_header(5, "🔬", "Dynamic Analysis  —  DAST  :7095", C.YELLOW)

    lang_hint = ""
    langs_detected = semgrep_result.get("languages", [])
    if langs_detected:
        lang_hint = langs_detected[0]

    dast_result   = call_dast_service(current_code, language_hint=lang_hint)
    dast_findings = dast_result.get("findings", [])
    dast_summary  = dast_result.get("summary", {})

    docker_up = dast_result.get("docker_available", False)
    _info("Docker sandbox",
          _c(C.GREEN, "active") if docker_up else _c(C.YELLOW, "unavailable — pattern scan only"),
          C.YELLOW)

    total_d = len(dast_findings)
    crit_d  = dast_summary.get("critical", 0)
    high_d  = dast_summary.get("high", 0)
    med_d   = dast_summary.get("medium", 0)

    sev_str = (
        f"{_c(C.RED,    f'CRITICAL={crit_d}')}  "
        f"{_c(C.YELLOW, f'HIGH={high_d}')}  "
        f"{_c(C.YELLOW, f'MEDIUM={med_d}')}"
    )

    if total_d == 0:
        _ok(f"DAST: {_c(C.WHITE, '0')} findings  {_c(C.DIM, f'[ {sev_str} ]')}")
    else:
        _warn(f"DAST: {_c(C.WHITE, str(total_d))} finding(s)  [ {sev_str} ]")

    # ── Stage 6: LLM re-fix for critical DAST findings ────────────────────
    _stage_header(6, "🤖", "LLM DAST Re-fix  (conditional)", C.MAGENTA)

    dast_llm_result = None
    critical_dast   = [
        f for f in dast_findings
        if f.get("severity", "").upper() in ("CRITICAL", "HIGH")
    ]

    if critical_dast:
        _info(f"Re-fixing {len(critical_dast)} critical DAST finding(s) with LLM...", color=C.MAGENTA)
        dast_llm_result = await fix_with_llm(current_code, critical_dast, max_attempts=2)
        if dast_llm_result.get("fixed"):
            current_code = dast_llm_result["code"]
            _ok(f"DAST LLM fixed {_c(C.WHITE, str(dast_llm_result['fixes_applied']))} {_c(C.DIM, 'issue(s)')}")
        else:
            _warn(f"DAST LLM re-fix unsuccessful:  {dast_llm_result.get('error')}")
    else:
        _ok(f"No critical DAST findings  {_c(C.DIM, '— LLM re-fix skipped')}")

    # ── Stage 7: UML ──────────────────────────────────────────────────────
    _stage_header(7, "📊", "UML Diagram Generation", C.CYAN)

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

    # ── Final summary box ─────────────────────────────────────────────────
    summary_color = C.GREEN if total_fixes > 0 or (initial_issues == 0 and total_d == 0) else C.YELLOW
    bar2 = "═" * (_W - 2)
    print(f"\n{summary_color}{C.BOLD}╔{bar2}╗{C.RESET}")
    hdr  = "  ✔  PIPELINE COMPLETE"
    print(f"{summary_color}{C.BOLD}║{C.RESET}{_c(summary_color + C.BOLD, hdr)}{' ' * (_W - 2 - len(hdr))}{summary_color}{C.BOLD}║{C.RESET}")
    print(f"{summary_color}{C.BOLD}╠{bar2}╣{C.RESET}")

    rows = [
        ("SAST initial",   str(initial_issues),                   C.WHITE if initial_issues == 0 else C.YELLOW),
        ("Semgrep fixed",  str(semgrep_fixed),                    C.GREEN if semgrep_fixed > 0 else C.DIM),
    ]
    if llm_fix_result and llm_fix_result.get("fixed"):
        rows.append(("LLM SAST fixed", str(llm_fix_result.get("fixes_applied", 0)), C.GREEN))
    rows += [
        ("DAST findings",  str(dast_summary.get("total", 0)),     C.WHITE if total_d == 0 else C.YELLOW),
    ]
    if dast_llm_result and dast_llm_result.get("fixed"):
        rows.append(("DAST LLM fixed", str(dast_llm_result.get("fixes_applied", 0)), C.GREEN))
    rows.append(("Total fixes",   str(total_fixes), C.GREEN if total_fixes > 0 else C.DIM))

    for label, value, vc in rows:
        inner = f"  {_c(C.DIM, f'{label:<18}')}  {_c(vc + C.BOLD, value)}"
        import re
        clean = re.sub(r"\033\[[0-9;]*m", "", inner)
        print(f"{summary_color}{C.BOLD}║{C.RESET}{inner}{' ' * max(_W - 2 - len(clean), 0)}{summary_color}{C.BOLD}║{C.RESET}")

    print(f"{summary_color}{C.BOLD}╚{bar2}╝{C.RESET}\n")

    # ── Decision ──────────────────────────────────────────────────────────
    if total_fixes > 0:
        decision = "CODE_FIXED"
        _ok(f"Decision: {_c(C.GREEN + C.BOLD, 'CODE_FIXED')}  {_c(C.DIM, '— vulnerabilities found and patched')}")
    elif dast_summary.get("total", 0) > 0:
        decision = "CODE_WITH_DAST_WARNINGS"
        _warn(f"Decision: {_c(C.YELLOW + C.BOLD, 'CODE_WITH_DAST_WARNINGS')}  {_c(C.DIM, '— manual review recommended')}")
    else:
        decision = "CODE_ONLY"
        _ok(f"Decision: {_c(C.GREEN + C.BOLD, 'CODE_ONLY')}  {_c(C.DIM, '— no issues detected')}")

    print()

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