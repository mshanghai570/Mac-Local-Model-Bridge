# IPA Installation Guide - Direct Inference Mode

## 📦 Available IPA Files

| File | Type | Size | Built | Description |
|------|------|------|-------|-------------|
| `MacLocalModelBridge-unsigned.ipa` | **Device (arm64)** | ~2.8MB | Aug 26, 2026 | Latest - **Direct inference mode** |
| `MacLocalModelBridge-device-unsigned.ipa` | Device | ~5.3MB | Aug 15, 2026 | Older version (proxy mode) |
| `MacLocalModelBridge-simulator-unsigned.ipa` | Simulator | ~7.1MB | Aug 15, 2026 | For iOS Simulator |
| `MacLocalModelBridge.ipa` | Device | ~5.5MB | Aug 16, 2026 | Older version |

**✅ Use `MacLocalModelBridge-unsigned.ipa` for testing the new direct inference mode!**

---

## 📱 Installation Methods

### Method 1: Sideloadly (Recommended - No Jailbreak)

1. **Download [Sideloadly](https://sideloadly.io/)** for Mac or Windows
2. **Connect your iPhone** via USB
3. **Trust the computer** on your iPhone
4. **Open Sideloadly** and drag & drop `MacLocalModelBridge-unsigned.ipa`
5. **Enter your Apple ID** (free account works)
6. **Click Start** to install
7. **Wait for installation** to complete
8. **Go to Settings > General > VPN & Device Management** on your iPhone
9. **Trust the developer certificate** (your Apple ID)
10. **Open the app** and grant Local Network permission

### Method 2: AltStore

1. **Install AltStore** on your iPhone
2. **Connect iPhone to Mac** and open AltStore
3. **Drag & drop the IPA** into AltStore
4. **Wait for installation**
5. **Trust the certificate** in Settings
6. **Open the app**

### Method 3: TrollStore (Permanent Sideloading)

1. **Install TrollStore** on your iPhone (requires iOS 14.0-15.4.1 or 16.0-16.6.1)
2. **Use TrollStore's built-in IPA installer**
3. **Select `MacLocalModelBridge-unsigned.ipa`**
4. **Install the app**
5. **No certificate trust needed** - permanent signing!

---

## ⚠️ Requirements

### iPhone Requirements
- **iOS 16.0 or later** (for Swift Concurrency)
- **A12 chip or later** (iPhone XS/XR or newer) for good performance
- **At least 2GB RAM** (iPhone 8 and later recommended)
- **5-10GB free storage** for GGUF models

### Model Requirements
- **.gguf format only** (not GGML, safetensors, or MLX)
- **Recommended models for iPhone:**
  - `llama-2-7b-chat.Q4_K_M.gguf` (~4.3GB)
  - `mistral-7b-instruct.Q4_0.gguf` (~3.8GB)
  - `phi-2.Q4_K_M.gguf` (~1.6GB)
  - `tinyllama-1.1b.Q4_K_M.gguf` (~600MB) - Fastest

### Mac Requirements
- **macOS 12.0+**
- **Same Wi-Fi network** as iPhone
- **Python 3.9+** for the CLI

---

## 🚀 First Launch

### On iPhone:
1. Open **MacLocalModelBridge** app
2. Grant **Local Network** permission when prompted
   - If not prompted, go to: **Settings > Privacy & Security > Local Network > MacLocalModelBridge > Enable**
3. Tap **Models** tab
4. Tap **+ Import Model**
5. Select a `.gguf` file from Files, iCloud, or download
6. Wait for import to complete (validates file integrity)
7. Tap on the model to **load it**
8. Wait for model to finish loading (may take 10-60 seconds)

### On Mac:
```bash
# Install the CLI
cd /path/to/remix-mac-local-ai-gateway-for-iphone
pip install -e .

# Connect to iPhone (replace with your iPhone's IP)
bridge-cli serve --phone-url http://192.168.1.100:9090

# Or use auto-discovery
bridge-cli serve

# Test it
bridge-cli "Hello from Mac!"
```

---

## 🔍 Verify Installation

### Check if server is running:
```bash
curl http://IPHONE_IP:9090/health
```

Expected response:
```json
{
  "status": "ok",
  "device": "iPhone",
  "provider": "iphone-gguf",
  "mode": "direct",
  "model_loaded": true,
  "model_name": "your-model.gguf"
}
```

### List loaded models:
```bash
curl http://IPHONE_IP:9090/v1/models
```

---

## ❌ Troubleshooting

### "Unable to install app"
- **Solution:** Try a different sideloading method
- **Check:** Your Apple ID may have too many sideloaded apps (limit: 3)
- **Fix:** Remove old sideloaded apps or use a different Apple ID

### "App crashes on launch"
- **Check:** Local Network permission granted?
- **Check:** Is a model loaded?
- **Check:** iOS version compatibility

### "Connection refused" when testing
- **Check:** Is the iOS app open?
- **Check:** Are both devices on the same Wi-Fi?
- **Check:** Is the iPhone's IP correct?
- **Try:** `curl http://IPHONE_IP:9090/health`

### "No model loaded"
- **Solution:** Import and load a GGUF model in the Models tab first

### "Model fails to load"
- **Check:** Is the file a valid GGUF?
- **Check:** Is the file downloaded completely?
- **Check:** Does the iPhone have enough memory? (Close other apps)

---

## 📊 What's New in This IPA

✅ **Direct Inference Mode** (NEW!)
- iPhone runs GGUF models directly via llama.cpp
- No dependency on Mac gateway
- Faster response times (no network hop)

✅ **New API Endpoints**
- `GET /health` - Server status and loaded model
- `GET /v1/models` - List installed models
- `POST /v1/chat/completions` - OpenAI-compatible chat

✅ **Streaming Support**
- Real-time token streaming via SSE
- Compatible with OpenAI client libraries

✅ **Mac CLI Integration**
- `bridge-cli` can connect to iPhone for inference
- Mac executes tools (file system access)
- iPhone provides the intelligence

---

## 🎯 Quick Test

After installation:

1. **Load a model** on iPhone (Models tab)
2. **On Mac, run:**
   ```bash
   bridge-cli serve --phone-url http://YOUR_IPHONE_IP:9090
   ```
3. **In another terminal:**
   ```bash
   bridge-cli "What is the capital of France?"
   ```
4. **Expected:** Response from iPhone model!

---

## 📝 Notes

- **Unsigned IPA expires** after 7 days (free Apple Developer account)
- **Re-sideload** every 7 days, or use TrollStore for permanent installation
- **Model files are NOT included** in the IPA - you need to download them separately
- **First launch may be slow** as it initializes the inference engine

---

## 📚 Resources

- **GGUF Models:** https://huggingface.co/models?library=gguf
- **Model Recommendations:** See README.md in the project
- **CLI Documentation:** PHONE_DIRECT_INFERENCE.md
- **Support:** Open an issue on GitHub
