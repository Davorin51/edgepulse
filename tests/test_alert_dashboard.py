"""Static dashboard contract for the alert center."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "dist"


def test_alert_center_markup():
    html = (ROOT / "index.html").read_text()
    assert 'id="alert-list"' in html
    assert 'id="alert-count"' in html
    assert 'id="alerts-note"' in html


def test_alert_center_api_and_simulation_paths():
    js = (ROOT / "app.js").read_text()
    assert "fetch('/api/alerts'" in js
    assert "showAlerts(localAlerts()" in js
    assert "alerts unavailable (not zero)" in js
    assert "SIMULATED" in js
