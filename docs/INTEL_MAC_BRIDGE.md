# Intel Mac GGUF Bridge

This guide describes the **Mac-hosted GGUF inference path**. It is designed for an Intel (`x86_64`) Mac where CPU execution is the reliable default: the Mac owns the runtime and model cache, and the iPhone is a paired controller and transfer client. The existing Ollama integration and legacy iPhone direct-inference path remain available, but neither is required for this workflow.

> The raw llama.cpp process binds only to `127.0.0.1`. The LAN-facing gateway mediates discovery, pairing, status, and model transfers.

## Architecture

```text
iPhone local GGUF library
  -> SHA-256 + 4 MiB resumable upload chunks
  -> Mac gateway :8080 (paired-device token required)
  -> Mac model store (~/.local/share/local-ai-gateway/models)
  -> loopback llama.cpp :8081 (CPU-first, --gpu-layers 0)
  -> bridge CLI and Zed on the Mac
```

The Mac store promotes a file only after its declared size, SHA-256 digest, and GGUF tensor extent have been validated. Transfers are staged as `.part` files and promoted atomically, so an interrupted or corrupt upload never appears in the available-model list.

## Prerequisites

Install Python 3 and a current **x86_64** build of llama.cpp that provides either `llama-server` or `llama serve`. llama.cpp documents a standard CPU build with CMake and describes its server as an OpenAI-compatible HTTP server.[1][2]

```bash
./install.sh
source .venv/bin/activate
```

The installer intentionally does **not** download a runtime binary or a model automatically. Set an explicit path if the runtime is not on `PATH`:

```bash
export LLAMA_SERVER_PATH="/absolute/path/to/llama-server"
export LLAMA_SERVER_PORT=8081          # optional; defaults to 8081
export MODEL_PROVIDER=llama_cpp         # optional; makes existing gateway chat routes use it
```

## End-to-End Workflow

Start the gateway on the Mac. Port 8080 is the only LAN-facing service in this design.

```bash
local-ai-gateway serve --port 8080
```

Create an explicit, time-limited pairing code on the Mac. Enter that code in the iPhone app’s **Connection → Secure Model Bridge Pairing** section. The gateway stores only a SHA-256 hash of the issued device token in an owner-only registry; the app stores the token in the iPhone Keychain.

```bash
local-ai-gateway pair
```

On the iPhone, import a `.gguf` into the app’s on-device library, open its **On-Device** models tab, and select **Send to Mac**. The transfer screen reports its byte progress. Selecting **Cancel** preserves the staged bytes on the Mac, and pressing **Send to Mac** again resumes at the server-reported offset.

After transfer, use the iPhone **Mac** tab to select/start/stop a model or use the Mac CLI:

```bash
bridge models
bridge select my-model.gguf
bridge start --context-size 2048 --threads 4
bridge status
bridge run "Summarize the project architecture."
bridge chat
```

`bridge start` always passes `--gpu-layers 0`, making this path CPU-first and appropriate for an Intel Mac. Use a conservative model and context size suited to the machine’s RAM; the runtime does not pretend that GPU acceleration is available.

## Bridge-v1 API

Every endpoint in this table requires an explicitly paired-device bearer token. Legacy gateway routes retain their existing authentication behavior for compatibility.

| Endpoint | Method | Purpose |
|---|---:|---|
| `/bridge/v1/health` | `GET` | Transfer store, selected model, and runtime status. |
| `/bridge/v1/models` | `GET` | List only verified Mac-stored GGUF models. |
| `/bridge/v1/models/lookup?sha256=…` | `GET` | Check whether an iPhone model digest is already available. |
| `/bridge/v1/transfers` | `POST` | Create or resume a transfer manifest. |
| `/bridge/v1/transfers/{id}` | `GET` | Read persisted resume offset and state. |
| `/bridge/v1/transfers/{id}/chunk` | `PUT` | Append a bounded chunk with `X-Upload-Offset`. |
| `/bridge/v1/transfers/{id}/complete` | `POST` | Verify SHA-256/GGUF then atomically register the model. |
| `/bridge/v1/transfers/{id}/cancel` | `POST` | Mark a transfer cancelled while keeping resumable staged bytes. |
| `/bridge/v1/models/{sha256}/select` | `POST` | Select a transferred model. |
| `/bridge/v1/runtime` | `GET` | Read managed llama.cpp status, PID, selected model, and memory. |
| `/bridge/v1/runtime/start` | `POST` | Start a selected model on loopback. |
| `/bridge/v1/runtime/stop` | `POST` | Stop only the subprocess started by this bridge. |
| `/bridge/v1/runtime/restart` | `POST` | Restart the selected or specified managed model. |

A transfer is declared with a JSON manifest:

```json
{
  "filename": "qwen2.5-3b-instruct-q4_k_m.gguf",
  "size_bytes": 2147483648,
  "sha256": "<64-character lowercase hexadecimal SHA-256>"
}
```

Chunks are binary request bodies. The gateway accepts at most **8 MiB** per chunk by default (`MAX_UPLOAD_CHUNK_BYTES`), and each append must use the exact byte offset returned by the transfer status. An offset conflict returns HTTP 409 and the expected offset; a checksum or GGUF failure returns HTTP 400; insufficient disk space returns HTTP 507.

## Zed

Zed directly supports a local llama.cpp server and can automatically discover models served by a recent llama.cpp build.[3] Start the model as above, then configure Zed on the same Mac to use the loopback endpoint. The following configuration follows Zed’s documented llama.cpp provider shape:

```json
{
  "language_models": {
    "llama.cpp": {
      "api_url": "http://127.0.0.1:8081",
      "context_window": 2048
    }
  }
}
```

If you intentionally start the runtime with `--runtime-api-key` / `LLAMA_SERVER_API_KEY`, enter that key through Zed’s provider UI or its supported secure provider configuration. Do not copy a paired iPhone token into an editor configuration; it authorizes model administration, not just local inference.

## Security and Operational Boundaries

| Boundary | Design decision |
|---|---|
| Pairing | A short-lived random code is exchanged for a per-device token. Tokens are shown only at exchange time. |
| Mac persistence | The registry contains device IDs, friendly names, timestamps, and SHA-256 token hashes; it is written atomically with `0600` file permissions. |
| iPhone persistence | The bridge token uses the system Keychain. Older plaintext `UserDefaults` values are migrated and removed. |
| Transfer | File names cannot contain path components; chunks have a strict size cap; data is never assembled in RAM; uploads validate fixed length/digest/GGUF structure before availability. |
| Runtime | Only the process launched by the controller is stopped. The engine is loopback-only; remote iPhone access remains through the authenticated gateway. |
| Existing components | Ollama and direct phone inference are not deleted. Direct phone inference is now an explicit off-by-default fallback in the app settings. |

## Troubleshooting

| Symptom | Check |
|---|---|
| `llama.cpp executable not found` | Install a current binary, place it on `PATH`, or set `LLAMA_SERVER_PATH`. |
| `Port 8081 is already in use` | Stop the conflicting loopback service or set `LLAMA_SERVER_PORT` to a free port before starting the gateway. |
| iPhone gets `401` on Mac models | Generate a new `local-ai-gateway pair` code and pair the iPhone; generic open-LAN access is intentionally not sufficient. |
| Upload resumes at a non-zero offset | This is expected after interruption/cancel. The app requests the persisted offset and sends only the remaining bytes. |
| Upload fails a digest check | Delete/re-import the source `.gguf` on the phone and retry. The Mac has not promoted the staged file. |
| Zed cannot see the model | Confirm `bridge status` is running, visit `http://127.0.0.1:8081/health` on the Mac, and set Zed’s llama.cpp API URL to that loopback address. |

## References

[1]: https://github.com/ggml-org/llama.cpp "llama.cpp official repository"
[2]: https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md "llama.cpp official build guide"
[3]: https://zed.dev/docs/ai/use-a-local-model "Zed: Use a Local Model"
