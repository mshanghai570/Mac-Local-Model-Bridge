"""
Primary REST API routes for Local AI Gateway.
"""
import json
import time
import uuid
import logging
from typing import Optional, Dict, Any, List

from ..config import config
from ..models import ChatRequest, ChatMessage, GenerateRequest
from ..auth import verify_token, extract_api_key, device_manager
from ..providers import get_provider
from ..sessions import session_manager, estimate_tokens
from ..router import model_router
from ..metrics import metrics_collector
from ..errors import (
    GatewayError,
    AuthenticationError,
    InvalidRequestError,
    ModelNotFoundError,
    SessionNotFoundError,
    ProviderUnavailableError,
    format_error_response
)
from .streaming import format_sse_event, format_sse_done, format_sse_comment

logger = logging.getLogger("local_ai_gateway.api.rest")

try:
    from fastapi import APIRouter, Request, Response, HTTPException
    from fastapi.responses import StreamingResponse, JSONResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    class DummyRouter:
        def get(self, *args, **kwargs): return lambda f: f
        def post(self, *args, **kwargs): return lambda f: f
        def put(self, *args, **kwargs): return lambda f: f
        def delete(self, *args, **kwargs): return lambda f: f
    APIRouter = DummyRouter
    Request = Any
    Response = Any
    HTTPException = Exception
    StreamingResponse = Any
    JSONResponse = Any

provider = get_provider(config.provider)
router = APIRouter()

def get_or_create_request_id(request: Request, payload: Optional[Dict[str, Any]] = None) -> str:
    """Extracts or generates a clean unique request ID."""
    req_id = request.headers.get("x-request-id")
    if not req_id and payload:
        req_id = payload.get("request_id")
    if not req_id:
        req_id = f"req_{uuid.uuid4().hex[:10]}"
    return req_id

def check_auth(request: Request):
    if not config.api_key:
        return
    token = extract_api_key(
        headers=dict(request.headers),
        query_params=dict(request.query_params)
    )
    if not verify_token(token):
        raise AuthenticationError("Unauthorized: Missing or invalid API key or paired device token.")

# 1. Health, Readiness, and Version Endpoints
@router.get("/health")
async def get_health(request: Request):
    """
    Liveness probe: verifies the Local AI Gateway process is alive.
    Returns Mac bridge status (Zed running, Accessibility trust), memory stats,
    active sessions, request counters, and uptime.
    """
    from ..macos import build_bridge_health
    summary = metrics_collector.get_summary()
    payload = build_bridge_health()
    payload.update({
        "service": "local-ai-gateway",
        "version": "1.0.0",
        "uptime_seconds": summary["uptime_seconds"],
        "lan_url": config.lan_url,
        "active_requests": summary["active_requests"],
        "active_sessions": session_manager.count(),
        "total_requests": summary["total_requests"],
        "system_resources": summary["system_resources"]
    })
    return payload

@router.get("/ready")
async def get_readiness(request: Request):
    """
    Readiness probe: verifies gateway can accept inference requests and backend model provider is reachable.
    Returns 200 OK if provider is connected, or 503 Service Unavailable if provider is offline.
    """
    health_info = await provider.check_health()
    status_code = 200 if health_info.provider_status == "connected" else 503
    return JSONResponse(status_code=status_code, content=health_info.to_dict())

@router.get("/version")
async def get_version(request: Request):
    """Returns semantic versioning details of the gateway."""
    return {
        "name": "Local AI Gateway for iPhone & Mac",
        "version": "1.0.0",
        "protocol_version": "1.0.0",
        "provider": config.provider
    }

# 2. Model Discovery & Metadata
@router.get("/models")
async def list_models(request: Request):
    """List locally installed models on the Mac, normalized capabilities, and configured aliases."""
    check_auth(request)
    try:
        models = await provider.list_models()
        return {
            "models": [m.to_dict() for m in models],
            "count": len(models),
            "aliases": model_router.get_aliases(),
            "default_model": config.default_model
        }
    except Exception as e:
        req_id = get_or_create_request_id(request)
        logger.error(f"[{req_id}] Error listing models: {e}")
        raise ProviderUnavailableError(f"Failed to fetch models from {config.provider}: {str(e)}", request_id=req_id)

@router.get("/models/{model_name:path}")
async def get_model_info(model_name: str, request: Request):
    """Get detailed specifications, context length, parameters, and prompt template for a specific model."""
    check_auth(request)
    req_id = get_or_create_request_id(request)
    try:
        resolved_model = model_router.resolve_model(model_name)
        info = await provider.get_model_info(resolved_model)
        return info
    except ModelNotFoundError:
        raise ModelNotFoundError(model_name, request_id=req_id)
    except Exception as e:
        logger.error(f"[{req_id}] Error getting model info for '{model_name}': {e}")
        raise ProviderUnavailableError(str(e), request_id=req_id)

# 3. Chat & Generation Endpoints
@router.post("/chat")
async def chat_endpoint(payload: Dict[str, Any], request: Request):
    """
    Chat completion endpoint with optional SSE streaming, context management, and session linkage.
    """
    check_auth(request)
    req_id = get_or_create_request_id(request, payload)

    raw_model = payload.get("model", "auto")
    task = payload.get("task")
    raw_msgs = payload.get("messages", [])
    session_id = payload.get("session_id")

    if not isinstance(raw_msgs, list) or not raw_msgs:
        if session_id:
            sess = session_manager.get_session(session_id)
            if sess and sess.messages:
                messages = list(sess.messages)
            else:
                raise SessionNotFoundError(session_id, request_id=req_id)
        else:
            raise InvalidRequestError("'messages' must be a non-empty list of message objects", param="messages", request_id=req_id)
    else:
        messages = [
            ChatMessage(
                role=m.get("role", "user"),
                content=m.get("content", ""),
                images=m.get("images"),
                tool_calls=m.get("tool_calls"),
                tool_call_id=m.get("tool_call_id")
            )
            for m in raw_msgs
        ]

    # Model resolution with task & alias awareness
    resolved_model = model_router.resolve_model(
        requested_model=raw_model,
        task=task,
        messages=messages
    )

    # Context awareness and trimming
    managed_messages, context_telemetry = session_manager.check_and_manage_context(
        messages=messages,
        system_prompt=payload.get("system"),
        strategy=payload.get("context_strategy")
    )

    metrics_collector.start_request(req_id, resolved_model, "/chat")
    stream_requested = bool(payload.get("stream", False)) or request.headers.get("accept") == "text/event-stream"

    chat_req = ChatRequest(
        model=resolved_model,
        messages=managed_messages,
        temperature=payload.get("temperature", 0.7),
        top_p=payload.get("top_p", 0.9),
        max_tokens=payload.get("max_tokens"),
        system=payload.get("system"),
        stream=stream_requested,
        tools=payload.get("tools"),
        response_format=payload.get("response_format"),
        options=payload.get("options", {}),
        request_id=req_id
    )

    if stream_requested:
        async def event_generator():
            token_count = 0
            full_response_text = ""
            start_t = time.time()
            try:
                # Initial telemetry event
                yield format_sse_event({
                    "event": "context_telemetry",
                    "telemetry": context_telemetry,
                    "resolved_model": resolved_model,
                    "request_id": req_id
                })

                async for chunk in provider.chat_stream(chat_req):
                    token_count += 1
                    content = chunk.get("content", "")
                    full_response_text += content
                    yield format_sse_event({
                        "request_id": req_id,
                        "model": resolved_model,
                        "content": content,
                        "role": chunk.get("role", "assistant"),
                        "tool_calls": chunk.get("tool_calls"),
                        "done": chunk.get("done", False)
                    })

                # Record metrics and update session if linked
                duration_s = max(0.001, time.time() - start_t)
                metrics_collector.finish_request(req_id, completion_tokens=token_count, success=True)
                
                if session_id and full_response_text:
                    if messages and messages[-1].role == "user":
                        session_manager.add_message(session_id, messages[-1])
                    session_manager.add_message(session_id, ChatMessage(role="assistant", content=full_response_text))

                # Final metrics event
                yield format_sse_event({
                    "event": "done",
                    "request_id": req_id,
                    "total_tokens": token_count,
                    "duration_seconds": round(duration_s, 2),
                    "tokens_per_second": round(token_count / duration_s, 1) if duration_s > 0 else 0
                })
                yield format_sse_done()

            except Exception as e:
                logger.error(f"[{req_id}] Stream error: {e}")
                metrics_collector.finish_request(req_id, completion_tokens=token_count, success=False, error_message=str(e))
                yield format_sse_event({"error": str(e), "request_id": req_id})
                yield format_sse_done()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Request-ID": req_id
            }
        )

    # Non-streaming execution
    try:
        res = await provider.chat(chat_req)
        content = res.get("content", "")
        tokens = estimate_tokens(content)
        metrics_collector.finish_request(req_id, completion_tokens=tokens, success=True)

        if session_id and content:
            if messages and messages[-1].role == "user":
                session_manager.add_message(session_id, messages[-1])
            session_manager.add_message(session_id, ChatMessage(role="assistant", content=content))

        return {
            "request_id": req_id,
            "model": resolved_model,
            "role": res.get("role", "assistant"),
            "content": content,
            "tool_calls": res.get("tool_calls"),
            "context_telemetry": context_telemetry,
            "done": True
        }
    except Exception as e:
        metrics_collector.finish_request(req_id, success=False, error_message=str(e))
        raise

@router.post("/generate")
async def generate_endpoint(payload: Dict[str, Any], request: Request):
    """Raw prompt completion endpoint with optional SSE streaming."""
    check_auth(request)
    req_id = get_or_create_request_id(request, payload)

    prompt = payload.get("prompt", "")
    if not prompt:
        raise InvalidRequestError("'prompt' field is required and cannot be empty", param="prompt", request_id=req_id)

    raw_model = payload.get("model", "auto")
    task = payload.get("task")
    resolved_model = model_router.resolve_model(requested_model=raw_model, task=task, prompt=prompt)

    metrics_collector.start_request(req_id, resolved_model, "/generate")
    stream_requested = bool(payload.get("stream", False)) or request.headers.get("accept") == "text/event-stream"

    gen_req = GenerateRequest(
        model=resolved_model,
        prompt=prompt,
        temperature=payload.get("temperature", 0.7),
        top_p=payload.get("top_p", 0.9),
        max_tokens=payload.get("max_tokens"),
        system=payload.get("system"),
        stream=stream_requested,
        images=payload.get("images"),
        options=payload.get("options", {}),
        request_id=req_id
    )

    if stream_requested:
        async def event_generator():
            token_count = 0
            start_t = time.time()
            try:
                async for chunk in provider.generate_stream(gen_req):
                    token_count += 1
                    yield format_sse_event({
                        "request_id": req_id,
                        "model": resolved_model,
                        "response": chunk.get("response", ""),
                        "done": chunk.get("done", False)
                    })

                duration_s = max(0.001, time.time() - start_t)
                metrics_collector.finish_request(req_id, completion_tokens=token_count, success=True)
                yield format_sse_event({
                    "event": "done",
                    "request_id": req_id,
                    "total_tokens": token_count,
                    "duration_seconds": round(duration_s, 2),
                    "tokens_per_second": round(token_count / duration_s, 1)
                })
                yield format_sse_done()
            except Exception as e:
                logger.error(f"[{req_id}] Generate stream error: {e}")
                metrics_collector.finish_request(req_id, completion_tokens=token_count, success=False, error_message=str(e))
                yield format_sse_event({"error": str(e), "request_id": req_id})
                yield format_sse_done()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Request-ID": req_id
            }
        )

    try:
        res = await provider.generate(gen_req)
        response_text = res.get("response", "")
        tokens = estimate_tokens(response_text)
        metrics_collector.finish_request(req_id, completion_tokens=tokens, success=True)
        return {
            "request_id": req_id,
            "model": resolved_model,
            "response": response_text,
            "done": True
        }
    except Exception as e:
        metrics_collector.finish_request(req_id, success=False, error_message=str(e))
        raise

@router.post("/cancel")
async def cancel_endpoint(payload: Dict[str, Any], request: Request):
    """Cancels an active in-flight generation task."""
    check_auth(request)
    req_id = payload.get("request_id")
    if not req_id:
        raise InvalidRequestError("Missing 'request_id' to cancel", param="request_id")

    cancelled = await provider.cancel_request(req_id)
    return {"request_id": req_id, "cancelled": cancelled}

# 4. Sessions Management
@router.post("/sessions")
async def create_session(payload: Dict[str, Any], request: Request):
    """Creates a new conversational session on the gateway."""
    check_auth(request)
    sess = session_manager.create_session(
        model=payload.get("model"),
        title=payload.get("title"),
        system_prompt=payload.get("system_prompt"),
        metadata=payload.get("metadata")
    )
    return sess.to_dict()

@router.get("/sessions")
async def list_sessions(request: Request):
    """Lists all active sessions on the gateway."""
    check_auth(request)
    sessions = session_manager.list_sessions()
    return {"sessions": [s.to_dict() for s in sessions], "count": len(sessions)}

@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    """Gets a session history and messages."""
    check_auth(request)
    sess = session_manager.get_session(session_id)
    if not sess:
        raise SessionNotFoundError(session_id)
    return sess.to_dict()

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    """Deletes a conversation session."""
    check_auth(request)
    deleted = session_manager.delete_session(session_id)
    if not deleted:
        raise SessionNotFoundError(session_id)
    return {"session_id": session_id, "deleted": True}

# 5. Device Pairing & Management
@router.get("/pair")
async def get_pairing_info(request: Request):
    """Generates a dynamic short-lived pairing code and connection URL for iPhone."""
    check_auth(request)
    code = device_manager.generate_pairing_code()
    return {
        "pairing_code": code,
        "static_pairing_code": config.pairing_code,
        "lan_url": config.lan_url,
        "lan_ip": config.lan_ip,
        "port": config.port,
        "auth_required": bool(config.api_key),
        "bonjour_service": "_local-ai-bridge._tcp"
    }

@router.post("/pair/exchange")
async def exchange_pairing_code(payload: Dict[str, Any], request: Request):
    """Exchanges a pairing code for a persistent device token."""
    code = payload.get("code") or payload.get("pairing_code")
    if not code:
        raise InvalidRequestError("Missing 'code' or 'pairing_code'", param="code")
    
    device_name = payload.get("device_name") or payload.get("name")
    result = device_manager.exchange_pairing_code(code, device_name)
    return result

@router.get("/devices")
async def list_devices(request: Request):
    """Lists all paired devices."""
    check_auth(request)
    return {"devices": device_manager.list_devices()}

@router.delete("/devices/{device_id}")
async def revoke_device(device_id: str, request: Request):
    """Revokes a paired device token."""
    check_auth(request)
    revoked = device_manager.revoke_device(device_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"device_id": device_id, "revoked": True}

# 6. Performance Telemetry & Metrics
@router.get("/metrics")
async def get_metrics(request: Request):
    """Returns gateway performance metrics, TTFT, TPS, and recent request telemetry."""
    check_auth(request)
    summary = metrics_collector.get_summary()
    recent = metrics_collector.get_recent_requests(limit=30)
    summary["recent_requests"] = recent
    summary["active_sessions_count"] = session_manager.count()
    return summary

# 7. Model Context Protocol (MCP) HTTP Endpoint
@router.post("/mcp")
async def mcp_endpoint(payload: Dict[str, Any], request: Request):
    """
    HTTP JSON-RPC 2.0 endpoint for MCP clients (iOS app, web inspector, CLI tools).
    Supports tools/list, tools/call, initialize, ping.
    """
    check_auth(request)
    from ..mcp.server import handle_json_rpc
    response = await handle_json_rpc(payload)
    return response
