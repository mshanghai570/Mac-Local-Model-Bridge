"""
Mac agent HTTP server.

The iPhone is the brain (GGUF inference) and the control surface.
This process is the Mac's hands: filesystem/shell tools, a live terminal
log, and an orchestrator that calls back to the iPhone for tokens.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from .discovery import lan_ip
from .phone_client import PhoneClient, PhoneClientError
from .tool_parser import parse_tool_calls, strip_tool_calls
from .tools import ToolExecutor

logger = logging.getLogger("bridge_cli.agent")

PROTOCOL_VERSION = "1.1"
MAX_TOOL_ROUNDS = 6


class PhoneRegistry:
    """Remembers the iPhone that last pinged or paired with this agent."""

    def __init__(self) -> None:
        self.url: Optional[str] = None
        self.name: str = "iPhone"
        self.last_seen: float = 0.0

    def register(self, url: str, name: Optional[str] = None) -> None:
        cleaned = (url or "").strip().rstrip("/")
        if not cleaned:
            return
        if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
            cleaned = "http://" + cleaned
        self.url = cleaned
        if name:
            self.name = name
        self.last_seen = time.time()
        logger.info("Registered iPhone %s at %s", self.name, self.url)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "name": self.name,
            "last_seen": self.last_seen,
            "connected": bool(self.url),
        }


def _merge_system(user_system: Optional[str], tool_prompt: str) -> str:
    parts = [p for p in (user_system, tool_prompt) if p]
    return "\n\n".join(parts)


def _print_event(kind: str, text: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp}] {kind}: {text}", flush=True)


async def run_agent_loop(
    phone: PhoneClient,
    executor: ToolExecutor,
    messages: List[Dict[str, Any]],
    model: str,
    temperature: float,
    system: Optional[str],
) -> AsyncIterator[Dict[str, Any]]:
    """
    Call the iPhone model, execute any <tool_call> blocks on this Mac,
    and yield SSE-friendly event dicts.
    """
    working = [dict(m) for m in messages]
    combined_system = _merge_system(system, executor.system_prompt())

    for round_index in range(MAX_TOOL_ROUNDS):
        collected = ""
        async for token in phone.chat(
            messages=working,
            model=model,
            temperature=temperature,
            system=combined_system,
            stream=True,
        ):
            collected += token
            visible = token
            # Don't stream raw XML tags to the iPhone UI if we can help it;
            # still collect them for parsing at the end of the round.
            yield {"type": "token", "content": visible}

        calls = parse_tool_calls(collected)
        visible_text = strip_tool_calls(collected)
        if not calls:
            yield {"type": "done", "content": visible_text, "model": model}
            return

        working.append({"role": "assistant", "content": collected})
        for call in calls:
            _print_event("tool", f"{call['name']} {json.dumps(call.get('arguments') or {})}")
            yield {"type": "tool", "name": call["name"], "arguments": call.get("arguments") or {}}
            result = executor.execute(call["name"], call.get("arguments") or {})
            body = result["content"] if result["ok"] else f"ERROR: {result['error']}"
            _print_event("result", f"{call['name']} ok={result['ok']} ({len(body)} chars)")
            yield {
                "type": "tool_result",
                "name": call["name"],
                "ok": result["ok"],
                "content": body,
            }
            working.append(
                {
                    "role": "user",
                    "content": f"[Mac tool result — {call['name']}]\n\n{body}",
                }
            )

        if round_index == MAX_TOOL_ROUNDS - 1:
            yield {
                "type": "done",
                "content": visible_text,
                "model": model,
                "warning": "tool round limit reached",
            }
            return


def create_app(
    executor: ToolExecutor,
    registry: PhoneRegistry,
    api_key: str = "",
    port: int = 8080,
) -> Any:
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse

    app = FastAPI(title="Mac Bridge CLI", version=PROTOCOL_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    started_at = time.time()

    def _unauthorized() -> Optional[JSONResponse]:
        return None

    @app.middleware("http")
    async def register_phone_and_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        phone_url = request.headers.get("x-phone-url") or request.headers.get("X-Phone-URL")
        phone_name = request.headers.get("x-phone-name") or request.headers.get("X-Phone-Name")
        if phone_url:
            registry.register(phone_url, phone_name)

        if api_key:
            supplied = ""
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                supplied = auth[7:].strip()
            if not supplied:
                supplied = request.headers.get("x-api-key") or ""
            if supplied != api_key:
                return JSONResponse({"error": "authentication failed"}, status_code=401)

        return await call_next(request)

    def health_payload() -> Dict[str, Any]:
        try:
            from local_ai_gateway.macos.status import build_bridge_health

            payload = build_bridge_health()
        except Exception:
            payload = {
                "status": "ok",
                "device": "Mac",
                "bridge": "running",
                "zed": False,
                "accessibility": False,
                "protocolVersion": PROTOCOL_VERSION,
            }
        payload.update(
            {
                "provider": "iphone-gguf",
                "provider_name": "iphone-gguf",
                "backend_reachable": bool(registry.url),
                "backend_url": registry.url,
                "models_count": 0,
                "message": (
                    f"Mac agent ready. iPhone: {registry.url}"
                    if registry.url
                    else "Mac agent ready. Open the iOS app and tap PING BUS to register this iPhone."
                ),
                "auth_required": bool(api_key),
                "lan_ip": lan_ip(),
                "port": port,
                "service": "bridge-cli",
                "version": PROTOCOL_VERSION,
                "uptime_seconds": int(time.time() - started_at),
                "phone": registry.snapshot(),
                "tools": executor.available_names(),
                "hostname": socket.gethostname(),
            }
        )
        return payload

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        return health_payload()

    @app.get("/ready")
    async def ready() -> JSONResponse:
        payload = health_payload()
        code = 200 if registry.url else 503
        return JSONResponse(payload, status_code=code)

    @app.get("/version")
    async def version() -> Dict[str, Any]:
        return {
            "name": "Mac Bridge CLI",
            "version": PROTOCOL_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "provider": "iphone-gguf",
        }

    @app.get("/tools")
    async def list_tools() -> Dict[str, Any]:
        return {"tools": executor.definitions(), "names": executor.available_names()}

    @app.post("/tools/call")
    async def call_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
        name = payload.get("name") or ""
        arguments = payload.get("arguments") or {}
        _print_event("tool", f"{name} {json.dumps(arguments)}")
        result = executor.execute(str(name), arguments if isinstance(arguments, dict) else {})
        _print_event("result", f"{name} ok={result['ok']}")
        return result

    @app.post("/pair/phone")
    async def pair_phone(payload: Dict[str, Any]) -> Dict[str, Any]:
        url = payload.get("url") or payload.get("phone_url") or ""
        name = payload.get("name") or "iPhone"
        if not url:
            return JSONResponse({"error": "url is required"}, status_code=400)  # type: ignore[return-value]
        registry.register(str(url), str(name))
        return {"ok": True, "phone": registry.snapshot()}

    @app.get("/phone")
    async def get_phone() -> Dict[str, Any]:
        return registry.snapshot()

    @app.get("/models")
    async def list_models() -> Dict[str, Any]:
        if not registry.url:
            return {"models": [], "count": 0, "default_model": "auto", "phone": None}
        client = PhoneClient(registry.url, api_key=api_key)
        try:
            models = await client.list_models()
        except PhoneClientError as exc:
            return {"models": [], "count": 0, "error": str(exc), "phone": registry.snapshot()}
        finally:
            await client.aclose()
        return {
            "models": models,
            "count": len(models),
            "default_model": models[0]["name"] if models else "auto",
            "phone": registry.snapshot(),
        }

    @app.get("/v1/models")
    async def openai_models() -> Dict[str, Any]:
        listing = await list_models()
        data = []
        for model in listing.get("models") or []:
            name = model.get("name") or model.get("id") or model.get("model")
            if name:
                data.append({"id": name, "object": "model", "owned_by": "iphone"})
        return {"object": "list", "data": data}

    async def _chat_events(payload: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        if not registry.url:
            yield {
                "type": "error",
                "content": "No iPhone registered. Open the iOS app, wait for the inference server, then tap PING BUS.",
            }
            return
        raw_messages = payload.get("messages") or []
        messages: List[Dict[str, Any]] = []
        for item in raw_messages:
            if not isinstance(item, dict):
                continue
            role = item.get("role") or "user"
            content = item.get("content") or ""
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part) for part in content
                )
            messages.append({"role": role, "content": str(content)})
        if not messages:
            yield {"type": "error", "content": "messages is required"}
            return
        model = payload.get("model") or "auto"
        temperature = float(payload.get("temperature") or 0.7)
        system = payload.get("system")
        preview = messages[-1]["content"][:80].replace("\n", " ")
        _print_event("prompt", f"{registry.name}: {preview}")
        client = PhoneClient(registry.url, api_key=api_key)
        try:
            async for event in run_agent_loop(
                phone=client,
                executor=executor,
                messages=messages,
                model=str(model),
                temperature=temperature,
                system=system,
            ):
                yield event
        except PhoneClientError as exc:
            yield {"type": "error", "content": str(exc)}
        finally:
            await client.aclose()

    def _native_sse(event: Dict[str, Any]) -> bytes:
        if event.get("type") == "token":
            body = {"content": event.get("content") or "", "done": False}
        elif event.get("type") == "tool":
            body = {
                "content": f"\n\n[mac tool: {event.get('name')}]\n",
                "done": False,
                "tool_calls": [
                    {
                        "id": f"call_{event.get('name')}",
                        "type": "function",
                        "function": {
                            "name": event.get("name"),
                            "arguments": json.dumps(event.get("arguments") or {}),
                        },
                    }
                ],
            }
        elif event.get("type") == "tool_result":
            body = {
                "content": f"\n{event.get('content')}\n",
                "done": False,
            }
        elif event.get("type") == "error":
            body = {"content": f"⚠️ {event.get('content')}", "done": True}
        else:
            body = {"content": "", "done": True, "model": event.get("model")}
        return f"data: {json.dumps(body)}\n\n".encode("utf-8")

    def _openai_sse(event: Dict[str, Any], chunk_id: str, created: int, model: str) -> bytes:
        if event.get("type") == "token":
            payload = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": event.get("content") or ""},
                        "finish_reason": None,
                    }
                ],
            }
            return f"data: {json.dumps(payload)}\n\n".encode("utf-8")
        if event.get("type") in {"tool", "tool_result"}:
            text = (
                f"\n\n[mac tool: {event.get('name')}]\n"
                if event.get("type") == "tool"
                else f"\n{event.get('content')}\n"
            )
            payload = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
            }
            return f"data: {json.dumps(payload)}\n\n".encode("utf-8")
        if event.get("type") == "error":
            payload = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": f"⚠️ {event.get('content')}"},
                        "finish_reason": "stop",
                    }
                ],
            }
            return f"data: {json.dumps(payload)}\n\n".encode("utf-8")
        payload = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        return f"data: {json.dumps(payload)}\n\n".encode("utf-8")

    @app.post("/chat")
    async def chat(payload: Dict[str, Any], request: Request) -> Any:
        stream = bool(payload.get("stream", True))
        if not stream:
            collected = ""
            async for event in _chat_events(payload):
                if event.get("type") == "token":
                    collected += event.get("content") or ""
                elif event.get("type") == "error":
                    return JSONResponse({"error": event.get("content")}, status_code=502)
            return {
                "content": strip_tool_calls(collected),
                "model": payload.get("model") or "auto",
            }

        async def generate() -> AsyncIterator[bytes]:
            async for event in _chat_events(payload):
                yield _native_sse(event)
                if event.get("type") in {"done", "error"}:
                    yield b"data: [DONE]\n\n"
                    return
            yield b"data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/v1/chat/completions")
    async def openai_chat(payload: Dict[str, Any]) -> Any:
        stream = bool(payload.get("stream", True))
        model = payload.get("model") or "auto"
        created = int(time.time())
        chunk_id = f"chatcmpl-{created}"
        if not stream:
            collected = ""
            async for event in _chat_events(payload):
                if event.get("type") == "token":
                    collected += event.get("content") or ""
                elif event.get("type") == "error":
                    return JSONResponse({"error": {"message": event.get("content")}}, status_code=502)
            return {
                "id": chunk_id,
                "object": "chat.completion",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": strip_tool_calls(collected)},
                        "finish_reason": "stop",
                    }
                ],
            }

        async def generate() -> AsyncIterator[bytes]:
            async for event in _chat_events(payload):
                yield _openai_sse(event, chunk_id, created, str(model))
                if event.get("type") in {"done", "error"}:
                    yield b"data: [DONE]\n\n"
                    return
            yield b"data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/agent/run")
    async def agent_run(payload: Dict[str, Any]) -> Any:
        phone_url = payload.get("phone_url") or payload.get("url")
        if phone_url:
            registry.register(str(phone_url), payload.get("name"))
        prompt = payload.get("prompt") or ""
        if not prompt and payload.get("messages"):
            return await chat(payload, None)  # type: ignore[arg-type]
        if not prompt:
            return JSONResponse({"error": "prompt is required"}, status_code=400)
        wrapped = {
            "model": payload.get("model") or "auto",
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "temperature": payload.get("temperature") or 0.7,
            "system": payload.get("system"),
        }
        return await chat(wrapped, None)  # type: ignore[arg-type]

    # silence unused
    _ = os.environ
    return app


def serve(
    host: str = "0.0.0.0",
    port: int = 8080,
    allow_write: bool = False,
    allow_shell: bool = False,
    api_key: str = "",
    phone_url: str = "",
) -> int:
    try:
        import uvicorn
    except ImportError:
        print("error: uvicorn is required. pip install uvicorn fastapi")
        return 1

    executor = ToolExecutor(allow_write=allow_write, allow_shell=allow_shell)
    registry = PhoneRegistry()
    if phone_url:
        registry.register(phone_url)

    app = create_app(executor=executor, registry=registry, api_key=api_key, port=port)

    advertiser = None
    try:
        from local_ai_gateway.discovery.bonjour import BonjourAdvertiser

        advertiser = BonjourAdvertiser(
            port=port,
            service_name="Mac Bridge CLI",
            properties={"provider": "iphone-gguf", "auth_required": bool(api_key)},
        )
        advertiser.start()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bonjour advertise failed: %s", exc)

    ip = lan_ip()
    print("=" * 64)
    print("  Mac Bridge CLI  —  iPhone-controlled Mac agent")
    print("=" * 64)
    print(f"  LAN:        http://{ip}:{port}")
    print(f"  Health:     http://{ip}:{port}/health")
    print(f"  Tools:      {', '.join(executor.available_names())}")
    print(f"  Write:      {'ON' if allow_write else 'off  (pass --allow-write)'}")
    print(f"  Shell:      {'ON' if allow_shell else 'off  (pass --allow-shell)'}")
    if registry.url:
        print(f"  iPhone:     {registry.url}")
    else:
        print("  iPhone:     waiting — open the app and tap PING BUS")
    print("=" * 64)
    print("  The iPhone runs GGUF models. This process executes Mac tools")
    print("  and mirrors the session here.")
    print("=" * 64, flush=True)

    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
        return 0
    finally:
        if advertiser is not None:
            try:
                advertiser.stop()
            except Exception:
                pass
