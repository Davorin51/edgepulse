import math
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Mode(StrEnum):
    measured = "measured"
    simulated = "simulated"


class Fault(StrEnum):
    normal = "normal"
    heat = "heat"
    pause = "pause"


class Sample(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    device_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,48}$")
    name: str = Field(min_length=1, max_length=64)
    platform: str = Field(min_length=1, max_length=64)
    mode: Mode = Mode.measured
    cpu: float = Field(ge=0, le=100)
    memory: float = Field(ge=0, le=100)
    temperature: float | None = Field(default=None, ge=-40, le=150)
    uptime: float = Field(ge=0)
    sequence: int = Field(ge=0)


def state(sample: dict, now: float, last_seen: float, offline_after: float = 12) -> str:
    if now - last_seen > offline_after:
        return "offline"
    if sample.get("temperature") is not None and sample["temperature"] >= 80:
        return "hot"
    if sample["cpu"] >= 90 or sample["memory"] >= 90:
        return "busy"
    return "healthy"


def demo_sample(index: int, tick: int, fault: Fault) -> Sample:
    names = [
        ("pi-lab", "Raspberry Pi · Lab", "Raspberry Pi demo"),
        ("jetson-lab", "Jetson · Vision", "Jetson demo"),
        ("linux-lab", "Linux · Gateway", "Linux demo"),
    ]
    device, name, platform = names[index]
    cpu = round(32 + index * 13 + 12 * math.sin(tick / 4 + index), 1)
    return Sample(
        device_id=device,
        name=name,
        platform=platform,
        mode=Mode.simulated,
        cpu=cpu,
        memory=42 + index * 12,
        temperature=88
        if fault == Fault.heat
        else round(46 + index * 7 + 4 * math.sin(tick / 8), 1),
        uptime=tick * 3,
        sequence=tick,
    )
