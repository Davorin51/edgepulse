# EdgePulse Pro roadmap

EdgePulse is currently a local-first lab, **not** an Internet-facing SaaS. Upgrade in stages without breaking existing agent ingestion.

## Foundation (in this branch)
- Optional `EDGEPULSE_READ_TOKEN` to protect `GET /api/fleet`, minimum 24 characters.
- Existing local demo continues unchanged when the variable is absent.
- Existing static dashboard does not supply the token: enabling it deliberately blocks fleet API calls from that dashboard. Do not embed secrets in public browser JavaScript. A session-based UI is needed before production use.

## Next: private multi-user MVP
- Authenticated browser sessions, account and organization management.
- Tenant-scoped database access, PostgreSQL migration, per-device enrollment tokens, revocation and rotation.
- HTTPS, rate limiting, audit events and integration tests.

## Operations
- Alerts, historical charts, device tags, log ingestion, disk and network metrics, optional Jetson sensors validated on hardware.
- Backups, retention policies, agent offline handling, alert deduplication and notification channels.

## Commercial readiness
- Subscription billing, quota enforcement, data export/deletion, privacy compliance and documentation.
- Real Raspberry Pi and Jetson end-to-end validation.

Later milestones are plans, not implemented features.
