#!/usr/bin/env python3
"""
Session manager for persistent chat history.
Stores and retrieves conversation sessions locally (JSON-based).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict


SESSION_DIR = Path.home() / ".local" / "share" / "bridge-cli" / "sessions"


@dataclass
class Message:
    role: str  # "user", "assistant", "tool"
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Message:
        return cls(**data)


@dataclass
class Session:
    id: str
    created_at: str
    updated_at: str
    model: str
    host: str
    port: int
    messages: List[Message]
    metadata: Dict[str, Any]

    @classmethod
    def create(
        cls,
        session_id: str,
        model: str,
        host: str,
        port: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Session:
        now = datetime.utcnow().isoformat()
        return cls(
            id=session_id,
            created_at=now,
            updated_at=now,
            model=model,
            host=host,
            port=port,
            messages=[],
            metadata=metadata or {},
        )

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = datetime.utcnow().isoformat()

    def save(self) -> Path:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        filepath = SESSION_DIR / f"{self.id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return filepath

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model": self.model,
            "host": self.host,
            "port": self.port,
            "messages": [msg.to_dict() for msg in self.messages],
            "metadata": self.metadata,
        }

    @classmethod
    def load(cls, session_id: str) -> Optional[Session]:
        filepath = SESSION_DIR / f"{session_id}.json"
        if not filepath.exists():
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Convert message dicts to Message objects
            messages = [Message.from_dict(msg) for msg in data.get("messages", [])]
            return cls(
                id=data["id"],
                created_at=data["created_at"],
                updated_at=data["updated_at"],
                model=data["model"],
                host=data["host"],
                port=data["port"],
                messages=messages,
                metadata=data.get("metadata", {}),
            )
        except Exception:
            return None


class SessionManager:
    """Manages session persistence and retrieval."""

    @staticmethod
    def list_sessions() -> List[Dict[str, Any]]:
        """List all saved sessions with metadata."""
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        sessions = []
        for filepath in sorted(SESSION_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append(
                    {
                        "id": data["id"],
                        "created_at": data["created_at"],
                        "updated_at": data["updated_at"],
                        "model": data["model"],
                        "host": data["host"],
                        "port": data["port"],
                        "message_count": len(data.get("messages", [])),
                        "preview": (
                            data["messages"][0]["content"][:50]
                            if data.get("messages")
                            else ""
                        ),
                    }
                )
            except Exception:
                pass
        return sessions

    @staticmethod
    def get_session_summary(session_id: str) -> Optional[Dict[str, Any]]:
        """Get summary of a session without loading full messages."""
        filepath = SESSION_DIR / f"{session_id}.json"
        if not filepath.exists():
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "id": data["id"],
                "created_at": data["created_at"],
                "updated_at": data["updated_at"],
                "model": data["model"],
                "message_count": len(data.get("messages", [])),
            }
        except Exception:
            return None

    @staticmethod
    def export_session(session_id: str, format: str = "json") -> Optional[str]:
        """Export session to JSON or Markdown."""
        session = Session.load(session_id)
        if not session:
            return None

        if format == "json":
            return json.dumps(session.to_dict(), indent=2)
        elif format == "markdown":
            lines = [
                f"# Session: {session.id}",
                f"**Model:** {session.model}",
                f"**Created:** {session.created_at}",
                f"**Updated:** {session.updated_at}",
                "",
                "## Conversation",
                "",
            ]
            for msg in session.messages:
                if msg.role == "user":
                    lines.append(f"**You:**\n\n{msg.content}\n")
                elif msg.role == "assistant":
                    lines.append(f"**Assistant:**\n\n{msg.content}\n")
                elif msg.role == "tool":
                    lines.append(f"**Tool Result:**\n\n```\n{msg.content}\n```\n")
            return "\n".join(lines)
        return None

    @staticmethod
    def delete_session(session_id: str) -> bool:
        """Delete a session."""
        filepath = SESSION_DIR / f"{session_id}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    @staticmethod
    def clear_all_sessions() -> int:
        """Delete all sessions. Returns count deleted."""
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        count = 0
        for filepath in SESSION_DIR.glob("*.json"):
            filepath.unlink()
            count += 1
        return count
