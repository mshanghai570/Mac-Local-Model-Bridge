oflow cli
# CLI Enhancement Guide

## Overview

The Local AI Gateway now includes two powerful CLI tools:

1. **`local-ai-gateway`** - Gateway control & diagnostics
2. **`bridge-cli`** - Interactive client for chat & sessions

Both support interactive REPL mode, session management, and rich terminal UI.

---

## Gateway CLI Commands

```bash
# Start gateway server
local-ai-gateway serve --host 0.0.0.0 --port 8080

# Run diagnostics
local-ai-gateway doctor

# Test inference
local-ai-gateway test --prompt "Your prompt here"

# List available models
local-ai-gateway models

# Show configuration
local-ai-gateway config

# Show statistics
local-ai-gateway stats

# Start MCP server
local-ai-gateway mcp

# Show version
local-ai-gateway version
```

---

## Bridge CLI Commands

### Interactive REPL Mode

```bash
# Start REPL
bridge-cli

# Load saved session
bridge-cli repl --session <session-id>

# Save config
bridge-cli --host 192.168.1.100 --port 8080 --save-config "hello"
```

### REPL Commands

Inside the REPL:

```
/models          - List available models
/sessions        - Show saved sessions
/load <id>       - Load session by ID
/export          - Export current session
/clear           - Clear conversation
/history         - Show history
/switch <model>  - Switch model
/settings        - Show settings
/help            - Show help
/exit or /quit   - Exit REPL
```

### One-Shot Mode

```bash
# Send single prompt
bridge-cli "Your prompt here"

# With specific model
bridge-cli --model qwen2.5-coder "Write Python code"

# With custom host/port
bridge-cli --host 192.168.1.100 --port 9000 "Hello"
```

### Session Management

```bash
# List all sessions
bridge-cli sessions list

# Export session
bridge-cli sessions export <session-id>

# Delete session
bridge-cli sessions delete <session-id>

# Clear all sessions
bridge-cli sessions clear --force
```

### Model Management

```bash
# List available models
bridge-cli models
```

### Configuration

```bash
# Show current config
bridge-cli config show

# Set config value
bridge-cli config set host 192.168.1.100
bridge-cli config set port 9000
bridge-cli config set model llama3.2:3b

# Reset to defaults
bridge-cli config reset
```

---

## Configuration Files

### Bridge CLI Config

Location: `~/.bridge-cli/config.json`

```json
{
  "host": "127.0.0.1",
  "port": 8080,
  "model": "auto",
  "api_key": ""
}
```

### Session Storage

Location: `~/.local/share/bridge-cli/sessions/`

Each session is a JSON file with full conversation history.

---

## Environment Variables

```bash
# Gateway CLI
LM_BRIDGE_HOST=192.168.1.100
LM_BRIDGE_PORT=8080
LM_BRIDGE_API_KEY=your-api-key

# Then run:
bridge-cli "Your prompt"
```

---

## Tips & Tricks

1. **Quick Save**: Use `--save-config` with first prompt to save defaults
2. **Session Replay**: Use `/load <id>` to resume conversations
3. **Model Switching**: Use `/switch <model>` in REPL to try different models
4. **Export**: Use `/export` to save conversation as JSON for analysis
5. **Auto-Completion**: Sessions auto-save after each message

---

## New Features

✨ **Session Persistence**
- Auto-saves conversations to `~/.local/share/bridge-cli/sessions/`
- Load previous sessions with `/load <id>` or `bridge-cli repl --session <id>`
- Export sessions to JSON or Markdown

💾 **Configuration Management**
- System-wide config in `~/.bridge-cli/config.json`
- Environment variable overrides
- `config show/set/reset` commands

🎨 **Rich Terminal UI**
- Colored output with `rich` library
- Formatted tables for models and sessions
- Spinners and progress indicators
- Highlighted code blocks

📋 **Model Discovery**
- `models` command lists capabilities
- Vision, tools, context window info
- Easy model switching in REPL

🔄 **Flexible Input**
- Interactive REPL mode for multi-turn chat
- One-shot mode for scripting
- Piped input support

---

## Troubleshooting

### "Cannot connect to gateway"

```bash
# Check gateway is running
local-ai-gateway serve --port 8080

# Check connection
curl http://127.0.0.1:8080/health

# Set correct host/port
export LM_BRIDGE_HOST=192.168.1.100
bridge-cli "test"
```

### "rich library not found"

```bash
pip install rich
# Or reinstall with optional deps:
pip install -e ".[dev]"
```

### Sessions not loading

```bash
# Check session directory
ls ~/.local/share/bridge-cli/sessions/

# Export to verify
bridge-cli sessions export abc123
```

---

## Architecture

### Session Manager (`cli/session_manager.py`)

Handles persistent session storage with:
- Message objects (user, assistant, tool)
- Session creation and loading
- JSON serialization
- Session listing and export

### REPL Engine (`cli/repl_engine.py`)

Interactive chat engine with:
- Streaming response handling
- Tool integration
- Rich UI rendering
- Session auto-save
- Command parsing

### Bridge CLI (`cli/mac_cli.py`)

Main CLI interface providing:
- Command routing
- Config management
- Session/model commands
- REPL mode launcher
- One-shot mode

### Gateway CLI (`local_ai_gateway/main.py`)

Enhanced with:
- Model listing
- Config display
- Statistics display
- Better doctor diagnostics
- Rich formatting

---

## Development Notes

- Uses `httpx` for async HTTP
- Uses `rich` for terminal UI
- Sessions stored as JSON in `~/.local/share/bridge-cli/sessions/`
- Config stored in `~/.bridge-cli/config.json`
- Fully async/await compatible
- Error handling for network issues

