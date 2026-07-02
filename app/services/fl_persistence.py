import json
import sqlite3
import time
from pathlib import Path


class FLPersistence:
    """SQLite persistence for federated learning state."""

    def __init__(self, db_path: str = "data/fl_state.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS fl_devices (
                device_id TEXT PRIMARY KEY,
                dialect TEXT,
                last_seen REAL,
                update_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS fl_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                dialect TEXT,
                calibration_params TEXT,
                phoneme_stats TEXT,
                timestamp REAL,
                processed BOOLEAN DEFAULT FALSE
            );
            CREATE TABLE IF NOT EXISTS fl_models (
                dialect TEXT,
                version TEXT,
                calibration_params TEXT,
                phoneme_stats TEXT,
                created_at REAL,
                PRIMARY KEY (dialect, version)
            );
        """)

    def save_update(self, device_id, dialect, params, phonemes, timestamp):
        """Persist incoming update."""
        self.conn.execute(
            "INSERT INTO fl_updates (device_id, dialect, calibration_params, phoneme_stats, timestamp) VALUES (?,?,?,?,?)",
            (device_id, dialect, json.dumps(params), json.dumps(phonemes), timestamp),
        )
        self.conn.commit()

    def get_pending_updates(self, dialect):
        """Get unprocessed updates."""
        cur = self.conn.execute(
            "SELECT device_id, calibration_params, phoneme_stats, timestamp FROM fl_updates WHERE dialect=? AND processed=FALSE",
            (dialect,),
        )
        return cur.fetchall()

    def mark_processed(self, dialect):
        """Mark all pending updates for a dialect as processed."""
        self.conn.execute(
            "UPDATE fl_updates SET processed=TRUE WHERE dialect=? AND processed=FALSE",
            (dialect,),
        )
        self.conn.commit()

    def save_global_model(self, dialect, version, params, phonemes):
        """Save aggregated model."""
        self.conn.execute(
            "INSERT OR REPLACE INTO fl_models (dialect, version, calibration_params, phoneme_stats, created_at) VALUES (?,?,?,?,?)",
            (dialect, version, json.dumps(params), json.dumps(phonemes), time.time()),
        )
        self.conn.commit()

    def get_latest_model(self, dialect):
        """Get latest aggregated model."""
        cur = self.conn.execute(
            "SELECT version, calibration_params, phoneme_stats FROM fl_models WHERE dialect=? ORDER BY created_at DESC LIMIT 1",
            (dialect,),
        )
        return cur.fetchone()

    def get_device_count(self):
        """Get count of unique devices."""
        cur = self.conn.execute("SELECT COUNT(DISTINCT device_id) FROM fl_updates")
        return cur.fetchone()[0]

    def get_total_update_count(self):
        """Get total number of updates."""
        cur = self.conn.execute("SELECT COUNT(*) FROM fl_updates")
        return cur.fetchone()[0]

    def save_device_info(self, device_id, dialect):
        """Save or update device info."""
        self.conn.execute(
            "INSERT OR REPLACE INTO fl_devices (device_id, dialect, last_seen, update_count) VALUES (?,?,?,COALESCE((SELECT update_count FROM fl_devices WHERE device_id=?),0)+1)",
            (device_id, dialect, time.time(), device_id),
        )
        self.conn.commit()

    def close(self):
        """Close the database connection."""
        self.conn.close()
