"""
Authentication, pairing code exchange, and lightweight device token management.
"""
import hmac
import hashlib
import secrets
import time
import threading
from typing import Optional, Dict, Any, List
from .config import config
from .models import DeviceRecord
from .errors import AuthenticationError

class DeviceManager:
    """
    In-memory device registry allowing iPhone/client pairing tokens to be managed
    and individually revoked without rotating the master GATEWAY_API_KEY.
    """
    def __init__(self):
        self._devices: Dict[str, DeviceRecord] = {}
        self._token_to_device_id: Dict[str, str] = {}
        self._pending_pairing_codes: Dict[str, float] = {} # code -> expiry timestamp
        self._lock = threading.RLock()

    def generate_pairing_code(self, ttl_seconds: float = 300.0) -> str:
        """Generates a cryptographically random, short-lived 6-character hex pairing code."""
        with self._lock:
            # Clean expired codes
            now = time.time()
            self._pending_pairing_codes = {c: exp for c, exp in self._pending_pairing_codes.items() if exp > now}
            
            code = secrets.token_hex(3).upper()
            self._pending_pairing_codes[code] = now + ttl_seconds
            return code

    def exchange_pairing_code(self, code: str, device_name: Optional[str] = None) -> Dict[str, str]:
        """
        Exchanges a short-lived pairing code (or static config pairing code) for a persistent device token.
        """
        with self._lock:
            now = time.time()
            code_upper = code.strip().upper()

            # Check dynamic or static pairing code
            valid = False
            if code_upper in self._pending_pairing_codes:
                if self._pending_pairing_codes[code_upper] > now:
                    valid = True
                    del self._pending_pairing_codes[code_upper] # Single use
            elif hmac.compare_digest(code_upper, config.pairing_code.upper()):
                valid = True

            if not valid:
                raise AuthenticationError("Invalid or expired pairing code.")

            device_id = f"dev_{secrets.token_hex(4)}"
            device_token = f"gw_dev_{secrets.token_urlsafe(24)}"
            token_hash = hashlib.sha256(device_token.encode("utf-8")).hexdigest()

            dev = DeviceRecord(
                device_id=device_id,
                name=device_name or f"iPhone ({device_id})",
                token_hash=token_hash,
                created_at=now,
                last_used_at=now
            )
            self._devices[device_id] = dev
            self._token_to_device_id[token_hash] = device_id

            return {
                "device_id": device_id,
                "device_token": device_token,
                "name": dev.name
            }

    def verify_token(self, provided_token: Optional[str]) -> bool:
        """
        Verifies token against master GATEWAY_API_KEY OR registered device tokens.
        If no GATEWAY_API_KEY is configured on the gateway, all requests are permitted.
        """
        if not config.api_key:
            return True
        if not provided_token:
            return False

        clean_token = provided_token.strip()

        # 1. Check Master Gateway API Key
        if hmac.compare_digest(clean_token, config.api_key.strip()):
            return True

        # 2. Check Device Tokens
        token_hash = hashlib.sha256(clean_token.encode("utf-8")).hexdigest()
        with self._lock:
            if token_hash in self._token_to_device_id:
                dev_id = self._token_to_device_id[token_hash]
                dev = self._devices.get(dev_id)
                if dev:
                    dev.last_used_at = time.time()
                return True

        return False

    def list_devices(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [d.to_dict() for d in self._devices.values()]

    def revoke_device(self, device_id: str) -> bool:
        with self._lock:
            dev = self._devices.pop(device_id, None)
            if dev:
                self._token_to_device_id.pop(dev.token_hash, None)
                return True
            return False

device_manager = DeviceManager()

def verify_token(provided_token: Optional[str]) -> bool:
    return device_manager.verify_token(provided_token)

def extract_api_key(headers: Dict[str, str], query_params: Optional[Dict[str, str]] = None) -> Optional[str]:
    """
    Extracts API key from HTTP headers (Authorization: Bearer <key>, X-API-Key) or query parameters.
    """
    # 1. Authorization: Bearer <token>
    auth_header = headers.get("authorization") or headers.get("Authorization")
    if auth_header:
        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return auth_header.strip()

    # 2. X-API-Key / x-api-key / x-gateway-key
    for key in ["x-api-key", "X-API-Key", "x-gateway-key", "X-Gateway-Key"]:
        if key in headers:
            return headers[key].strip()

    # 3. Query parameters (useful for EventSource / WebSockets / Apple Shortcuts)
    if query_params:
        for q in ["api_key", "apiKey", "key", "token"]:
            if q in query_params:
                return query_params[q].strip()

    return None

def mask_api_key(key: Optional[str]) -> str:
    """Masks an API key for safe logging (e.g. 'secr****1234')."""
    if not key:
        return "[UNCONFIGURED]"
    if len(key) <= 6:
        return "******"
    return f"{key[:3]}****{key[-3:]}"
