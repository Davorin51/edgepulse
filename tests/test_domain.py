import math

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from edgepulse.agent import cpu_percent, read_metrics
from edgepulse.domain import Fault, Sample, demo_sample, state


def sample(**kw):
    return Sample(
        device_id="real-node",
        name="Local edge",
        platform="Linux",
        cpu=30,
        memory=40,
        uptime=3,
        sequence=1,
        **kw,
    )


@pytest.mark.parametrize("value", [-1, 101, math.nan, math.inf])
def test_invalid_cpu(value):
    data = sample().model_dump()
    data["cpu"] = value
    with pytest.raises(ValidationError):
        Sample(**data)


@pytest.mark.parametrize("ident", ["../evil", "has space", "", "a" * 49, "<script>"])
def test_invalid_id(ident):
    data = sample().model_dump()
    data["device_id"] = ident
    with pytest.raises(ValidationError):
        Sample(**data)


@pytest.mark.parametrize(
    "elapsed,temp,cpu,expected",
    [
        (13, 90, 99, "offline"),
        (0, 80, 30, "hot"),
        (0, None, 90, "busy"),
        (0, None, 20, "healthy"),
        (12, 40, 30, "healthy"),
    ],
)
def test_states(elapsed, temp, cpu, expected):
    assert state({"temperature": temp, "cpu": cpu, "memory": 40}, 100 + elapsed, 100) == expected


def test_seeded_demo():
    assert demo_sample(1, 10, Fault.normal) == demo_sample(1, 10, Fault.normal)
    assert demo_sample(1, 10, Fault.heat).temperature == 88
    assert demo_sample(1, 10, Fault.normal).mode == "simulated"


@given(st.integers(1, 100000), st.floats(0, 1, allow_nan=False))
def test_cpu_percent_bounds(total, ratio):
    result = cpu_percent((0, 0), (total, int(total * ratio)))
    assert 0 <= result <= 100


def test_cpu_no_elapsed():
    assert cpu_percent((10, 3), (10, 3)) is None
    assert cpu_percent((10, 3), (5, 1)) is None


def test_linux_metrics_real_format(tmp_path):
    (tmp_path / "stat").write_text("cpu  10 0 20 70 0 0 0 0\n")
    (tmp_path / "meminfo").write_text("MemTotal: 1000 kB\nMemAvailable: 600 kB\n")
    (tmp_path / "uptime").write_text("123.45 67.2\n")
    thermal = tmp_path / "temp"
    thermal.write_text("52000\n")
    counters, metrics = read_metrics((0, 0), tmp_path, thermal)
    assert counters == (100, 70)
    assert metrics == {"cpu": 30.0, "memory": 40.0, "temperature": 52.0, "uptime": 123.45}
    thermal.unlink()
    assert read_metrics((0, 0), tmp_path, thermal)[1]["temperature"] is None
    (tmp_path / "meminfo").write_text("MemTotal: 0 kB\n")
    with pytest.raises(ValueError):
        read_metrics((0, 0), tmp_path, thermal)
