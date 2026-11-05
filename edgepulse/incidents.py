"""SQLite-backed incident lifecycle based on alert snapshots.

Reconciliation runs periodically in the app lifespan. This is a polling-based
prototype, not a guaranteed event capture service.
"""

import json
import sqlite3

from edgepulse.alerts import fleet_alerts


class IncidentTracker:
    def __init__(self, database):
        self.database = str(database)
        with sqlite3.connect(self.database) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                severity TEXT NOT NULL,
                payload TEXT NOT NULL,
                opened REAL NOT NULL,
                resolved REAL,
                acknowledged REAL
            )""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(incidents)")}
            if "acknowledged" not in columns:
                db.execute("ALTER TABLE incidents ADD COLUMN acknowledged REAL")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_open_incident
                ON incidents(device_id, kind) WHERE resolved IS NULL""")

    def reconcile(self, devices, now):
        active = {(a["device_id"], a["kind"]): a for a in fleet_alerts(devices)}
        with sqlite3.connect(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = {
                (row[1], row[2]): row[0]
                for row in db.execute(
                    "SELECT id, device_id, kind FROM incidents WHERE resolved IS NULL"
                )
            }
            for key, ident in existing.items():
                if key not in active:
                    db.execute("UPDATE incidents SET resolved=? WHERE id=?", (now, ident))
            for key, alert in active.items():
                if key not in existing:
                    db.execute(
                        "INSERT INTO incidents(device_id,kind,severity,payload,opened) VALUES(?,?,?,?,?)",
                        (key[0], key[1], alert["severity"], json.dumps(alert), now),
                    )

    def list(self, limit=50, status="all"):
        clause = {
            "all": "",
            "open": "WHERE resolved IS NULL",
            "resolved": "WHERE resolved IS NOT NULL",
        }[status]
        with sqlite3.connect(self.database, timeout=10) as db:
            rows = db.execute(
                f"SELECT id,device_id,kind,severity,payload,opened,resolved,acknowledged FROM incidents {clause} ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": ident,
                "device_id": device,
                "kind": kind,
                "severity": severity,
                "alert": json.loads(payload),
                "opened": opened,
                "resolved": resolved,
                "status": "resolved" if resolved is not None else "open",
                "acknowledged": acknowledged,
            }
            for ident, device, kind, severity, payload, opened, resolved, acknowledged in rows
        ]

    def acknowledge(self, incident_id: int, now: float) -> bool:
        """Mark an incident reviewed without resolving it. Repeated calls are idempotent."""
        with sqlite3.connect(self.database, timeout=10) as db:
            cursor = db.execute(
                "UPDATE incidents SET acknowledged=COALESCE(acknowledged, ?) WHERE id=?",
                (now, incident_id),
            )
            return cursor.rowcount > 0
