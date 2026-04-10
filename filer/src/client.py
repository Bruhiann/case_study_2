"""
HMAC-signed HTTP client for the Crescent Harbor Customs Authority.

Implements the submission protocol in §10 and §11 of the spec:

  POST /v3/manifests              — submit a manifest, receive a receiptId
  GET  /v3/acks/{receiptId}       — poll until terminal acknowledgment

Both endpoints require three authentication headers per §10.2–§10.3:
  X-Crescent-FilerId     — the filer's identifier
  X-Crescent-Timestamp   — integer Unix epoch seconds
  X-Crescent-Signature   — HMAC-SHA256 of the canonical signing string

Configuration is read from environment variables so that tests and
different environments can override without touching source code:
  CUSTOMS_BASE_URL      (default: http://localhost:8080)
  CUSTOMS_FILER_ID      (default: CHC100001)
  CUSTOMS_FILER_SECRET  (default: the case-study test secret)

The default secret is the value shipped in mock-customs/secrets.json.
In a real deployment it must never appear in source and must come from
a secrets manager or environment variable (see THREAT-MODEL.md).
"""

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Configuration — overridable via environment variables
# ---------------------------------------------------------------------------

BASE_URL     = os.environ.get("CUSTOMS_BASE_URL",     "http://localhost:8080")
FILER_ID     = os.environ.get("CUSTOMS_FILER_ID",     "CHC100001")
FILER_SECRET = os.environ.get(
    "CUSTOMS_FILER_SECRET",
    "case-study-shared-secret-do-not-use-in-production-zX4qP9rL",
)

# Polling constants (§11.2 and §11.3)
_POLL_INTERVAL_S = 2    # minimum wait between polls
_POLL_TIMEOUT_S  = 60   # treat PENDING beyond this as an Authority error


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class TransmissionError(Exception):
    """Raised when the Authority returns a non-successful HTTP response."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class PollTimeoutError(Exception):
    """Raised when an acknowledgment remains PENDING beyond the timeout."""


# ---------------------------------------------------------------------------
# HMAC signing — §10.3
# ---------------------------------------------------------------------------

def _sign(method: str, path: str, timestamp: int, body_bytes: bytes) -> str:
    """
    Compute the HMAC-SHA256 signature for a request.

    Canonical string (fields joined by \\n, no trailing newline):
      1. Literal "CHCAv3"
      2. HTTP method  (e.g. "POST", "GET")
      3. Request path (e.g. "/v3/manifests")
      4. Timestamp as a decimal integer string
      5. Lowercase hex SHA-256 digest of the request body bytes
         (empty body → SHA-256 of b"")

    Returns the signature as a 64-character lowercase hex string.
    """
    body_digest = hashlib.sha256(body_bytes).hexdigest()
    canonical = "\n".join([
        "CHCAv3",
        method,
        path,
        str(timestamp),
        body_digest,
    ])
    return hmac.new(
        FILER_SECRET.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _auth_headers(method: str, path: str, body_bytes: bytes) -> dict[str, str]:
    """Build the three authentication headers for a request."""
    timestamp = int(time.time())
    return {
        "X-Crescent-FilerId":    FILER_ID,
        "X-Crescent-Timestamp":  str(timestamp),
        "X-Crescent-Signature":  _sign(method, path, timestamp, body_bytes),
    }


# ---------------------------------------------------------------------------
# Submission — POST /v3/manifests
# ---------------------------------------------------------------------------

def submit(manifest: dict) -> dict:
    """
    Serialize and POST a manifest to the Authority.

    The body bytes are hashed for the HMAC and then sent as-is, so the
    signature always covers exactly the bytes the server receives.

    :param manifest: A fully-built, validated manifest dict.
    :returns: The 202 response body: {"receiptId": ..., "manifestId": ...,
              "status": "RECEIVED"}
    :raises TransmissionError: On any non-202 HTTP response.
    :raises urllib.error.URLError: On network failure (server not reachable).
    """
    path = "/v3/manifests"
    body_bytes = json.dumps(manifest, ensure_ascii=False).encode("utf-8")

    headers = _auth_headers("POST", path, body_bytes)
    headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        BASE_URL + path,
        data=body_bytes,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw)
            msg = body.get("error", raw.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, AttributeError):
            msg = raw.decode("utf-8", errors="replace")
        raise TransmissionError(exc.code, msg) from exc


# ---------------------------------------------------------------------------
# Acknowledgment polling — GET /v3/acks/{receiptId}
# ---------------------------------------------------------------------------

def poll_ack(receipt_id: str) -> dict:
    """
    Poll GET /v3/acks/{receiptId} until a terminal acknowledgment is received.

    Per §11.2: poll no more often than every 2 seconds while the status is
    PENDING. Per §11.3: the Authority guarantees a terminal state within 30 s;
    we treat any PENDING lasting beyond 60 s as an internal Authority error.

    :param receipt_id: The receiptId returned by submit().
    :returns: The terminal ack dict, status "ACCEPTED" or "REJECTED".
    :raises TransmissionError: On any non-200 HTTP response.
    :raises PollTimeoutError: If PENDING persists beyond _POLL_TIMEOUT_S.
    :raises urllib.error.URLError: On network failure.
    """
    path = f"/v3/acks/{receipt_id}"
    deadline = time.monotonic() + _POLL_TIMEOUT_S

    while True:
        body_bytes = b""    # GET has no body; SHA-256 of b"" is well-defined
        headers = _auth_headers("GET", path, body_bytes)

        req = urllib.request.Request(
            BASE_URL + path,
            headers=headers,
            method="GET",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                ack = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                body = json.loads(raw)
                msg = body.get("error", raw.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, AttributeError):
                msg = raw.decode("utf-8", errors="replace")
            raise TransmissionError(exc.code, msg) from exc

        status = ack.get("status")

        if status in ("ACCEPTED", "REJECTED"):
            return ack

        if status == "PENDING":
            if time.monotonic() >= deadline:
                raise PollTimeoutError(
                    f"acknowledgment for receipt {receipt_id} remained PENDING "
                    f"for more than {_POLL_TIMEOUT_S}s"
                )
            time.sleep(_POLL_INTERVAL_S)
            continue

        # Any other status value is unexpected
        raise TransmissionError(0, f"unexpected ack status: {status!r}")
