"""Background incident reconciliation tests."""
import asyncio
from fastapi.testclient import TestClient
from edgepulse.domain import Sample
from edgepulse.server import create_app


def test_background_worker_opens_and_resolves(tmp_path, monkeypatch):
    monkeypatch.delenv("EDGEPULSE_READ_TOKEN", raising=False)
    now = [100.0]
    app = create_app(database=tmp_path / "worker.sqlite", demo=False, clock=lambda: now[0])
    app.state.store.put(Sample(device_id="node1", name="Node", platform="Linux", mode="measured", cpu=95, memory=10, uptime=1, sequence=1), 100)
    with TestClient(app) as client:
        # Polling worker may take up to 3 seconds; use the API to observe the result.
        import time
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if client.get("/api/incidents?status=open").json()["count"] == 1:
                break
            time.sleep(0.1)
        assert client.get("/api/incidents?status=open").json()["count"] == 1
        assert client.get("/api/incidents").json()["tracking"] == "background_poll"
        now[0] = 120.0
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if client.get("/api/incidents?status=resolved").json()["count"] == 1:
                break
            time.sleep(0.1)
        assert client.get("/api/incidents?status=resolved").json()["count"] == 1
