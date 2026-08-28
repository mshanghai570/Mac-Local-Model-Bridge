"""Opt-in, privacy-preserving inference-path diagnostics.

Set GATEWAY_INFERENCE_TRACE=1 only while investigating a request. Trace events
contain correlation IDs, message roles, lengths, and short SHA-256 fingerprints;
they never include API keys, authorization headers, full prompts, or generated
model text.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Iterable, Mapping

logger = logging.getLogger("local_ai_gateway.inference_trace")

CONTROL_TOKENS = ("<｜end｜>", "<|end|>", "<|eot_id|>", "</s>")


def fingerprint(value: Any) -> str:
    """Returns a compact, stable fingerprint without retaining content."""
    encoded = str(value or "").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def message_manifest(messages: Iterable[Any]) -> list[Dict[str, Any]]:
    """Describes message order and content identity without exposing text."""
    manifest: list[Dict[str, Any]] = []
    for index, message in enumerate(messages):
        if isinstance(message, Mapping):
            role = message.get("role", "user")
            content = message.get("content", "")
        else:
            role = getattr(message, "role", "user")
            content = getattr(message, "content", "")
        text = str(content or "")
        manifest.append(
            {
                "index": index,
                "role": str(role),
                "characters": len(text),
                "sha256_16": fingerprint(text),
            }
        )
    return manifest


def control_token_flags(value: str) -> list[str]:
    return [token for token in CONTROL_TOKENS if token in value]


def emit(enabled: bool, request_id: str, boundary: str, **fields: Any) -> None:
    """Writes one structured trace record only when explicitly enabled."""
    if not enabled:
        return
    event: Dict[str, Any] = {"request_id": request_id, "boundary": boundary}
    event.update(fields)
    logger.info("INFERENCE_TRACE %s", json.dumps(event, sort_keys=True, default=str))
