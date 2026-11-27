"""Run an isolated EdgePulse fault drill and produce a JSON report."""

import argparse
import http.client
import json
import socket
import sys
import time
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

import uvicorn

from edgepulse.domain import Fault
from edgepulse.server import create_app

DEVICE = "pi-lab"
STARTUP_TIMEOUT = 5
STAGE_TIMEOUT = 25
POLL_INTERVAL = 0.5


class DrillError(Exception):
    """A fault drill did not complete successfully."""


@contextmanager
def simulator():
    with TemporaryDirectory(prefix="edgepulse-drill-") as directory, socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        host, port = listener.getsockname()
        app = create_app(database=Path(directory) / "drill.sqlite3", token="", read_token="")
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                lifespan="on",
                proxy_headers=False,
                workers=1,
                log_level="warning",
                access_log=False,
                timeout_graceful_shutdown=3,
            )
        )
        worker = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            deadline = time.monotonic() + STARTUP_TIMEOUT
            while not server.started:
                if not worker.is_alive() or time.monotonic() >= deadline:
                    raise DrillError("The local simulator did not start")
                time.sleep(0.05)
            with closing(http.client.HTTPConnection(host, port, timeout=3)) as client:
                yield client
        finally:
            server.should_exit = True
            worker.join(timeout=5)
            if worker.is_alive():
                raise DrillError("The local simulator did not shut down")


def request_json(client, method, path):
    client.request(method, path)
    response = client.getresponse()
    body = response.read()
    if response.status != 200:
        raise DrillError(f"{method} {path} returned HTTP {response.status}")
    return json.loads(body)


def wait_for_stage(client, name, state, *, after=None, kind=None, resolve=None):
    started = time.monotonic()
    deadline = started + STAGE_TIMEOUT
    status = "open" if resolve is None else "resolved"
    while time.monotonic() < deadline:
        fleet = request_json(client, "GET", "/api/fleet")
        device = next((item for item in fleet["devices"] if item["device_id"] == DEVICE), None)
        if (
            device
            and device["mode"] == "simulated"
            and device["state"] == state
            and (after is None or device["last_seen"] > after)
        ):
            incident = None
            if kind is not None:
                incidents = request_json(client, "GET", f"/api/incidents?status={status}")
                incident = next(
                    (
                        item
                        for item in incidents["incidents"]
                        if item["device_id"] == DEVICE
                        and item["kind"] == kind
                        and item["status"] == status
                        and (resolve is None or item["id"] == resolve)
                    ),
                    None,
                )
            if kind is None or incident is not None:
                return {
                    "stage": name,
                    "wait_s": round(time.monotonic() - started, 3),
                    "state": state,
                    "last_seen": device["last_seen"],
                    "temperature_c": device["temperature"],
                    "incident": {
                        key: incident[key] for key in ("id", "kind", "status", "opened", "resolved")
                    }
                    if incident
                    else None,
                }
        time.sleep(min(POLL_INTERVAL, max(0, deadline - time.monotonic())))
    expected = f"{state} state"
    if kind is not None:
        expected += f" and a {status} {kind} incident"
    raise DrillError(f"{name} timed out waiting for {expected}")


def run_drill():
    report = {"schema": 1, "mode": "simulated", "device_id": DEVICE, "passed": False, "stages": []}
    stages = report["stages"]

    def set_fault(client, fault):
        request_json(client, "POST", f"/api/demo/{DEVICE}/{fault}")

    try:
        with simulator() as client:
            baseline = wait_for_stage(client, "baseline", "healthy")
            stages.append(baseline)
            set_fault(client, Fault.heat)
            hot = wait_for_stage(
                client, "overheat", "hot", after=baseline["last_seen"], kind="temperature"
            )
            stages.append(hot)
            set_fault(client, Fault.normal)
            stages.append(
                wait_for_stage(
                    client,
                    "cooldown",
                    "healthy",
                    after=hot["last_seen"],
                    kind="temperature",
                    resolve=hot["incident"]["id"],
                )
            )
            set_fault(client, Fault.pause)
            offline = wait_for_stage(client, "link_loss", "offline", kind="offline")
            stages.append(offline)
            set_fault(client, Fault.normal)
            stages.append(
                wait_for_stage(
                    client,
                    "recovery",
                    "healthy",
                    after=offline["last_seen"],
                    kind="offline",
                    resolve=offline["incident"]["id"],
                )
            )
    except DrillError as exc:
        report["error"] = str(exc)
    except (OSError, http.client.HTTPException, ValueError, TypeError, KeyError) as exc:
        report["error"] = f"Simulator or API error ({type(exc).__name__})"
    else:
        report["passed"] = True
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="Write the report to a new file instead of stdout"
    )
    args = parser.parse_args(argv)
    if args.output is None:
        report = run_drill()
        print(json.dumps(report, indent=2))
    else:
        try:
            with args.output.open("x", encoding="utf-8") as target:
                report = run_drill()
                json.dump(report, target, indent=2)
                target.write("\n")
        except OSError as exc:
            parser.exit(2, f"{parser.prog}: {exc}\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
