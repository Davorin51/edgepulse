# Changelog

## 0.2.0

- Add configurable exponential retry/backoff for transient Linux-agent transport failures.
- Send fresh samples after recovery; explicitly count discarded samples, without stale replay.
- Reject redirects, invalid acknowledgements, unsafe URL/token configuration and permanent HTTP errors.
- Replace numeric agent status logs with named events and structured delivery fields.
- Bound `--samples` by collection attempts; return a nonzero exit when none are acknowledged.
- Handle unreadable or invalid collected metrics without exposing raw exception details.
- Explicitly close SQLite connections after transactions.
- Add deterministic retry tests and real loopback HTTP failure/recovery and redirect tests.

## 0.1.0

- Initial local telemetry lab, Linux agent, SQLite history, dashboard and simulated fault controls.
