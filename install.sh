#!/usr/bin/env bash
# ==============================================================================
# Local AI Gateway - Fresh Installation Script for macOS Apple Silicon
# ==============================================================================
set -e

echo "======================================================"
echo "  Local AI Gateway - Installer for Apple Silicon Mac  "
echo "======================================================"

# 1. Homebrew check
if ! command -v brew &> /dev/null; then
    echo "ℹ️  Homebrew not detected. Installing dependencies via standard tools."
fi

# 2. Ollama installation check
if ! command -v ollama &> /dev/null; then
    echo "⚠️  Ollama is not installed."
    if command -v brew &> /dev/null; then
        echo "Installing Ollama via Homebrew..."
        brew install --cask ollama
    else
        echo "Please download Ollama from https://ollama.ai/download"
    fi
else
    echo "✓ Ollama is installed."
fi

# 3. Create Python venv
echo "📦 Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev,mcp]"

# 4. Pull default lightweight model
if command -v ollama &> /dev/null; then
    echo "⬇️  Pulling recommended default model (llama3.2:3b)..."
    ollama pull llama3.2:3b || true
fi

echo ""
echo "======================================================"
echo "  ✓ Installation complete!"
echo "  To start the gateway, run:"
echo "    ./start.sh"
echo "  Or run diagnostic doctor:"
echo "    ./start.sh doctor"
echo "======================================================"
