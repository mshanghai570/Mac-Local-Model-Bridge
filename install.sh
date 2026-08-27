#!/usr/bin/env bash
# ==============================================================================
# Mac Local Model Bridge - Intel Mac, CPU-first installation helper
# ==============================================================================
set -euo pipefail

printf '%s\n' "======================================================"
printf '%s\n' "  Mac Local Model Bridge - CPU-first installation    "
printf '%s\n' "======================================================"

machine_arch="$(uname -m)"
if [[ "$machine_arch" == "x86_64" ]]; then
  printf '%s\n' "Detected Intel Mac (x86_64). The bridge will launch llama.cpp with --gpu-layers 0."
else
  printf '%s\n' "Detected $machine_arch. This setup remains CPU-first; Intel x86_64 is the documented target."
fi

if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' "Python 3 is required. Install a current Python 3 distribution, then run this script again." >&2
  exit 1
fi

printf '%s\n' "Creating/updating the Python virtual environment..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mcp]"

if command -v llama-server >/dev/null 2>&1; then
  printf '%s\n' "Found llama-server: $(command -v llama-server)"
elif command -v llama >/dev/null 2>&1; then
  printf '%s\n' "Found llama; the bridge will use 'llama serve': $(command -v llama)"
else
  cat <<'EOF'

No llama.cpp server binary was found. The bridge does not download or execute an
unverified inference runtime automatically. Install a current x86_64 llama.cpp
build that provides `llama-server` (or `llama serve`), then make it available on
PATH or set LLAMA_SERVER_PATH to its absolute path.

Typical source build (review upstream instructions before running):
  git clone https://github.com/ggml-org/llama.cpp
  cd llama.cpp
  cmake -B build -DCMAKE_BUILD_TYPE=Release
  cmake --build build --config Release
  export LLAMA_SERVER_PATH="$PWD/build/bin/llama-server"
EOF
fi

if command -v ollama >/dev/null 2>&1; then
  printf '%s\n' "Ollama detected. Existing Ollama gateway workflows remain available."
else
  printf '%s\n' "Ollama is optional; it is not required for the managed GGUF/llama.cpp path."
fi

cat <<'EOF'

Installation complete.

Recommended Intel-Mac GGUF workflow:
  1. local-ai-gateway serve
  2. local-ai-gateway pair        # Copy the short-lived code into the iPhone Connection screen.
  3. On iPhone: import a .gguf, then choose SEND TO MAC.
  4. bridge models
  5. bridge start <filename-or-sha256> --context-size 2048 --threads 4
  6. bridge run "Explain this project in one paragraph."

The bridge stores models in ~/.local/share/local-ai-gateway/models, verifies
SHA-256 and GGUF structure before promotion, and keeps llama.cpp on loopback.
EOF
