"""
Zero-configuration Bonjour/mDNS service advertiser for Apple Local Network discovery.
Allows iPhone apps, macOS clients, and Safari to discover Local AI Gateway automatically.
"""
import socket
import logging
from typing import List, Optional

logger = logging.getLogger("local_ai_gateway.bonjour")

try:
    from zeroconf import Zeroconf, ServiceInfo
    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False
    Zeroconf = None # type: ignore
    ServiceInfo = None # type: ignore

class BonjourAdvertiser:
    """
    Advertises Local AI Gateway on the local network via Apple Bonjour.
    Primary type is `_local-ai-bridge._tcp` (15-byte, RFC 6763 compliant); the
    legacy `_local-ai-gateway._tcp` alias is also attempted but non-fatal on failure.
    """
    SERVICE_TYPES = ["_local-ai-bridge._tcp", "_local-ai-gateway._tcp"]

    def __init__(self, port: int, service_name: str = "Local AI Gateway", properties: Optional[dict] = None):
        self.port = port
        self.service_name = service_name
        self.properties = properties or {}
        self.zeroconf: Optional[Zeroconf] = None
        self._registered: List[ServiceInfo] = []

    def start(self) -> bool:
        if not HAS_ZEROCONF:
            logger.info("Zeroconf not installed. Bonjour local advertising disabled.")
            return False

        try:
            self.zeroconf = Zeroconf()
            hostname = socket.gethostname()
            if hostname.endswith(".local"):
                hostname = hostname[:-len(".local")]
            local_ip = self._get_local_ip()

            txt_records = {
                b"path": b"/",
                b"version": b"1.0.0",
                b"service": b"local-ai-gateway",
                b"provider": str(self.properties.get("provider", "ollama")).encode("utf-8"),
                b"auth_required": b"true" if self.properties.get("auth_required") else b"false",
                b"ip": local_ip.encode("utf-8"),
                b"host": f"{hostname}.local.".encode("utf-8"),
                b"port": str(self.port).encode("utf-8")
            }

            registered_any = False
            for stype in self.SERVICE_TYPES:
                try:
                    service_info = ServiceInfo(
                        type_=f"{stype}.local.",
                        name=f"{self.service_name}.{stype}.local.",
                        addresses=[socket.inet_aton(local_ip)],
                        port=self.port,
                        properties=txt_records,
                        server=f"{hostname}.local."
                    )
                    self.zeroconf.register_service(service_info)
                    self._registered.append(service_info)
                    logger.info(f"Bonjour service registered: {self.service_name} ({stype}) on {local_ip}:{self.port}")
                    registered_any = True
                except Exception as e:
                    logger.warning(f"Failed to register Bonjour service '{stype}': {repr(e)}")
            return registered_any
        except Exception as e:
            logger.warning(f"Bonjour advertiser failed to start: {repr(e)}")
            return False

    def stop(self) -> None:
        if self.zeroconf:
            for service_info in self._registered:
                try:
                    self.zeroconf.unregister_service(service_info)
                except Exception as e:
                    logger.warning(f"Error unregistering Bonjour service: {repr(e)}")
            self._registered = []
            try:
                self.zeroconf.close()
                logger.info("Bonjour advertiser stopped.")
            except Exception as e:
                logger.warning(f"Error closing Bonjour advertiser: {repr(e)}")
            self.zeroconf = None

    def _get_local_ip(self) -> str:
        # Prefer the IP of the interface used for the default route (the primary
        # outbound interface, typically Wi-Fi). This matches config.lan_ip and is
        # the address other LAN devices can actually reach.
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        finally:
            s.close()

        # Fallback: resolve the hostname and take the first non-loopback address.
        try:
            hostname = socket.gethostname()
            addresses = socket.getaddrinfo(
                hostname, None, family=socket.AF_INET, type=socket.SOCK_DGRAM
            )
            for addr in addresses:
                ip = addr[4][0]
                if not ip.startswith("127.") and ip != "0.0.0.0":
                    return ip
        except Exception:
            pass

        return "127.0.0.1"
