"""
Mac bridge health payload served by GET /health.

The iPhone app discovers the Mac and calls this endpoint to learn:
- whether the bridge process is running
- whether Zed is currently running
- whether the bridge holds macOS Accessibility permission

protocolVersion is bumped whenever the bridge control API contract changes.
"""
from .accessibility import is_accessibility_trusted, is_zed_running

BRIDGE_PROTOCOL_VERSION = "1.0"


def build_bridge_health() -> dict:
    """Builds the canonical bridge health payload for GET /health."""
    return {
        "status": "ok",
        "device": "Mac",
        "bridge": "running",
        "zed": is_zed_running(),
        "accessibility": is_accessibility_trusted(),
        "protocolVersion": BRIDGE_PROTOCOL_VERSION,
    }
