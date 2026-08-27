# Mac CLI — `cli/mac_cli.py`

Thin Python client that talks to the iPhone's `/v1/chat/completions` endpoint.

## Prerequisites

The project uses a virtual environment at `.venv`. Use that Python, not the system Python:

```bash
PY=/Users/michaelshingara/Documents/remix-mac-local-ai-gateway-for-iphone/.venv/bin/python3
```

Or add to your `~/.zshrc`:

```bash
alias bridge-cli='/Users/michaelshingara/Documents/remix-mac-local-ai-gateway-for-iphone/.venv/bin/python3 /Users/michaelshingara/Documents/remix-mac-local-ai-gateway-for-iphone/cli/mac_cli.py'
```

## Usage

```bash
# Send a prompt (streams response to stdout)
$PY cli/mac_cli.py "list the files in /Users/michaelshingara/Documents"

# With explicit host/port
LM_BRIDGE_HOST=192.168.1.100 LM_BRIDGE_PORT=9090 $PY cli/mac_cli.py "read /etc/hosts"

# Save host/port to ~/.lm_bridge_config.json
$PY cli/mac_cli.py --save-config --host 192.168.1.100 "hello"

# Non-streaming
$PY cli/mac_cli.py --no-stream "what is 2+2?"

# List available tools
$PY cli/mac_cli.py --list-tools
```

## Config

Environment variables (highest priority):
- `LM_BRIDGE_HOST` — iPhone LAN IP
- `LM_BRIDGE_PORT` — iPhone HTTP server port (default `9090`)
- `LM_BRIDGE_API_KEY` — optional API key

Fallback config file: `~/.lm_bridge_config.json`

```json
{
  "host": "192.168.1.100",
  "port": 9090,
  "api_key": ""
}
```

## Tool-call loop

The CLI sends `read_file` and `list_directory` in the `tools` field. When the model returns `tool_calls`, the CLI:
1. Parses the function name + JSON arguments
2. Executes the tool locally against the Mac filesystem
3. Sends the result back in a follow-up `role: tool` message
4. Repeats until the model stops calling tools

## Safety

- Read-only tools only (`read_file`, `list_directory`)
- No write/edit/delete tools yet
- Paths must be absolute
- `read_file` caps output at 200 KB
