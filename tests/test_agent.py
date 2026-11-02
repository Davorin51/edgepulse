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
        return Response(b'{"accepted": true}')

    class Opener:
        open = staticmethod(send)

    monkeypatch.setattr("edgepulse.delivery.urllib.request.build_opener", lambda *args: Opener())
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


def test_bounded_collection_errors_and_no_cpu_delta(monkeypatch, capsys):
    monkeypatch.setenv("EDGEPULSE_TOKEN", "a-token-of-at-least-24-characters")
    monkeypatch.setattr(sys, "argv", ["agent", "--id", "x", "--name", "x", "--samples", "2"])
    monkeypatch.setattr("edgepulse.agent.cpu_counters", lambda _: (0, 0))
    monkeypatch.setattr("edgepulse.agent.time.sleep", lambda _: None)
    calls = []

    def collect(_):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("private file location not for logs")
        return (0, 0), {"cpu": None}

    monkeypatch.setattr("edgepulse.agent.read_metrics", collect)
    assert main() == 1
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [e["status"] for e in events] == ["collection_error", "no_cpu_delta"]
    assert len(calls) == 2


def test_fatal_auth_error_stops_agent_without_leaking_token(monkeypatch, capsys):
    from edgepulse.delivery import FatalDeliveryError

    monkeypatch.setenv("EDGEPULSE_TOKEN", "a-token-of-at-least-24-characters")
    monkeypatch.setattr(sys, "argv", ["agent", "--id", "x", "--name", "x", "--samples", "10"])
    monkeypatch.setattr("edgepulse.agent.cpu_counters", lambda _: (0, 0))
    monkeypatch.setattr(
        "edgepulse.agent.read_metrics",
        lambda _: ((100, 70), {"cpu": 30, "memory": 40, "temperature": None, "uptime": 100}),
    )
    monkeypatch.setattr("edgepulse.agent.time.sleep", lambda _: None)
    calls = []

    def rejected(*args):
        calls.append(1)
        raise FatalDeliveryError("http_401")

    monkeypatch.setattr("edgepulse.agent.HTTPTransport", lambda *args: rejected)
    assert main() == 1
    result = capsys.readouterr().out
    assert "a-token-of-at-least" not in result and len(calls) == 1
    assert json.loads(result)["status"] == "fatal"


def test_out_of_range_collected_metric_is_sanitized(monkeypatch, capsys):
    monkeypatch.setenv("EDGEPULSE_TOKEN", "a-token-of-at-least-24-characters")
    monkeypatch.setattr(sys, "argv", ["agent", "--id", "x", "--name", "x", "--samples", "1"])
    monkeypatch.setattr("edgepulse.agent.cpu_counters", lambda _: (0, 0))
    monkeypatch.setattr("edgepulse.agent.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "edgepulse.agent.read_metrics", lambda _: ((1, 1), {"cpu": 200, "memory": 40, "uptime": 1})
    )
    assert main() == 1
    assert json.loads(capsys.readouterr().out)["status"] == "collection_error"
