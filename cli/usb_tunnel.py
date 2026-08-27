"""
USB tunnel to iPhone via usbmuxd.

Uses pymobiledevice3's usbmux forward to proxy iPhone ports over USB,
then exposes them on localhost for the CLI to connect to.

    usb_tunnel.start()        -> starts forwarder, returns local port
    usb_tunnel.stop()         -> kills forwarder
    usb_tunnel.url            -> http://127.0.0.1:<port>
"""
from __future__ import annotations

import json
import logging
import shutil
import signal
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bridge_cli.usb")

DEFAULT_IPHONE_PORT = 9090


def _find_pymobiledevice3() -> Optional[str]:
    """Locate the pymobiledevice3 CLI."""
    # Try the venv first, then PATH
    for candidate in [
        shutil.which("pymobiledevice3"),
        ".venv/bin/pymobiledevice3",
    ]:
        if candidate and shutil.which(candidate):
            return candidate
    if shutil.which("pymobiledevice3"):
        return "pymobiledevice3"
    return None


def list_usb_devices() -> List[Dict[str, Any]]:
    """List iOS devices connected over USB via pymobiledevice3."""
    cli = _find_pymobiledevice3()
    if cli is None:
        logger.warning("pymobiledevice3 not found; cannot list USB devices")
        return []
    try:
        result = subprocess.run(
            [cli, "usbmux", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("pymobiledevice3 usbmux list failed: %s", result.stderr[:300])
            return []
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as exc:
        logger.warning("Failed to list USB devices: %s", exc)
        return []


def find_iphone_usb() -> Optional[Dict[str, Any]]:
    """Find the first USB-connected iPhone. Returns device dict or None."""
    devices = list_usb_devices()
    for d in devices:
        if d.get("ConnectionType") == "USB":
            return d
    return devices[0] if devices else None


def _pick_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class UsbTunnel:
    """
    Manages a USB tunnel from iPhone -> localhost via pymobiledevice3.

    Usage:
        tunnel = UsbTunnel(iphone_port=9090)
        local_port = tunnel.start()
        # connect to http://127.0.0.1:<local_port>
        tunnel.stop()
    """

    def __init__(
        self,
        iphone_port: int = DEFAULT_IPHONE_PORT,
        local_port: int = 0,
        device_serial: Optional[str] = None,
    ):
        self.iphone_port = iphone_port
        self.local_port = local_port or _pick_free_port()
        self.device_serial = device_serial
        self._process: Optional[subprocess.Popen] = None
        self._actual_port: int = 0

    def start(self) -> int:
        """
        Start the USB forwarder. Returns the local port.
        Raises RuntimeError if pymobiledevice3 is missing or no device found.
        """
        if self._process is not None and self._process.poll() is None:
            return self._actual_port

        cli = _find_pymobiledevice3()
        if cli is None:
            raise RuntimeError(
                "pymobiledevice3 not found.\n"
                "Install it:  pip install pymobiledevice3[tunnel]"
            )

        device = find_iphone_usb()
        if device is None:
            raise RuntimeError(
                "No iPhone found on USB.\n"
                "Connect your iPhone with a USB cable and tap 'Trust' when prompted."
            )

        serial = device.get("UniqueDeviceID") or device.get("Identifier") or ""
        self.device_serial = serial
        logger.info(
            "USB device: %s (%s) serial=%s",
            device.get("DeviceName", "iPhone"),
            device.get("ProductType", ""),
            serial[:12],
        )

        self.local_port = self.local_port or _pick_free_port()
        cmd = [
            cli,
            "usbmux",
            "forward",
            str(self.local_port),
            str(self.iphone_port),
            "--host",
            "127.0.0.1",
            "--serial",
            serial,
        ]
        logger.info("Starting USB tunnel: %s", " ".join(cmd))

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for the forwarder to be ready (check that port is listening)
        if not self._wait_for_port(timeout=8.0):
            stderr = ""
            if self._process and self._process.poll() is not None:
                stderr = (self._process.stderr.read() or b"").decode("utf-8", errors="replace")
            self.stop()
            raise RuntimeError(
                f"USB tunnel failed to start.\n"
                f"  Device: {device.get('DeviceName')} ({serial[:12]}…)\n"
                f"  iPhone port: {self.iphone_port}\n"
                f"  Error: {stderr[:500]}"
            )

        self._actual_port = self.local_port
        logger.info("USB tunnel ready: 127.0.0.1:%d -> iPhone:%d", self.local_port, self.iphone_port)
        return self.local_port

    def _wait_for_port(self, timeout: float = 8.0) -> bool:
        """Poll until the local port is accepting connections."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._process and self._process.poll() is not None:
                return False
            try:
                with socket.create_connection(("127.0.0.1", self.local_port), timeout=0.5):
                    return True
            except (ConnectionRefusedError, OSError, TimeoutError):
                time.sleep(0.3)
        return False

    def stop(self) -> None:
        """Kill the forwarder process."""
        if self._process is not None:
            try:
                self._process.send_signal(signal.SIGTERM)
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.kill()
            except Exception:
                pass
            self._process = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.local_port}"
