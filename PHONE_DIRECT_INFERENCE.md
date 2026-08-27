# iPhone Direct Inference Mode - CLI Integration Guide

## Overview

This guide explains the new **direct inference mode** for the iPhone HTTP server, which allows your iPhone to run GGUF models and serve them directly to the Mac CLI (`bridge-cli`). This enables the workflow where:

1. **iPhone powers the models** - Runs GGUF inference on-device via `LocalInferenceEngine`
2. **Mac executes tools** - Runs filesystem/shell operations via `bridge-cli`
3. **iPhone controls the CLI** - Sends prompts and receives tool results

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   iPhone        │     │   Mac           │
│                 │     │                 │
│  ┌─────────────┐│     │  ┌─────────────┐│
│  │GGUF Model   ││     │  │ bridge-cli   ││
│  │(llama.cpp)  ││     │  │ (serve mode) ││
│  └──────┬──────┘│     │  └──────┬──────┘│
│         │         │     │         │        │
│  ┌──────▼──────┐│     │  ┌──────▼──────┐│
│  │PhoneHttp    │◄─────►│  │FastAPI Agent││
│  │Server       ││     │  │(/chat,       ││
│  │:9090        ││     │  │ /tools/call) ││
│  └─────────────┘│     │  └─────────────┘│
└─────────────────┘     └─────────────────┘
     Direct Inference         Tool Execution
```

## Changes Made

### 1. PhoneHttpServer.swift (iOS)

**Added direct inference mode with the following endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health + loaded model info |
| `/v1/models` | GET | List installed GGUF models |
| `/v1/chat/completions` | POST | OpenAI-compatible chat completion |
| `/chat` | POST | Legacy chat endpoint (same as above) |

**Key Features:**
- ✅ Streaming (SSE) and non-streaming modes
- ✅ OpenAI-compatible request/response format
- ✅ Automatic model loading from DeviceModelStore
- ✅ Error handling with proper HTTP status codes
- ✅ Backward compatible with proxy mode

**Server Mode Configuration:**
```swift
PhoneHttpServer.shared.mode = .directInference  // Default: run models on iPhone
PhoneHttpServer.shared.mode = .proxyToUpstream   // Legacy: proxy to Mac gateway
```

### 2. MacLocalModelBridgeApp.swift (iOS)

**Updated to start in direct inference mode by default:**
```swift
// Configure server for direct inference mode (iPhone powers the models)
PhoneHttpServer.shared.mode = .directInference
PhoneHttpServer.shared.start(port: settings.serverPort)
```

## Usage

### Step 1: Load a Model on iPhone

1. Open the **MacLocalModelBridge** app on your iPhone
2. Tap the **Models** tab
3. Import a `.gguf` file (from Files app, iCloud, or download)
4. Tap on the model to load it
5. Wait for the model to finish loading

The iPhone HTTP server starts automatically when you open the app, listening on port **9090** by default.

### Step 2: Start the Mac CLI in Serve Mode

On your Mac, run:

```bash
# Navigate to project directory
cd /path/to/remix-mac-local-ai-gateway-for-iphone

# Start the Mac agent that connects to iPhone for inference
bridge-cli serve --phone-url http://IPHONE_IP:9090
```

Replace `IPHONE_IP` with your iPhone's local network IP address (e.g., `192.168.1.100`).

**Alternative: Auto-discovery via Bonjour**
```bash
# The CLI will automatically discover iPhones on the same Wi-Fi
bridge-cli serve
```

### Step 3: Use the CLI

Once connected, you can:

**Option A: Interactive Chat (REPL mode)**
```bash
bridge-cli chat
# Type prompts, tokens stream from iPhone
# Use /models, /switch, /clear, /exit commands
```

**Option B: One-Shot Prompt**
```bash
bridge-cli "Summarize this document"
```

**Option C: With Specific Model**
```bash
bridge-cli --model my-model.gguf "Write Python code to sort a list"
```

**Option D: List Available Models on iPhone**
```bash
bridge-cli models
```

### Step 4: Mac Executes Tools (Automatic)

When the model running on iPhone needs to execute a tool (read a file, list a directory, etc.), the Mac CLI automatically:

1. Receives the tool call from iPhone
2. Executes the tool on the Mac filesystem
3. Returns the result to the iPhone
4. iPhone continues inference with the tool result

Example flow:
```
You: "What's in my Documents folder?"
    ↓
iPhone: Runs model, generates tool call: list_directory(path: "/Users/me/Documents")
    ↓
Mac CLI: Executes tool, returns: "file1.txt, file2.pdf, project/"
    ↓
iPhone: Model continues with tool result, generates final answer
    ↓
You: See the list of files in your Documents folder
```

## Available Tools on Mac CLI

| Tool | Description | Enabled by Default |
|------|-------------|-------------------|
| `read_file` | Read file contents (capped at 200KB) | ✅ Yes |
| `list_directory` | List files in a directory | ✅ Yes |
| `get_cwd` | Get current working directory | ✅ Yes |
| `hostname` | Get Mac hostname | ✅ Yes |
| `write_file` | Write to a file | ❌ No (use `--allow-write`) |
| `run_command` | Run shell command | ❌ No (use `--allow-shell`) |

Enable additional tools:
```bash
bridge-cli serve --allow-write --allow-shell
```

## API Reference

### Health Endpoint

**GET /health**

Returns server status and loaded model information.

**Response:**
```json
{
  "status": "ok",
  "device": "iPhone",
  "provider": "iphone-gguf",
  "service": "phone-http-server",
  "mode": "direct",
  "model_loaded": true,
  "model_name": "llama-2-7b.Q4_K_M.gguf",
  "lan_ip": "192.168.1.100",
  "models": ["llama-2-7b.Q4_K_M.gguf", "mistral-7b.Q4_0.gguf"]
}
```

### Models Endpoint

**GET /v1/models**

List all installed GGUF models on the iPhone.

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "llama-2-7b.Q4_K_M.gguf",
      "name": "llama-2-7b.Q4_K_M.gguf",
      "size_bytes": 4294967296,
      "size_formatted": "4 GB",
      "loaded": true,
      "parameter_count": 7000000000,
      "context_length": 4096,
      "quantization": "Q4_K_M"
    },
    {
      "id": "mistral-7b.Q4_0.gguf",
      "name": "mistral-7b.Q4_0.gguf",
      "size_bytes": 3800000000,
      "size_formatted": "3.8 GB",
      "loaded": false
    }
  ]
}
```

### Chat Completions Endpoint

**POST /v1/chat/completions**

Run inference with streaming or non-streaming response.

**Request Headers:**
- `Accept: text/event-stream` - For streaming
- `Content-Type: application/json`

**Request Body:**
```json
{
  "model": "llama-2-7b.Q4_K_M.gguf",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 512,
  "stream": true
}
```

**Non-Streaming Response:**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1712345678,
  "model": "llama-2-7b.Q4_K_M.gguf",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 10,
    "total_tokens": 25
  }
}
```

**Streaming Response (SSE):**
```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1712345678,"model":"llama-2-7b.Q4_K_M.gguf","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1712345678,"model":"llama-2-7b.Q4_K_M.gguf","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1712345678,"model":"llama-2-7b.Q4_K_M.gguf","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1712345678,"model":"llama-2-7b.Q4_K_M.gguf","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## Error Handling

| Error | HTTP Status | Description |
|-------|-------------|-------------|
| `modelNotLoaded` | 400 | No model loaded on iPhone |
| `invalidRequest` | 400 | Malformed request |
| `inferenceError` | 500 | Inference failed |
| `upstreamError` | 502 | Proxy mode error (legacy) |

## Configuration

### iPhone Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `serverPort` | 9090 | HTTP server port |
| `autoDiscover` | true | Auto-discover Mac bridges |

### Mac CLI Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LM_BRIDGE_HOST` | (auto-discover) | iPhone IP address |
| `LM_BRIDGE_PORT` | 9090 | iPhone HTTP port |
| `LM_PHONE_URL` | (auto-discover) | Full iPhone URL |

## Testing

### Test with curl

```bash
# Health check
curl http://IPHONE_IP:9090/health

# List models
curl http://IPHONE_IP:9090/v1/models

# Non-streaming chat
curl -X POST http://IPHONE_IP:9090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"my-model.gguf","messages":[{"role":"user","content":"Hello"}],"stream":false}'

# Streaming chat
curl -X POST http://IPHONE_IP:9090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"model":"my-model.gguf","messages":[{"role":"user","content":"Hello"}],"stream":true}'
```

### Test with Python

```python
import requests
import json

# List models
response = requests.get("http://IPHONE_IP:9090/v1/models")
print(response.json())

# Chat completion
response = requests.post(
    "http://IPHONE_IP:9090/v1/chat/completions",
    json={
        "model": "my-model.gguf",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False
    }
)
print(response.json())

# Streaming chat
import sseclient
response = requests.post(
    "http://IPHONE_IP:9090/v1/chat/completions",
    json={
        "model": "my-model.gguf",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True
    },
    headers={"Accept": "text/event-stream"}
)
client = sseclient.SSEClient(response)
for event in client.events():
    print(event.data)
```

## Troubleshooting

### "No on-device model is loaded"

**Solution:** Open the iOS app, go to the **Models** tab, and load a GGUF model.

### "Connection refused" or timeout

**Checklist:**
1. Is the iOS app open?
2. Is the iPhone on the same Wi-Fi network as the Mac?
3. What is the iPhone's IP? (Check in Settings > Wi-Fi > [your network])
4. Try: `curl http://IPHONE_IP:9090/health`
5. Check macOS Firewall settings (System Settings > Network > Firewall)

### "Invalid request"

**Solution:** Ensure your request:
- Has correct `Content-Type: application/json` header
- Has valid JSON body
- Uses POST method for `/v1/chat/completions`

### Models not appearing

**Solution:** 
1. Import GGUF files via the iOS app's Models tab
2. Files must have `.gguf` extension
3. Wait for import to complete (check notifications)
4. Refresh the models list

## Performance Notes

- **Model Size**: Larger models (>4GB) may fail to load on iPhones with limited RAM
- **GPU Offload**: iPhone uses Metal acceleration automatically for supported models
- **Context Length**: Limited by model's trained context window
- **Token Budget**: Default max_tokens is 512; increase for longer responses
- **Memory**: Running inference on iPhone uses significant memory; close other apps

## Supported Model Formats

- ✅ GGUF (all quantization types: Q4_0, Q4_K_M, Q5_0, Q5_K_M, Q8_0, etc.)
- ✅ Models with chat templates (Llama, Mistral, Phi, etc.)
- ❌ GGML (not supported)
- ❌ Safetensors (not supported)
- ❌ MLX (not supported in this path - use Mac for MLX)

## Security

- 🔒 All communication is on local network (not internet)
- 🔒 No data leaves your devices
- 🔒 Optional API key support for authenticated access
- ⚠️ Enable `--allow-write` and `--allow-shell` carefully (gives model file system access)

## Version Compatibility

| Component | Version |
|-----------|---------|
| iOS App | 1.0.0+ |
| bridge-cli | 1.0.0+ |
| llama.cpp | b10446 |
| LlamaSwift | Latest |

## Migration from Proxy Mode

If you were previously using the proxy mode (where iPhone forwarded to a Mac gateway):

**Old flow:**
```
iPhone → Mac Gateway → Ollama → Model
```

**New flow (this document):**
```
iPhone (GGUF Model) ←→ Mac CLI (Tools)
```

To switch:
1. Ensure you have GGUF models on your iPhone
2. Update the iOS app with the new PhoneHttpServer code
3. No changes needed to Mac CLI - it works with both modes!

## Source Code References

- **iOS HTTP Server**: `ios/MacLocalModelBridge/Services/PhoneHttpServer.swift`
- **iOS Inference Engine**: `ios/MacLocalModelBridge/Services/LocalInferenceEngine.swift`
- **Mac CLI**: `cli/mac_cli.py`
- **Mac Agent Server**: `cli/agent_server.py`
