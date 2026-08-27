#!/bin/bash
export LM_BRIDGE_HOST="${LM_BRIDGE_HOST:-192.168.68.100}"
export LM_BRIDGE_PORT="${LM_BRIDGE_PORT:-9090}"
exec /Users/michaelshingara/Documents/remix-mac-local-ai-gateway-for-iphone/.venv/bin/bridge-cli "$@"
