import json
import sqlite3
from pathlib import Path

from edgepulse.domain import Sample, state


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, payload TEXT NOT NULL, seen REAL NOT NULL, seq INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, device TEXT NOT NULL, payload TEXT NOT NULL, received REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS device_samples ON samples(device,id);
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def put(self, sample: Sample, now: float):
        data = sample.model_dump_json()
        with self.connect() as db:
            # Sequence is local to an agent process; receive-time is the source of liveness.
            existing = db.execute(
                "SELECT payload FROM devices WHERE id=?", (sample.device_id,)
            ).fetchone()
            if existing and json.loads(existing[0])["mode"] != sample.mode:
                raise ValueError("Device ID is already owned by a different telemetry mode")
            db.execute(
                "INSERT INTO devices VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,seen=excluded.seen,seq=excluded.seq",
                (sample.device_id, data, now, sample.sequence),
            )
            db.execute(
                "INSERT INTO samples(device,payload,received) VALUES(?,?,?)",
                (sample.device_id, data, now),
            )
            db.execute(
                "DELETE FROM samples WHERE device=? AND id NOT IN (SELECT id FROM samples WHERE device=? ORDER BY id DESC LIMIT 120)",
                (sample.device_id, sample.device_id),
            )

    def fleet(self, now: float):
        with self.connect() as db:
            rows = db.execute("SELECT id,payload,seen FROM devices ORDER BY id").fetchall()
            result = []
            for ident, payload, seen in rows:
                sample = json.loads(payload)
                points = db.execute(
                    "SELECT payload,received FROM samples WHERE device=? ORDER BY id", (ident,)
                ).fetchall()
                result.append(
                    {
                        **sample,
                        "last_seen": seen,
                        "age": max(0, now - seen),
                        "state": state(sample, now, seen),
                        "history": [{**json.loads(p), "received": t} for p, t in points],
                    }
                )
            return result
