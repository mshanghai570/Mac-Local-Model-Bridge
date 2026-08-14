#!/usr/bin/env bash
# ==============================================================================
# Local AI Gateway - One-Command Startup Script
# ==============================================================================
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# 1. Check Python installation
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed. Please install Python 3.9+ (brew install python)."
    exit 1
fi

# 2. Setup or activate virtual environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment (.venv)..."
    python3 -m venv .venv
    source .venv/bin/activate
    echo "⬇️  Installing gateway dependencies..."
    pip install --upgrade pip
    pip install -e .
else
    source .venv/bin/activate
fi

# 3. Check if Ollama is running
if ! curl -s http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
    echo "⚠️  Ollama does not appear to be running on http://127.0.0.1:11434."
    echo "   Attempting to start Ollama in background (or run 'ollama serve' manually)..."
    if command -v ollama &> /dev/null; then
        ollama serve > /dev/null 2>&1 &
        sleep 2
    fi
fi

# 4. Start Local AI Gateway
echo "🚀 Starting Local AI Gateway..."
python3 -m local_ai_gateway.main serve
