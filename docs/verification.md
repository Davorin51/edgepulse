# Verification

Local Python tests, Ruff lint/format, JavaScript syntax check and Python package builds were executed.
The browser demo was opened through the managed preview, and heat/pause controls were exercised.
A simulated Jetson card changed to HOT at 88°C; a paused card's sample stream stopped. These are
simulation results, not board measurements. API tests use isolated temporary SQLite databases.

Docker is unavailable in the authoring environment. No Raspberry Pi, Jetson, FPGA, power draw,
network-throughput or hardware latency result is claimed. The GitHub Actions workflow was subsequently run after publication; see the verified result below.

Final local result: **36 passed**, **94.29% Python statement coverage**. Ruff lint/format,
JavaScript syntax and Python sdist/wheel builds passed. One dependency deprecation warning
from Starlette/httpx was emitted; it was not suppressed or counted as a test failure.

An additional read of the actual authoring Linux /proc counters was accepted through the API
(HTTP 202), stored in SQLite and returned as `mode=measured`, with unavailable temperature
represented as null. This checks the collector-to-store path on the authoring host, not on a board.


## GitHub publication verification

[Run 41489569383](https://github.com/Davorin51/edgepulse/actions/runs/41489569383) passed both Python 3.11 and 3.12 jobs on source commit `c84c780692bee5da060bb78bbeed65592c8581bf`. The jobs ran Ruff, formatting, pytest, package builds, Docker image build, Compose startup and an HTTP readiness request. No Raspberry Pi/Jetson board test was performed. The follow-up documentation commit does not change tested application code.

## v0.2.0 agent delivery upgrade

Executed locally on Python 3.12.14: **80 tests passed**, **96.33% statement coverage**.
Ruff lint, formatting and whitespace checks passed. The existing Starlette/httpx deprecation
warning remains visible. New loopback HTTP integration tests exercise a 503 response followed
by a successful 202 acknowledgement and verify that a 302 redirect sends no request to the
redirect target. Deterministic-clock tests check exponential delay, cap, fresh-sample recovery
and discarded counts; additional tests cover malformed acknowledgements, timeouts, HTTP error
classification, invalid configuration, bounded collection failures and sanitized fatal logs.
These tests do not require or demonstrate an attached Raspberry Pi/Jetson.
