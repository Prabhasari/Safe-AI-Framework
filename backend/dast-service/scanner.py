# backend/dast-service/scanner.py

"""
Layer 1 — Static pattern scan for runtime-risky code patterns.
Always runs. No Docker required.
Covers: OWASP A01, A02, A03, A05, A09, A10

FIXES:
  - `missing_logging` only fires on service/dao/controller/util/handler files.
    Model/entity/POJO files are intentionally excluded — they contain only
    fields + getters/setters and are not expected to have loggers.
  - Non-code files (.xml, .sql, .properties, pom.xml, etc.) are fully skipped.
  - Every finding carries `file` and `line` for frontend display.
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Set

# ─────────────────────────────────────────────────────────────────────────────
#  Multi-file blob splitter
# ─────────────────────────────────────────────────────────────────────────────

_FILE_SEP_RE = re.compile(r"^===\s*FILE:\s*(.+?)\s*===$", re.M)
_FENCE_RE    = re.compile(r"^```[a-zA-Z0-9_+\-]*\s*\n([\s\S]*?)\n```$", re.M)

# Extensions we scan for security patterns
_CODE_EXTS: Set[str] = {
    ".java", ".py", ".js", ".ts", ".jsx", ".tsx",
    ".go", ".rb", ".php", ".cs", ".rs", ".scala",
    ".kt", ".kts", ".groovy", ".c", ".cpp", ".cc",
}

# Extensions we never scan (config, data, build files)
_SKIP_EXTS: Set[str] = {
    ".xml", ".yml", ".yaml", ".json", ".sql",
    ".properties", ".env", ".toml", ".ini",
    ".md", ".txt", ".gradle", ".lock", ".sh",
    ".bat", ".ps1", ".csv", ".html", ".css",
}

# Path segments that identify "logic" files that SHOULD have logging.
# If a file path contains any of these segments (case-insensitive), it
# is a candidate for the missing_logging check.
_LOGGING_REQUIRED_SEGMENTS = {
    "service", "services",
    "dao", "repository", "repositories",
    "controller", "controllers",
    "handler", "handlers",
    "util", "utils", "helper", "helpers",
    "manager", "managers",
    "filter", "filters",
    "interceptor", "interceptors",
    "security", "auth",
}

# Path segments that identify POJO/model files that should NOT be flagged.
_LOGGING_EXEMPT_SEGMENTS = {
    "model", "models",
    "entity", "entities",
    "dto", "dtos",
    "vo", "vos",
    "domain",
    "record", "records",
    "bean", "beans",
    "pojo",
}


def _strip_fence(blob: str) -> str:
    m = _FENCE_RE.search(blob.strip())
    return m.group(1).strip() if m else blob.strip()


def _split_into_named_files(inner: str) -> Dict[str, str]:
    separators = list(_FILE_SEP_RE.finditer(inner))
    if not separators:
        return {"main.py": inner}

    files: Dict[str, str] = {}
    for i, sep in enumerate(separators):
        filename      = sep.group(1).strip().replace("\\", "/")
        content_start = sep.end()
        content_end   = separators[i + 1].start() if i + 1 < len(separators) else len(inner)
        files[filename] = inner[content_start:content_end].strip()
    return files


def _file_ext(filename: str) -> str:
    parts = filename.rsplit(".", 1)
    return ("." + parts[-1].lower()) if len(parts) == 2 else ""


def _is_code_file(filename: str) -> bool:
    """True if this file should be scanned for security patterns."""
    ext  = _file_ext(filename)
    if ext in _SKIP_EXTS:
        return False
    if ext in _CODE_EXTS:
        return True
    base = filename.rsplit("/", 1)[-1].lower()
    skip_names = {
        "pom.xml", "build.gradle", "settings.gradle",
        "dockerfile", "makefile", ".gitignore", ".dockerignore",
    }
    return base not in skip_names


def _should_check_logging(filename: str) -> bool:
    """
    Returns True only for files that are reasonably expected to contain loggers:
    service, DAO, controller, util, handler, manager, security files.

    Returns False for model/entity/POJO/DTO files — they hold data only and
    are intentionally logger-free.
    """
    # Normalise path separators and lower-case for matching
    path_lower = filename.replace("\\", "/").lower()

    # Split into path segments (directory names + filename stem)
    segments = set(re.split(r"[/._\-]", path_lower))

    # If ANY segment matches an exempt category → skip
    if segments & _LOGGING_EXEMPT_SEGMENTS:
        return False

    # If ANY segment matches a required category → check
    if segments & _LOGGING_REQUIRED_SEGMENTS:
        return True

    # Fallback heuristic: if it's a sizeable file with no exempt label, check it
    return False   # be conservative — only flag explicitly recognised roles


# ─────────────────────────────────────────────────────────────────────────────
#  Pattern definitions
# ─────────────────────────────────────────────────────────────────────────────

PATTERNS: Dict[str, Dict[str, Any]] = {

    # ── OWASP A10 — SSRF ──────────────────────────────────────────────────
    "ssrf_internal_ip": {
        "regex": re.compile(
            r"(requests\.(get|post|put|delete|head)|urllib|httpx|fetch|axios"
            r"|http\.get|http\.post|new\s+URL|HttpURLConnection|URLConnection"
            r"|OkHttpClient|RestTemplate)"
            r".{0,80}(127\.0\.0\.1|localhost|169\.254\.|10\.\d"
            r"|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)",
            re.I | re.S,
        ),
        "severity": "CRITICAL",
        "owasp":    "A10 - SSRF",
        "cwe":      "CWE-918",
        "message":  "HTTP call targets an internal/loopback IP — SSRF vulnerability.",
        "fix_hint": "Validate the URL against an allowlist of safe external domains. "
                    "Reject requests to 127.x, 10.x, 172.16-31.x, 192.168.x, 169.254.x.",
    },
    "ssrf_url_from_input": {
        "regex": re.compile(
            r"(requests\.(get|post)|fetch|axios|new\s+URL\s*\(|openConnection\s*\()"
            r"\s*\(?\s*(request\.|req\.|params\.|query\.|body\.|input|getParameter)",
            re.I,
        ),
        "severity": "HIGH",
        "owasp":    "A10 - SSRF",
        "cwe":      "CWE-918",
        "message":  "HTTP URL derived from user input without validation — SSRF risk.",
        "fix_hint": "Verify the hostname against an allowlist before making the request.",
    },

    # ── OWASP A01 — Broken Access Control ────────────────────────────────
    "path_traversal": {
        "regex": re.compile(
            r"(open|read_file|include|require|fopen|file_get_contents"
            r"|new\s+File\s*\(|Paths\.get\s*\(|FileInputStream\s*\()\s*\(.*?\.\.[/\\]",
            re.I | re.S,
        ),
        "severity": "HIGH",
        "owasp":    "A01 - Broken Access Control",
        "cwe":      "CWE-22",
        "message":  "Path traversal '../' in file operation — directory traversal risk.",
        "fix_hint": "Resolve canonical path with toRealPath() / os.path.realpath(), "
                    "then assert it starts with the expected base directory.",
    },
    "unvalidated_redirect": {
        "regex": re.compile(
            r"(redirect|sendRedirect|header\s*\(\s*['\"]Location)\s*\(?\s*"
            r"(request\.|req\.|params\.|input|getParameter)",
            re.I,
        ),
        "severity": "HIGH",
        "owasp":    "A01 - Broken Access Control",
        "cwe":      "CWE-601",
        "message":  "Redirect destination taken from user input — open redirect vulnerability.",
        "fix_hint": "Validate redirect URL against a known-safe allowlist of relative paths.",
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
        "fix_hint": "Remove shell=True and pass arguments as a list: "
                    "subprocess.run(['cmd', arg1]). Never interpolate user input.",
    },
    "os_system": {
        "regex": re.compile(r"\bos\.system\s*\(", re.I),
        "severity": "CRITICAL",
        "owasp":    "A03 - Injection",
        "cwe":      "CWE-78",
        "message":  "os.system() usage — prefer subprocess with list argument.",
        "fix_hint": "Replace with subprocess.run(['cmd'], check=True). Never pass user input.",
    },
    "eval_exec": {
        "regex": re.compile(r"\b(eval|exec)\s*\(", re.I),
        "severity": "CRITICAL",
        "owasp":    "A03 - Injection",
        "cwe":      "CWE-95",
        "message":  "eval()/exec() detected — arbitrary code execution risk.",
        "fix_hint": "Refactor to avoid eval/exec. Use ast.literal_eval() for safe data parsing.",
    },
    "sql_format_string": {
        "regex": re.compile(
            r"(execute|cursor\.execute|createStatement|executeQuery|executeUpdate)"
            r'\s*\(\s*["\'].*?(%s|\+\s*\w|{.*?}|f["\']|\bString\.format)',
            re.I,
        ),
        "severity": "CRITICAL",
        "owasp":    "A03 - Injection",
        "cwe":      "CWE-89",
        "message":  "SQL query built with string formatting — SQL injection risk.",
        "fix_hint": "Use parameterized queries / PreparedStatement. "
                    "Never interpolate values directly into SQL strings.",
    },

    # ── OWASP A02 — Cryptographic Failures ───────────────────────────────
    "hardcoded_secret": {
        "regex": re.compile(
            r'(password|passwd|pwd|secret|api_key|apikey|token|auth_token)'
            r'\s*=\s*["\'][^"\']{6,}["\']',
            re.I,
        ),
        "severity": "HIGH",
        "owasp":    "A02 - Cryptographic Failures",
        "cwe":      "CWE-798",
        "message":  "Hardcoded credential — use environment variables instead.",
        "fix_hint": "Use System.getenv(\"SECRET\") or os.getenv('SECRET'). "
                    "Never commit credentials to source code.",
    },
    "weak_random": {
        "regex": re.compile(r"\brandom\.(random|randint|choice|seed)\s*\(", re.I),
        "severity": "MEDIUM",
        "owasp":    "A02 - Cryptographic Failures",
        "cwe":      "CWE-338",
        "message":  "Non-cryptographic random — use secrets module for security tokens.",
        "fix_hint": "Use secrets.randbelow() / secrets.choice() (Python) "
                    "or SecureRandom (Java) for security-sensitive values.",
    },
    "md5_sha1_password": {
        "regex": re.compile(
            r"(hashlib\.(md5|sha1)"
            r"|MessageDigest\.getInstance\s*\(\s*['\"]MD5['\"]"
            r"|MessageDigest\.getInstance\s*\(\s*['\"]SHA-1['\"])",
            re.I,
        ),
        "severity": "HIGH",
        "owasp":    "A02 - Cryptographic Failures",
        "cwe":      "CWE-327",
        "message":  "MD5/SHA1 used for hashing — use bcrypt/argon2 for passwords.",
        "fix_hint": "Use BCrypt.hashpw() (Java/Python) or argon2-cffi for password hashing.",
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
        "fix_hint": "Set DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'. "
                    "Default to False in production.",
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
        "fix_hint": "Replace * with an explicit list: allow_origins=['https://yourapp.com'].",
    },

    # ── OWASP A09 — Security Logging Failures ─────────────────────────────
    # regex=None → structural check handled in the loop below.
    # Only fires on service/dao/controller/util files via _should_check_logging().
    "missing_logging": {
        "regex":    None,
        "severity": "MEDIUM",
        "owasp":    "A09 - Security Logging and Monitoring Failures",
        "cwe":      "CWE-778",
        "message":  "No security event logging detected in this service/DAO/util file.",
        "fix_hint": "Add: private static final Logger log = LoggerFactory.getLogger(getClass()); "
                    "Log authentication attempts, authorization failures, and input validation errors.",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
#  Logging detector regex (covers Java + Python + JS)
# ─────────────────────────────────────────────────────────────────────────────

_HAS_LOGGING_RE = re.compile(
    r"(logging\.|logger\.|log\.(info|warn|error|debug|critical|trace)"
    r"|LoggerFactory\.getLogger|Logger\.getLogger|getLogger\s*\("
    r"|console\.(warn|error)|audit|SecurityLogger|AuditLog"
    r"|\.info\s*\(|\.warn\s*\(|\.error\s*\(|\.debug\s*\()",
    re.I,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Public function
# ─────────────────────────────────────────────────────────────────────────────

def run_pattern_scan(code: str) -> List[Dict[str, Any]]:
    """
    Scan multi-file code blob for security patterns.
    Each finding includes: check_id, severity, message, owasp, cwe,
    file, line, snippet, fix_hint, source.
    """
    inner    = _strip_fence(code)
    file_map = _split_into_named_files(inner)

    findings: List[Dict[str, Any]] = []

    for filename, file_content in file_map.items():

        # Skip non-code files entirely (XML, SQL, properties, pom.xml, etc.)
        if not _is_code_file(filename):
            continue

        has_logging = bool(_HAS_LOGGING_RE.search(file_content))

        for check_id, check in PATTERNS.items():

            # ── structural check: missing_logging ──────────────────────────
            if check["regex"] is None:
                if (
                    check_id == "missing_logging"
                    and not has_logging
                    and len(file_content) > 300
                    and _should_check_logging(filename)   # ← only service/dao/util/etc.
                ):
                    findings.append({
                        "check_id": f"dast-{check_id}",
                        "severity": check["severity"],
                        "message":  check["message"],
                        "owasp":    check["owasp"],
                        "cwe":      check["cwe"],
                        "file":     filename,
                        "line":     None,
                        "snippet":  None,
                        "fix_hint": check.get("fix_hint"),
                        "source":   "pattern_scan",
                        "runtime":  False,
                    })
                continue

            # ── regex check ────────────────────────────────────────────────
            for match in check["regex"].finditer(file_content):
                line_num = file_content[: match.start()].count("\n") + 1
                findings.append({
                    "check_id": f"dast-{check_id}",
                    "severity": check["severity"],
                    "message":  check["message"],
                    "owasp":    check["owasp"],
                    "cwe":      check["cwe"],
                    "file":     filename,
                    "line":     line_num,
                    "snippet":  match.group(0)[:120],
                    "fix_hint": check.get("fix_hint"),
                    "source":   "pattern_scan",
                    "runtime":  False,
                })

    return findings