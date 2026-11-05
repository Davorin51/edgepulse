"""Alert snapshot behavior and API access control."""

from fastapi.testclient import TestClient

from edgepulse.alerts import fleet_alerts
from edgepulse.domain import Sample
from edgepulse.server import create_app


def device(state="healthy", temperature=None, cpu=20, memory=30):
    return {
        "device_id": "node1",
        "name": "Node",
        "mode": "measured",
        "last_seen": 100,
        "state": state,
        "temperature": temperature,
        "cpu": cpu,
        "memory": memory,
    }


def test_alert_rules_and_offline_priority():
    assert fleet_alerts([device()]) == []
    alerts = fleet_alerts([device(temperature=80, cpu=90, memory=95)])
    assert [a["kind"] for a in alerts] == ["temperature", "cpu", "memory"]
    assert [a["severity"] for a in alerts] == ["critical", "warning", "warning"]
    assert [a["kind"] for a in fleet_alerts([device(state="offline", temperature=99, cpu=99)])] == [
        "offline"
    ]
    assert fleet_alerts([device(temperature=None, cpu=89.9, memory=89.9)]) == []


def test_alerts_endpoint_and_auth(tmp_path, monkeypatch):
    token = "read-access-token-at-least-24-characters"
    monkeypatch.setenv("EDGEPULSE_READ_TOKEN", token)
    app = create_app(database=tmp_path / "db.sqlite", demo=False, clock=lambda: 101)
    app.state.store.put(
        Sample(
            device_id="node1",
            name="Node",
            platform="Linux",
            mode="measured",
            cpu=95,
            memory=20,
            temperature=None,
            uptime=1,
            sequence=1,
        ),
        100,
    )
    with TestClient(app) as client:
        assert client.get("/api/alerts").status_code == 401
        r = client.get("/api/alerts", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["type"] == "snapshot"
        assert r.json()["count"] == 1
        assert r.json()["alerts"][0]["kind"] == "cpu"
