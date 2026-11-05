import asyncio
import hmac
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Path as ApiPath, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from edgepulse.alerts import fleet_alerts
from edgepulse.domain import Fault, Sample, demo_sample
from edgepulse.incidents import IncidentTracker
from edgepulse.store import Store


def create_app(database=None, token=None, demo=True, clock=time.time):
    store = Store(database or os.environ.get("EDGEPULSE_DB", "edgepulse.sqlite3"))
    incidents = IncidentTracker(store.path)
    key = token if token is not None else os.environ.get("EDGEPULSE_TOKEN", "")
    read_key = os.environ.get("EDGEPULSE_READ_TOKEN", "")
    if read_key and len(read_key) < 24:
        raise ValueError("EDGEPULSE_READ_TOKEN must have at least 24 characters")
    faults = {ident: Fault.normal for ident in ("pi-lab", "jetson-lab", "linux-lab")}

    async def loop():
        tick = 0
        while True:
            for i, ident in enumerate(faults):
                if faults[ident] != Fault.pause:
                    store.put(demo_sample(i, tick, faults[ident]), clock())
            tick += 1
            await asyncio.sleep(3)

    async def monitor_incidents():
        while True:
            now = clock()
            incidents.reconcile(store.fleet(now), now)
            await asyncio.sleep(3)

    @asynccontextmanager
    async def lifespan(_):
        tasks = [asyncio.create_task(monitor_incidents())]
        if demo:
            tasks.append(asyncio.create_task(loop()))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(title="EdgePulse", lifespan=lifespan)
    app.state.store = store

    def same_origin(request: Request):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Cross-origin controls are disabled")

    @app.get("/api/status")
    def status():
        return {"service": "edgepulse", "demo_enabled": demo, "ingestion_enabled": len(key) >= 24, "read_auth_enabled": bool(read_key)}

    @app.get("/api/fleet")
    def fleet(authorization: str = Header(default="")):
        if read_key and not hmac.compare_digest(authorization.encode(), ("Bearer " + read_key).encode()):
            raise HTTPException(401, "Invalid dashboard read token")
        return {"devices": store.fleet(clock()), "now": clock()}

    @app.get("/api/alerts")
    def alerts(authorization: str = Header(default="")):
        if read_key and not hmac.compare_digest(
            authorization.encode(), ("Bearer " + read_key).encode()
        ):
            raise HTTPException(401, "Invalid dashboard read token")
        active = fleet_alerts(store.fleet(clock()))
        return {"alerts": active, "count": len(active), "now": clock(), "type": "snapshot"}

    @app.get("/api/incidents")
    def incident_history(
        limit: int = Query(default=50, ge=1, le=200),
        status: str = Query(default="all", pattern="^(all|open|resolved)$"),
        authorization: str = Header(default=""),
    ):
        if read_key and not hmac.compare_digest(
            authorization.encode(), ("Bearer " + read_key).encode()
        ):
            raise HTTPException(401, "Invalid dashboard read token")
        now = clock()
        records = incidents.list(limit=limit, status=status)
        return {"incidents": records, "count": len(records), "now": now, "tracking": "background_poll"}

    @app.get("/api/devices/{device_id}/history")
    def device_history(
        device_id: str = ApiPath(pattern=r"^[a-zA-Z0-9_-]{1,48}$"),
        limit: int = Query(default=60, ge=1, le=120),
        authorization: str = Header(default=""),
    ):
        if read_key and not hmac.compare_digest(
            authorization.encode(), ("Bearer " + read_key).encode()
        ):
            raise HTTPException(401, "Invalid dashboard read token")
        samples = store.history(device_id, limit)
        if samples is None:
            raise HTTPException(404, "Device not found")
        return {"device_id": device_id, "samples": samples, "count": len(samples)}

    @app.post("/api/telemetry", status_code=202)
    def ingest(sample: Sample, authorization: str = Header(default="")):
        if len(key) < 24:
            raise HTTPException(503, "Configure EDGEPULSE_TOKEN with at least 24 characters")
        if not hmac.compare_digest(authorization.encode(), ("Bearer " + key).encode()):
            raise HTTPException(401, "Invalid telemetry token")
        if sample.mode != "measured":
            raise HTTPException(422, "External agents submit measured telemetry only")
        if sample.device_id in faults:
            raise HTTPException(409, "Reserved demo device ID")
        if len(store.fleet(clock())) >= 64 and sample.device_id not in {
            d["device_id"] for d in store.fleet(clock())
        }:
            raise HTTPException(409, "Device limit reached")
        try:
            store.put(sample, clock())
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"accepted": True}

    @app.post("/api/demo/{device}/{fault}")
    def set_fault(device: str, fault: Fault, request: Request):
        same_origin(request)
        if not demo or device not in faults:
            raise HTTPException(404, "Only built-in demo nodes support fault injection")
        faults[device] = fault
        return {"device": device, "fault": fault, "scope": "simulator_only"}

    static = Path(__file__).resolve().parent.parent / "dist"
    if static.exists():

        @app.get("/")
        def index():
            return FileResponse(static / "index.html")

        @app.get("/style.css")
        def stylesheet():
            return FileResponse(static / "style.css")

        @app.get("/app.js")
        def javascript():
            return FileResponse(static / "app.js")

        app.mount("/assets", StaticFiles(directory=static), name="assets")
    return app


def main():
    import uvicorn

    uvicorn.run(
        create_app(demo=os.environ.get("EDGEPULSE_DEMO", "1") == "1"),
        host=os.environ.get("EDGEPULSE_HOST", "127.0.0.1"),
        port=8000,
    )


if __name__ == "__main__":
    main()
