"""
Data models and typed definitions for Local AI Gateway.
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import time

@dataclass
class ModelCapabilities:
    """Normalized capabilities matrix for a model."""
    text: bool = True
    vision: bool = False
    tools: bool = False
    structured_output: bool = True
    embeddings: bool = False
    coding: bool = False

    def to_dict(self) -> Dict[str, bool]:
        return {
            "text": self.text,
            "vision": self.vision,
            "tools": self.tools,
            "structured_output": self.structured_output,
            "embeddings": self.embeddings,
            "coding": self.coding
        }

    def to_list(self) -> List[str]:
        items = []
        if self.text: items.append("chat")
        if self.vision: items.append("vision")
        if self.tools: items.append("tools")
        if self.embeddings: items.append("embeddings")
        if self.coding: items.append("coding")
        return items

    def __contains__(self, item: str) -> bool:
        item_lower = item.lower()
        if item_lower in ("chat", "text") and self.text: return True
        if item_lower == "vision" and self.vision: return True
        if item_lower == "tools" and self.tools: return True
        if item_lower in ("coding", "code") and (self.coding or self.tools or self.text): return True
        if item_lower == "embeddings" and self.embeddings: return True
        return False

    def __iter__(self):
        return iter(self.to_list())


@dataclass
class ChatMessage:
    role: str # "system", "user", "assistant", "tool"
    content: str = ""
    images: Optional[List[str]] = None # Base64 encoded images for vision models
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.images:
            d["images"] = self.images
        if self.name:
            d["name"] = self.name
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d

@dataclass
class ChatRequest:
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    max_tokens: Optional[int] = None
    system: Optional[str] = None
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    response_format: Optional[Dict[str, Any]] = None
    options: Optional[Dict[str, Any]] = field(default_factory=dict)
    request_id: Optional[str] = None

@dataclass
class GenerateRequest:
    model: str
    prompt: str
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    max_tokens: Optional[int] = None
    system: Optional[str] = None
    stream: bool = False
    images: Optional[List[str]] = None
    options: Optional[Dict[str, Any]] = field(default_factory=dict)
    request_id: Optional[str] = None

@dataclass
class ModelInfo:
    name: str
    size_bytes: int
    size_formatted: str
    modified_at: str
    digest: str
    format: Optional[str] = None
    family: Optional[str] = None
    families: Optional[List[str]] = None
    parameter_size: Optional[str] = None
    quantization_level: Optional[str] = None
    context_length: Optional[int] = None
    capabilities: Any = field(default_factory=ModelCapabilities)
    raw_details: Optional[Dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.capabilities, list):
            caps_set = {c.lower() for c in self.capabilities}
            self.capabilities = ModelCapabilities(
                text="chat" in caps_set or "text" in caps_set,
                vision="vision" in caps_set,
                tools="tools" in caps_set,
                embeddings="embeddings" in caps_set,
                coding="coding" in caps_set or "code" in caps_set
            )
        elif isinstance(self.capabilities, dict):
            self.capabilities = ModelCapabilities(
                text=self.capabilities.get("text", True),
                vision=self.capabilities.get("vision", False),
                tools=self.capabilities.get("tools", False),
                structured_output=self.capabilities.get("structured_output", True),
                embeddings=self.capabilities.get("embeddings", False),
                coding=self.capabilities.get("coding", False)
            )

    def to_dict(self) -> Dict[str, Any]:
        caps_list = []
        if hasattr(self.capabilities, "text") and self.capabilities.text: caps_list.append("chat")
        if hasattr(self.capabilities, "vision") and self.capabilities.vision: caps_list.append("vision")
        if hasattr(self.capabilities, "tools") and self.capabilities.tools: caps_list.append("tools")
        if hasattr(self.capabilities, "embeddings") and self.capabilities.embeddings: caps_list.append("embeddings")
        return {
            "name": self.name,
            "model": self.name,
            "size": self.size_bytes,
            "size_bytes": self.size_bytes,
            "size_formatted": self.size_formatted,
            "modified_at": self.modified_at,
            "digest": self.digest,
            "format": self.format,
            "family": self.family,
            "families": self.families,
            "parameter_size": self.parameter_size,
            "quantization_level": self.quantization_level,
            "context_length": self.context_length,
            "capabilities": self.capabilities.to_dict() if hasattr(self.capabilities, "to_dict") else self.capabilities,
            "capabilities_list": caps_list,
            "vision": getattr(self.capabilities, "vision", False),
            "tools_support": getattr(self.capabilities, "tools", False),
            "structured_output": getattr(self.capabilities, "structured_output", True),
            "details": self.raw_details
        }

@dataclass
class Session:
    id: str
    title: str
    model: str
    messages: List[ChatMessage] = field(default_factory=list)
    system_prompt: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "model": self.model,
            "messages": [m.to_dict() for m in self.messages],
            "system_prompt": self.system_prompt,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.messages),
            "metadata": self.metadata
        }

@dataclass
class RequestMetric:
    request_id: str
    model: str
    endpoint: str
    start_time: float
    ttft_ms: Optional[float] = None
    total_duration_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    tokens_per_second: Optional[float] = None
    success: bool = True
    cancelled: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "model": self.model,
            "endpoint": self.endpoint,
            "start_time": self.start_time,
            "ttft_ms": round(self.ttft_ms, 2) if self.ttft_ms is not None else None,
            "total_duration_ms": round(self.total_duration_ms, 2) if self.total_duration_ms is not None else None,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "tokens_per_second": round(self.tokens_per_second, 2) if self.tokens_per_second is not None else None,
            "success": self.success,
            "cancelled": self.cancelled,
            "error_message": self.error_message
        }

@dataclass
class HealthResponse:
    status: str # "ok", "degraded", "error"
    gateway_status: str # "healthy"
    provider_status: str # "connected", "unreachable", "error"
    provider_name: str
    provider_url: str
    lan_address: str
    port: int
    auth_enabled: bool
    active_requests: int
    active_sessions: int
    available_models: int
    uptime_seconds: float
    version: str = "1.0.0"
    message: Optional[str] = None

    @property
    def backend_reachable(self) -> bool:
        return self.provider_status == "connected"

    @property
    def inference_backend_status(self) -> str:
        return self.provider_status

    @property
    def backend_url(self) -> str:
        return self.provider_url

    @property
    def provider(self) -> str:
        return self.provider_name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "gateway_status": self.gateway_status,
            "provider_status": self.provider_status,
            "provider": self.provider_name,
            "provider_name": self.provider_name,
            "provider_url": self.provider_url,
            "backend_url": self.provider_url,
            "backend_reachable": self.provider_status == "connected",
            "inference_backend_status": self.provider_status,
            "lan_address": self.lan_address,
            "lan_ip": self.lan_address,
            "port": self.port,
            "gateway_url": f"http://{self.lan_address}:{self.port}",
            "bridge_url": f"http://{self.lan_address}:{self.port}",
            "auth_enabled": self.auth_enabled,
            "auth_required": self.auth_enabled,
            "active_requests": self.active_requests,
            "active_sessions": self.active_sessions,
            "available_models": self.available_models,
            "models_count": self.available_models,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "timestamp": time.time(),
            "version": self.version,
            "message": self.message or f"Gateway status: {self.status}"
        }

@dataclass
class DeviceRecord:
    device_id: str
    name: str
    token_hash: str
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at
        }
