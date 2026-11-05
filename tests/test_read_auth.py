"""Tests for optional fleet read authentication."""
import pytest
from fastapi.testclient import TestClient
from edgepulse.server import create_app


def test_short_read_token_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGEPULSE_READ_TOKEN", "short")
    with pytest.raises(ValueError, match="at least 24"):
        create_app(database=tmp_path / "db.sqlite", demo=False)


def test_read_token_protects_fleet(tmp_path, monkeypatch):
    token = "long-test-read-token-1234567890"
    monkeypatch.setenv("EDGEPULSE_READ_TOKEN", token)
    with TestClient(create_app(database=tmp_path / "db.sqlite", demo=False)) as client:
        assert client.get("/api/fleet").status_code == 401
        assert client.get("/api/fleet", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/api/fleet", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert client.get("/api/status").json()["read_auth_enabled"] is True


def test_read_token_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("EDGEPULSE_READ_TOKEN", raising=False)
    with TestClient(create_app(database=tmp_path / "db.sqlite", demo=False)) as client:
        assert client.get("/api/fleet").status_code == 200
