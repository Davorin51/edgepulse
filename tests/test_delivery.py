import io
import json
import threading
import urllib.error
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from edgepulse.delivery import (
    FatalDeliveryError,
    HTTPTransport,
    LatestDelivery,
    RetryableDeliveryError,
    telemetry_url,
)
from edgepulse.domain import Sample

TOKEN = "private-test-token-0123456789"


def sample(sequence=0):
    return Sample(
        device_id="my-edge",
        name="Local",
        platform="Linux",
        cpu=10,
        memory=20,
        uptime=3,
        sequence=sequence,
    )


class Clock:
    value = 0

    def __call__(self):
        return self.value


def test_reconnection_sends_fresh_sample_not_old_failed_payload():
    clock = Clock()
    sent = []

    def send(payload):
        sent.append(payload.sequence)
        if len(sent) <= 2:
            raise RetryableDeliveryError("network_error")

    client = LatestDelivery(send, retry_base=2, retry_max=4, clock=clock)
    assert client.offer(sample(0)).retry_in == 2
    clock.value = 1
    assert client.offer(sample(1)).status == "backoff"
    clock.value = 2
    assert client.offer(sample(2)).retry_in == 4
    for i in [3, 4, 5]:
        clock.value = i
        assert client.offer(sample(i)).status == "backoff"
    clock.value = 6
    result = client.offer(sample(6))
    assert sent == [0, 2, 6]
    assert result.status == "delivered" and result.discarded_samples == 6
    assert client.discarded == 0 and client.delay == 0
    clock.value = 7
    assert client.offer(sample(7)).discarded_samples == 0


def test_backoff_is_capped_and_measured_after_slow_request():
    clock = Clock()

    def send(_):
        clock.value += 5
        raise RetryableDeliveryError("http_503")

    client = LatestDelivery(send, retry_base=2, retry_max=3, clock=clock)
    assert client.offer(sample()).retry_in == 2
    assert client.next_attempt == 7
    clock.value = 7
    assert client.offer(sample()).retry_in == 3
    clock.value = client.next_attempt
    assert client.offer(sample()).retry_in == 3


@pytest.mark.parametrize(
    "base,maximum", [(0, 1), (-1, 1), (2, 1), (1, float("inf")), (float("nan"), 2)]
)
def test_invalid_retry_policy(base, maximum):
    with pytest.raises(ValueError):
        LatestDelivery(lambda _: None, retry_base=base, retry_max=maximum)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://lab",
        "http://",
        "http://user:pass@host",
        "http://lab?token=secret",
        "http://lab/#x",
        "http://host:99999",
        "http://ho st",
        "http://[broken",
    ],
)
def test_invalid_url_rejected_before_request(url):
    with pytest.raises(ValueError):
        telemetry_url(url)


@pytest.mark.parametrize("token", ["short", "x" * 24 + "\r\nHeader: x", "x" * 24 + " ", "é" * 24])
def test_invalid_token(token):
    with pytest.raises(ValueError):
        HTTPTransport("http://localhost", token)


@pytest.mark.parametrize(
    "code,retry",
    [
        (408, True),
        (429, True),
        (500, True),
        (503, True),
        (599, True),
        (301, False),
        (307, False),
        (401, False),
        (403, False),
        (422, False),
    ],
)
def test_status_classification_and_response_close(code, retry):
    transport = HTTPTransport("http://localhost", TOKEN)
    body = io.BytesIO(b"do not log this secret response")

    def open_request(*args, **kwargs):
        raise urllib.error.HTTPError("http://localhost", code, "error", {}, body)

    transport.opener.open = open_request
    with pytest.raises(
        RetryableDeliveryError if retry else FatalDeliveryError, match=f"http_{code}"
    ) as error:
        transport(sample())
    assert "secret" not in str(error.value) and TOKEN not in str(error.value)
    assert body.closed


@pytest.mark.parametrize(
    "body", [b"<html>login</html>", b"null", b"{}", b'{"accepted":false}', b"x" * 4097]
)
def test_malformed_acknowledgements_are_not_success(body):
    transport = HTTPTransport("http://localhost", TOKEN)

    class Response(io.BytesIO):
        status = 202

    transport.opener.open = lambda *a, **k: Response(body)
    with pytest.raises(FatalDeliveryError, match="invalid_acknowledgement"):
        transport(sample())


@contextmanager
def server(handler):
    instance = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{instance.server_port}"
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


def test_real_http_retry_recovery_and_no_credential_redirect():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.headers["Authorization"], data["sequence"]))
            self.send_response(503 if len(requests) == 1 else 202)
            self.end_headers()
            self.wfile.write(b'{"accepted":true}')

    with server(Handler) as url:
        clock = Clock()
        delivery = LatestDelivery(HTTPTransport(url, TOKEN), clock=clock)
        assert delivery.offer(sample(1)).status == "retry_scheduled"
        clock.value = 2
        assert delivery.offer(sample(2)).status == "delivered"
    assert requests == [("Bearer " + TOKEN, 1), ("Bearer " + TOKEN, 2)]

    class Redirect(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.send_response(302)
            self.send_header("Location", target + "/steal")
            self.end_headers()

    with server(Handler) as target, server(Redirect) as source:
        with pytest.raises(FatalDeliveryError, match="http_302"):
            HTTPTransport(source, TOKEN)(sample(3))
    assert len(requests) == 2


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout(timeout):
    with pytest.raises(ValueError):
        HTTPTransport("http://localhost", TOKEN, timeout)


def test_network_and_truncated_response_are_retryable():
    import http.client

    transport = HTTPTransport("http://localhost", TOKEN)
    for failure in [TimeoutError("private address"), http.client.IncompleteRead(b"secret", 2)]:

        def fail(*args, error=failure, **kwargs):
            raise error

        transport.opener.open = fail
        with pytest.raises(RetryableDeliveryError, match="^network_error$"):
            transport(sample())
