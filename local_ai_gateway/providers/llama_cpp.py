"""Provider adapter for a bridge-managed loopback llama.cpp server."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from .base import BaseModelProvider
from .ollama import format_size, infer_capabilities
from ..config import config
from ..errors import ModelNotFoundError, ProviderError, ProviderTimeoutError, ProviderUnavailableError
from ..metrics import metrics_collector
from ..inference_trace import control_token_flags, emit as emit_inference_trace, fingerprint, message_manifest
from ..model_store import model_store
from ..models import ChatMessage, ChatRequest, GenerateRequest, HealthResponse, ModelInfo
from ..runtime import llama_cpp_runtime
from ..sessions import session_manager


class LlamaCppProvider(BaseModelProvider):
    """Talk to the managed local llama.cpp server through its OpenAI API."""

    provider_name = "llama.cpp"

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None) -> None:
        self.base_url = (base_url or llama_cpp_runtime.base_url).rstrip("/")
        self.timeout = timeout or config.request_timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=config.connect_timeout,
                    read=config.generation_timeout,
                    write=config.request_timeout,
                    pool=10.0,
                )
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    def _require_running(self) -> Dict[str, Any]:
        status = llama_cpp_runtime.status()
        if not status.get("running"):
            reason = status.get("last_error") or "Select a Mac-stored GGUF and start the llama.cpp runtime first."
            raise ProviderUnavailableError(f"llama.cpp runtime is not running: {reason}")
        return status

    async def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._require_running()
        try:
            response = await self._get_client().request(method, f"{self.base_url}{path}", json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ProviderUnavailableError(f"Cannot reach managed llama.cpp runtime at {self.base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"Request to llama.cpp timed out at {self.base_url}{path}.") from exc
        if response.status_code == 404:
            raise ModelNotFoundError(payload.get("model", path) if payload else path)
        if response.status_code >= 400:
            raise ProviderError(f"llama.cpp returned HTTP {response.status_code}: {response.text}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError("llama.cpp returned an invalid JSON response.") from exc

    def _active_model(self) -> Dict[str, Any]:
        model = model_store.active_model()
        if not model:
            raise ModelNotFoundError("No selected Mac GGUF model")
        return model

    async def check_health(self) -> HealthResponse:
        status = llama_cpp_runtime.status()
        running = bool(status.get("running"))
        active = model_store.active_model()
        return HealthResponse(
            status="ok" if running else "degraded",
            gateway_status="healthy",
            provider_status="connected" if running else "unreachable",
            provider_name="llama.cpp",
            provider_url=self.base_url,
            lan_address=config.lan_ip,
            port=config.port,
            auth_enabled=bool(config.api_key),
            active_requests=metrics_collector.get_active_count(),
            active_sessions=session_manager.count(),
            available_models=1 if active else 0,
            uptime_seconds=0.0,
            message=(
                f"llama.cpp serving {active['filename']} on loopback."
                if running and active
                else status.get("last_error") or "llama.cpp runtime is not running."
            ),
        )

    async def list_models(self) -> List[ModelInfo]:
        self._require_running()
        local = self._active_model()
        metadata = local.get("metadata") or {}
        return [
            ModelInfo(
                name=local["filename"],
                size_bytes=int(local["size_bytes"]),
                size_formatted=format_size(int(local["size_bytes"])),
                modified_at=str(local.get("imported_at") or ""),
                digest=str(local["sha256"])[:12],
                format="gguf",
                family=metadata.get("architecture"),
                parameter_size=None,
                quantization_level=str(metadata.get("file_type")) if metadata.get("file_type") is not None else None,
                context_length=metadata.get("context_length"),
                capabilities=infer_capabilities(local["filename"], metadata.get("architecture")),
                raw_details=metadata,
            )
        ]

    async def get_model_info(self, model_name: str) -> Dict[str, Any]:
        local = self._active_model()
        if model_name not in {"auto", local["filename"], local["sha256"]}:
            raise ModelNotFoundError(model_name)
        metadata = local.get("metadata") or {}
        capabilities = infer_capabilities(local["filename"], metadata.get("architecture"))
        return {
            "name": local["filename"],
            "sha256": local["sha256"],
            "size_bytes": local["size_bytes"],
            "format": "gguf",
            "family": metadata.get("architecture"),
            "context_length": metadata.get("context_length"),
            "details": metadata,
            "capabilities": capabilities.to_dict(),
            "vision": capabilities.vision,
            "tools_support": capabilities.tools,
            "structured_output": capabilities.structured_output,
        }

    @staticmethod
    def _messages(request: ChatRequest) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(message.to_dict() for message in request.messages)
        return messages

    def _model_name(self, request_model: str) -> str:
        active = self._active_model()
        if request_model not in {"auto", active["filename"], active["sha256"]}:
            raise ModelNotFoundError(
                f"The active llama.cpp model is {active['filename']}; requested {request_model}."
            )
        return active["filename"]

    def _chat_payload(self, request: ChatRequest, stream: bool) -> Dict[str, Any]:
        model = self._model_name(request.model)
        payload: Dict[str, Any] = {
            "model": model,
            "messages": self._messages(request),
            "stream": stream,
            "temperature": request.temperature,
            "top_p": request.top_p,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools
        if request.response_format:
            payload["response_format"] = request.response_format
        return {key: value for key, value in payload.items() if value is not None}

    async def chat(self, request: ChatRequest) -> Dict[str, Any]:
        body = await self._request("POST", "/v1/chat/completions", self._chat_payload(request, stream=False))
        choices = body.get("choices") or []
        if not choices:
            raise ProviderError("llama.cpp response had no completion choices.")
        message = choices[0].get("message") or {}
        return {
            "model": body.get("model", request.model),
            "role": message.get("role", "assistant"),
            "content": message.get("content", ""),
            "tool_calls": message.get("tool_calls"),
            "done": True,
            "usage": body.get("usage"),
        }

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[Dict[str, Any]]:
        runtime_status = self._require_running()
        req_id = request.request_id or f"llamacpp-{int(time.time() * 1000)}"
        upstream_payload = self._chat_payload(request, stream=True)
        running_model = runtime_status.get("model") or {}
        emit_inference_trace(
            config.inference_trace,
            req_id,
            "llama_cpp_request",
            endpoint=f"{self.base_url}/v1/chat/completions",
            runtime_pid=runtime_status.get("pid"),
            runtime_model=running_model.get("filename"),
            runtime_model_sha256_16=str(runtime_status.get("model_sha256") or "")[:16],
            message_manifest=message_manifest(upstream_payload.get("messages") or []),
        )
        response_text = ""
        chunk_count = 0
        try:
            async with self._get_client().stream(
                "POST", f"{self.base_url}/v1/chat/completions", json=upstream_payload
            ) as response:
                if response.status_code == 404:
                    raise ModelNotFoundError(request.model)
                if response.status_code >= 400:
                    raise ProviderError(f"llama.cpp stream HTTP {response.status_code}: {(await response.aread()).decode('utf-8', 'replace')}")
                first = True
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        return
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    content = delta.get("content") or ""
                    response_text += content
                    if content:
                        chunk_count += 1
                    if content and first:
                        metrics_collector.record_first_token(req_id)
                        first = False
                    yield {
                        "model": chunk.get("model", request.model),
                        "content": content,
                        "role": delta.get("role", "assistant"),
                        "tool_calls": delta.get("tool_calls"),
                        "done": choice.get("finish_reason") is not None,
                    }
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ProviderUnavailableError(f"Lost connection to llama.cpp at {self.base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("llama.cpp streaming request timed out.") from exc
        finally:
            emit_inference_trace(
                config.inference_trace,
                req_id,
                "llama_cpp_response",
                chunks=chunk_count,
                response_characters=len(response_text),
                response_sha256_16=fingerprint(response_text),
                surfaced_control_tokens=control_token_flags(response_text),
            )

    async def generate(self, request: GenerateRequest) -> Dict[str, Any]:
        # The chat-completions endpoint is used deliberately because it is the stable shared surface
        # consumed by both Zed and the bridge; a single user message preserves raw prompt semantics.
        result = await self.chat(
            ChatRequest(
                model=request.model,
                messages=[ChatMessage(role="user", content=request.prompt)],
                system=request.system,
                temperature=request.temperature,
                top_p=request.top_p,
                max_tokens=request.max_tokens,
                options=request.options,
            )
        )
        return {"model": result["model"], "response": result["content"], "done": True}

    async def generate_stream(self, request: GenerateRequest) -> AsyncIterator[Dict[str, Any]]:
        chat_request = ChatRequest(
            model=request.model,
            messages=[ChatMessage(role="user", content=request.prompt)],
            system=request.system,
            temperature=request.temperature,
            top_p=request.top_p,
            max_tokens=request.max_tokens,
            request_id=request.request_id,
        )
        async for chunk in self.chat_stream(chat_request):
            yield {"model": chunk["model"], "response": chunk["content"], "done": chunk["done"]}

    async def cancel_request(self, request_id: str) -> bool:
        # llama.cpp exposes cancellation differently between versions; do not send an invented command.
        return False
