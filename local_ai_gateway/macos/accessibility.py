"""
Zero-dependency macOS capability probes for the Mac bridge:
Accessibility trust and running-app detection.
"""
import ctypes
import logging
import subprocess

logger = logging.getLogger("local_ai_gateway.macos.accessibility")

ZED_BUNDLE_ID = "dev.zed.Zed"

_APPLICATION_SERVICES_FRAMEWORK = (
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)


def is_accessibility_trusted() -> bool:
    """
    Returns True if this process already holds macOS Accessibility trust.

    Uses AXIsProcessTrusted() via ctypes so no pyobjc dependency is required.
    The Mac bridge must be granted Accessibility permission (System Settings >
    Privacy & Security > Accessibility) before it can read/control apps.
    """
    try:
        lib = ctypes.cdll.LoadLibrary(_APPLICATION_SERVICES_FRAMEWORK)
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        lib.AXIsProcessTrusted.argtypes = []
        return bool(lib.AXIsProcessTrusted())
    except Exception as exc:
        logger.debug("AXIsProcessTrusted unavailable: %s", exc)
        return False


def is_zed_running() -> bool:
    """
    Returns True if the Zed editor (bundle id dev.zed.Zed) is currently running.

    Primary check uses lsappinfo (bundle id based, matches the canonical app);
    falls back to a process-name match because Zed's executable is 'zed'.
    """
    try:
        result = subprocess.run(
            ["lsappinfo", "find", f"bundleID={ZED_BUNDLE_ID}"],
            capture_output=True,
            timeout=3,
        )
        if result.returncode == 0:
            return True
    except Exception as exc:
        logger.debug("lsappinfo probe failed: %s", exc)

    try:
        result = subprocess.run(["pgrep", "-x", "zed"], capture_output=True, timeout=3)
        return result.returncode == 0
    except Exception as exc:
        logger.debug("pgrep probe failed: %s", exc)
        return False
