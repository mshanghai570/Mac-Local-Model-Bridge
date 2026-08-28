"""
Ollama Provider implementation for Local AI Gateway.
Provides connection pooling, retry resilience, streaming robustness, and normalized capabilities.
"""
from __future__ import annotations
import json
import asyncio
import time
import logging
from typing import List, Dict, Any, AsyncIterator, Optional

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    httpx = None  # type: ignore
    HAS_HTTPX = False

from .base import BaseModelProvider
from ..models import ChatRequest, GenerateRequest, ModelInfo, HealthResponse, ModelCapabilities
from ..config import config
from ..metrics import metrics_collector
from ..inference_trace import control_token_flags, emit as emit_inference_trace, fingerprint, message_manifest
from ..sessions import session_manager
from ..errors import (
    ProviderUnavailableError,
    ProviderError,
    ProviderTimeoutError,
    ModelNotFoundError,
)

logger = logging.getLogger("local_ai_gateway.provider.ollama")

def format_size(bytes_num: int) -> str:
    if bytes_num < 1024:
        return f"{bytes_num} B"
    elif bytes_num < 1024 * 1024:
        return f"{bytes_num / 1024:.1f} KB"
    elif bytes_num < 1024 * 1024 * 1024:
        return f"{bytes_num / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_num / (1024 * 1024 * 1024):.2f} GB"

def infer_capabilities(name: str, family: Optional[str] = None) -> ModelCapabilities:
    name_lower = name.lower()
    family_lower = (family or "").lower()

    is_vision = any(k in name_lower or k in family_lower for k in [
        "vision", "llava", "moondream", "minicpm-v", "bakllava", "qwen-vl", "phi3-vision"
    ])
    is_tools = any(k in name_lower or k in family_lower for k in [
        "llama3", "llama3.1", "llama3.2", "llama3.3", "qwen2.5", "mistral", "command-r", "hermes", "deepseek"
    ])
    is_embed = any(k in name_lower for k in ["embed", "nomic-embed", "bge", "all-minilm"])

    return ModelCapabilities(
        text=not is_embed,
        vision=is_vision,
        tools=is_tools,
        structured_output=True,
        embeddings=is_embed
    )

class OllamaProvider(BaseModelProvider):
    provider_name: str = "ollama"

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self.base_url = (base_url or config.ollama_url).rstrip("/")
        self.timeout = timeout or config.request_timeout
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self._boot_time = time.time()
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Returns or lazily creates a shared, connection-pooled AsyncClient."""
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
            timeout_config = httpx.Timeout(
                connect=config.connect_timeout,
                read=config.generation_timeout,
                write=config.request_timeout,
                pool=10.0
            )
            self._client = httpx.AsyncClient(limits=limits, timeout=timeout_config)
        return self._client

    async def close(self) -> None:
        """Closes the reusable HTTP client session cleanly."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request_http(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        Executes HTTP request to Ollama with connection reuse and exponential backoff on connection errors.
        """
        url = f"{self.base_url}{path}"
        client = self._get_client()

        last_err: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                if method.upper() == "GET":
                    resp = await client.get(url)
                else:
                    resp = await client.post(url, json=payload)

                if resp.status_code == 404:
                    err_msg = f"Resource '{path}' or model not found in Ollama."
                    try:
                        err_msg = resp.json().get("error", err_msg)
                    except Exception:
                        pass
                    raise ModelNotFoundError(err_msg, message=err_msg)

                if resp.status_code >= 400:
                    raise ProviderError(f"Ollama returned HTTP {resp.status_code}: {resp.text}")

                return resp.json()

            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                last_err = e
                if attempt < max_retries:
                    await asyncio.sleep(0.25 * (2 ** attempt))
                    continue
                raise ProviderUnavailableError(
                    f"Unable to connect to Ollama at {self.base_url}. Ensure Ollama is running ('ollama serve')."
                )
            except httpx.TimeoutException:
                raise ProviderTimeoutError(f"Request to Ollama at {url} timed out.")
            except (ModelNotFoundError, ProviderError, ProviderUnavailableError):
                raise
            except Exception as e:
                raise ProviderError(f"Unexpected error communicating with Ollama: {str(e)}")

        raise ProviderUnavailableError(f"Failed to reach Ollama at {self.base_url}: {last_err}")

    async def check_health(self) -> HealthResponse:
        uptime = time.time() - self._boot_time
        active_reqs = metrics_collector.get_active_count()
        active_sess = session_manager.count()

        try:
            res = await self._request_http("GET", "/api/tags", max_retries=1)
            models = res.get("models", [])
            return HealthResponse(
                status="ok",
                gateway_status="healthy",
                provider_status="connected",
                provider_name="Ollama",
                provider_url=self.base_url,
                lan_address=config.lan_ip,
                port=config.port,
                auth_enabled=bool(config.api_key),
                active_requests=active_reqs,
                active_sessions=active_sess,
                available_models=len(models),
                uptime_seconds=uptime,
                message=f"Connected to Ollama. {len(models)} model(s) installed on Mac."
            )
        except Exception as e:
            return HealthResponse(
                status="degraded",
                gateway_status="healthy",
                provider_status="unreachable",
                provider_name="Ollama",
                provider_url=self.base_url,
                lan_address=config.lan_ip,
                port=config.port,
                auth_enabled=bool(config.api_key),
                active_requests=active_reqs,
                active_sessions=active_sess,
                available_models=0,
                uptime_seconds=uptime,
                message=str(e)
            )

    async def list_models(self) -> List[ModelInfo]:
        res = await self._request_http("GET", "/api/tags")
        raw_models = res.get("models", [])
        output: List[ModelInfo] = []

        for m in raw_models:
            name = m.get("name", "unknown")
            size = m.get("size", 0)
            details = m.get("details", {})
            family = details.get("family")
            caps = infer_capabilities(name, family)
            param_size = details.get("parameter_size")
            quant = details.get("quantization_level")

            output.append(
                ModelInfo(
                    name=name,
                    size_bytes=size,
                    size_formatted=format_size(size),
                    modified_at=m.get("modified_at", ""),
                    digest=m.get("digest", "")[:12],
                    format=details.get("format"),
                    family=family,
                    families=details.get("families"),
                    parameter_size=param_size,
                    quantization_level=quant,
                    context_length=details.get("context_length") or 4096,
                    capabilities=caps,
                    raw_details=details
                )
            )
        return output

    async def get_model_info(self, model_name: str) -> Dict[str, Any]:
        res = await self._request_http("POST", "/api/show", {"name": model_name})
        details = res.get("details", {})
        family = details.get("family")
        caps = infer_capabilities(model_name, family)
        
        return {
            "name": model_name,
            "license": res.get("license"),
            "modelfile": res.get("modelfile"),
            "parameters": res.get("parameters"),
            "template": res.get("template"),
            "system": res.get("system"),
            "details": details,
            "family": family,
            "parameter_size": details.get("parameter_size"),
            "quantization_level": details.get("quantization_level"),
            "format": details.get("format"),
            "capabilities": caps.to_dict(),
            "vision": caps.vision,
            "tools_support": caps.tools,
            "structured_output": caps.structured_output,
            "model_info": res.get("model_info", {})
        }

    def _build_ollama_messages(self, request: ChatRequest) -> List[Dict[str, Any]]:
        ollama_msgs = []
        if request.system:
            ollama_msgs.append({"role": "system", "content": request.system})

        for msg in request.messages:
            m_dict: Dict[str, Any] = {"role": msg.role, "content": msg.content or ""}
            if msg.images:
                m_dict["images"] = msg.images
            if msg.tool_calls:
                m_dict["tool_calls"] = msg.tool_calls
            ollama_msgs.append(m_dict)

        return ollama_msgs

    async def chat(self, request: ChatRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": self._build_ollama_messages(request),
            "stream": False
        }
        options = dict(request.options or {})
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.top_p is not None:
            options["top_p"] = request.top_p
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if options:
            payload["options"] = options
        if request.tools:
            payload["tools"] = request.tools
        if request.response_format:
            payload["format"] = request.response_format

        res = await self._request_http("POST", "/api/chat", payload)
        message = res.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls")

        return {
            "model": res.get("model", request.model),
            "role": message.get("role", "assistant"),
            "content": content,
            "tool_calls": tool_calls,
            "done": res.get("done", True),
            "total_duration_ns": res.get("total_duration"),
            "load_duration_ns": res.get("load_duration"),
            "prompt_eval_count": res.get("prompt_eval_count"),
            "eval_count": res.get("eval_count"),
            "eval_duration_ns": res.get("eval_duration")
        }

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[Dict[str, Any]]:
        url = f"{self.base_url}/api/chat"
        upstream_messages = self._build_ollama_messages(request)
        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": upstream_messages,
            "stream": True
        }
        options = dict(request.options or {})
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.top_p is not None:
            options["top_p"] = request.top_p
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if options:
            payload["options"] = options
        if request.tools:
            payload["tools"] = request.tools
        if request.response_format:
            payload["format"] = request.response_format

        req_id = request.request_id or f"req-{int(time.time()*1000)}"
        client = self._get_client()
        emit_inference_trace(
            config.inference_trace,
            req_id,
            "ollama_request",
            endpoint=url,
            runtime_model=request.model,
            message_manifest=message_manifest(upstream_messages),
        )
        response_text = ""
        token_count = 0

        try:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code == 404:
                    raise ModelNotFoundError(request.model)
                if response.status_code != 200:
                    err_body = await response.aread()
                    raise ProviderError(f"Ollama stream HTTP {response.status_code}: {err_body.decode('utf-8')}")

                async for line in response.aiter_lines():
                    if not line or not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        msg = chunk.get("message", {})
                        content_piece = msg.get("content", "")
                        response_text += content_piece
                        tool_calls = msg.get("tool_calls")
                        
                        if content_piece or tool_calls:
                            token_count += 1
                            if token_count == 1:
                                metrics_collector.record_first_token(req_id)

                        yield {
                            "model": chunk.get("model", request.model),
                            "content": content_piece,
                            "role": msg.get("role", "assistant"),
                            "tool_calls": tool_calls,
                            "done": chunk.get("done", False),
                            "total_duration": chunk.get("total_duration"),
                            "eval_count": chunk.get("eval_count"),
                            "eval_duration": chunk.get("eval_duration")
                        }
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise ProviderUnavailableError(f"Lost connection to Ollama at {self.base_url}: {e}")
        except httpx.TimeoutException:
            raise ProviderTimeoutError(f"Streaming request to Ollama timed out after {config.generation_timeout}s.")
        finally:
            emit_inference_trace(
                config.inference_trace,
                req_id,
                "ollama_response",
                chunks=token_count,
                response_characters=len(response_text),
                response_sha256_16=fingerprint(response_text),
                surfaced_control_tokens=control_token_flags(response_text),
            )

    async def generate(self, request: GenerateRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
            "stream": False
        }
        if request.system:
            payload["system"] = request.system
        if request.images:
            payload["images"] = request.images
        options = dict(request.options or {})
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.top_p is not None:
            options["top_p"] = request.top_p
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if options:
            payload["options"] = options

        res = await self._request_http("POST", "/api/generate", payload)
        return {
            "model": res.get("model", request.model),
            "response": res.get("response", ""),
            "done": res.get("done", True),
            "total_duration_ns": res.get("total_duration"),
            "eval_count": res.get("eval_count")
        }

    async def generate_stream(self, request: GenerateRequest) -> AsyncIterator[Dict[str, Any]]:
        url = f"{self.base_url}/api/generate"
        payload: Dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
            "stream": True
        }
        if request.system:
            payload["system"] = request.system
        if request.images:
            payload["images"] = request.images
        options = dict(request.options or {})
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.top_p is not None:
            options["top_p"] = request.top_p
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if options:
            payload["options"] = options

        req_id = request.request_id or f"gen-{int(time.time()*1000)}"
        client = self._get_client()

        try:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code == 404:
                    raise ModelNotFoundError(request.model)
                if response.status_code != 200:
                    err_body = await response.aread()
                    raise ProviderError(f"Ollama generate stream HTTP {response.status_code}: {err_body.decode('utf-8')}")

                token_count = 0
                async for line in response.aiter_lines():
                    if not line or not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        token_count += 1
                        if token_count == 1:
                            metrics_collector.record_first_token(req_id)
                        yield {
                            "model": chunk.get("model", request.model),
                            "response": chunk.get("response", ""),
                            "done": chunk.get("done", False),
                            "eval_count": chunk.get("eval_count")
                        }
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise ProviderUnavailableError(f"Lost connection to Ollama at {self.base_url}: {e}")
        except httpx.TimeoutException:
            raise ProviderTimeoutError(f"Generate stream to Ollama timed out after {config.generation_timeout}s.")

    async def cancel_request(self, request_id: str) -> bool:
        task = self.active_tasks.get(request_id)
        if task and not task.done():
            task.cancel()
            metrics_collector.finish_request(request_id, cancelled=True)
            return True
        return False

    async def stop(self, task_id: Optional[str] = None, request_id: Optional[str] = None) -> Dict[str, Any]:
        target = task_id or request_id or ""
        cancelled = await self.cancel_request(target)
        return {"status": "cancelled" if cancelled else "not_found", "task_id": target}

