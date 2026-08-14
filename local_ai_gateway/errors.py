"""
Standardized error classes and response formatters for Local AI Gateway.
"""
from typing import Optional, Dict, Any

class GatewayError(Exception):
    """Base error for all gateway exceptions."""
    def __init__(
        self,
        message: str,
        error_type: str = "server_error",
        status_code: int = 500,
        param: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.status_code = status_code
        self.param = param
        self.request_id = request_id

    def to_dict(self) -> Dict[str, Any]:
        err_dict: Dict[str, Any] = {
            "type": self.error_type,
            "message": self.message,
            "code": self.status_code
        }
        if self.param:
            err_dict["param"] = self.param
        if self.request_id:
            err_dict["request_id"] = self.request_id
        return {"error": err_dict}

class ProviderUnavailableError(GatewayError):
    """Raised when the backend LLM provider (e.g. Ollama) is not running or unreachable."""
    def __init__(self, message: str = "Backend provider is not reachable. Ensure Ollama is running ('ollama serve').", request_id: Optional[str] = None):
        super().__init__(message=message, error_type="provider_unavailable", status_code=503, request_id=request_id)

class ProviderError(GatewayError):
    """Raised when the backend LLM provider returns an internal error."""
    def __init__(self, message: str, request_id: Optional[str] = None):
        super().__init__(message=message, error_type="provider_error", status_code=502, request_id=request_id)

class ProviderTimeoutError(GatewayError):
    """Raised when request or generation exceeds configured timeout."""
    def __init__(self, message: str = "Request to model provider timed out.", request_id: Optional[str] = None):
        super().__init__(message=message, error_type="provider_timeout", status_code=504, request_id=request_id)

class ModelNotFoundError(GatewayError):
    """Raised when a requested model or alias is not installed."""
    def __init__(self, model_name: str, request_id: Optional[str] = None, message: Optional[str] = None):
        super().__init__(
            message=message or f"Model '{model_name}' not found. Check installed models via 'GET /models' or run 'ollama pull {model_name}'.",
            error_type="not_found_error",
            status_code=404,
            param="model",
            request_id=request_id
        )

class SessionNotFoundError(GatewayError):
    """Raised when a requested session does not exist or has expired."""
    def __init__(self, session_id: str, request_id: Optional[str] = None):
        super().__init__(
            message=f"Session '{session_id}' not found or has expired.",
            error_type="not_found_error",
            status_code=404,
            param="session_id",
            request_id=request_id
        )

class AuthenticationError(GatewayError):
    """Raised when API key or device token is invalid or missing."""
    def __init__(self, message: str = "Incorrect API key or device token provided.", request_id: Optional[str] = None):
        super().__init__(message=message, error_type="authentication_error", status_code=401, request_id=request_id)

class InvalidRequestError(GatewayError):
    """Raised when request payload or parameters are malformed."""
    def __init__(self, message: str, param: Optional[str] = None, request_id: Optional[str] = None):
        super().__init__(message=message, error_type="invalid_request_error", status_code=400, param=param, request_id=request_id)

class ConcurrencyLimitError(GatewayError):
    """Raised when max concurrent requests limit is exceeded."""
    def __init__(self, message: str = "Maximum concurrent request capacity reached. Please try again shortly.", request_id: Optional[str] = None):
        super().__init__(message=message, error_type="rate_limit_error", status_code=429, request_id=request_id)

class PayloadTooLargeError(GatewayError):
    """Raised when request payload or image size exceeds configured memory limits."""
    def __init__(self, message: str = "Request body or image exceeds maximum allowed size.", request_id: Optional[str] = None):
        super().__init__(message=message, error_type="payload_too_large", status_code=413, request_id=request_id)

def format_error_response(
    message: str,
    error_type: str = "server_error",
    status_code: int = 500,
    param: Optional[str] = None,
    request_id: Optional[str] = None
) -> Dict[str, Any]:
    """Formats an error response consistently for both humans and client SDKs."""
    err: Dict[str, Any] = {
        "type": error_type,
        "message": message,
        "code": status_code
    }
    if param:
        err["param"] = param
    if request_id:
        err["request_id"] = request_id
    return {"error": err}
