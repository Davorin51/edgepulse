# EdgePulse v0.3 — real Linux device validation

This protocol is **not** evidence that a Raspberry Pi or Jetson has already been tested.
It provides repeatable operator-run checks and locally saved JSON observations. No remote
commands, SSH credentials, simulated device data or telemetry tokens are recorded.

## Setup

On the lab host, install and start the backend:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export EDGEPULSE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export EDGEPULSE_READ_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export EDGEPULSE_DEMO=0
export EDGEPULSE_HOST=0.0.0.0
python -m edgepulse.server
```

On the **same trusted LAN**, install the package on the Linux device and set
`EDGEPULSE_TOKEN` to the exact ingestion token generated on the host. Run:

```bash
edgepulse-agent --url http://LAB_HOST_IP:8000 --id pi-real --name "Real Pi" --platform Linux --interval 3
```

Never expose the plaintext HTTP lab endpoint to the Internet. Use a private LAN or
TLS-secured transport. The agent is read-only; do not run it as root. Verify that
`/api/fleet` shows `pi-real` with `mode: measured`, not `simulated`.

## Three observation phases

On the **host**, keep the backend running, set the read token, and collect each phase
to a separate file. JSON files contain device IDs, telemetry and timestamps; handle
them as private lab data. The collector makes only GET requests.

```bash
mkdir -p evidence
python -m edgepulse.validation --url http://127.0.0.1:8000 --device pi-real --phase baseline --duration 60 --interval 2 --output evidence/baseline.json
```

Next **stop only the agent process** (Ctrl+C on the device), not the backend. Wait
at least 15 seconds; the server offline threshold is 12 seconds. Collect:

```bash
python -m edgepulse.validation --url http://127.0.0.1:8000 --device pi-real --phase outage --duration 20 --interval 2 --output evidence/outage.json
```

Restart the agent on the device with the same ID and token. Collect:

```bash
python -m edgepulse.validation --url http://127.0.0.1:8000 --device pi-real --phase recovery --duration 60 --interval 2 --output evidence/recovery.json
```

Each command exits 0 for a passed phase, 1 for failed observation and 2 for invalid
arguments. Baseline and recovery require at least two measured observations with
increasing sequence numbers. Outage requires an actual `offline` server state.
These are separate phases: the recovery check alone does not prove the preceding
outage; retain all three reports.

## Extended soak run

Leave the real agent running for several hours (e.g. 4 h) while periodically
running baseline checks with `--duration 300`. Record machine type, OS, thermal
zone used, server/agent versions, number of reconnects, and any failures in a lab
notebook. The tool itself does not certify a 4-hour run or aggregate multiple files.
Inspect server logs and the dashboard incident timeline for opening/resolution.

## Limits

The validator cannot cause or verify physical network disruption; stopping the
agent is a controlled telemetry interruption. It cannot guarantee every sample was
delivered, verify GPU temperature, or assert a device was actually physical rather
than a replaying client. Its results reflect only the API observations captured.
Do not commit `evidence/` files containing real telemetry.
