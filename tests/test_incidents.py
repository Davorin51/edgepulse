"""Incident lifecycle persistence, filtering and API authorization."""

from fastapi.testclient import TestClient

from edgepulse.domain import Sample
from edgepulse.incidents import IncidentTracker
from edgepulse.server import create_app


def device(cpu=95, state="busy"):
    return {
        "device_id": "node1",
        "name": "Node",
        "mode": "measured",
        "last_seen": 100,
        "state": state,
        "cpu": cpu,
        "memory": 10,
        "temperature": None,
    }


def test_lifecycle_and_restart(tmp_path):
    db = tmp_path / "incidents.sqlite"
    tracker = IncidentTracker(db)
    tracker.reconcile([device()], 101)
    tracker.reconcile([device()], 102)
    assert len(tracker.list()) == 1
    assert tracker.list()[0]["opened"] == 101
    tracker.reconcile([device(cpu=20, state="healthy")], 103)
    assert tracker.list(status="open") == []
    assert tracker.list(status="resolved")[0]["resolved"] == 103
    tracker.reconcile([device()], 104)
    assert len(IncidentTracker(db).list()) == 2
    assert len(tracker.list(status="open")) == 1


def test_incident_api_auth_and_filters(tmp_path, monkeypatch):
    token = "read-token-longer-than-twenty-four-characters"
    monkeypatch.setenv("EDGEPULSE_READ_TOKEN", token)
    app = create_app(database=tmp_path / "api.sqlite", demo=False, clock=lambda: 101)
    app.state.store.put(
        Sample(
            device_id="node1",
            name="Node",
            platform="Linux",
            mode="measured",
            cpu=95,
            memory=10,
            uptime=1,
            sequence=1,
        ),
        100,
    )
    with TestClient(app) as client:
        assert client.get("/api/incidents").status_code == 401
        headers = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/incidents?status=open", headers=headers)
        assert r.status_code == 200
        assert r.json()["count"] == 1
        assert r.json()["incidents"][0]["kind"] == "cpu"
        assert client.get("/api/incidents?limit=201", headers=headers).status_code == 422
        assert client.get("/api/incidents?status=invalid", headers=headers).status_code == 422
