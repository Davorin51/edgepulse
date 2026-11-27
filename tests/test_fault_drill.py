import json

from edgepulse import drill


def test_drill_runs_full_http_scenario_in_isolation(tmp_path, monkeypatch):
    output = tmp_path / "drill.json"
    external_database = tmp_path / "external.sqlite3"
    monkeypatch.setenv("EDGEPULSE_DB", str(external_database))
    monkeypatch.setenv("EDGEPULSE_READ_TOKEN", "invalid-external-token")
    monkeypatch.setenv("EDGEPULSE_DEMO", "0")

    assert drill.main(["--output", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] and report["mode"] == "simulated"
    assert not external_database.exists()
    baseline, hot, cooldown, offline, recovery = report["stages"]
    assert [stage["state"] for stage in report["stages"]] == [
        "healthy",
        "hot",
        "healthy",
        "offline",
        "healthy",
    ]
    assert hot["temperature_c"] == 88
    assert baseline["last_seen"] < hot["last_seen"] < cooldown["last_seen"]
    assert offline["last_seen"] < recovery["last_seen"]
    for opened, resolved, kind in (
        (hot, cooldown, "temperature"),
        (offline, recovery, "offline"),
    ):
        assert opened["incident"]["kind"] == resolved["incident"]["kind"] == kind
        assert opened["incident"]["id"] == resolved["incident"]["id"]
        assert opened["incident"]["status"] == "open"
        assert resolved["incident"]["status"] == "resolved"


def test_drill_timeout_reports_failure(tmp_path, monkeypatch):
    output = tmp_path / "drill.json"
    monkeypatch.setattr(drill, "STAGE_TIMEOUT", 0)

    assert drill.main(["--output", str(output)]) == 1

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert report["stages"] == []
    assert report["error"] == "baseline timed out waiting for healthy state"
