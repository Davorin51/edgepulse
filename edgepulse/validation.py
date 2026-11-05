"""Read-only, operator-driven validation of a real EdgePulse Linux agent."""

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def fetch_json(base_url, path, token="", timeout=5):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(base_url.rstrip("/") + path, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def validate_phase(
    fetch, device_id, phase, duration, interval, sleep=time.sleep, clock=time.monotonic
):
    """Observe server state; never send commands to a monitored device."""
    started = clock()
    observations = []
    while True:
        elapsed = clock() - started
        try:
            data = fetch("/api/fleet")
            devices = [d for d in data["devices"] if d["device_id"] == device_id]
            device = devices[0] if devices else None
            observations.append(
                {
                    "elapsed_s": round(elapsed, 2),
                    "state": device["state"] if device else "missing",
                    "mode": device["mode"] if device else None,
                    "sequence": device["sequence"] if device else None,
                    "cpu": device["cpu"] if device else None,
                    "memory": device["memory"] if device else None,
                    "temperature": device["temperature"] if device else None,
                }
            )
        except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError) as exc:
            observations.append(
                {
                    "elapsed_s": round(elapsed, 2),
                    "state": "request_error",
                    "error": type(exc).__name__,
                }
            )
        if elapsed >= duration:
            break
        sleep(min(interval, max(0, duration - elapsed)))
    states = [item["state"] for item in observations]
    measured = [item for item in observations if item.get("mode") == "measured"]
    sequences = [item["sequence"] for item in measured]
    progressed = any(b > a for a, b in zip(sequences, sequences[1:], strict=False))
    if phase == "baseline":
        passed = len(measured) >= 2 and progressed and all(s != "offline" for s in states)
    elif phase == "outage":
        passed = "offline" in states
    else:
        passed = (
            len(measured) >= 2
            and progressed
            and states[-1] not in ("offline", "missing", "request_error")
        )
    return {"phase": phase, "passed": passed, "observations": observations}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--device", required=True)
    parser.add_argument("--phase", choices=("baseline", "outage", "recovery"), required=True)
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("--output", required=True, help="Local JSON evidence file")
    args = parser.parse_args(argv)
    if not 0 < args.interval <= args.duration <= 86400:
        parser.error("Require 0 < interval <= duration <= 86400 seconds")
    token = os.environ.get("EDGEPULSE_READ_TOKEN", "")

    def fetch(path):
        return fetch_json(args.url, path, token)

    result = validate_phase(fetch, args.device, args.phase, args.duration, args.interval)
    report = {
        "schema": 1,
        "device_id": args.device,
        "server_url": args.url,
        "observed_at": datetime.now(UTC).isoformat(),
        **result,
    }
    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
        file.write("\n")
    print(json.dumps({"phase": args.phase, "passed": result["passed"], "output": args.output}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
