"""
macOS system integration for Local AI Gateway: Accessibility, Zed detection,
and Mac bridge status. Zero external dependencies (stdlib only).
"""
from .accessibility import is_accessibility_trusted, is_zed_running
from .status import build_bridge_health, BRIDGE_PROTOCOL_VERSION

__all__ = [
    "is_accessibility_trusted",
    "is_zed_running",
    "build_bridge_health",
    "BRIDGE_PROTOCOL_VERSION",
]
