"""Read-only Linux agent. No remote shell or command execution endpoints."""

import argparse
import json
import math
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def cpu_counters(proc: Path):
    values = [int(x) for x in (proc / "stat").read_text().splitlines()[0].split()[1:9]]
    return sum(values), values[3] + (values[4] if len(values) > 4 else 0)


def cpu_percent(previous, current):
    total, idle = current[0] - previous[0], current[1] - previous[1]
    return None if total <= 0 else round(max(0, min(100, 100 * (1 - idle / total))), 2)


def read_metrics(
    previous, proc=Path("/proc"), thermal=Path("/sys/class/thermal/thermal_zone0/temp")
):
    current = cpu_counters(proc)
    memory = {}
    for line in (proc / "meminfo").read_text().splitlines():
        key, raw = line.split(":", 1)
        memory[key] = int(raw.split()[0])
    if memory.get("MemTotal", 0) <= 0 or "MemAvailable" not in memory:
        raise ValueError("MemTotal/MemAvailable are required")
    temperature = None
    try:
        temperature = float(thermal.read_text().strip()) / 1000
        if not -40 <= temperature <= 150:
            temperature = None
    except (OSError, ValueError):
        pass
    return current, {
        "cpu": cpu_percent(previous, current),
        "memory": round(100 * (1 - memory["MemAvailable"] / memory["MemTotal"]), 2),
        "temperature": temperature,
        "uptime": float((proc / "uptime").read_text().split()[0]),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Read-only Linux telemetry; configure a TLS endpoint on untrusted networks"
    )
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--platform", default="Linux")
    parser.add_argument("--interval", type=float, default=3)
    parser.add_argument("--samples", type=int)
    args = parser.parse_args()
    token = os.environ.get("EDGEPULSE_TOKEN", "")
    if (
        len(token) < 24
        or not math.isfinite(args.interval)
        or args.interval < 0.2
        or (args.samples is not None and args.samples < 1)
    ):
        parser.error("Set a token of at least 24 characters; interval >= .2 and samples >= 1")
    previous, sequence = cpu_counters(Path("/proc")), 0
    try:
        while args.samples is None or sequence < args.samples:
            time.sleep(args.interval)
            previous, metrics = read_metrics(previous)
            if metrics["cpu"] is None:
                continue
            from edgepulse.domain import Sample

            payload = Sample(
                device_id=args.id,
                name=args.name,
                platform=args.platform,
                sequence=sequence,
                **metrics,
            )
            request = urllib.request.Request(
                args.url.rstrip("/") + "/api/telemetry",
                data=payload.model_dump_json().encode(),
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    print(json.dumps({"sequence": sequence, "status": response.status}), flush=True)
            except (OSError, urllib.error.URLError) as exc:
                print(json.dumps({"sequence": sequence, "error": str(exc)}), flush=True)
            sequence += 1
    except KeyboardInterrupt:
        pass
