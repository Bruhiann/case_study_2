"""
JSON Schema validator.

Wraps jsonschema.Draft202012Validator to validate a manifest dict against
schema/manifest.schema.json (the schema published by the Authority at §3.1).

Design notes:
  - The schema is loaded once at import time so repeated calls are cheap.
  - Returns a list of structured error dicts rather than raising exceptions
    so the pipeline can collect every violation before deciding what to do.
  - Format-level checks (e.g. email syntactic validity per RFC 5322) are NOT
    enforced here. The JSON Schema's "format" keyword is an annotation under
    Draft 2020-12 and is not automatically asserted unless a format checker is
    configured. Email validity is covered by R-003 in the rules engine, which
    produces a more specific error message.
  - Rejection code mapping mirrors the mock Authority's own logic (server.py)
    so that pre-transmission schema errors surface the same codes that the
    Authority would return.
"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator


# ---------------------------------------------------------------------------
# Load the schema once at import time.
# This file lives at filer/src/validator.py; the schema is at
# schema/manifest.schema.json relative to the case-study root.
# ---------------------------------------------------------------------------

_SCHEMA_PATH = (
    Path(__file__).parent  # filer/src
    .parent                 # filer
    .parent                 # case-study root
    / "schema"
    / "manifest.schema.json"
)

with _SCHEMA_PATH.open(encoding="utf-8") as _f:
    _SCHEMA = json.load(_f)

_VALIDATOR = Draft202012Validator(_SCHEMA)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def validate(manifest: dict) -> list[dict]:
    """
    Validate a manifest dict against the Crescent Harbor JSON Schema.

    :param manifest: The manifest dict to validate (as returned by builder.build).
    :returns: List of error dicts. An empty list means the manifest is schema-valid.
              Each error dict contains:
                "code"    — spec rejection code (M-102, M-103, or R-602)
                "path"    — JSON Pointer to the offending field, e.g. "/vessel/name"
                "message" — human-readable description of the violation
    """
    errors = []
    for err in _VALIDATOR.iter_errors(manifest):
        errors.append(_format_error(err))
    return errors


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _format_error(err) -> dict:
    """
    Convert a jsonschema ValidationError into a structured error dict.

    Path is expressed as a JSON Pointer string (e.g. "/containers/0/type").
    Rejection codes follow §11.4:
      M-103 — unrecognized top-level field (additionalProperties violation)
      R-602 — required field missing
      M-102 — all other schema violations
    """
    if err.absolute_path:
        path = "/" + "/".join(str(p) for p in err.absolute_path)
    else:
        path = "/"

    msg = err.message

    if "Additional properties are not allowed" in msg:
        code = "M-103"
    elif "is a required property" in msg:
        code = "R-602"
    else:
        code = "M-102"

    return {"code": code, "path": path, "message": msg}
