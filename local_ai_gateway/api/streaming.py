"""
Server-Sent Events (SSE) streaming formatting and serialization helpers.
"""
import json
from typing import Any, Optional

def format_sse_event(data: Any, event: Optional[str] = None) -> str:
    """Formats payload as a compliant Server-Sent Event (SSE) frame."""
    lines = []
    if event:
        lines.append(f"event: {event}")
    
    if isinstance(data, (dict, list)):
        payload_str = json.dumps(data)
    else:
        payload_str = str(data)

    for line in payload_str.split("\n"):
        lines.append(f"data: {line}")

    return "\n".join(lines) + "\n\n"

def format_sse_done() -> str:
    """Returns standard SSE stream completion signal."""
    return "data: [DONE]\n\n"

def format_sse_comment(comment: str = "keep-alive") -> str:
    """Returns SSE keep-alive comment frame."""
    return f": {comment}\n\n"

def format_openai_chat_chunk(
    chunk_id: str,
    model: str,
    created: int,
    content: Optional[str] = None,
    role: Optional[str] = None,
    finish_reason: Optional[str] = None,
    tool_calls: Optional[Any] = None
) -> str:
    """Serializes a single OpenAI-compatible chat.completion.chunk SSE frame."""
    delta: dict[str, Any] = {}
    if role:
        delta["role"] = role
    if content is not None:
        delta["content"] = content
    if tool_calls:
        delta["tool_calls"] = tool_calls

    chunk_payload = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason
            }
        ]
    }
    return format_sse_event(chunk_payload)
