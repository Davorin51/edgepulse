"""Read-only, deterministic alert snapshots derived from current fleet state.

This is not an incident database or notification delivery service.
"""


def fleet_alerts(devices):
    alerts = []
    for device in devices:
        ident = device["device_id"]
        base = {
            "device_id": ident,
            "device_name": device["name"],
            "mode": device["mode"],
            "last_seen": device["last_seen"],
        }
        if device["state"] == "offline":
            alerts.append(
                {
                    **base,
                    "kind": "offline",
                    "severity": "critical",
                    "message": "Device has stopped reporting telemetry",
                }
            )
            continue
        temp = device.get("temperature")
        if temp is not None and temp >= 80:
            alerts.append(
                {
                    **base,
                    "kind": "temperature",
                    "severity": "critical",
                    "message": "Temperature is at or above 80 C",
                    "value": temp,
                    "threshold": 80,
                }
            )
        for metric in ("cpu", "memory"):
            value = device[metric]
            if value >= 90:
                alerts.append(
                    {
                        **base,
                        "kind": metric,
                        "severity": "warning",
                        "message": f"{metric.upper()} utilization is at or above 90%",
                        "value": value,
                        "threshold": 90,
                    }
                )
    return alerts
