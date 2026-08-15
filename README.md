# ⚡ Local AI Gateway for iPhone & Apple Silicon Mac

Lightweight, high-performance on-device AI Gateway bridging **iPhone, Safari, Claude Desktop, and LAN clients** to locally hosted LLMs running with Metal GPU acceleration on Apple Silicon Mac (M1–M4).

**The Mac is the inference host. The iPhone is the client. Zero cloud dependencies, zero data leakage, zero subscription fees.**

---

## 1. Highlights & Capabilities

* **🍎 Native Apple Ecosystem Integration**: Automatic Wi-Fi discovery via Apple Bonjour / mDNS (`_local-ai-gateway._tcp`), QR pairing for iPhone, and complete Swift/SwiftUI client library.
* **🌐 Triple Protocol Support**:
  1. **OpenAI-Compatible API** (`/v1/chat/completions`, `/v1/models`, `/v1/completions`) for drop-in use with OpenAI SDKs, LangChain, LlamaIndex, Cursor, Chatbox, and Apple Shortcuts.
  2. **Model Context Protocol (MCP)** for native integration with Claude Desktop.
  3. **High-Performance Streaming REST API** with native Server-Sent Events (SSE), TTFT & TPS telemetry, and in-memory session management.
* **⚡ Deterministic Model Routing**: Direct support for task aliases (`fast`, `coding`, `reasoning`, `vision`, `general`, `auto`) and memory guards against oversized models.
* **🛡️ Hardened & Resilient**: Connection pooling, automatic exponential backoff retries, request timeout controls, bounded memory history, and graceful SIGINT/SIGTERM shutdown.
* **📱 Embedded Mobile Dashboard**: Fast, responsive web dashboard with live chat tester, token speed gauge, QR pairing, and device token management.

---

## 2. Quick Start (One Command)

### Prerequisites
1. Install [Ollama](https://ollama.ai) on your Mac:
   ```bash
   brew install --cask ollama
   ollama serve
   ```
2. Pull recommended local models:
   ```bash
   ollama pull llama3.2:3b
   ollama pull qwen2.5-coder
   ollama pull deepseek-r1:1.5b
   ```

### Installation & Launch
```bash
# 1. Clone repository
git clone https://github.com/your-username/local-ai-gateway.git
cd local-ai-gateway

# 2. Run fresh Mac installer (or ./start.sh)
./install.sh

# 3. Start gateway
./start.sh
```

Or run via the CLI directly:
```bash
# Run comprehensive diagnostic doctor
local-ai-gateway doctor

# Run a quick live inference test
local-ai-gateway test

# Start the gateway server
local-ai-gateway serve --port 8080
```

---

## 3. Connecting from iPhone & Clients

### Option A: Mobile Web Dashboard & QR Pairing
Open Safari on your iPhone and navigate to:
```text
http://YOUR_MAC_LAN_IP:8080/
```
Or click **Pair iPhone** in the dashboard and scan the QR code with your iPhone camera.

### Option B: Native SwiftUI App (iOS)
Use the included `/ios/MacLocalModelBridge` Swift package:
1. Open the project in Xcode.
2. Build and run on your physical iPhone.
3. The app scans your local network using Bonjour discovery (`_local-ai-gateway._tcp.local.`) and connects automatically.

### Option C: Apple Shortcuts
1. Open the **Shortcuts** app on your iPhone.
2. Add **Get Contents of URL**:
   * **URL**: `http://YOUR_MAC_LAN_IP:8080/v1/chat/completions`
   * **Method**: `POST`
   * **Headers**: `Content-Type: application/json`
   * **Request Body (JSON)**:
     ```json
     {
       "model": "fast",
       "messages": [{"role": "user", "content": "Shortcut Input"}],
       "stream": false
     }
     ```

### Option D: Claude Desktop (MCP Integration)
Add Local AI Gateway to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "local-mac-gateway": {
      "command": "local-ai-gateway",
      "args": ["mcp"]
    }
  }
}
```

---

## 4. API Endpoints Reference

### OpenAI-Compatible API (`/v1`)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/v1/models` | `GET` | Lists installed models in OpenAI format |
| `/v1/models/{model}` | `GET` | Returns individual model card |
| `/v1/chat/completions` | `POST` | Chat completions (JSON or SSE stream `stream: true`) |
| `/v1/completions` | `POST` | Raw text completions |

### Native REST & Streaming API
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/health` | `GET` | Liveness probe (process status, active requests, memory) |
| `/ready` | `GET` | Readiness probe (verifies Ollama connection; 200 OK / 503 Service Unavailable) |
| `/version` | `GET` | Semantic version metadata |
| `/models` | `GET` | Lists models with normalized capabilities (vision, tools, etc.) |
| `/models/{model}` | `GET` | Deep model specifications (context window, parameters, prompt template) |
| `/chat` | `POST` | Native chat with SSE streaming, context management, & token metrics |
| `/generate` | `POST` | Raw prompt generation with streaming |
| `/cancel` | `POST` | Cancels an in-flight generation task |
| `/sessions` | `GET`/`POST` | Create or list conversation sessions |
| `/sessions/{id}` | `GET`/`DELETE`| Retrieve or delete session history |
| `/pair` | `GET` | Dynamic pairing code & discovery metadata |
| `/pair/exchange`| `POST` | Exchange pairing code for persistent device token |
| `/devices` | `GET` | List paired devices |
| `/devices/{id}` | `DELETE` | Revoke a paired device |
| `/metrics` | `GET` | Performance metrics (TTFT, TPS, completed requests, RAM usage) |

---

## 5. Model Routing & Tasks

Instead of hardcoding model tags in client apps, pass a semantic task or alias:

| Task / Alias | Target Model (Default) | Primary Use Case |
| :--- | :--- | :--- |
| `fast` | `llama3.2:3b` | Low-latency summaries, single-turn prompts |
| `coding` | `qwen2.5-coder` | Code generation, refactoring, syntax inspection |
| `reasoning` | `deepseek-r1:1.5b` | Complex logic, step-by-step mathematical proofs |
| `vision` | `llava` | Multimodal photo and diagram analysis |
| `general` | `llama3.2:3b` | General conversational assistant |
| `auto` | *Dynamic Heuristic* | Automatically inspects prompt and attachments to select optimal model |

Aliases can be customized in `.env` via `MODEL_ALIASES_JSON` or `ALIAS_CODING=codestral`.

---

## 6. Configuration Reference

The gateway is built with **zero-configuration defaults**—it starts immediately with no environment variables or configuration files required.

### Normal Configuration (Sensible Built-in Defaults)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `GATEWAY_HOST` | `0.0.0.0` | Network interface to bind |
| `GATEWAY_PORT` | `8080` | Port for incoming LAN connections |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Backend Ollama server URL |
| `MODEL_PROVIDER` | `ollama` | Inference engine (`ollama`, `mlx`) |
| `DEFAULT_MODEL` | `llama3.2:3b` | Default model (or auto-detected from installed models) |
| `MAX_CONCURRENT_REQUESTS`| `1` | Concurrency limit to prevent Apple Silicon memory thrashing |
| `CONNECT_TIMEOUT_SECONDS`| `10` | Provider connection timeout in seconds |
| `REQUEST_TIMEOUT_SECONDS`| `300` | Total request timeout in seconds |
| `GENERATION_TIMEOUT_SECONDS`| `300` | LLM generation timeout in seconds |
| `STREAMING_IDLE_TIMEOUT_SECONDS`| `60` | SSE streaming idle timeout in seconds |
| `MAX_REQUEST_BYTES` | `10485760` | Max request payload size in bytes (10 MB) |
| `MAX_IMAGE_BYTES` | `10485760` | Max image attachment size in bytes (10 MB) |
| `MAX_SESSION_MESSAGES` | `100` | Max messages stored per session |
| `SESSION_TTL` | `86400` | Session expiration TTL in seconds (24h) |
| `CONTEXT_LIMIT_STRATEGY`| `trim` | Strategy when exceeding context (`trim`, `warn`, `strict`) |
| `ENABLE_BONJOUR` | `true` | Broadcast mDNS service on local Wi-Fi |
| `ENABLE_PAIRING` | `true` | Enable pairing code exchange API and QR codes |
| `ENABLE_DASHBOARD` | `true` | Serve embedded web playground on `/` |
| `ENABLE_SESSIONS` | `true` | Enable stateful session management APIs |
| `ENABLE_AUTO_ROUTING` | `true` | Enable heuristic routing for `auto` model |
| `VERBOSE_LOGGING` | `false` | Enable verbose debug logging |
| `ALLOWED_ORIGINS` | `*` | Allowed CORS origins (comma-separated or `*`) |

### Optional Secrets

| Secret Variable | Default | Description |
| :--- | :--- | :--- |
| `GATEWAY_API_KEY` | *(None)* | Optional master API key. If empty, authentication is disabled for open LAN dev. |
| `PAIRING_CODE` | *(Generated)* | Optional static pairing code. If empty, a secure 6-char random code is generated at runtime. |

---

## 7. macOS Firewall & Troubleshooting

If your iPhone cannot connect to `http://YOUR_MAC_IP:8080`:

### Step 1: Allow python3 through macOS Firewall
1. Open **System Settings** → **Network** → **Firewall**.
2. If Firewall is ON, click **Options...**.
3. Ensure **Terminal** (or your shell app: iTerm, Warp, etc.) is set to **Allow incoming connections**.
4. Ensure **python3** is set to **Allow incoming connections**.
   - If python3 is not listed, click **+** and add `/usr/local/bin/python3` or your Python binary.
5. Click **OK** to save.

**Quick Terminal Check:**
```bash
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
/usr/libexec/ApplicationFirewall/socketfilterfw --listapps
```

### Step 2: Start the Gateway
```bash
# From the project root
./start.sh
# Or directly:
python3 -m local_ai_gateway.main serve --port 8080
```

Verify it's running:
```bash
curl http://127.0.0.1:8080/health
```

### Step 3: Run Diagnostic Doctor
```bash
python3 -m local_ai_gateway.main doctor
```
This verifies port availability, Python dependencies, Ollama connectivity, and firewall status.

### Step 4: iPhone Setup
1. Open the **LM Bridge** app on your iPhone.
2. When prompted, grant **Local Network** permission (System Settings > Privacy & Security > Local Network).
3. In the app, either:
   - Tap **CONNECT** next to a discovered Bonjour bridge, OR
   - Manually enter your Mac's LAN IP (e.g. `192.168.1.100`) and port `8080`.
4. Tap **PING BUS** to verify the connection.
5. Send a prompt to stream tokens.

### Step 5: If Still Not Working
- **Same Wi-Fi**: Confirm both devices are on the **same Wi-Fi network** (not separate 2.4GHz/5GHz SSIDs that may be isolated).
- **LAN IP**: On your Mac, run `ifconfig | grep "inet " | grep -v 127.0.0.1` to find your Wi-Fi IP.
- **Firewall**: Temporarily disable the firewall to test: `sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off`
- **Restart**: Restart both your Mac and iPhone if the connection was previously cached.

---

## 8. Development & Tests

```bash
# Install development dependencies
make install

# Run full test suite
make test

# Check code linting
make lint

# Run diagnostic check
make doctor
```

---

## 9. License

MIT License. Crafted for high-reliability local inference on Apple Silicon.
