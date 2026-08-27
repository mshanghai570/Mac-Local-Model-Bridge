"""
Bonjour / mDNS helpers: find iPhones advertising on-device inference.
"""
from __future__ import annotations

import socket
import time
from typing import Any, Dict, List, Optional

IPHONE_SERVICE_TYPE = "_iphone-inference._tcp.local."
MAC_SERVICE_TYPES = (
    "_local-ai-bridge._tcp.local.",
    "_local-ai-gateway._tcp.local.",
)


def _local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def discover_services(service_type: str, timeout: float = 2.5) -> List[Dict[str, Any]]:
    try:
        from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf
    except ImportError:
        return []

    found: Dict[str, Dict[str, Any]] = {}
    zeroconf = Zeroconf()

    def _on_change(
        zeroconf_obj: Any,
        service_type_arg: str,
        name: str,
        state_change: Any,
    ) -> None:
        if state_change is not ServiceStateChange.Added:
            return
        info = zeroconf_obj.get_service_info(service_type_arg, name, timeout=1000)
        if info is None:
            return
        addresses = []
        for addr in info.parsed_addresses():
            if ":" in addr:
                continue
            if addr.startswith("127."):
                continue
            addresses.append(addr)
        if not addresses and info.parsed_addresses():
            addresses = [info.parsed_addresses()[0]]
        if not addresses:
            return
        host = addresses[0]
        port = int(info.port or 0)
        props = {}
        for key, value in (info.properties or {}).items():
            k = key.decode("utf-8", errors="replace") if isinstance(key, bytes) else str(key)
            if value is None:
                props[k] = ""
            elif isinstance(value, bytes):
                props[k] = value.decode("utf-8", errors="replace")
            else:
                props[k] = str(value)
        found[f"{host}:{port}"] = {
            "name": name.split(".")[0],
            "host": host,
            "port": port,
            "url": f"http://{host}:{port}",
            "properties": props,
        }

    browser = ServiceBrowser(zeroconf, service_type, handlers=[_on_change])
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.15)
    finally:
        browser.cancel()
        zeroconf.close()
    return list(found.values())


def discover_iphones(timeout: float = 2.5) -> List[Dict[str, Any]]:
    return discover_services(IPHONE_SERVICE_TYPE, timeout=timeout)


def lan_ip() -> str:
    return _local_ip()
