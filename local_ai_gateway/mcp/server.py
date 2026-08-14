"""
MCP (Model Context Protocol) Server for Claude Desktop and MCP clients.
Provides tools to control, prompt, and inspect local Apple Silicon LLMs directly from Claude Desktop.
"""
import sys
import json
import asyncio
import logging
from typing import Dict, Any, Optional

from .tools import (
    mcp_health,
    mcp_list_models,
    mcp_model_info,
    mcp_chat,
    mcp_generate,
    mcp_cancel,
    mcp_create_session,
    mcp_get_session,
    mcp_delete_session
)

logger = logging.getLogger("local_ai_gateway.mcp")

# Tool definitions schema for JSON-RPC MCP
MCP_TOOLS_MANIFEST = [
    {
        "name": "gateway_health",
        "description": "Check connection to Local AI Gateway and backend model inference engine (e.g. Ollama).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "health",
        "description": "Check connection health to Local AI Gateway (alias).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "list_local_models",
        "description": "List all installed LLM models on the host Mac, including parameter count, quantization, and vision/tools support.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "list_models",
        "description": "List all installed LLM models (alias).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_model_spec",
        "description": "Retrieve detailed metadata, prompt templates, and parameters for a local model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Name of the model (e.g. llama3.2:3b, qwen2.5-coder)"}
            },
            "required": ["model"]
        }
    },
    {
        "name": "model_info",
        "description": "Retrieve model specification and metadata (alias).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Name of the model"}
            },
            "required": ["model"]
        }
    },
    {
        "name": "local_chat",
        "description": "Execute a chat prompt using local Apple Silicon models. Bypasses cloud, zero latency, runs offline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "User message or query to pass to the model"},
                "model": {"type": "string", "description": "Model or alias (e.g. 'coding', 'reasoning', 'fast', 'llama3.2:3b')"},
                "system": {"type": "string", "description": "Optional system prompt instructions"},
                "temperature": {"type": "number", "description": "Sampling temperature (0.0 - 1.0)"},
                "session_id": {"type": "string", "description": "Optional session ID for conversational memory"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "chat",
        "description": "Execute a chat prompt using local models (alias).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "User message or query to pass to the model"},
                "model": {"type": "string", "description": "Model or alias"},
                "system": {"type": "string", "description": "Optional system prompt instructions"},
                "temperature": {"type": "number", "description": "Sampling temperature (0.0 - 1.0)"},
                "session_id": {"type": "string", "description": "Optional session ID for conversational memory"}
            }
        }
    },
    {
        "name": "local_generate",
        "description": "Run raw text generation from a prompt on the local Mac model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text prompt to complete"},
                "model": {"type": "string", "description": "Model or alias name"},
                "system": {"type": "string", "description": "System prompt"},
                "temperature": {"type": "number", "description": "Temperature"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "generate",
        "description": "Run text generation from prompt (alias).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text prompt to complete"},
                "model": {"type": "string", "description": "Model or alias name"},
                "system": {"type": "string", "description": "System prompt"},
                "temperature": {"type": "number", "description": "Temperature"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "create_session",
        "description": "Create a new conversation session on the Local AI Gateway.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title for session"},
                "model": {"type": "string", "description": "Default model for session"}
            }
        }
    },
    {
        "name": "cancel_request",
        "description": "Cancel an in-flight generation task on the Mac.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "description": "ID of request to cancel"}
            },
            "required": ["request_id"]
        }
    },
    {
        "name": "stop",
        "description": "Cancel or stop an in-flight request (alias).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "description": "ID of request to cancel"}
            }
        }
    }
]

async def execute_tool(name: str, args: Dict[str, Any]) -> Any:
    # Support both gateway canonical names and client alias names
    if name in ("gateway_health", "health"):
        return await mcp_health()
    elif name in ("list_local_models", "list_models"):
        return await mcp_list_models()
    elif name in ("get_model_spec", "model_info"):
        return await mcp_model_info(args.get("model", "auto"))
    elif name in ("local_chat", "chat"):
        # Handle both prompt (string) and messages (array of dicts or ChatMessage)
        prompt = args.get("prompt", "")
        if not prompt and "messages" in args:
            raw_msgs = args.get("messages", [])
            if isinstance(raw_msgs, list) and raw_msgs:
                last_msg = raw_msgs[-1]
                if isinstance(last_msg, dict):
                    prompt = last_msg.get("content", "")
                elif isinstance(last_msg, str):
                    prompt = last_msg
        return await mcp_chat(
            prompt=prompt,
            model=args.get("model"),
            system=args.get("system"),
            temperature=args.get("temperature", 0.7),
            session_id=args.get("session_id")
        )
    elif name in ("local_generate", "generate"):
        return await mcp_generate(
            prompt=args.get("prompt", ""),
            model=args.get("model"),
            system=args.get("system"),
            temperature=args.get("temperature", 0.7)
        )
    elif name in ("create_session",):
        return await mcp_create_session(
            title=args.get("title"),
            model=args.get("model")
        )
    elif name in ("cancel_request", "stop"):
        req_id = args.get("request_id") or args.get("task_id") or ""
        return await mcp_cancel(req_id)
    else:
        raise ValueError(f"Unknown MCP tool: {name}")

async def handle_json_rpc(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Helper function to process a single JSON-RPC 2.0 message and return the response dictionary."""
    server = StdioMCPServer()
    res = await server.handle_message(msg)
    return res or {"jsonrpc": "2.0", "id": msg.get("id"), "result": None}

def create_fastmcp_server():
    """Factory creating an MCP server instance."""
    return StdioMCPServer()

class StdioMCPServer:
    """Standard JSON-RPC 2.0 stdio MCP server for Claude Desktop."""
    async def run(self):
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            line = await reader.readline()
            if not line:
                break
            line_str = line.decode("utf-8").strip()
            if not line_str:
                continue

            try:
                msg = json.loads(line_str)
                response = await self.handle_message(msg)
                if response:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(e)}
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()

    async def handle_message(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False}
                    },
                    "serverInfo": {
                        "name": "local-ai-gateway",
                        "version": "1.0.0"
                    }
                }
            }

        elif method == "notifications/initialized":
            return None

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": MCP_TOOLS_MANIFEST
                }
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            try:
                tool_result = await execute_tool(tool_name, arguments)
                if isinstance(tool_result, dict) and "content" in tool_result and isinstance(tool_result["content"], str):
                    text_out = tool_result["content"]
                elif isinstance(tool_result, dict) and "response" in tool_result and isinstance(tool_result["response"], str):
                    text_out = tool_result["response"]
                elif isinstance(tool_result, (dict, list)):
                    text_out = json.dumps(tool_result, indent=2)
                else:
                    text_out = str(tool_result)

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": text_out
                            }
                        ],
                        "isError": False
                    }
                }
            except ValueError as e:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": str(e)}
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error executing {tool_name}: {str(e)}"}],
                        "isError": True
                    }
                }

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"}
        }

def start_mcp_server():
    """Entrypoint for standalone MCP server process."""
    server = StdioMCPServer()
    asyncio.run(server.run())

if __name__ == "__main__":
    start_mcp_server()
