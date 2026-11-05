"""Incident Management v2: schema migration, API security and dashboard contract."""

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from edgepulse.domain import Sample
from edgepulse.incidents import IncidentTracker
from edgepulse.server import create_app


def test_legacy_schema_migrates_and_acknowledgement_survives_restart(tmp_path):
    db = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db) as connection:
        connection.execute(
            "CREATE TABLE incidents (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "device_id TEXT NOT NULL, kind TEXT NOT NULL, severity TEXT NOT NULL, "
            "payload TEXT NOT NULL, opened REAL NOT NULL, resolved REAL)"
        )
        connection.execute(
            "INSERT INTO incidents(device_id,kind,severity,payload,opened) "
            "VALUES('pi','cpu','warning','{}',100)"
        )
    tracker = IncidentTracker(db)
    assert tracker.list()[0]["acknowledged"] is None
    assert tracker.acknowledge(1, 105)
    assert tracker.acknowledge(1, 120)
    assert IncidentTracker(db).list()[0]["acknowledged"] == 105
    assert not tracker.acknowledge(999, 130)


def test_acknowledge_requires_auth_and_preserves_incident_status(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGEPULSE_READ_TOKEN", "a-strong-read-token-123456789")
    app = create_app(database=tmp_path / "api.sqlite", demo=False, clock=lambda: 150)
    app.state.store.put(
        Sample(
            device_id="pi", name="Pi", platform="Linux", mode="measured",
            cpu=95,
            memory=20,
            uptime=1,
            sequence=1,
        ),
        150,
    )
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer a-strong-read-token-123456789"}
        records = client.get("/api/incidents", headers=headers).json()["incidents"]
        assert len(records) == 1
        ident = records[0]["id"]
        path = f"/api/incidents/{ident}/acknowledge"
        assert client.post(path).status_code == 401
        assert (
            client.post(path, headers={"Origin": "https://evil.example", **headers}).status_code
            == 403
        )
        assert client.post("/api/incidents/999/acknowledge", headers=headers).status_code == 404
        assert client.post("/api/incidents/0/acknowledge", headers=headers).status_code == 422
        assert client.post(path, headers=headers).json() == {
            "id": ident,
            "acknowledged": True,
        }
        assert client.post(path, headers=headers).status_code == 200
        updated = client.get("/api/incidents", headers=headers).json()["incidents"][0]
        assert updated["acknowledged"] == 150
        assert updated["status"] == "open"


def test_acknowledge_disabled_without_write_token(tmp_path, monkeypatch):
    monkeypatch.delenv("EDGEPULSE_READ_TOKEN", raising=False)
    app = create_app(database=tmp_path / "no-token.sqlite", demo=False)
    with TestClient(app) as client:
        assert client.post("/api/incidents/1/acknowledge").status_code == 503


def test_dashboard_incident_contract():
    dist = Path(__file__).resolve().parents[1] / "dist"
    html = (dist / "index.html").read_text()
    js = (dist / "app.js").read_text()
    for element in ("incident-list", "incident-status", "incident-device", "incident-token"):
        assert f'id="{element}"' in html
    assert "pollIncidents" in js
    assert "data-ack" in js
    assert "/acknowledge" in js
