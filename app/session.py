"""Conversation and session state.

History is trimmed because every past turn is re-sent on the next request, so
an untrimmed history grows the prompt, the latency and the bill forever.

In-memory is right for a single-process demo. Swap the dict for Redis to scale
horizontally; the interface would not change.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from app.agents.base import PendingAction
from app.logging_setup import get_logger

log = get_logger(__name__)

MAX_HISTORY_TURNS = 8       # about 4 exchanges - enough for pronouns
SESSION_TTL_SECONDS = 3600


@dataclass
class Session:
    id: str
    history: list[dict] = field(default_factory=list)
    pending_action: PendingAction | None = None
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def add_user(self, text: str) -> None:
        self._append("user", text)

    def add_assistant(self, text: str) -> None:
        self._append("assistant", text)

    def _append(self, role: str, text: str) -> None:
        self.history.append({"role": role, "content": text})
        self.history = self.history[-MAX_HISTORY_TURNS:]
        self.last_seen = time.time()

    def recent_history(self) -> list[dict]:
        return list(self.history)

    @property
    def has_pending_action(self) -> bool:
        return self.pending_action is not None

    def clear_pending(self) -> None:
        self.pending_action = None


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str | None) -> Session:
        self._evict_expired()

        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            session.last_seen = time.time()
            return session

        new_id = session_id or f"sess-{uuid.uuid4().hex[:12]}"
        self._sessions[new_id] = Session(id=new_id)
        log.info("New session %s", new_id)
        return self._sessions[new_id]

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def count(self) -> int:
        return len(self._sessions)

    def _evict_expired(self) -> None:
        cutoff = time.time() - SESSION_TTL_SECONDS
        stale = [sid for sid, s in self._sessions.items() if s.last_seen < cutoff]
        for sid in stale:
            del self._sessions[sid]
        if stale:
            log.info("Evicted %d idle session(s)", len(stale))


session_store = SessionStore()
