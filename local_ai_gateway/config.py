"""
Configuration management with zero-configuration defaults for Local AI Gateway.

Architecture:
1. NORMAL CONFIGURATION: Sensible built-in defaults for immediate zero-config start.
2. OPTIONAL SECRETS: GATEWAY_API_KEY and PAIRING_CODE (both optional for local LAN dev).
"""
import os
import socket
import secrets
import json
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("local_ai_gateway.config")

class ConfigurationError(Exception):
    """Raised when user configuration is invalid or inconsistent."""
    pass

class GatewayConfig:
    def __init__(self):
        # ----------------------------------------------------------------------
        # 1. NORMAL CONFIGURATION (Built-in Sensible Defaults)
        # ----------------------------------------------------------------------
        # Server Binding
        self.host: str = os.getenv("GATEWAY_HOST", "0.0.0.0").strip()
        self.port: int = self._parse_int_env("GATEWAY_PORT", "8080", default=8080, min_val=1, max_val=65535)
        self.lan_ip: str = self._detect_lan_ip()

        # Backend Provider & URLs
        self.provider: str = os.getenv("MODEL_PROVIDER", "ollama").lower().strip()
        self.ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        self.default_model: str = os.getenv("DEFAULT_MODEL", "").strip() or "llama3.2:3b"

        # Model Aliases (Task routing)
        self.model_aliases: Dict[str, str] = self._load_model_aliases()

        # Concurrency Limits
        self.max_concurrent_requests: int = self._parse_int_env("MAX_CONCURRENT_REQUESTS", "1", default=1, min_val=1, max_val=128)

        # Timeouts (Seconds)
        self.connect_timeout: float = self._parse_float_env("CONNECT_TIMEOUT_SECONDS", "10", default=10.0)
        self.request_timeout: float = self._parse_float_env("REQUEST_TIMEOUT_SECONDS", "300", default=300.0)
        self.generation_timeout: float = self._parse_float_env("GENERATION_TIMEOUT_SECONDS", "300", default=300.0)
        self.streaming_idle_timeout: float = self._parse_float_env("STREAMING_IDLE_TIMEOUT_SECONDS", "60", default=60.0)

        # Memory & Safety Limits
        self.max_request_bytes: int = self._parse_int_env("MAX_REQUEST_BYTES", "10485760", default=10485760, min_val=1024) # 10 MB
        self.max_image_bytes: int = self._parse_int_env("MAX_IMAGE_BYTES", "10485760", default=10485760, min_val=1024) # 10 MB
        self.max_session_messages: int = self._parse_int_env("MAX_SESSION_MESSAGES", "100", default=100, min_val=1)
        self.session_ttl_seconds: float = self._parse_float_env("SESSION_TTL", "86400", default=86400.0) # 24 hours
        
        raw_context_strategy = os.getenv("CONTEXT_LIMIT_STRATEGY", "trim").lower().strip()
        self.context_limit_strategy: str = "trim" if raw_context_strategy in ("trim", "trim_oldest") else raw_context_strategy

        # Feature Flags
        self.enable_bonjour: bool = self._parse_bool_env("ENABLE_BONJOUR", default=True)
        self.enable_pairing: bool = self._parse_bool_env("ENABLE_PAIRING", default=True)
        self.enable_dashboard: bool = self._parse_bool_env("ENABLE_DASHBOARD", default=True)
        self.enable_sessions: bool = self._parse_bool_env("ENABLE_SESSIONS", default=True)
        self.enable_auto_routing: bool = self._parse_bool_env("ENABLE_AUTO_ROUTING", default=True)
        self.verbose_logging: bool = self._parse_bool_env("VERBOSE_LOGGING", default=False)

        # CORS
        self.allowed_origins: List[str] = self._parse_cors_origins()

        # ----------------------------------------------------------------------
        # 2. OPTIONAL SECRETS (Optional for local-network development)
        # ----------------------------------------------------------------------
        raw_api_key = os.getenv("GATEWAY_API_KEY", "").strip()
        self.api_key: Optional[str] = raw_api_key if raw_api_key else None

        raw_pairing_code = os.getenv("PAIRING_CODE", "").strip()
        if raw_pairing_code:
            self.pairing_code: str = raw_pairing_code
            self.is_pairing_code_generated: bool = False
        else:
            # Generate a secure cryptographically random 6-character hex code at runtime
            self.pairing_code: str = secrets.token_hex(3).upper()
            self.is_pairing_code_generated: bool = True

        # Validation
        self.validate()

    @property
    def is_auth_enabled(self) -> bool:
        """Returns True if master API key authentication is enforced."""
        return bool(self.api_key)

    def _parse_int_env(self, key: str, default_val: str, default: int, min_val: int = 1, max_val: int = 1000000000) -> int:
        val_str = os.getenv(key, default_val).strip()
        if not val_str:
            return default
        try:
            val = int(val_str)
            if val < min_val or val > max_val:
                logger.warning(f"Configuration {key}={val} out of range [{min_val}, {max_val}]. Using default {default}.")
                return default
            return val
        except ValueError:
            logger.warning(f"Invalid integer for {key}='{val_str}'. Using default {default}.")
            return default

    def _parse_float_env(self, key: str, default_val: str, default: float) -> float:
        val_str = os.getenv(key, default_val).strip()
        if not val_str:
            return default
        try:
            val = float(val_str)
            if val <= 0:
                logger.warning(f"Configuration {key}={val} must be positive. Using default {default}.")
                return default
            return val
        except ValueError:
            logger.warning(f"Invalid float for {key}='{val_str}'. Using default {default}.")
            return default

    def _parse_bool_env(self, key: str, default: bool) -> bool:
        val = os.getenv(key)
        if val is None or not val.strip():
            return default
        return val.strip().lower() in ("true", "1", "yes", "on", "enabled")

    def _parse_cors_origins(self) -> List[str]:
        raw = os.getenv("ALLOWED_ORIGINS", "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    def _load_model_aliases(self) -> Dict[str, str]:
        # Base task defaults
        defaults = {
            "fast": os.getenv("ALIAS_FAST", "").strip() or "llama3.2:3b",
            "general": os.getenv("ALIAS_GENERAL", "").strip() or "llama3.2:3b",
            "coding": os.getenv("ALIAS_CODING", "").strip() or "qwen2.5-coder",
            "reasoning": os.getenv("ALIAS_REASONING", "").strip() or "deepseek-r1:1.5b",
            "vision": os.getenv("ALIAS_VISION", "").strip() or "llava",
            "small": os.getenv("ALIAS_SMALL", "").strip() or "llama3.2:1b",
        }
        custom_json = os.getenv("MODEL_ALIASES_JSON", "").strip()
        if custom_json:
            try:
                parsed = json.loads(custom_json)
                if isinstance(parsed, dict):
                    defaults.update({k.lower().strip(): str(v).strip() for k, v in parsed.items()})
            except Exception as e:
                logger.warning(f"Failed to parse MODEL_ALIASES_JSON: {e}")
        
        # Check explicit ALIAS_<NAME> overrides in environment
        for key, val in os.environ.items():
            if key.startswith("ALIAS_") and val.strip():
                alias_name = key[6:].lower().strip()
                defaults[alias_name] = val.strip()
                
        return defaults

    def _detect_lan_ip(self) -> str:
        """Detects the Mac's primary local network IP address safely without internet transit."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
        except Exception:
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def validate(self) -> None:
        """Validates configuration bounds."""
        if not (1 <= self.port <= 65535):
            raise ConfigurationError(f"Invalid GATEWAY_PORT: {self.port}. Port must be between 1 and 65535.")

        if self.provider not in ("ollama", "mlx", "mock"):
            raise ConfigurationError(f"Unsupported MODEL_PROVIDER: '{self.provider}'. Choose 'ollama', 'mlx', or 'mock'.")

        if not self.ollama_url.startswith(("http://", "https://")):
            raise ConfigurationError(f"Invalid OLLAMA_URL: '{self.ollama_url}'. Must begin with http:// or https://.")

        if self.context_limit_strategy not in ("trim", "trim_oldest", "warn", "strict"):
            raise ConfigurationError(f"Invalid CONTEXT_LIMIT_STRATEGY: '{self.context_limit_strategy}'. Choose 'trim', 'warn', or 'strict'.")

    @property
    def lan_url(self) -> str:
        return f"http://{self.lan_ip}:{self.port}"

    @property
    def local_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

config = GatewayConfig()
