"""Bounded latest-sample delivery: retry transport failures, never replay stale history."""

from __future__ import annotations

import http.client
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from edgepulse.domain import Sample


class DeliveryError(Exception):
    """A sanitized transport failure; never contains a token or response body."""


class RetryableDeliveryError(DeliveryError):
    pass


class FatalDeliveryError(DeliveryError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A bearer token must not be forwarded to a Location chosen by a server/proxy.
        return None


def telemetry_url(base: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(base)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid backend URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(ord(c) <= 32 or ord(c) == 127 for c in base)
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError("Use an HTTP(S) backend URL without credentials, query or fragment")
    return base.rstrip("/") + "/api/telemetry"


class HTTPTransport:
    def __init__(self, base: str, token: str, timeout: float = 5):
        self.url = telemetry_url(base)
        if (
            len(token) < 24
            or not token.isascii()
            or any(ord(c) <= 32 or ord(c) == 127 for c in token)
        ):
            raise ValueError("Token must contain at least 24 printable non-space ASCII characters")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Request timeout must be finite and positive")
        self.token, self.timeout = token, timeout
        self.opener = urllib.request.build_opener(NoRedirect())

    def __call__(self, sample: Sample) -> None:
        request = urllib.request.Request(
            self.url,
            data=sample.model_dump_json().encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.status != 202:
                    raise FatalDeliveryError(f"unexpected_http_{response.status}")
                raw = response.read(4097)
                if len(raw) > 4096:
                    raise FatalDeliveryError("invalid_acknowledgement")
                try:
                    acknowledgement = json.loads(raw)
                except (ValueError, UnicodeError) as exc:
                    raise FatalDeliveryError("invalid_acknowledgement") from exc
                if (
                    not isinstance(acknowledgement, dict)
                    or acknowledgement.get("accepted") is not True
                ):
                    raise FatalDeliveryError("invalid_acknowledgement")
        except urllib.error.HTTPError as exc:
            exc.close()
            error = f"http_{exc.code}"
            if exc.code in {408, 429} or 500 <= exc.code <= 599:
                raise RetryableDeliveryError(error) from None
            raise FatalDeliveryError(error) from None
        except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:
            raise RetryableDeliveryError("network_error") from exc


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    discarded_samples: int
    retry_in: float = 0
    error: str | None = None


class LatestDelivery:
    """One current sample per call; no disk queue, stale replay, or unbounded retry burst.

    Sampling continues while the next attempt is deferred. Those unsent measurements are
    explicitly counted and discarded. The next permitted call sends its *fresh* sample.
    """

    def __init__(
        self,
        send: Callable[[Sample], None],
        *,
        retry_base: float = 2,
        retry_max: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ):
        if (
            not all(math.isfinite(v) and v > 0 for v in (retry_base, retry_max))
            or retry_max < retry_base
        ):
            raise ValueError("Retry limits must be positive, finite, and max >= base")
        self.send, self.clock = send, clock
        self.retry_base, self.retry_max = retry_base, retry_max
        self.next_attempt, self.delay, self.discarded = 0.0, 0.0, 0

    def offer(self, sample: Sample) -> DeliveryResult:
        now = self.clock()
        if now < self.next_attempt:
            self.discarded += 1
            return DeliveryResult("backoff", self.discarded, self.next_attempt - now)
        try:
            self.send(sample)
        except RetryableDeliveryError as exc:
            self.discarded += 1
            self.delay = self.retry_base if self.delay == 0 else min(self.retry_max, self.delay * 2)
            self.next_attempt = self.clock() + self.delay
            return DeliveryResult("retry_scheduled", self.discarded, self.delay, str(exc))
        discarded = self.discarded
        self.next_attempt, self.delay, self.discarded = 0.0, 0.0, 0
        return DeliveryResult("delivered", discarded)
