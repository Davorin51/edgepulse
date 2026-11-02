import pytest
from fastapi.testclient import TestClient

from edgepulse.domain import Sample
from edgepulse.server import create_app
from edgepulse.store import Store

TOKEN = "a-test-token-with-at-least-24-characters"


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "data.db", TOKEN, demo=False, clock=lambda: 100)
    with TestClient(app) as c:
        yield c


def payload(**updates):
    return {
        "device_id": "test-device",
        "name": "Test Linux",
        "platform": "Linux",
        "cpu": 12,
        "memory": 45,
        "temperature": None,
        "uptime": 10,
        "sequence": 1,
        **updates,
    }


def test_authenticated_ingestion_and_snapshot(client):
    response = client.post(
        "/api/telemetry", json=payload(), headers={"Authorization": "Bearer " + TOKEN}
    )
    assert response.status_code == 202
    fleet = client.get("/api/fleet").json()
    assert fleet["devices"][0]["mode"] == "measured"
    assert fleet["devices"][0]["history"][0]["cpu"] == 12
    assert fleet["devices"][0]["state"] == "healthy"


@pytest.mark.parametrize("header", ["", "Bearer bad", "Token " + TOKEN])
def test_token_required(client, header):
    assert (
        client.post("/api/telemetry", json=payload(), headers={"Authorization": header}).status_code
        == 401
    )


@pytest.mark.parametrize(
    "update",
    [
        {"cpu": -1},
        {"memory": 101},
        {"device_id": "../escape"},
        {"unknown": "x"},
        {"temperature": 180},
    ],
)
def test_invalid_payload(client, update):
    assert (
        client.post(
            "/api/telemetry", json=payload(**update), headers={"Authorization": "Bearer " + TOKEN}
        ).status_code
        == 422
    )


def test_unconfigured_server_rejects_ingestion(tmp_path):
    with TestClient(create_app(tmp_path / "a.db", token="", demo=False)) as client:
        assert not client.get("/api/status").json()["ingestion_enabled"]
        assert client.post("/api/telemetry", json=payload()).status_code == 503


def test_fake_measured_and_reserved_demo_ids_rejected(client):
    assert (
        client.post(
            "/api/telemetry",
            json=payload(mode="simulated"),
            headers={"Authorization": "Bearer " + TOKEN},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/telemetry",
            json=payload(device_id="pi-lab"),
            headers={"Authorization": "Bearer " + TOKEN},
        ).status_code
        == 409
    )
    assert client.post("/api/demo/test-device/heat").status_code == 404


def test_demo_controls_are_scoped_and_cross_origin_rejected(tmp_path):
    with TestClient(create_app(tmp_path / "demo.db", TOKEN, demo=True)) as c:
        assert c.post("/api/demo/pi-lab/heat").json()["scope"] == "simulator_only"
        assert c.post("/api/demo/pi-lab/shell").status_code == 422
        assert c.post("/api/demo/real-device/heat").status_code == 404
        assert (
            c.post("/api/demo/pi-lab/pause", headers={"Origin": "https://evil.example"}).status_code
            == 403
        )
        assert c.get("/").status_code == 200
        assert c.get("/app.js").status_code == 200
        assert c.get("/style.css").status_code == 200


def test_bounded_history_persists_and_goes_offline(tmp_path):
    path = tmp_path / "s.db"
    s = Store(path)
    for i in range(140):
        s.put(Sample(**payload(sequence=i)), i)
    restored = Store(path).fleet(200)
    assert len(restored[0]["history"]) == 120
    assert restored[0]["state"] == "offline"
    assert restored[0]["sequence"] == 139


def test_mode_cannot_be_reassigned(tmp_path):
    store = Store(tmp_path / "mode.db")
    store.put(Sample(**payload()), 0)
    with pytest.raises(ValueError):
        store.put(Sample(**payload(mode="simulated")), 1)
