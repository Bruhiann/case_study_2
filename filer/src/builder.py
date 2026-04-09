"""
Manifest builder.

Accepts a scenario input dict (raw parsed scenario JSON, which includes
_-prefixed metadata fields not part of the manifest spec) and returns a
complete Cargo Arrival Manifest dict that is ready for schema validation
and rules checking.

Fields added by the builder (not present in the scenario input):
  - manifestId      : UUIDv4, hyphens stripped, uppercased — 32 chars from
                      [A-Z0-9], satisfying the §3.4 format requirement.
  - filer           : Populated from FILER_CONFIG (filerId, legalName,
                      contactEmail).
  - arrival.eta     : Computed as UTC now + _etaOffsetHours, formatted as
                      ISO 8601 with second precision and trailing Z.
  - filerSignature  : Audit record per §10.5, populated from FILER_CONFIG
                      with signedAtUtc set to the current UTC time.

Normalization applied:
  - vessel.name is uppercased before inclusion. Per §4.1, "vessel names
    containing lowercase letters in the input shall be uppercased by the
    filer prior to submission." We treat this as a silent normalization
    step rather than a rejection (see ARCHITECTURE.md, R-005 decision).
  - _-prefixed metadata keys from the scenario are never copied into the
    manifest output.
"""

import uuid
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Filer configuration.
# In production this would be loaded from environment variables or a secrets
# manager at startup. Keeping it in one place here makes it easy to see what
# identity the filer presents to the Authority.
# ---------------------------------------------------------------------------

FILER_CONFIG = {
    "filerId": "CHC100001",
    "legalName": "Crescent Harbor Direct Filer Ltd.",
    "contactEmail": "filing@crescentharborfiler.example",
    "signerName": "Automated Filing System",
    "signerTitle": "Direct Filer Agent",
}


def build(scenario: dict) -> dict:
    """
    Build a complete manifest dict from a scenario input.

    :param scenario: Parsed scenario JSON. Must contain _etaOffsetHours plus
                     the vessel, arrival (without eta), containers, crew, and
                     declaredValueTotal fields.
    :returns: Complete manifest dict. All _-prefixed fields are excluded.
    :raises KeyError: If a required scenario field is missing.
    """
    now = datetime.now(tz=timezone.utc)

    # ETA is computed at build time so that the filing-window rules (R-022,
    # R-023) are evaluated against the actual transmission moment.
    eta_offset_hours = scenario["_etaOffsetHours"]
    eta_dt = now + timedelta(hours=eta_offset_hours)
    eta_str = _format_utc(eta_dt)

    # UUIDv4 with hyphens stripped and uppercased gives exactly 32 characters
    # from [A-Z0-9], satisfying §3.4's 12–32 char / [A-Z0-9-] constraint.
    manifest_id = uuid.uuid4().hex.upper()

    manifest = {
        "manifestId": manifest_id,
        "filer": _build_filer(),
        "vessel": _build_vessel(scenario["vessel"]),
        "arrival": _build_arrival(scenario["arrival"], eta_str),
        "containers": scenario["containers"],
        "crew": scenario["crew"],
        "declaredValueTotal": scenario["declaredValueTotal"],
        "filerSignature": _build_filer_signature(now),
    }

    return manifest


# ---------------------------------------------------------------------------
# Private helpers — each builds one section of the manifest.
# ---------------------------------------------------------------------------

def _build_filer() -> dict:
    return {
        "filerId": FILER_CONFIG["filerId"],
        "legalName": FILER_CONFIG["legalName"],
        "contactEmail": FILER_CONFIG["contactEmail"],
    }


def _build_vessel(vessel: dict) -> dict:
    """
    Return a copy of the vessel dict with the name uppercased.
    All other fields are passed through unchanged.
    """
    return {
        **vessel,
        "name": vessel["name"].upper(),
    }


def _build_arrival(arrival: dict, eta_str: str) -> dict:
    """
    Return a copy of the arrival dict with the computed eta field merged in.
    The scenario's arrival object intentionally omits eta because the correct
    value depends on when the filing is actually transmitted.
    """
    return {
        **arrival,
        "eta": eta_str,
    }


def _build_filer_signature(signed_at: datetime) -> dict:
    """
    Build the filerSignature audit block (§10.5).
    This is a record of who authorized the submission; it has no cryptographic
    role (that is handled separately by the HMAC header in client.py).
    """
    return {
        "signerName": FILER_CONFIG["signerName"],
        "signerTitle": FILER_CONFIG["signerTitle"],
        "signedAtUtc": _format_utc(signed_at),
    }


def _format_utc(dt: datetime) -> str:
    """Format a UTC datetime as ISO 8601 with second precision and trailing Z."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
