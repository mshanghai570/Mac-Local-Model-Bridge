"""
Provider registry and factory for Local AI Gateway.
"""
from typing import Dict, Type
from .base import BaseModelProvider
from .ollama import OllamaProvider

_PROVIDERS: Dict[str, Type[BaseModelProvider]] = {
    "ollama": OllamaProvider,
}

_INSTANCES: Dict[str, BaseModelProvider] = {}

def get_provider(provider_name: str = "ollama") -> BaseModelProvider:
    """Returns the singleton instance of the configured model provider."""
    name = provider_name.lower().strip()
    if name not in _INSTANCES:
        provider_cls = _PROVIDERS.get(name)
        if not provider_cls:
            # Fallback to Ollama
            provider_cls = OllamaProvider
        _INSTANCES[name] = provider_cls()
    return _INSTANCES[name]

def register_provider(name: str, provider_cls: Type[BaseModelProvider]) -> None:
    """Registers a new provider class (e.g. MLXProvider)."""
    _PROVIDERS[name.lower().strip()] = provider_cls

async def close_all_providers() -> None:
    """Gracefully closes all provider connections during gateway shutdown."""
    for p in _INSTANCES.values():
        try:
            await p.close()
        except Exception:
            pass
    _INSTANCES.clear()
