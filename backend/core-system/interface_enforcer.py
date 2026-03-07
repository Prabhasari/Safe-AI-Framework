"""
Interface Enforcement Module
Validates plugin structure, entry API, and permissions before execution.
"""

import json
import re
import logging
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REQUIRED_MANIFEST_FIELDS = {"name", "version", "entry", "permissions"}
ALLOWED_PERMISSIONS = {"network", "filesystem", "api"}

# Patterns that indicate the plugin exports an async `run(input, metadata)` function
_ENTRY_PATTERNS = [
    # ESM: export async function run(input, metadata)
    re.compile(
        r"export\s+async\s+function\s+run\s*\(\s*input\s*,\s*metadata\s*\)"
    ),
    # CommonJS: module.exports = { run } or exports.run = async function ...
    re.compile(
        r"module\.exports\s*=.*\brun\b"
    ),
    re.compile(
        r"exports\.run\s*="
    ),
    # Arrow / named: async function run(input, ...)  (non-exported but still present)
    re.compile(
        r"async\s+function\s+run\s*\("
    ),
    re.compile(
        r"function\s+run\s*\("
    ),
]

STORAGE_DIR = (Path(__file__).resolve().parents[1] / "storage").resolve()
VALIDATION_LOG = STORAGE_DIR / "plugin_validation.log"

# ---------------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------------
logger = logging.getLogger("interface_enforcer")
logger.setLevel(logging.INFO)

# File handler – append to storage/plugin_validation.log
_file_handler = logging.FileHandler(str(VALIDATION_LOG), encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_file_handler)


def _log_validation(plugin_slug: str, status: str, detail: str = ""):
    """Append a structured line to the validation log."""
    entry = {
        "plugin_slug": plugin_slug,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "validation_status": status,
    }
    if detail:
        entry["detail"] = detail
    logger.info(json.dumps(entry))


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------

def validate_manifest(plugin_path: str | Path) -> dict:
    """
    Validate that the plugin directory contains a well-formed manifest.json.

    Returns the parsed manifest dict on success.
    Raises ValueError on failure.
    """
    plugin_path = Path(plugin_path)

    manifest_file = plugin_path / "manifest.json"
    if not manifest_file.exists():
        raise ValueError("manifest.json not found in plugin directory")

    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest.json is not valid JSON: {exc}")

    missing = REQUIRED_MANIFEST_FIELDS - set(manifest.keys())
    if missing:
        raise ValueError(f"manifest.json missing required fields: {sorted(missing)}")

    return manifest


def validate_entry_function(plugin_path: str | Path) -> None:
    """
    Validate that entry.js exists and exports the required run(input, metadata) function.

    Raises ValueError on failure.
    """
    plugin_path = Path(plugin_path)

    entry_file = plugin_path / "entry.js"
    if not entry_file.exists():
        raise ValueError("entry.js not found in plugin directory")

    source = entry_file.read_text(encoding="utf-8")

    for pattern in _ENTRY_PATTERNS:
        if pattern.search(source):
            return  # found a valid run export

    raise ValueError(
        "entry.js does not export the required function: "
        "export async function run(input, metadata)"
    )


def validate_permissions(manifest: dict) -> None:
    """
    Validate that all requested permissions are in the allowed set.

    Raises ValueError if unknown permissions are found.
    """
    requested = set(manifest.get("permissions", []))
    unknown = requested - ALLOWED_PERMISSIONS
    if unknown:
        raise ValueError(f"Unknown permissions requested: {sorted(unknown)}")


# ---------------------------------------------------------------------------
# Public aggregator
# ---------------------------------------------------------------------------

def enforce_interface(plugin_path: str | Path) -> dict:
    """
    Run all interface validations on *plugin_path*.

    Returns the parsed manifest on success.
    Raises ValueError with a descriptive message on any failure.
    """
    plugin_path = Path(plugin_path)
    slug = plugin_path.name  # use folder name as slug

    try:
        manifest = validate_manifest(plugin_path)
        validate_entry_function(plugin_path)
        validate_permissions(manifest)
    except ValueError as exc:
        _log_validation(slug, "FAIL", str(exc))
        raise

    _log_validation(slug, "PASS")
    return manifest
