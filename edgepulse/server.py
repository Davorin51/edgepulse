import asyncio
import hmac
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from edgepulse.domain import Fault, Sample, demo_sample
from edgepulse.store import Store


def create_app(database=None, token=None, demo=True, clock=time.time):
    store = Store(database or os.environ.get("EDGEPULSE_DB", "edgepulse.sqlite3"))
    key = token if token is not None else os.environ.get("EDGEPULSE_TOKEN", "")
    faults = {ident: Fault.normal for ident in ("pi-lab", "jetson-lab", "linux-lab")}

    async def loop():
        tick = 0
        while True:
            for i, ident in enumerate(faults):
                if faults[ident] != Fault.pause:
                    store.put(demo_sample(i, tick, faults[ident]), clock())
            tick += 1
            await asyncio.sleep(3)

    @asynccontextmanager
    async def lifespan(_):
        task = asyncio.create_task(loop()) if demo else None
        yield
        if task:
            task.cancel()
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
        return {"service": "edgepulse", "demo_enabled": demo, "ingestion_enabled": len(key) >= 24}

    @app.get("/api/fleet")
    def fleet():
        return {"devices": store.fleet(clock()), "now": clock()}

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
