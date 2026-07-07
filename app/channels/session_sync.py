"""
Session Sync — SQLite-backed cross-channel session state.

Implements the Hermes pattern: sessions keyed by WORKER, not by CHANNEL.
A worker who switches from app to WhatsApp keeps their full context.

SQLite for zero-dependency, embedded storage that works on-device
and on the backend server.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.channels.adapters.base import ChannelType

logger = structlog.get_logger(__name__)

# Default path — can be overridden for on-device vs server
DEFAULT_DB_PATH = "angavu_sessions.db"


@dataclass
class Session:
    """A cross-channel session bound to a worker."""

    session_id: str
    worker_id: str
    created_at: str
    updated_at: str
    last_channel: str
    context: Dict[str, Any] = field(default_factory=dict)
    interaction_count: int = 0


@dataclass
class Interaction:
    """A single interaction record within a session."""

    interaction_id: str
    session_id: str
    worker_id: str
    channel: str
    user_message: str
    agent_response: str
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class SessionSync:
    """
    SQLite-backed session management with cross-channel continuity.

    Sessions are keyed by worker_id, NOT by channel. This means:
    - Same worker on app and WhatsApp shares one session
    - Conversation history carries across channel switches
    - Context (topic, variables) persists across channels
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._active_sessions: Dict[str, Session] = {}

    def initialize(self) -> None:
        """Create tables and indexes if they don't exist."""
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA cache_size=-8192")  # 8MB cache

        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_channel TEXT NOT NULL,
                context TEXT DEFAULT '{}',
                interaction_count INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_worker
                ON sessions(worker_id);

            CREATE TABLE IF NOT EXISTS interactions (
                interaction_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                user_message TEXT,
                agent_response TEXT,
                timestamp TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE INDEX IF NOT EXISTS idx_interactions_session
                ON interactions(session_id);
            CREATE INDEX IF NOT EXISTS idx_interactions_worker
                ON interactions(worker_id);
            CREATE INDEX IF NOT EXISTS idx_interactions_timestamp
                ON interactions(timestamp);

            CREATE TABLE IF NOT EXISTS worker_channel_map (
                worker_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                channel_user_id TEXT NOT NULL,
                linked_at TEXT NOT NULL,
                PRIMARY KEY (channel, channel_user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_wcm_worker
                ON worker_channel_map(worker_id);
            """
        )
        self._conn.commit()
        logger.info("session_sync_initialized", db_path=self._db_path)

    async def get_or_create_session(
        self,
        worker_id: str,
        channel: ChannelType,
    ) -> Session:
        """
        Get existing session for worker or create a new one.
        Same session regardless of which channel is used.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Check in-memory cache first
        if worker_id in self._active_sessions:
            session = self._active_sessions[worker_id]
            session.last_channel = channel.value
            session.updated_at = now
            self._update_session_db(session)
            return session

        # Check database
        cursor = self._conn.execute(
            "SELECT session_id, worker_id, created_at, updated_at, "
            "last_channel, context, interaction_count "
            "FROM sessions WHERE worker_id = ? ORDER BY updated_at DESC LIMIT 1",
            (worker_id,),
        )
        row = cursor.fetchone()

        if row:
            session = Session(
                session_id=row[0],
                worker_id=row[1],
                created_at=row[2],
                updated_at=now,
                last_channel=channel.value,
                context=json.loads(row[5]) if row[5] else {},
                interaction_count=row[6],
            )
            self._update_session_db(session)
        else:
            session = Session(
                session_id=str(uuid.uuid4()),
                worker_id=worker_id,
                created_at=now,
                updated_at=now,
                last_channel=channel.value,
                context={},
                interaction_count=0,
            )
            self._conn.execute(
                "INSERT INTO sessions "
                "(session_id, worker_id, created_at, updated_at, "
                "last_channel, context, interaction_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session.session_id,
                    session.worker_id,
                    session.created_at,
                    session.updated_at,
                    session.last_channel,
                    json.dumps(session.context),
                    session.interaction_count,
                ),
            )
            self._conn.commit()
            logger.info(
                "session_created",
                worker_id=worker_id,
                session_id=session.session_id,
                channel=channel.value,
            )

        self._active_sessions[worker_id] = session
        return session

    async def get_last_channel(
        self, worker_id: str
    ) -> Optional[ChannelType]:
        """Get the last channel a worker used."""
        if worker_id in self._active_sessions:
            ch = self._active_sessions[worker_id].last_channel
            try:
                return ChannelType(ch)
            except ValueError:
                return None

        cursor = self._conn.execute(
            "SELECT last_channel FROM sessions "
            "WHERE worker_id = ? ORDER BY updated_at DESC LIMIT 1",
            (worker_id,),
        )
        row = cursor.fetchone()
        if row:
            try:
                return ChannelType(row[0])
            except ValueError:
                return None
        return None

    async def get_preferred_channel(
        self, worker_id: str
    ) -> ChannelType:
        """
        Get the worker's most-used channel for proactive messaging.
        Falls back to APP_TEXT if no history.
        """
        cursor = self._conn.execute(
            "SELECT channel, COUNT(*) as cnt FROM interactions "
            "WHERE worker_id = ? GROUP BY channel ORDER BY cnt DESC LIMIT 1",
            (worker_id,),
        )
        row = cursor.fetchone()
        if row:
            try:
                return ChannelType(row[0])
            except ValueError:
                pass
        return ChannelType.APP_TEXT

    async def record_interaction(
        self,
        worker_id: str,
        session_id: str,
        channel: ChannelType,
        user_message: str,
        agent_response: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a complete interaction (user message + agent response)."""
        now = datetime.now(timezone.utc).isoformat()
        interaction_id = str(uuid.uuid4())

        self._conn.execute(
            "INSERT INTO interactions "
            "(interaction_id, session_id, worker_id, channel, "
            "user_message, agent_response, timestamp, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                interaction_id,
                session_id,
                worker_id,
                channel.value,
                user_message,
                agent_response,
                now,
                json.dumps(metadata or {}),
            ),
        )

        # Update session interaction count
        self._conn.execute(
            "UPDATE sessions SET interaction_count = interaction_count + 1, "
            "updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        self._conn.commit()

        # Update cache
        if worker_id in self._active_sessions:
            self._active_sessions[worker_id].interaction_count += 1

    async def get_recent_history(
        self,
        worker_id: str,
        limit: int = 10,
    ) -> List[Dict[str, str]]:
        """Get recent interaction history for context."""
        cursor = self._conn.execute(
            "SELECT channel, user_message, agent_response, timestamp "
            "FROM interactions WHERE worker_id = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (worker_id, limit),
        )
        history = []
        for row in cursor.fetchall():
            history.append(
                {
                    "channel": row[0],
                    "user_message": row[1],
                    "agent_response": row[2],
                    "timestamp": row[3],
                }
            )
        return list(reversed(history))  # Chronological order

    async def get_session_context(
        self, worker_id: str
    ) -> Dict[str, Any]:
        """Get the current session context for a worker."""
        if worker_id in self._active_sessions:
            return dict(self._active_sessions[worker_id].context)

        cursor = self._conn.execute(
            "SELECT context FROM sessions "
            "WHERE worker_id = ? ORDER BY updated_at DESC LIMIT 1",
            (worker_id,),
        )
        row = cursor.fetchone()
        if row and row[0]:
            return json.loads(row[0])
        return {}

    async def update_session_context(
        self,
        worker_id: str,
        context_update: Dict[str, Any],
    ) -> None:
        """Merge context updates into the session."""
        if worker_id in self._active_sessions:
            session = self._active_sessions[worker_id]
            session.context.update(context_update)
            self._conn.execute(
                "UPDATE sessions SET context = ? WHERE session_id = ?",
                (json.dumps(session.context), session.session_id),
            )
            self._conn.commit()

    @property
    def active_session_count(self) -> int:
        """Number of sessions cached in memory."""
        return len(self._active_sessions)

    def _update_session_db(self, session: Session) -> None:
        """Update session record in database."""
        self._conn.execute(
            "UPDATE sessions SET updated_at = ?, last_channel = ?, "
            "context = ?, interaction_count = ? WHERE session_id = ?",
            (
                session.updated_at,
                session.last_channel,
                json.dumps(session.context),
                session.interaction_count,
                session.session_id,
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
