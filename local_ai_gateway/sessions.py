"""
Thread-safe session manager with TTL expiration, context window management, and memory limits.
"""
import time
import uuid
import threading
from typing import Dict, List, Optional, Tuple, Any
from .models import Session, ChatMessage
from .config import config

def estimate_tokens(text: Optional[str]) -> int:
    """Estimates token count for English text (~4 chars per token average)."""
    if not text:
        return 0
    return max(1, len(text) // 4)

def estimate_messages_tokens(messages: List[ChatMessage], system: Optional[str] = None) -> int:
    """Estimates total token usage for a list of ChatMessages."""
    total = estimate_tokens(system) if system else 0
    for m in messages:
        total += estimate_tokens(m.content) + 4 # 4 tokens per message formatting overhead
        if m.images:
            total += 256 * len(m.images) # Approximate tokens per vision tile
    return total

class SessionManager:
    """Thread-safe in-memory session manager with TTL expiration and context trimming."""
    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.RLock()

    def _cleanup_expired(self) -> None:
        """Removes sessions that have exceeded SESSION_TTL."""
        now = time.time()
        ttl = config.session_ttl_seconds
        expired_ids = [
            sid for sid, sess in self._sessions.items()
            if (now - sess.updated_at) > ttl
        ]
        for sid in expired_ids:
            del self._sessions[sid]

    def create_session(
        self,
        model: Optional[str] = None,
        title: Optional[str] = None,
        system_prompt: Optional[str] = None,
        initial_messages: Optional[List[ChatMessage]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Session:
        with self._lock:
            self._cleanup_expired()
            session_id = str(uuid.uuid4())
            chosen_model = model or config.default_model
            session_title = title or f"Chat {time.strftime('%b %d %H:%M')}"
            session = Session(
                id=session_id,
                title=session_title,
                model=chosen_model,
                messages=list(initial_messages or []),
                system_prompt=system_prompt,
                created_at=time.time(),
                updated_at=time.time(),
                metadata=metadata or {}
            )
            self._sessions[session_id] = session
            return session

    def get_session(self, session_id: str) -> Optional[Session]:
        with self._lock:
            self._cleanup_expired()
            sess = self._sessions.get(session_id)
            if sess:
                sess.updated_at = time.time()
            return sess

    def list_sessions(self) -> List[Session]:
        with self._lock:
            self._cleanup_expired()
            return sorted(self._sessions.values(), key=lambda s: s.updated_at, reverse=True)

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    def add_message(self, session_id: str, message: ChatMessage) -> Optional[Session]:
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return None
            session.messages.append(message)
            # Bound session length to prevent memory leakage
            if len(session.messages) > config.max_session_messages:
                session.messages = session.messages[-config.max_session_messages:]
            session.updated_at = time.time()
            return session

    def check_and_manage_context(
        self,
        messages: List[ChatMessage],
        max_context_tokens: int = 4096,
        system_prompt: Optional[str] = None,
        strategy: Optional[str] = None
    ) -> Tuple[List[ChatMessage], Dict[str, Any]]:
        """
        Calculates context consumption. Trims or warns according to strategy.
        Returns: (managed_messages, telemetry_dict)
        """
        chosen_strategy = strategy or config.context_limit_strategy
        total_tokens = estimate_messages_tokens(messages, system_prompt)
        limit_threshold = int(max_context_tokens * 0.85) # 85% safety margin
        
        telemetry = {
            "estimated_tokens": total_tokens,
            "max_context_tokens": max_context_tokens,
            "context_usage_percent": round((total_tokens / max(1, max_context_tokens)) * 100, 1),
            "trimmed_messages_count": 0,
            "warning": None
        }

        if total_tokens <= limit_threshold:
            return messages, telemetry

        if chosen_strategy == "warn":
            telemetry["warning"] = f"Approaching context limit: {total_tokens}/{max_context_tokens} tokens ({telemetry['context_usage_percent']}%)"
            return messages, telemetry

        if chosen_strategy == "trim_oldest":
            trimmed = list(messages)
            trimmed_count = 0
            while len(trimmed) > 2 and estimate_messages_tokens(trimmed, system_prompt) > limit_threshold:
                trimmed.pop(0)
                trimmed_count += 1

            new_tokens = estimate_messages_tokens(trimmed, system_prompt)
            telemetry["trimmed_messages_count"] = trimmed_count
            telemetry["estimated_tokens"] = new_tokens
            telemetry["context_usage_percent"] = round((new_tokens / max(1, max_context_tokens)) * 100, 1)
            telemetry["warning"] = f"Trimmed {trimmed_count} older message(s) to fit {max_context_tokens} token context window."
            return trimmed, telemetry

        return messages, telemetry

    def count(self) -> int:
        with self._lock:
            self._cleanup_expired()
            return len(self._sessions)

session_manager = SessionManager()
