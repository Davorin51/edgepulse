import io
import json
import sys

import pytest

from edgepulse.agent import main


def test_agent_upload_loop_uses_token_and_measured_schema(monkeypatch):
    monkeypatch.setenv("EDGEPULSE_TOKEN", "a-token-of-at-least-24-characters")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "edgepulse-agent",
            "--id",
            "device-one",
            "--name",
            "Test Linux",
            "--samples",
            "2",
            "--interval",
            ".2",
        ],
    )
    monkeypatch.setattr("edgepulse.agent.cpu_counters", lambda _: (0, 0))
    monkeypatch.setattr(
        "edgepulse.agent.read_metrics",
        lambda _: ((100, 70), {"cpu": 30, "memory": 40, "temperature": None, "uptime": 100}),
    )
    monkeypatch.setattr("edgepulse.agent.time.sleep", lambda _: None)
    requests = []

    class Response(io.BytesIO):
        status = 202

    def send(request, timeout):
        requests.append(request)
        return Response()

    monkeypatch.setattr("edgepulse.agent.urllib.request.urlopen", send)
    main()
    assert len(requests) == 2
    assert json.loads(requests[0].data)["mode"] == "measured"
    assert json.loads(requests[1].data)["sequence"] == 1
    assert requests[0].get_header("Authorization").startswith("Bearer ")


@pytest.mark.parametrize("interval", ["0", "nan", "inf"])
def test_agent_bad_configuration(monkeypatch, interval):
    monkeypatch.setenv("EDGEPULSE_TOKEN", "a-token-of-at-least-24-characters")
    monkeypatch.setattr(sys, "argv", ["agent", "--id", "x", "--name", "x", "--interval", interval])
    with pytest.raises(SystemExit):
        main()
