"""
Abstract Base Provider contract for Local AI Gateway inference engines.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncIterator, Optional
from ..models import ChatRequest, GenerateRequest, ModelInfo, HealthResponse

class BaseModelProvider(ABC):
    """
    Abstract Base Class for Local AI Model Providers (Ollama, Apple MLX, llama.cpp, etc.).
    
    To implement a new provider (e.g. MLXProvider):
    1. Subclass `BaseModelProvider`.
    2. Implement all abstract methods below.
    3. Register via `register_provider("mlx", MLXProvider)` in `local_ai_gateway/providers/__init__.py`.
    """
    provider_name: str = "base"

    @abstractmethod
    async def check_health(self) -> HealthResponse:
        """Probes local inference runtime connectivity, installed models, and health."""
        pass

    @abstractmethod
    async def list_models(self) -> List[ModelInfo]:
        """Fetches all installed/available models on the Mac with normalized capabilities."""
        pass

    @abstractmethod
    async def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Fetches deep model parameters, context length, license, and prompt templates."""
        pass

    @abstractmethod
    async def chat(self, request: ChatRequest) -> Dict[str, Any]:
        """Executes a non-streaming chat completion."""
        pass

    @abstractmethod
    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[Dict[str, Any]]:
        """Yields real-time streamed chat completion token chunks."""
        pass

    @abstractmethod
    async def generate(self, request: GenerateRequest) -> Dict[str, Any]:
        """Executes a non-streaming raw text prompt completion."""
        pass

    @abstractmethod
    async def generate_stream(self, request: GenerateRequest) -> AsyncIterator[Dict[str, Any]]:
        """Yields real-time streamed prompt completion token chunks."""
        pass

    @abstractmethod
    async def cancel_request(self, request_id: str) -> bool:
        """Cancels an in-flight generation task if active."""
        pass

    async def close(self) -> None:
        """Performs cleanup of reusable HTTP clients or backend sessions upon server shutdown."""
        pass
