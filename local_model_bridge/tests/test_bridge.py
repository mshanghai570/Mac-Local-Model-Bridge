import unittest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock

from local_model_bridge.config import config
from local_model_bridge.models import ChatMessage, ChatRequest, GenerateRequest, ModelInfo
from local_model_bridge.auth import verify_token, extract_api_key, mask_api_key
from local_model_bridge.providers.ollama import OllamaProvider, format_size, infer_capabilities
from local_model_bridge.providers import get_provider
from local_model_bridge.api.routes import handle_mcp_jsonrpc

class TestLocalModelBridge(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    # 1. Test Authentication & Token Extraction
    def test_auth_no_key_configured(self):
        with patch.object(config, 'api_key', None):
            self.assertTrue(verify_token(None))
            self.assertTrue(verify_token("any-key"))

    def test_auth_with_key_configured(self):
        with patch.object(config, 'api_key', 'my-secret-key-123'):
            self.assertFalse(verify_token(None))
            self.assertFalse(verify_token("wrong-key"))
            self.assertTrue(verify_token("my-secret-key-123"))

    def test_auth_extraction_headers_and_params(self):
        headers_bearer = {"authorization": "Bearer secret-abc"}
        self.assertEqual(extract_api_key(headers_bearer), "secret-abc")

        headers_x_api_key = {"x-api-key": "secret-xyz"}
        self.assertEqual(extract_api_key(headers_x_api_key), "secret-xyz")

        query_params = {"api_key": "secret-query"}
        self.assertEqual(extract_api_key({}, query_params), "secret-query")

        # Masking
        self.assertEqual(mask_api_key("secret123456"), "se***56")
        self.assertEqual(mask_api_key("abc"), "***")
        self.assertEqual(mask_api_key(None), "<none>")

    # 2. Test Helpers & Formatting
    def test_size_formatting(self):
        self.assertEqual(format_size(500), "500 B")
        self.assertEqual(format_size(1024 * 500), "500.0 KB")
        self.assertEqual(format_size(1024 * 1024 * 700), "700.0 MB")
        self.assertEqual(format_size(3800000000), "3.54 GB")

    def test_capability_inference(self):
        caps_llama = infer_capabilities("llama3.2:3b", "llama")
        self.assertIn("chat", caps_llama)
        self.assertIn("tools", caps_llama)

        caps_vision = infer_capabilities("llava:7b", "clip")
        self.assertIn("vision", caps_vision)

        caps_coder = infer_capabilities("qwen2.5-coder:7b")
        self.assertIn("coding", caps_coder)

    # 3. Test Ollama Provider - Model Listing
    @patch.object(OllamaProvider, '_request_http')
    def test_list_models(self, mock_http):
        mock_http.return_value = {
            "models": [
                {
                    "name": "llama3.2:3b",
                    "size": 2019393189,
                    "digest": "a80c4f172edd",
                    "modified_at": "2026-08-10T12:00:00Z",
                    "details": {
                        "family": "llama",
                        "parameter_size": "3.2B",
                        "quantization_level": "Q4_K_M"
                    }
                }
            ]
        }
        provider = OllamaProvider()
        models = self.loop.run_until_complete(provider.list_models())

        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].name, "llama3.2:3b")
        self.assertEqual(models[0].parameter_size, "3.2B")
        self.assertIn("chat", models[0].capabilities)
        mock_http.assert_called_with("GET", "/api/tags")

    # 4. Test Ollama Provider - Model Info
    @patch.object(OllamaProvider, '_request_http')
    def test_model_info(self, mock_http):
        mock_http.return_value = {
            "modelfile": "FROM llama3.2:3b",
            "parameters": "stop <|eot_id|>",
            "template": "{{ .Prompt }}",
            "details": {"family": "llama"}
        }
        provider = OllamaProvider()
        info = self.loop.run_until_complete(provider.get_model_info("llama3.2:3b"))

        self.assertEqual(info["name"], "llama3.2:3b")
        self.assertIn("modelfile", info)
        mock_http.assert_called_with("POST", "/api/show", {"name": "llama3.2:3b"})

    # 5. Test Ollama Provider - Chat Non-Streaming
    @patch.object(OllamaProvider, '_request_http')
    def test_chat_non_streaming(self, mock_http):
        mock_http.return_value = {
            "model": "llama3.2:3b",
            "message": {"role": "assistant", "content": "Hello iPhone user!"},
            "done": True,
            "eval_count": 15,
            "eval_duration": 450000000
        }
        provider = OllamaProvider()
        req = ChatRequest(
            model="llama3.2:3b",
            messages=[ChatMessage(role="user", content="Hi!")],
            system="Be concise"
        )
        res = self.loop.run_until_complete(provider.chat(req))

        self.assertEqual(res["content"], "Hello iPhone user!")
        self.assertEqual(res["role"], "assistant")
        self.assertEqual(res["eval_count"], 15)

    # 6. Test Ollama Provider - Health Check (Success & Failure)
    @patch.object(OllamaProvider, '_request_http')
    def test_health_success(self, mock_http):
        mock_http.return_value = {"version": "0.3.14"}
        provider = OllamaProvider()
        health = self.loop.run_until_complete(provider.check_health())

        self.assertEqual(health.status, "ok")
        self.assertEqual(health.inference_backend_status, "connected")
        self.assertTrue(health.backend_reachable)

    @patch.object(OllamaProvider, '_request_http')
    def test_health_failure_backend_down(self, mock_http):
        mock_http.side_effect = ConnectionError("Unable to connect to Ollama at http://127.0.0.1:11434")
        provider = OllamaProvider()
        health = self.loop.run_until_complete(provider.check_health())

        self.assertEqual(health.status, "degraded")
        self.assertEqual(health.inference_backend_status, "unreachable")
        self.assertFalse(health.backend_reachable)
        self.assertIn("Unable to connect", health.message)

    # 7. Test MCP JSON-RPC 2.0 Handler
    @patch('local_model_bridge.api.routes.provider.list_models')
    def test_mcp_list_models_tool(self, mock_list):
        mock_list.return_value = [
            ModelInfo(
                name="llama3.2:3b",
                size_bytes=2000000000,
                size_formatted="1.86 GB",
                modified_at="2026-08-10T12:00:00Z",
                digest="abc",
                capabilities=["chat", "tools"]
            )
        ]
        payload = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "tools/call",
            "params": {"name": "list_models", "arguments": {}}
        }
        res = self.loop.run_until_complete(handle_mcp_jsonrpc(payload))
        self.assertEqual(res["id"], 42)
        content_text = res["result"]["content"][0]["text"]
        parsed = json.loads(content_text)
        self.assertEqual(parsed["count"], 1)
        self.assertEqual(parsed["models"][0]["name"], "llama3.2:3b")

    @patch('local_model_bridge.api.routes.provider.chat')
    def test_mcp_chat_tool(self, mock_chat):
        mock_chat.return_value = {
            "model": "llama3.2:3b",
            "content": "MCP is working!",
            "role": "assistant"
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {
                "name": "chat",
                "arguments": {
                    "model": "llama3.2:3b",
                    "messages": [{"role": "user", "content": "Test"}]
                }
            }
        }
        res = self.loop.run_until_complete(handle_mcp_jsonrpc(payload))
        self.assertEqual(res["id"], 99)
        self.assertEqual(res["result"]["content"][0]["text"], "MCP is working!")

    def test_mcp_tools_list(self):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }
        res = self.loop.run_until_complete(handle_mcp_jsonrpc(payload))
        tools = res["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("list_models", tool_names)
        self.assertIn("health", tool_names)
        self.assertIn("model_info", tool_names)
        self.assertIn("chat", tool_names)
        self.assertIn("generate", tool_names)
        self.assertIn("stop", tool_names)

    def test_mcp_generate_and_stop_tools(self):
        # Test MCP generate
        with patch('local_model_bridge.api.routes.provider.generate') as mock_gen:
            mock_gen.return_value = {"model": "llama3.2:3b", "response": "Raw completion result"}
            payload = {
                "jsonrpc": "2.0",
                "id": 101,
                "method": "tools/call",
                "params": {
                    "name": "generate",
                    "arguments": {"model": "llama3.2:3b", "prompt": "Complete this:"}
                }
            }
            res = self.loop.run_until_complete(handle_mcp_jsonrpc(payload))
            self.assertEqual(res["id"], 101)
            self.assertEqual(res["result"]["content"][0]["text"], "Raw completion result")

        # Test MCP stop
        with patch('local_model_bridge.api.routes.provider.stop') as mock_stop:
            mock_stop.return_value = {"status": "cancelled", "task_id": "task-abc"}
            payload = {
                "jsonrpc": "2.0",
                "id": 102,
                "method": "tools/call",
                "params": {"name": "stop", "arguments": {"task_id": "task-abc"}}
            }
            res = self.loop.run_until_complete(handle_mcp_jsonrpc(payload))
            self.assertEqual(res["id"], 102)
            self.assertIn("cancelled", res["result"]["content"][0]["text"])

    def test_mcp_unknown_tool_error(self):
        payload = {
            "jsonrpc": "2.0",
            "id": 77,
            "method": "tools/call",
            "params": {"name": "non_existent_tool"}
        }
        res = self.loop.run_until_complete(handle_mcp_jsonrpc(payload))
        self.assertEqual(res["id"], 77)
        self.assertIn("error", res)
        self.assertEqual(res["error"]["code"], -32601)

    def test_provider_factory(self):
        p_ollama = get_provider("ollama")
        self.assertEqual(p_ollama.provider_name, "ollama")
        p_default = get_provider("unknown_provider")
        self.assertEqual(p_default.provider_name, "ollama")

if __name__ == "__main__":
    unittest.main()
