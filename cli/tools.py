"""
Mac-side tools the iPhone (or a local chat session) can invoke.

Default surface is read-only. Destructive tools require explicit flags
on `bridge-cli serve` / `bridge-cli chat`.
"""
from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


READ_FILE_CAP_BYTES = 200 * 1024
LIST_DIR_CAP = 500
RUN_COMMAND_TIMEOUT_SECONDS = 30


class ToolError(Exception):
    """Raised when a tool cannot run. Message is safe to send back to the model."""


def _expand_path(raw: str) -> Path:
    if not raw or not str(raw).strip():
        raise ToolError("path is required")
    path = Path(os.path.expanduser(str(raw).strip())).resolve()
    return path


def _require_absolute(path: Path) -> Path:
    # resolve() already makes it absolute; still reject empty / relative inputs
    # that expand to cwd accidentally by requiring the original to look absolute
    # or start with ~.
    return path


def tool_read_file(arguments: Dict[str, Any], **_: Any) -> str:
    path = _require_absolute(_expand_path(arguments.get("path", "")))
    if not path.exists():
        raise ToolError(f"file not found: {path}")
    if not path.is_file():
        raise ToolError(f"not a file: {path}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ToolError(f"cannot read {path}: {exc}") from exc
    if len(data) > READ_FILE_CAP_BYTES:
        data = data[:READ_FILE_CAP_BYTES]
        truncated = True
    else:
        truncated = False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
        truncated = True
    if truncated:
        return text + f"\n\n[truncated at {READ_FILE_CAP_BYTES} bytes]"
    return text


def tool_list_directory(arguments: Dict[str, Any], **_: Any) -> str:
    path = _require_absolute(_expand_path(arguments.get("path", "")))
    if not path.exists():
        raise ToolError(f"directory not found: {path}")
    if not path.is_dir():
        raise ToolError(f"not a directory: {path}")
    try:
        entries = sorted(path.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        raise ToolError(f"cannot list {path}: {exc}") from exc

    lines: List[str] = []
    for entry in entries[:LIST_DIR_CAP]:
        suffix = "/" if entry.is_dir() else ""
        lines.append(f"{entry.name}{suffix}")
    extra = len(entries) - LIST_DIR_CAP
    if extra > 0:
        lines.append(f"... ({extra} more entries not shown)")
    if not lines:
        return "(empty directory)"
    return "\n".join(lines)


def tool_get_cwd(arguments: Dict[str, Any], **_: Any) -> str:
    return str(Path.cwd())


def tool_hostname(arguments: Dict[str, Any], **_: Any) -> str:
    return socket.gethostname()


def tool_write_file(arguments: Dict[str, Any], allow_write: bool = False, **_: Any) -> str:
    if not allow_write:
        raise ToolError(
            "write_file is disabled. Restart the Mac agent with --allow-write to enable it."
        )
    path = _require_absolute(_expand_path(arguments.get("path", "")))
    if "content" not in arguments:
        raise ToolError("content is required")
    content = arguments.get("content")
    if not isinstance(content, str):
        content = str(content)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ToolError(f"cannot write {path}: {exc}") from exc
    return f"wrote {len(content.encode('utf-8'))} bytes to {path}"


def tool_run_command(arguments: Dict[str, Any], allow_shell: bool = False, **_: Any) -> str:
    if not allow_shell:
        raise ToolError(
            "run_command is disabled. Restart the Mac agent with --allow-shell to enable it."
        )
    command = arguments.get("command")
    if not command or not str(command).strip():
        raise ToolError("command is required")
    cwd_raw = arguments.get("cwd")
    cwd = str(_expand_path(cwd_raw)) if cwd_raw else None
    try:
        result = subprocess.run(
            str(command),
            shell=True,
            capture_output=True,
            text=True,
            timeout=RUN_COMMAND_TIMEOUT_SECONDS,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(
            f"command timed out after {RUN_COMMAND_TIMEOUT_SECONDS}s: {command}"
        ) from exc
    except OSError as exc:
        raise ToolError(f"failed to run command: {exc}") from exc

    parts = [
        f"exit_code: {result.returncode}",
    ]
    stdout = (result.stdout or "").rstrip()
    stderr = (result.stderr or "").rstrip()
    if stdout:
        parts.append("stdout:\n" + stdout)
    if stderr:
        parts.append("stderr:\n" + stderr)
    if not stdout and not stderr:
        parts.append("(no output)")
    text = "\n".join(parts)
    if len(text) > READ_FILE_CAP_BYTES:
        return text[:READ_FILE_CAP_BYTES] + "\n\n[truncated]"
    return text


TOOL_HANDLERS: Dict[str, Callable[..., str]] = {
    "read_file": tool_read_file,
    "list_directory": tool_list_directory,
    "get_cwd": tool_get_cwd,
    "hostname": tool_hostname,
    "write_file": tool_write_file,
    "run_command": tool_run_command,
}


def openai_tool_definitions(allow_write: bool = False, allow_shell: bool = False) -> List[Dict[str, Any]]:
    """OpenAI-style tool schemas advertised to models and to the iPhone."""
    tools: List[Dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the text contents of a file on the Mac.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute path, or a path starting with ~",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "List files and subdirectories on the Mac.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute path, or a path starting with ~",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_cwd",
                "description": "Return the Mac agent's current working directory.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "hostname",
                "description": "Return the Mac hostname.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]
    if allow_write:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write text to a file on the Mac, creating parent directories.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Absolute destination path"},
                            "content": {"type": "string", "description": "Full file contents"},
                        },
                        "required": ["path", "content"],
                    },
                },
            }
        )
    if allow_shell:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Run a shell command on the Mac and return stdout/stderr.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Shell command to run"},
                            "cwd": {
                                "type": "string",
                                "description": "Optional working directory",
                            },
                        },
                        "required": ["command"],
                    },
                },
            }
        )
    return tools


def tool_system_prompt(allow_write: bool = False, allow_shell: bool = False) -> str:
    """Instructions injected so GGUF models without native tool-calling still work."""
    names = ["read_file", "list_directory", "get_cwd", "hostname"]
    if allow_write:
        names.append("write_file")
    if allow_shell:
        names.append("run_command")
    catalog = "\n".join(f"- {item}" for item in names)
    return (
        "You can use tools on the paired Mac. When you need a tool, output EXACTLY "
        "this block (and you may include a short preface before it):\n\n"
        "<tool_call>\n"
        '{"name": "TOOL_NAME", "arguments": {}}\n'
        "</tool_call>\n\n"
        "Available tools:\n"
        f"{catalog}\n\n"
        "read_file arguments: {\"path\": \"/absolute/or/~/path\"}\n"
        "list_directory arguments: {\"path\": \"/absolute/or/~/path\"}\n"
        "get_cwd arguments: {}\n"
        "hostname arguments: {}\n"
        + ('write_file arguments: {"path": "/absolute/path", "content": "..."}\n' if allow_write else "")
        + ('run_command arguments: {"command": "ls -la", "cwd": "/optional"}\n' if allow_shell else "")
        + "\nIf you do not need a tool, answer the user normally. After a tool result arrives, continue."
    )


class ToolExecutor:
    def __init__(self, allow_write: bool = False, allow_shell: bool = False):
        self.allow_write = allow_write
        self.allow_shell = allow_shell

    def available_names(self) -> List[str]:
        names = ["read_file", "list_directory", "get_cwd", "hostname"]
        if self.allow_write:
            names.append("write_file")
        if self.allow_shell:
            names.append("run_command")
        return names

    def definitions(self) -> List[Dict[str, Any]]:
        return openai_tool_definitions(self.allow_write, self.allow_shell)

    def system_prompt(self) -> str:
        return tool_system_prompt(self.allow_write, self.allow_shell)

    def execute(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = arguments or {}
        if not isinstance(args, dict):
            return {
                "ok": False,
                "name": name,
                "content": "",
                "error": "arguments must be an object",
            }
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return {
                "ok": False,
                "name": name,
                "content": "",
                "error": f"unknown tool: {name}",
            }
        try:
            content = handler(args, allow_write=self.allow_write, allow_shell=self.allow_shell)
            return {"ok": True, "name": name, "content": content, "error": None}
        except ToolError as exc:
            return {"ok": False, "name": name, "content": "", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — surface unexpected failures to the model
            return {"ok": False, "name": name, "content": "", "error": f"tool crashed: {exc}"}
