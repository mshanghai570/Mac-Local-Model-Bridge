"""Boundary contracts for the iPhone -> gateway -> provider streaming path."""
from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from local_ai_gateway.api import rest
from local_ai_gateway.config import config


WELCOME_NOTICE = (
    "Mac Local Model Bridge ready. Open Settings and enter your Mac's LAN IP address, "
    "or wait for Bonjour auto-discovery."
)
SENTINEL_PROMPT = "TRACE-PROMPT-7C2A: state the word ORBIT exactly once."
RUNTIME_RESPONSE = "ORBIT"


class _Request:
    headers = {"accept": "text/event-stream"}
    query_params = {}


class _CapturingProvider:
    provider_name = "capturing-runtime"

    def __init__(self) -> None:
        self.requests = []

    async def chat_stream(self, request):
        self.requests.append(request)
        yield {"content": RUNTIME_RESPONSE, "role": "assistant", "done": False}
        yield {"content": "", "role": "assistant", "done": True}


async def _read_stream(response) -> str:
    parts = []
    async for part in response.body_iterator:
        parts.append(part if isinstance(part, bytes) else part.encode("utf-8"))
    return b"".join(parts).decode("utf-8")


class TestInferenceTraceContract(unittest.TestCase):
    def test_gateway_forwards_received_history_and_returns_provider_content(self) -> None:
        """The gateway must not invent/cached-replace prompt history or stream content."""
        fake_provider = _CapturingProvider()
        payload = {
            "request_id": "req-trace-contract",
            "model": "trace-model",
            "stream": True,
            "system": "TRACE-SYSTEM",
            "messages": [
                {"role": "assistant", "content": WELCOME_NOTICE},
                {"role": "user", "content": SENTINEL_PROMPT},
            ],
        }
        previous_trace = config.inference_trace
        try:
            config.inference_trace = True
            with patch.object(rest, "provider", fake_provider), self.assertLogs(
                "local_ai_gateway.inference_trace", level="INFO"
            ) as captured:
                response = asyncio.run(rest.chat_endpoint(payload, _Request()))
                sse = asyncio.run(_read_stream(response))
        finally:
            config.inference_trace = previous_trace

        self.assertEqual(len(fake_provider.requests), 1)
        request = fake_provider.requests[0]
        self.assertEqual(
            [(message.role, message.content) for message in request.messages],
            [("assistant", WELCOME_NOTICE), ("user", SENTINEL_PROMPT)],
        )
        self.assertEqual(request.system, "TRACE-SYSTEM")
        self.assertEqual(request.model, "trace-model")
        self.assertIn('"content": "ORBIT"', sse)
        self.assertNotIn(WELCOME_NOTICE, sse)
        self.assertNotIn(SENTINEL_PROMPT, sse)

        trace = "\n".join(captured.output)
        self.assertIn('"boundary": "gateway_received"', trace)
        self.assertIn('"boundary": "gateway_dispatch"', trace)
        self.assertIn('"boundary": "gateway_stream_complete"', trace)
        self.assertIn('"provider": "capturing-runtime"', trace)
        self.assertNotIn(WELCOME_NOTICE, trace)
        self.assertNotIn(SENTINEL_PROMPT, trace)
        self.assertNotIn(RUNTIME_RESPONSE, trace)


if __name__ == "__main__":
    unittest.main()
