from __future__ import annotations
from models import Plugin

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

RESTRICTED_DENY_PREFIXES = (
    "/core/upload-folder",
    "/core/save",
    "/core/delete",
    "/core/reset",
    "/core/stop",
    "/core/start",
    "/core/docker",
)

def is_allowed(plugin: Plugin, path: str, method: str) -> tuple[bool, str]:
    if plugin.status == "blocked":
        return False, "Plugin is blocked by policy"

    if plugin.status == "restricted":
        for prefix in RESTRICTED_DENY_PREFIXES:
            if path.startswith(prefix):
                return False, f"Restricted plugin cannot access {prefix}"
        if method.upper() in WRITE_METHODS:
            return False, "Restricted plugin cannot perform write operations"

    return True, "Allowed"