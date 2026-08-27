"""
Unit and integration test suite for Local AI Gateway.
"""
import unittest
import time
import tempfile
import os
from pathlib import Path
from local_ai_gateway.config import GatewayConfig, ConfigurationError
from local_ai_gateway.auth import verify_token, extract_api_key, mask_api_key, DeviceManager
from local_ai_gateway.router import ModelRouter
from local_ai_gateway.models import ChatMessage, ModelCapabilities, HealthResponse
from local_ai_gateway.sessions import SessionManager, estimate_tokens, estimate_messages_tokens
from local_ai_gateway.api.streaming import format_sse_event, format_sse_done, format_openai_chat_chunk
from local_ai_gateway.metrics import MetricsCollector
from local_ai_gateway.errors import (
    GatewayError,
    ProviderUnavailableError,
    ModelNotFoundError,
    AuthenticationError,
    format_error_response
)

class TestGateway(unittest.TestCase):

    def test_config_validation(self):
        cfg = GatewayConfig()
        self.assertGreater(cfg.port, 0)
        self.assertLessEqual(cfg.port, 65535)
        self.assertIn(cfg.provider, ["ollama", "mlx", "mock"])

    def test_auth_and_masking(self):
        self.assertTrue(verify_token(None))  # when no API key configured
        self.assertEqual(mask_api_key(None), "[UNCONFIGURED]")
        self.assertEqual(mask_api_key("secret123456"), "sec****456")

        headers = {"Authorization": "Bearer my-test-key"}
        self.assertEqual(extract_api_key(headers), "my-test-key")

        headers_x = {"X-API-Key": "custom-key"}
        self.assertEqual(extract_api_key(headers_x), "custom-key")

        params = {"token": "query-param-token"}
        self.assertEqual(extract_api_key({}, query_params=params), "query-param-token")

    def test_device_pairing_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            dm = DeviceManager(state_path=Path(directory) / "devices.json")
            code = dm.generate_pairing_code(ttl_seconds=60)
            self.assertEqual(len(code), 6)

            # Exchange pairing code
            exchanged = dm.exchange_pairing_code(code, "iPhone 15 Pro")
            self.assertIn("device_id", exchanged)
            self.assertIn("device_token", exchanged)
            self.assertEqual(exchanged["name"], "iPhone 15 Pro")

            # Test listing devices
            devs = dm.list_devices()
            self.assertEqual(len(devs), 1)
            self.assertEqual(devs[0]["name"], "iPhone 15 Pro")

            # Test revocation
            self.assertTrue(dm.revoke_device(exchanged["device_id"]))
            self.assertEqual(len(dm.list_devices()), 0)

    def test_paired_device_token_persists_as_hash_only(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "devices.json"
            dm = DeviceManager(state_path=state_path)
            code = dm.generate_pairing_code()
            issued = dm.exchange_pairing_code(code, "Bridge Phone")
            self.assertTrue(dm.verify_paired_device_token(issued["device_token"]))

            reloaded = DeviceManager(state_path=state_path)
            self.assertTrue(reloaded.verify_paired_device_token(issued["device_token"]))
            persisted = state_path.read_text(encoding="utf-8")
            self.assertNotIn(issued["device_token"], persisted)
            self.assertIn(issued["device_id"], persisted)
            self.assertEqual(os.stat(state_path).st_mode & 0o777, 0o600)

    def test_model_router_and_capabilities(self):
        router = ModelRouter()
        self.assertEqual(router.resolve_model("coding"), router.aliases.get("coding"))
        self.assertEqual(router.resolve_model("reasoning"), router.aliases.get("reasoning"))
        self.assertEqual(router.resolve_model("fast"), router.aliases.get("fast"))

        # Explicit task routing
        self.assertEqual(router.resolve_model(task="coding"), router.aliases.get("coding"))
        self.assertEqual(router.resolve_model(task="vision"), router.aliases.get("vision"))

        # Auto detection heuristics
        code_msg = [ChatMessage(role="user", content="def fibonacci(n): return n")]
        self.assertIn("coder", router.resolve_model("auto", messages=code_msg).lower())

        reason_msg = [ChatMessage(role="user", content="Explain step by step the mathematical proof.")]
        self.assertIn("r1", router.resolve_model("auto", messages=reason_msg).lower())

        vision_msg = [ChatMessage(role="user", content="What is in this photo?", images=["base64data"])]
        auto_vision = router.resolve_model("auto", messages=vision_msg).lower()
        self.assertTrue("llava" in auto_vision or "vision" in auto_vision)

        # ModelCapabilities
        caps = ModelCapabilities(text=True, vision=True, tools=True)
        self.assertTrue(caps.to_dict()["vision"])
        self.assertTrue(caps.to_dict()["tools"])

    def test_session_manager_and_context_trimming(self):
        sm = SessionManager()
        session = sm.create_session(model="llama3.2:3b", title="Test Session")
        self.assertIsNotNone(session.id)
        self.assertEqual(session.model, "llama3.2:3b")

        sm.add_message(session.id, ChatMessage(role="user", content="Hello"))
        sm.add_message(session.id, ChatMessage(role="assistant", content="Hi!"))

        fetched = sm.get_session(session.id)
        self.assertEqual(len(fetched.messages), 2)

        # Test context trimming
        long_msgs = [ChatMessage(role="user", content="word " * 300) for _ in range(8)]
        managed, telemetry = sm.check_and_manage_context(long_msgs, max_context_tokens=800, strategy="trim_oldest")
        self.assertLess(len(managed), len(long_msgs))
        self.assertGreater(telemetry["trimmed_messages_count"], 0)

        # Deletion
        self.assertTrue(sm.delete_session(session.id))
        self.assertIsNone(sm.get_session(session.id))

    def test_streaming_and_openai_chunk_formatting(self):
        frame = format_sse_event({"content": "Hello", "done": False})
        self.assertTrue(frame.startswith("data: {"))
        self.assertTrue(frame.endswith("\n\n"))

        done_frame = format_sse_done()
        self.assertEqual(done_frame, "data: [DONE]\n\n")

        # OpenAI chunk formatting
        chunk = format_openai_chat_chunk(
            chunk_id="chatcmpl-123",
            model="llama3.2:3b",
            created=1700000000,
            content="Hello world"
        )
        self.assertIn("chat.completion.chunk", chunk)
        self.assertIn("Hello world", chunk)

    def test_metrics_and_token_estimation(self):
        self.assertEqual(estimate_tokens("Hello world!"), 3)
        self.assertGreater(estimate_messages_tokens([ChatMessage(role="user", content="Test")]), 0)

        metrics = MetricsCollector()
        metrics.start_request("req-1", "llama3.2:3b", "/chat")
        summary_active = metrics.get_summary()
        self.assertEqual(summary_active["active_requests"], 1)

        metrics.record_first_token("req-1")
        metrics.finish_request("req-1", completion_tokens=50, prompt_tokens=10, success=True)
        
        summary_done = metrics.get_summary()
        self.assertEqual(summary_done["active_requests"], 0)
        self.assertEqual(summary_done["total_requests"], 1)
        self.assertEqual(summary_done["total_tokens_streamed"], 50)
        self.assertEqual(summary_done["completed_requests"], 1)

    def test_standardized_error_handling(self):
        err = ModelNotFoundError("qwen2.5:32b", request_id="req_99")
        self.assertEqual(err.status_code, 404)
        self.assertEqual(err.error_type, "not_found_error")
        self.assertEqual(err.param, "model")
        
        err_dict = err.to_dict()
        self.assertIn("error", err_dict)
        self.assertEqual(err_dict["error"]["code"], 404)
        self.assertEqual(err_dict["error"]["request_id"], "req_99")

        formatted = format_error_response("Test error", "invalid_request_error", 400, "param1", "req_1")
        self.assertEqual(formatted["error"]["param"], "param1")

    def test_macos_bridge_health_payload(self):
        from local_ai_gateway.macos.status import build_bridge_health, BRIDGE_PROTOCOL_VERSION
        payload = build_bridge_health()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["device"], "Mac")
        self.assertEqual(payload["bridge"], "running")
        self.assertIsInstance(payload["zed"], bool)
        self.assertIsInstance(payload["accessibility"], bool)
        self.assertEqual(payload["protocolVersion"], BRIDGE_PROTOCOL_VERSION)

    def test_macos_capability_probes(self):
        from local_ai_gateway.macos.accessibility import is_accessibility_trusted, is_zed_running
        self.assertIsInstance(is_accessibility_trusted(), bool)
        self.assertIsInstance(is_zed_running(), bool)

    def test_zero_config_defaults(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=True):
            cfg = GatewayConfig()
            self.assertEqual(cfg.host, "0.0.0.0")
            self.assertEqual(cfg.port, 8080)
            self.assertEqual(cfg.ollama_url, "http://127.0.0.1:11434")
            self.assertFalse(cfg.is_auth_enabled)
            self.assertIsNone(cfg.api_key)
            self.assertTrue(cfg.is_pairing_code_generated)
            self.assertEqual(len(cfg.pairing_code), 6)
            self.assertEqual(cfg.max_concurrent_requests, 1)
            self.assertEqual(cfg.connect_timeout, 10.0)
            self.assertEqual(cfg.request_timeout, 300.0)
            self.assertEqual(cfg.generation_timeout, 300.0)
            self.assertEqual(cfg.streaming_idle_timeout, 60.0)
            self.assertEqual(cfg.max_request_bytes, 10485760)
            self.assertEqual(cfg.max_image_bytes, 10485760)
            self.assertEqual(cfg.max_session_messages, 100)
            self.assertEqual(cfg.session_ttl_seconds, 86400.0)
            self.assertEqual(cfg.context_limit_strategy, "trim")
            self.assertTrue(cfg.enable_bonjour)
            self.assertTrue(cfg.enable_pairing)
            self.assertTrue(cfg.enable_dashboard)
            self.assertTrue(cfg.enable_sessions)
            self.assertTrue(cfg.enable_auto_routing)
            self.assertFalse(cfg.verbose_logging)
            self.assertEqual(cfg.allowed_origins, ["*"])

    def test_optional_secrets_when_set(self):
        import os
        from unittest.mock import patch

        env = {
            "GATEWAY_API_KEY": "my-secret-key-123",
            "PAIRING_CODE": "ABC999",
            "GATEWAY_PORT": "9090",
            "MAX_CONCURRENT_REQUESTS": "2"
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = GatewayConfig()
            self.assertEqual(cfg.port, 9090)
            self.assertEqual(cfg.max_concurrent_requests, 2)
            self.assertTrue(cfg.is_auth_enabled)
            self.assertEqual(cfg.api_key, "my-secret-key-123")
            self.assertEqual(cfg.pairing_code, "ABC999")
            self.assertFalse(cfg.is_pairing_code_generated)

    def test_device_pairing_and_open_auth(self):
        from local_ai_gateway.auth import DeviceManager, mask_api_key

        # Open Auth mode (no API key configured)
        with tempfile.TemporaryDirectory() as directory:
            dm = DeviceManager(state_path=Path(directory) / "devices.json")
            self.assertTrue(dm.verify_token(None))
            self.assertTrue(dm.verify_token(""))
            self.assertTrue(dm.verify_token("any-token-passes-in-dev"))

            # Masking utility
            self.assertEqual(mask_api_key(None), "[UNCONFIGURED]")
            self.assertEqual(mask_api_key(""), "[UNCONFIGURED]")
            self.assertEqual(mask_api_key("12345"), "******")
            self.assertEqual(mask_api_key("secret_token_123456"), "sec****456")

            # Dynamic temporary single-use pairing code
            code = dm.generate_pairing_code(ttl_seconds=60)
            self.assertEqual(len(code), 6)

            # Exchange pairing code for scoped device token
            res = dm.exchange_pairing_code(code, "iPhone 15 Pro")
            self.assertIn("device_token", res)
            self.assertIn("device_id", res)
            self.assertTrue(res["device_token"].startswith("gw_dev_"))

            # Single-use: Second exchange with same code must fail
            with self.assertRaises(Exception):
                dm.exchange_pairing_code(code, "Attacker")

if __name__ == "__main__":
    unittest.main()

