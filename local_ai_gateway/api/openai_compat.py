"""
OpenAI-compatible HTTP API endpoints for Local AI Gateway.
Provides 1:1 drop-in compatibility for OpenAI SDKs, LangChain, LlamaIndex,
Claude Desktop, Apple Shortcuts, and OpenAI-compatible apps.
"""
import json
import time
import uuid
import logging
from typing import Dict, Any, List, Optional

from ..config import config
from ..models import ChatRequest, ChatMessage, GenerateRequest
from ..auth import verify_token, extract_api_key
from ..providers import get_provider
from ..router import model_router
from ..sessions import session_manager, estimate_tokens
from ..metrics import metrics_collector
from ..errors import (
    AuthenticationError,
    InvalidRequestError,
    ModelNotFoundError,
    ProviderUnavailableError
)
from .streaming import format_openai_chat_chunk, format_sse_done, format_sse_event

logger = logging.getLogger("local_ai_gateway.api.openai")

try:
    from fastapi import APIRouter, Request, HTTPException
    from fastapi.responses import StreamingResponse, JSONResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    class DummyRouter:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda f: f
        def post(self, *args, **kwargs): return lambda f: f
        def put(self, *args, **kwargs): return lambda f: f
        def delete(self, *args, **kwargs): return lambda f: f
    APIRouter = DummyRouter
    Request = Any
    HTTPException = Exception
    StreamingResponse = Any
    JSONResponse = Any

provider = get_provider(config.provider)
openai_router = APIRouter(prefix="/v1")

def check_auth(request: Request):
    if not config.api_key:
        return
    token = extract_api_key(
        headers=dict(request.headers),
        query_params=dict(request.query_params)
    )
    if not verify_token(token):
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "Incorrect API key or paired device token provided.", "type": "invalid_request_error", "code": "invalid_api_key"}}
        )

@openai_router.get("/models")
async def list_openai_models(request: Request):
    """Returns installed models formatted according to the OpenAI /v1/models specification."""
    check_auth(request)
    try:
        models = await provider.list_models()
        data = []
        for m in models:
            data.append({
                "id": m.name,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local-mac",
                "permission": [],
                "root": m.name,
                "parent": None
            })
        
        # Expose model aliases as valid OpenAI models
        for alias, target in model_router.get_aliases().items():
            data.append({
                "id": alias,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "alias",
                "permission": [],
                "root": target,
                "parent": target
            })

        return {"object": "list", "data": data}
    except Exception as e:
        logger.error(f"Error in /v1/models: {e}")
        raise HTTPException(status_code=502, detail={"error": {"message": str(e), "type": "server_error"}})

@openai_router.get("/models/{model_name:path}")
async def get_openai_model(model_name: str, request: Request):
    """Returns individual model card in OpenAI format."""
    check_auth(request)
    resolved = model_router.resolve_model(model_name)
    try:
        info = await provider.get_model_info(resolved)
        return {
            "id": model_name,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "local-mac",
            "details": info
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail={"error": {"message": f"Model '{model_name}' not found", "type": "invalid_request_error"}})

@openai_router.post("/chat/completions")
async def openai_chat_completions(payload: Dict[str, Any], request: Request):
    """
    OpenAI-compatible Chat Completions endpoint (`POST /v1/chat/completions`).
    Supports SSE chunk streaming (`stream: true`), multimodal messages, tools, and token tracking.
    """
    check_auth(request)

    raw_model = payload.get("model", "auto")
    raw_msgs = payload.get("messages", [])
    if not isinstance(raw_msgs, list) or not raw_msgs:
        raise HTTPException(
            status_code=400,
            detail={"error": {"message": "'messages' is a required non-empty array", "type": "invalid_request_error", "param": "messages"}}
        )

    messages: List[ChatMessage] = []
    for m in raw_msgs:
        role = m.get("role", "user")
        content = m.get("content", "")
        images = []
        
        # Support OpenAI multimodal message structure
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        img_url = part.get("image_url", {}).get("url", "")
                        if "base64," in img_url:
                            images.append(img_url.split("base64,")[-1])
                        else:
                            images.append(img_url)
            content = " ".join(text_parts)

        messages.append(
            ChatMessage(
                role=role,
                content=content or "",
                images=images if images else None,
                name=m.get("name"),
                tool_calls=m.get("tool_calls"),
                tool_call_id=m.get("tool_call_id")
            )
        )

    resolved_model = model_router.resolve_model(raw_model, messages=messages)
    stream_requested = bool(payload.get("stream", False))

    req_id = payload.get("request_id") or request.headers.get("x-request-id") or f"chatcmpl-{uuid.uuid4().hex[:12]}"
    metrics_collector.start_request(req_id, resolved_model, "/v1/chat/completions")

    chat_req = ChatRequest(
        model=resolved_model,
        messages=messages,
        temperature=payload.get("temperature", 0.7),
        top_p=payload.get("top_p", 0.9),
        max_tokens=payload.get("max_tokens"),
        tools=payload.get("tools"),
        response_format=payload.get("response_format"),
        options=payload.get("options", {}),
        request_id=req_id
    )

    created_timestamp = int(time.time())

    if stream_requested:
        async def openai_stream_generator():
            token_count = 0
            try:
                # 1. Initial role chunk
                yield format_openai_chat_chunk(
                    chunk_id=req_id,
                    model=resolved_model,
                    created=created_timestamp,
                    role="assistant"
                )

                # 2. Content delta chunks
                async for chunk in provider.chat_stream(chat_req):
                    token_count += 1
                    content_piece = chunk.get("content", "")
                    tool_calls = chunk.get("tool_calls")
                    if content_piece or tool_calls:
                        yield format_openai_chat_chunk(
                            chunk_id=req_id,
                            model=resolved_model,
                            created=created_timestamp,
                            content=content_piece if content_piece else None,
                            tool_calls=tool_calls
                        )

                # 3. Finish chunk
                yield format_openai_chat_chunk(
                    chunk_id=req_id,
                    model=resolved_model,
                    created=created_timestamp,
                    finish_reason="stop"
                )
                yield format_sse_done()

                metrics_collector.finish_request(req_id, completion_tokens=token_count, success=True)

            except Exception as e:
                logger.error(f"[{req_id}] OpenAI stream error: {e}")
                metrics_collector.finish_request(req_id, completion_tokens=token_count, success=False, error_message=str(e))
                err_payload = {"error": {"message": str(e), "type": "server_error"}}
                yield format_sse_event(err_payload)
                yield format_sse_done()

        return StreamingResponse(
            openai_stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Request-ID": req_id
            }
        )

    # Non-streaming response
    try:
        res = await provider.chat(chat_req)
        content = res.get("content", "")
        tool_calls = res.get("tool_calls")
        prompt_tokens = estimate_tokens(" ".join([m.content for m in messages]))
        completion_tokens = estimate_tokens(content)

        metrics_collector.finish_request(req_id, completion_tokens=completion_tokens, prompt_tokens=prompt_tokens, success=True)

        message_obj: Dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            message_obj["tool_calls"] = tool_calls

        return {
            "id": req_id,
            "object": "chat.completion",
            "created": created_timestamp,
            "model": resolved_model,
            "choices": [
                {
                    "index": 0,
                    "message": message_obj,
                    "finish_reason": "tool_calls" if tool_calls else "stop"
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            }
        }
    except Exception as e:
        metrics_collector.finish_request(req_id, success=False, error_message=str(e))
        logger.error(f"[{req_id}] OpenAI chat completion error: {e}")
        raise HTTPException(
            status_code=502,
            detail={"error": {"message": str(e), "type": "provider_error"}}
        )

@openai_router.post("/completions")
async def openai_legacy_completions(payload: Dict[str, Any], request: Request):
    """
    OpenAI-compatible raw prompt completions endpoint (`POST /v1/completions`).
    """
    check_auth(request)

    prompt = payload.get("prompt", "")
    if isinstance(prompt, list):
        prompt = " ".join([str(p) for p in prompt])

    if not prompt:
        raise HTTPException(
            status_code=400,
            detail={"error": {"message": "'prompt' is required", "type": "invalid_request_error", "param": "prompt"}}
        )

    raw_model = payload.get("model", "auto")
    resolved_model = model_router.resolve_model(raw_model, prompt=prompt)
    stream_requested = bool(payload.get("stream", False))

    req_id = payload.get("request_id") or request.headers.get("x-request-id") or f"cmpl-{uuid.uuid4().hex[:12]}"
    created_timestamp = int(time.time())
    metrics_collector.start_request(req_id, resolved_model, "/v1/completions")

    gen_req = GenerateRequest(
        model=resolved_model,
        prompt=prompt,
        temperature=payload.get("temperature", 0.7),
        top_p=payload.get("top_p", 0.9),
        max_tokens=payload.get("max_tokens"),
        request_id=req_id
    )

    if stream_requested:
        async def completion_stream_generator():
            token_count = 0
            try:
                async for chunk in provider.generate_stream(gen_req):
                    token_count += 1
                    piece = chunk.get("response", "")
                    yield format_sse_event({
                        "id": req_id,
                        "object": "text_completion",
                        "created": created_timestamp,
                        "model": resolved_model,
                        "choices": [
                            {
                                "text": piece,
                                "index": 0,
                                "finish_reason": None
                            }
                        ]
                    })

                yield format_sse_event({
                    "id": req_id,
                    "object": "text_completion",
                    "created": created_timestamp,
                    "model": resolved_model,
                    "choices": [
                        {
                            "text": "",
                            "index": 0,
                            "finish_reason": "stop"
                        }
                    ]
                })
                yield format_sse_done()
                metrics_collector.finish_request(req_id, completion_tokens=token_count, success=True)
            except Exception as e:
                metrics_collector.finish_request(req_id, completion_tokens=token_count, success=False, error_message=str(e))
                yield format_sse_event({"error": {"message": str(e), "type": "server_error"}})
                yield format_sse_done()

        return StreamingResponse(
            completion_stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Request-ID": req_id}
        )

    try:
        res = await provider.generate(gen_req)
        response_text = res.get("response", "")
        tokens = estimate_tokens(response_text)
        metrics_collector.finish_request(req_id, completion_tokens=tokens, success=True)

        return {
            "id": req_id,
            "object": "text_completion",
            "created": created_timestamp,
            "model": resolved_model,
            "choices": [
                {
                    "text": response_text,
                    "index": 0,
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": estimate_tokens(prompt),
                "completion_tokens": tokens,
                "total_tokens": estimate_tokens(prompt) + tokens
            }
        }
    except Exception as e:
        metrics_collector.finish_request(req_id, success=False, error_message=str(e))
        raise HTTPException(status_code=502, detail={"error": {"message": str(e), "type": "provider_error"}})
