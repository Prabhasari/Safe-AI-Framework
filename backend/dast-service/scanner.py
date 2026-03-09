# backend/dast-service/scanner.py

"""
Layer 1 — Static pattern scan for runtime-risky code patterns.
Always runs. No Docker required.
Covers: OWASP A01, A02, A03, A05, A09, A10
"""

from __future__ import annotations
import re
from typing import Any, Dict, List

# ─────────────────────────────────────────────────────────────────────────────
#  Pattern definitions
# ─────────────────────────────────────────────────────────────────────────────

PATTERNS: Dict[str, Dict[str, Any]] = {

    # ── OWASP A10 — SSRF ──────────────────────────────────────────────────
    "ssrf_internal_ip": {
        "regex": re.compile(
            r"(requests\.(get|post|put|delete|head)|urllib|httpx|fetch|axios|http\.get|http\.post)"
            r".{0,80}(127\.0\.0\.1|localhost|169\.254\.|10\.\d|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)",
            re.I | re.S,
        ),
        "severity": "CRITICAL",
        "owasp":    "A10 - SSRF",
        "cwe":      "CWE-918",
        "message":  "HTTP call targets an internal/loopback IP — SSRF vulnerability.",
    },
    "ssrf_url_from_input": {
        "regex": re.compile(
            r"(requests\.(get|post)|fetch|axios)\s*\(\s*(request\.|req\.|params\.|query\.|body\.|input)",
            re.I,
        ),
        "severity": "HIGH",
        "owasp":    "A10 - SSRF",
        "cwe":      "CWE-918",
        "message":  "HTTP URL derived from user input without validation — SSRF risk.",
    },

    # ── OWASP A01 — Broken Access Control ────────────────────────────────
    "path_traversal": {
        "regex": re.compile(
            r'(open|read_file|include|require|fopen|file_get_contents)\s*\(.*?\.\.[/\\]',
            re.I | re.S,
        ),
        "severity": "HIGH",
        "owasp":    "A01 - Broken Access Control",
        "cwe":      "CWE-22",
        "message":  "Path traversal '../' in file operation — directory traversal risk.",
    },
    "unvalidated_redirect": {
        "regex": re.compile(
            r"(redirect|sendRedirect|header\s*\(\s*['\"]Location)\s*\(?\s*(request\.|req\.|params\.|input)",
            re.I,
        ),
        "severity": "HIGH",
        "owasp":    "A01 - Broken Access Control",
        "cwe":      "CWE-601",
        "message":  "Redirect destination taken from user input — open redirect vulnerability.",
    },

    # ── OWASP A03 — Injection ─────────────────────────────────────────────
    "command_injection_shell": {
        "regex": re.compile(
            r"subprocess\.(call|run|Popen|check_output)\s*\(.*?shell\s*=\s*True",
            re.I | re.S,
        ),
        "severity": "CRITICAL",
        "owasp":    "A03 - Injection",
        "cwe":      "CWE-78",
        "message":  "subprocess with shell=True — command injection risk.",
    },
    "os_system": {
        "regex": re.compile(r"\bos\.system\s*\(", re.I),
        "severity": "CRITICAL",
        "owasp":    "A03 - Injection",
        "cwe":      "CWE-78",
        "message":  "os.system() usage — prefer subprocess with list argument.",
    },
    "eval_exec": {
        "regex": re.compile(r"\b(eval|exec)\s*\(", re.I),
        "severity": "CRITICAL",
        "owasp":    "A03 - Injection",
        "cwe":      "CWE-95",
        "message":  "eval()/exec() detected — arbitrary code execution risk.",
    },
    "sql_format_string": {
        "regex": re.compile(
            r'(execute|cursor\.execute|query)\s*\(\s*["\'].*?(%s|{.*?}|f["\'])',
            re.I,
        ),
        "severity": "CRITICAL",
        "owasp":    "A03 - Injection",
        "cwe":      "CWE-89",
        "message":  "SQL query built with string formatting — SQL injection risk.",
    },

    # ── OWASP A02 — Cryptographic Failures ───────────────────────────────
    "hardcoded_secret": {
        "regex": re.compile(
            r'(password|passwd|pwd|secret|api_key|apikey|token|auth_token)\s*=\s*["\'][^"\']{6,}["\']',
            re.I,
        ),
        "severity": "HIGH",
        "owasp":    "A02 - Cryptographic Failures",
        "cwe":      "CWE-798",
        "message":  "Hardcoded credential — use environment variables instead.",
    },
    "weak_random": {
        "regex": re.compile(r"\brandom\.(random|randint|choice|seed)\s*\(", re.I),
        "severity": "MEDIUM",
        "owasp":    "A02 - Cryptographic Failures",
        "cwe":      "CWE-338",
        "message":  "Non-cryptographic random — use secrets module for security tokens.",
    },
    "md5_sha1_password": {
        "regex": re.compile(
            r'(hashlib\.(md5|sha1)|MessageDigest\.getInstance\s*\(\s*["\']MD5["\'])',
            re.I,
        ),
        "severity": "HIGH",
        "owasp":    "A02 - Cryptographic Failures",
        "cwe":      "CWE-327",
        "message":  "MD5/SHA1 used for hashing — use bcrypt/argon2 for passwords.",
    },

    # ── OWASP A05 — Security Misconfiguration ────────────────────────────
    "debug_mode": {
        "regex": re.compile(
            r"(DEBUG\s*=\s*True|app\.run\s*\(.*?debug\s*=\s*True)",
            re.I | re.S,
        ),
        "severity": "HIGH",
        "owasp":    "A05 - Security Misconfiguration",
        "cwe":      "CWE-94",
        "message":  "Debug mode enabled — must be disabled in production.",
    },
    "cors_wildcard": {
        "regex": re.compile(
            r'(allow_origins|Access-Control-Allow-Origin)\s*[=:]\s*["\']?\*["\']?',
            re.I,
        ),
        "severity": "MEDIUM",
        "owasp":    "A05 - Security Misconfiguration",
        "cwe":      "CWE-942",
        "message":  "CORS wildcard (*) — restrict to known origins in production.",
    },

    # ── OWASP A09 — Security Logging Failures (structural) ────────────────
    "missing_logging": {
        "regex":    None,   # structural check — handled separately
        "severity": "MEDIUM",
        "owasp":    "A09 - Security Logging and Monitoring Failures",
        "cwe":      "CWE-778",
        "message":  "No security event logging detected in the code.",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
#  Public function
# ─────────────────────────────────────────────────────────────────────────────

def run_pattern_scan(code: str) -> List[Dict[str, Any]]:
    """
    Scan `code` for all risk patterns.
    Returns list of finding dicts.
    """
    findings: List[Dict[str, Any]] = []

    has_logging = bool(re.search(
        r"(logging\.|logger\.|log\.(info|warn|error|debug|critical)|"
        r"console\.(warn|error)|audit|SecurityLogger|AuditLog)",
        code, re.I,
    ))

    for check_id, check in PATTERNS.items():

        # ── structural checks ──
        if check["regex"] is None:
            if check_id == "missing_logging" and not has_logging and len(code) > 300:
                findings.append({
                    "check_id": f"dast-{check_id}",
                    "severity": check["severity"],
                    "message":  check["message"],
                    "owasp":    check["owasp"],
                    "cwe":      check["cwe"],
                    "line":     None,
                    "snippet":  None,
                    "source":   "pattern_scan",
                    "runtime":  True,
                })
            continue

        # ── regex checks ──
        for match in check["regex"].finditer(code):
            line_num = code[: match.start()].count("\n") + 1
            findings.append({
                "check_id": f"dast-{check_id}",
                "severity": check["severity"],
                "message":  check["message"],
                "owasp":    check["owasp"],
                "cwe":      check["cwe"],
                "line":     line_num,
                "snippet":  match.group(0)[:120],
                "source":   "pattern_scan",
                "runtime":  True,
            })

    return findings