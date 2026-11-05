# Incident history v1

`GET /api/incidents?status=all&limit=50` returns SQLite-persisted incident lifecycles. Filter `status` by `all`, `open` or `resolved`; `limit` is 1–200. The endpoint uses the existing optional `EDGEPULSE_READ_TOKEN` read authorization.

An incident is keyed by device ID and alert kind. Repeated observations of the same active condition do not create duplicates. Once an alert disappears, the incident is resolved; a later recurrence creates a new record. Offline state takes priority over stale CPU/temperature/memory alerts.

**Important limitations:** Reconciliation only runs when this endpoint is called, so incidents occurring entirely between polls can be missed and timestamps are observation times, not guaranteed fault onset/recovery times. No background scheduler, acknowledgements, user ownership, notification delivery, retention policy or incident UI yet. Use this as a local-lab building block, not a production incident management service. A later milestone should move reconciliation into a dedicated single worker and add tenant-scoped authentication before cloud deployment.
