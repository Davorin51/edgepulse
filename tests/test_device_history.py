"""Device history endpoint: bounds, ordering and optional read protection."""

from fastapi.testclient import TestClient

from edgepulse.domain import Sample
from edgepulse.server import create_app


def sample(seq):
    return Sample(device_id="pi-real", name="Pi", platform="Linux", mode="measured", cpu=float(seq), memory=30, uptime=seq, sequence=seq)


def test_history_bounds_and_order(tmp_path, monkeypatch):
    monkeypatch.delenv("EDGEPULSE_READ_TOKEN", raising=False)
    app = create_app(database=tmp_path / "test.sqlite", demo=False)
    for i in range(5):
        app.state.store.put(sample(i), 1000 + i)
    with TestClient(app) as client:
        r = client.get("/api/devices/pi-real/history?limit=2")
        assert r.status_code == 200
        assert [x["sequence"] for x in r.json()["samples"]] == [3, 4]
        assert [x["received"] for x in r.json()["samples"]] == [1003, 1004]
        assert r.json()["count"] == 2
        assert client.get("/api/devices/unknown/history").status_code == 404
        assert client.get("/api/devices/pi-real/history?limit=121").status_code == 422
        assert client.get("/api/devices/pi-real/history?limit=0").status_code == 422
        assert client.get("/api/devices/bad%20id/history").status_code == 422


def test_history_requires_read_token_when_configured(tmp_path, monkeypatch):
    token = "test-token-with-at-least-24-characters"
    monkeypatch.setenv("EDGEPULSE_READ_TOKEN", token)
    app = create_app(database=tmp_path / "test.sqlite", demo=False)
    app.state.store.put(sample(1), 1000)
    with TestClient(app) as client:
        assert client.get("/api/devices/pi-real/history").status_code == 401
        r = client.get("/api/devices/pi-real/history", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["count"] == 1
