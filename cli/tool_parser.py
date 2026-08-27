"""
Parse <tool_call> blocks out of on-device GGUF text.

Local llama.cpp does not emit OpenAI tool_calls, so the Mac agent and the
iPhone chat loop share this XML-ish protocol.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple


TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def parse_tool_calls(text: str) -> List[Dict[str, Any]]:
    """Return [{name, arguments}, ...] for every well-formed <tool_call> block."""
    if not text:
        return []
    calls: List[Dict[str, Any]] = []
    for match in TOOL_CALL_RE.finditer(text):
        raw = match.group(1).strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        name = obj.get("name")
        if not name or not isinstance(name, str):
            continue
        arguments = obj.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"value": arguments}
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append({"name": name.strip(), "arguments": arguments})
    return calls


def strip_tool_calls(text: str) -> str:
    """Remove <tool_call> blocks, collapsing leftover blank lines."""
    if not text:
        return ""
    stripped = TOOL_CALL_RE.sub("", text)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    return stripped.strip()


def split_text_and_tools(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    return strip_tool_calls(text), parse_tool_calls(text)
