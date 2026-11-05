"""Deterministic tests for read-only hardware validation."""

from edgepulse.validation import validate_phase


def fake_device(sequence, state="healthy", mode="measured"):
    return {
        "devices": [
            {
                "device_id": "pi-real",
                "state": state,
                "mode": mode,
                "sequence": sequence,
                "cpu": 10,
                "memory": 20,
                "temperature": None,
            }
        ]
    }


def run_phase(phase, snapshots):
    values = iter(snapshots)
    ticks = iter((0, *range(len(snapshots))))

    def fetch(_path):
        return next(values)

    def clock():
        return next(ticks)

    return validate_phase(
        fetch, "pi-real", phase, len(snapshots) - 1, 1, sleep=lambda _s: None, clock=clock
    )


def test_baseline_requires_real_measured_progress():
    assert run_phase("baseline", [fake_device(1), fake_device(2)])["passed"]
    assert not run_phase("baseline", [fake_device(1), fake_device(1)])["passed"]
    assert not run_phase(
        "baseline", [fake_device(1, mode="simulated"), fake_device(2, mode="simulated")]
    )["passed"]


def test_outage_requires_server_observed_offline():
    assert run_phase("outage", [fake_device(2), fake_device(2, "offline")])["passed"]
    assert not run_phase("outage", [fake_device(2), fake_device(3)])["passed"]


def test_recovery_requires_fresh_progress_and_online_state():
    assert run_phase("recovery", [fake_device(4), fake_device(5)])["passed"]
    assert not run_phase("recovery", [fake_device(4), fake_device(4)])["passed"]
    assert not run_phase("recovery", [fake_device(4), fake_device(5, "offline")])["passed"]


def test_request_errors_are_not_success():
    def fetch(_path):
        raise OSError("network down")

    ticks = iter((0, 0, 1))
    result = validate_phase(
        fetch, "pi-real", "outage", 1, 1, sleep=lambda _s: None, clock=lambda: next(ticks)
    )
    assert not result["passed"]
    assert result["observations"][0]["state"] == "request_error"
