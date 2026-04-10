"""
Business rules engine.

Implements the rules engine for all 25 rule IDs from rules/rules.md against a fully-built manifest
dict. The rule catalog (rules/rules.json) supplies metadata (id, severity,
field, specRef, summary); this module supplies the evaluation logic.

Design
------
_HANDLERS is a dict mapping rule ID → handler function. Adding a new rule
means adding one entry here and writing one function. There are no long
if/elif chains keyed on rule ID.

Each handler has the signature:
    (manifest: dict, rule_meta: dict) -> list[Issue]

An empty list means the rule passed. Both rejections and warnings are
returned as Issue objects; check() partitions them by severity.

Ambiguities resolved (documented inline and in ARCHITECTURE.md)
----------------------------------------------------------------
R-005  Vessel name lowercase: silent normalization — the builder uppercases
       the name before rules run. Any remaining invalid characters are caught
       here as character-set violations.

R-014  HAZ gross weight comparison: the spec compares grossWeightKg (mass in
       kg) to grossRegisterTons (a volumetric unit). Direct numeric comparison
       is dimensionally inconsistent. Decision: convert HAZ weight to metric
       tons (÷ 1000) before comparing to GRT. For example, 18 500 kg ÷ 1 000
       = 18.5 t, which is well within 25% of 52 100 GRT. If any HAZ container
       is missing grossWeightKg the check is skipped and a warning is emitted.

R-023  Filing clock: the check uses datetime.now(UTC) at the moment the rules
       engine runs, which is immediately before transmission. This is the
       client-side send time, consistent with how R-022 is applied.

R-024/R-025  Amendment invariants: without a database of prior accepted
       manifests, we can only verify that amendmentSequence is an integer ≥ 1.
       Cross-submission invariants (imoNumber/eta unchanged, monotonic
       sequence) are documented as out-of-scope for this stateless filer.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path


# ---------------------------------------------------------------------------
# Issue — the unit of output for every rule evaluation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Issue:
    rule_id: str
    severity: str    # "reject" | "warning"
    field_path: str
    message: str

    def to_dict(self) -> dict:
        return {
            "ruleId": self.rule_id,
            "severity": self.severity,
            "fieldPath": self.field_path,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Load the rule catalog from rules/rules.json once at import time.
# Metadata (severity, field, specRef, summary) lives in the JSON;
# evaluation logic lives in this module.
# ---------------------------------------------------------------------------

_CATALOG_PATH = (
    Path(__file__).parent   # filer/src
    .parent                  # filer
    .parent                  # case-study root
    / "rules"
    / "rules.json"
)

with _CATALOG_PATH.open(encoding="utf-8") as _f:
    _CATALOG: dict[str, dict] = {
        r["id"]: r for r in json.load(_f)["rules"]
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def check(manifest: dict) -> tuple[list[Issue], list[Issue]]:
    """
    Run the rules engine across all 25 rule IDs against a manifest dict.
    R-024 and R-025 are enforced in a documented stateless, partial form.

    :param manifest: A fully-built manifest dict (output of builder.build).
    :returns: (rejections, warnings)
              rejections — severity="reject" issues that block transmission
              warnings   — severity="warning" issues for operational visibility
    """
    all_issues: list[Issue] = []
    for rule_id, handler in _HANDLERS.items():
        all_issues.extend(handler(manifest, _CATALOG[rule_id]))

    rejections = [i for i in all_issues if i.severity == "reject"]
    warnings   = [i for i in all_issues if i.severity == "warning"]
    return rejections, warnings


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _issue(rule_meta: dict, field_path: str | None, message: str) -> Issue:
    """Construct an Issue from rule metadata and a runtime message."""
    return Issue(
        rule_id=rule_meta["id"],
        severity=rule_meta["severity"],
        field_path=field_path or rule_meta.get("field", "/"),
        message=message,
    )


def _round_half_away(value) -> Decimal:
    """Round a numeric value to 2 decimal places, half-away-from-zero."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _age_at_date(dob: date, reference: date) -> int:
    """Return whole-year age at the reference date."""
    age = reference.year - dob.year
    if (reference.month, reference.day) < (dob.month, dob.day):
        age -= 1
    return age


# ---------------------------------------------------------------------------
# Rule handlers — grouped by category, one function per rule.
# ---------------------------------------------------------------------------

# ---- Identity rules (R-001 – R-003) --------------------------------------

def _r001_manifest_id(manifest: dict, rule_meta: dict) -> list[Issue]:
    """manifestId must be 12–32 chars from [A-Z0-9-]. No lowercase tolerated."""
    value = manifest.get("manifestId", "")
    if not re.fullmatch(r"[A-Z0-9\-]{12,32}", value):
        return [_issue(rule_meta, "/manifestId",
                       f"manifestId '{value}' must be 12–32 characters "
                       "drawn from [A-Z0-9-] with no lowercase letters")]
    return []


def _r002_filer_id(manifest: dict, rule_meta: dict) -> list[Issue]:
    """filerId must be three uppercase letters followed by six digits."""
    value = manifest.get("filer", {}).get("filerId", "")
    if not re.fullmatch(r"[A-Z]{3}[0-9]{6}", value):
        return [_issue(rule_meta, "/filer/filerId",
                       f"filerId '{value}' must be three uppercase letters "
                       "followed by six digits (e.g. CHC100001)")]
    return []


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

def _r003_contact_email(manifest: dict, rule_meta: dict) -> list[Issue]:
    """contactEmail must be syntactically valid per RFC 5322 §3.4.1."""
    value = manifest.get("filer", {}).get("contactEmail", "")
    if not _EMAIL_RE.match(value):
        return [_issue(rule_meta, "/filer/contactEmail",
                       f"contactEmail '{value}' is not a valid email address")]
    return []


# ---- Vessel rules (R-004 – R-007) ----------------------------------------

def _r004_imo_check_digit(manifest: dict, rule_meta: dict) -> list[Issue]:
    """
    IMO check-digit algorithm: multiply the first six digits by weights
    [7, 6, 5, 4, 3, 2], sum the products; the last digit of the sum must
    equal the seventh digit.
    """
    imo = manifest.get("vessel", {}).get("imoNumber", "")
    digits_str = imo[3:] if imo.startswith("IMO") else ""
    if len(digits_str) != 7 or not digits_str.isdigit():
        return []   # Malformed format — schema validation handles this.

    digits = [int(d) for d in digits_str]
    total = sum(d * w for d, w in zip(digits[:6], [7, 6, 5, 4, 3, 2]))
    if (total % 10) != digits[6]:
        return [_issue(rule_meta, "/vessel/imoNumber",
                       f"IMO check digit invalid for '{imo}': "
                       f"expected {total % 10}, got {digits[6]}")]
    return []


def _r005_vessel_name_chars(manifest: dict, rule_meta: dict) -> list[Issue]:
    """
    Vessel name must consist only of [A-Z0-9 .-] after normalization.
    The builder has already uppercased the name; any remaining invalid
    characters indicate non-letter content that cannot be normalized.
    """
    name = manifest.get("vessel", {}).get("name", "")
    if not re.fullmatch(r"[A-Z0-9 .\-]+", name):
        return [_issue(rule_meta, "/vessel/name",
                       f"vessel name '{name}' contains characters "
                       "outside [A-Z0-9 .-]")]
    return []


def _r006_gross_register_tons(manifest: dict, rule_meta: dict) -> list[Issue]:
    """Vessel grossRegisterTons must be greater than 500."""
    grt = manifest.get("vessel", {}).get("grossRegisterTons", 0)
    if grt <= 500:
        return [_issue(rule_meta, "/vessel/grossRegisterTons",
                       f"grossRegisterTons {grt} must be greater than 500")]
    return []


_VESSEL_TERMINAL: dict[str, set[str]] = {
    "CONTAINER": {"CH-A", "CH-B"},
    "BULK":      {"CH-C"},
    "TANKER":    {"CH-C"},
    "RORO":      {"CH-D"},
    "GENERAL":   {"CH-A", "CH-B", "CH-C", "CH-D"},
}

def _r007_vessel_type_terminal(manifest: dict, rule_meta: dict) -> list[Issue]:
    """Vessel type must be consistent with the arrival terminal (§4.3)."""
    vessel_type = manifest.get("vessel", {}).get("vesselType", "")
    terminal = manifest.get("arrival", {}).get("terminal", "")
    allowed = _VESSEL_TERMINAL.get(vessel_type)
    if allowed is None:
        return []   # Unknown type — schema catches invalid enums.
    if terminal not in allowed:
        return [_issue(rule_meta, "/arrival/terminal",
                       f"vessel type {vessel_type} may not arrive at "
                       f"terminal {terminal} (allowed: {sorted(allowed)})")]
    return []


# ---- Container structural rules (R-008 – R-012) --------------------------

def _r008_container_id_uniqueness(manifest: dict, rule_meta: dict) -> list[Issue]:
    """containerId values must be unique within a single Manifest."""
    seen: set[str] = set()
    issues: list[Issue] = []
    for i, container in enumerate(manifest.get("containers", [])):
        cid = container.get("containerId", "")
        if cid in seen:
            issues.append(_issue(rule_meta, f"/containers/{i}/containerId",
                                 f"containerId '{cid}' appears more than once "
                                 "in this manifest"))
        seen.add(cid)
    return issues


def _r009_at_least_one_container(manifest: dict, rule_meta: dict) -> list[Issue]:
    """The containers array must contain at least one entry."""
    if not manifest.get("containers"):
        return [_issue(rule_meta, "/containers",
                       "containers array must contain at least one entry")]
    return []


def _r010_ballast_exclusivity(manifest: dict, rule_meta: dict) -> list[Issue]:
    """A BALLAST container must be the only container in the manifest."""
    containers = manifest.get("containers", [])
    has_ballast = any(c.get("type") == "BALLAST" for c in containers)
    if has_ballast and len(containers) > 1:
        return [_issue(rule_meta, "/containers",
                       f"BALLAST container must be the sole container; "
                       f"found {len(containers)} containers total")]
    return []


def _r011_reserved_commodity_code(manifest: dict, rule_meta: dict) -> list[Issue]:
    """REF container commodityCode may not be the reserved value '0000'."""
    issues: list[Issue] = []
    for i, c in enumerate(manifest.get("containers", [])):
        if c.get("type") == "REF" and c.get("commodityCode") == "0000":
            issues.append(_issue(rule_meta, f"/containers/{i}/commodityCode",
                                 f"REF container '{c.get('containerId')}' uses "
                                 "reserved commodityCode '0000'"))
    return issues


def _r012_vin_list_length(manifest: dict, rule_meta: dict) -> list[Issue]:
    """For each VEH container, vins.length must equal the container's quantity."""
    issues: list[Issue] = []
    for i, c in enumerate(manifest.get("containers", [])):
        if c.get("type") != "VEH":
            continue
        qty = c.get("quantity", 0)
        vins = c.get("vins", [])
        if len(vins) != qty:
            issues.append(_issue(rule_meta, f"/containers/{i}/vins",
                                 f"VEH container '{c.get('containerId')}' has "
                                 f"quantity={qty} but {len(vins)} VIN(s) listed"))
    return issues


# ---- Hazardous materials rules (R-013 – R-015) ---------------------------

def _r013_class7_prior_auth(manifest: dict, rule_meta: dict) -> list[Issue]:
    """HAZ containers with hazardClass '7' must carry priorAuthorizationRef."""
    issues: list[Issue] = []
    for i, c in enumerate(manifest.get("containers", [])):
        if c.get("type") == "HAZ" and c.get("hazardClass") == "7":
            if not c.get("priorAuthorizationRef"):
                issues.append(_issue(
                    rule_meta, f"/containers/{i}/priorAuthorizationRef",
                    f"HAZ container '{c.get('containerId')}' is class 7 "
                    "(Radioactive Material) and requires priorAuthorizationRef",
                ))
    return issues


def _r014_hazmat_weight_proportion(manifest: dict, rule_meta: dict) -> list[Issue]:
    """
    Combined HAZ gross weight must not exceed 25% of vessel GRT.

    Unit assumption (R-014 ambiguity): grossWeightKg is in kilograms; the spec
    compares it directly to grossRegisterTons, a volumetric measure. A raw
    numeric comparison would give a dimensionally inconsistent result and
    would wrongly reject valid manifests. Decision: convert grossWeightKg to
    metric tons (÷ 1000) before comparing to GRT as a weight-equivalent figure.

    If any HAZ container lacks grossWeightKg the check cannot be completed
    accurately and is skipped; a warning is emitted instead.
    """
    containers = manifest.get("containers", [])
    haz = [c for c in containers if c.get("type") == "HAZ"]
    if not haz:
        return []

    missing = [c for c in haz if "grossWeightKg" not in c]
    if missing:
        cids = [c.get("containerId") for c in missing]
        return [Issue(
            rule_id=rule_meta["id"],
            severity="warning",
            field_path="/containers",
            message=(
                "R-014 hazmat weight check skipped — grossWeightKg missing on "
                f"container(s) {cids}; cannot verify the 25% GRT limit"
            ),
        )]

    grt = manifest.get("vessel", {}).get("grossRegisterTons", 0)
    total_haz_t = sum(c["grossWeightKg"] for c in haz) / 1000   # kg → metric tons
    limit_t = grt * 0.25
    if total_haz_t > limit_t:
        return [_issue(rule_meta, "/containers",
                       f"combined HAZ weight {total_haz_t:.3f} t exceeds "
                       f"25% of vessel GRT ({grt} → limit {limit_t:.1f} t)")]
    return []


def _r015_hazmat_warning(manifest: dict, rule_meta: dict) -> list[Issue]:
    """Emit a warning (not a rejection) when any HAZ container is present."""
    haz = [c for c in manifest.get("containers", []) if c.get("type") == "HAZ"]
    if haz:
        cids = [c.get("containerId") for c in haz]
        return [_issue(rule_meta, "/containers",
                       f"manifest contains {len(haz)} HAZ container(s) {cids}; "
                       "flagged for harbormaster review per §6.1")]
    return []


# ---- Cargo valuation rules (R-016 – R-018) --------------------------------

def _r016_declared_value_sum(manifest: dict, rule_meta: dict) -> list[Issue]:
    """
    declaredValueTotal must equal the sum of all container declaredValueUSD
    values, each rounded to 2 d.p. using half-away-from-zero.
    Uses Decimal arithmetic throughout to avoid floating-point drift.
    """
    containers = manifest.get("containers", [])
    computed = sum(
        _round_half_away(c.get("declaredValueUSD", 0)) for c in containers
    )
    stated = _round_half_away(manifest.get("declaredValueTotal", 0))
    if computed != stated:
        diff = abs(computed - stated)
        return [_issue(rule_meta, "/declaredValueTotal",
                       f"declaredValueTotal {stated} does not match the "
                       f"computed container sum {computed} "
                       f"(difference: {diff})")]
    return []


def _r017_declared_value_cap(manifest: dict, rule_meta: dict) -> list[Issue]:
    """declaredValueTotal must not exceed USD 500,000,000."""
    total = manifest.get("declaredValueTotal", 0)
    cap = 500_000_000
    if total > cap:
        return [_issue(rule_meta, "/declaredValueTotal",
                       f"declaredValueTotal {total} exceeds the "
                       f"USD {cap:,} maximum")]
    return []


def _r018_container_value_precision(manifest: dict, rule_meta: dict) -> list[Issue]:
    """
    Warning: each container's declaredValueUSD should have at most 2 decimal
    places. The Authority rounds higher-precision values downstream; we surface
    this for source data quality.
    """
    issues: list[Issue] = []
    for i, c in enumerate(manifest.get("containers", [])):
        value = c.get("declaredValueUSD")
        if value is None:
            continue
        if Decimal(str(value)) != _round_half_away(value):
            issues.append(_issue(
                rule_meta, f"/containers/{i}/declaredValueUSD",
                f"container '{c.get('containerId')}' declaredValueUSD {value} "
                "has more than 2 decimal places and will be rounded by the Authority",
            ))
    return issues


# ---- Crew rules (R-019 – R-021) ------------------------------------------

def _r019_exactly_one_master(manifest: dict, rule_meta: dict) -> list[Issue]:
    """The crew array must contain exactly one entry with role='MASTER'."""
    masters = [m for m in manifest.get("crew", []) if m.get("role") == "MASTER"]
    if len(masters) != 1:
        return [_issue(rule_meta, "/crew",
                       f"manifest has {len(masters)} crew member(s) with role "
                       "MASTER; exactly one is required")]
    return []


def _r020_crew_age_range(manifest: dict, rule_meta: dict) -> list[Issue]:
    """
    Every crew member's age on the ETA date must be between 16 and 80 inclusive.
    Age is computed as the number of full years between dateOfBirth and the
    date portion of arrival.eta.
    """
    eta_str = manifest.get("arrival", {}).get("eta", "")
    try:
        eta_date = datetime.strptime(eta_str, "%Y-%m-%dT%H:%M:%SZ").date()
    except ValueError:
        return []   # Malformed ETA — schema catches this.

    issues: list[Issue] = []
    for i, member in enumerate(manifest.get("crew", [])):
        dob_str = member.get("dateOfBirth", "")
        try:
            dob = date.fromisoformat(dob_str)
        except ValueError:
            continue   # Malformed date — schema catches this.
        age = _age_at_date(dob, eta_date)
        if not (16 <= age <= 80):
            issues.append(_issue(
                rule_meta, f"/crew/{i}/dateOfBirth",
                f"crew member '{member.get('fullName')}' is {age} years old "
                "at ETA; must be between 16 and 80",
            ))
    return issues


def _r021_master_nationality(manifest: dict, rule_meta: dict) -> list[Issue]:
    """The crew member with role=MASTER must have a non-empty nationality."""
    for member in manifest.get("crew", []):
        if member.get("role") == "MASTER" and not member.get("nationality"):
            return [_issue(rule_meta, "/crew/nationality",
                           f"master '{member.get('fullName')}' "
                           "is missing nationality")]
    return []


# ---- Filing window rules (R-022 – R-023) ----------------------------------

def _r022_not_too_early(manifest: dict, rule_meta: dict) -> list[Issue]:
    """Manifest may not be transmitted earlier than 96 hours before ETA."""
    eta_str = manifest.get("arrival", {}).get("eta", "")
    try:
        eta_dt = datetime.strptime(eta_str, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return []
    now = datetime.now(tz=timezone.utc)
    earliest = eta_dt - timedelta(hours=96)
    if now < earliest:
        hours_early = (earliest - now).total_seconds() / 3600
        return [_issue(rule_meta, "/arrival/eta",
                       f"filing is {hours_early:.1f} h too early; "
                       f"earliest allowed: {earliest.strftime('%Y-%m-%dT%H:%M:%SZ')}")]
    return []


def _r023_not_too_late(manifest: dict, rule_meta: dict) -> list[Issue]:
    """
    Manifest may not be transmitted later than 24 hours before ETA.
    Clock: datetime.now(UTC) at the moment this check runs (client send time).
    """
    eta_str = manifest.get("arrival", {}).get("eta", "")
    try:
        eta_dt = datetime.strptime(eta_str, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return []
    now = datetime.now(tz=timezone.utc)
    latest = eta_dt - timedelta(hours=24)
    if now > latest:
        hours_late = (now - latest).total_seconds() / 3600
        return [_issue(rule_meta, "/arrival/eta",
                       f"filing is {hours_late:.1f} h too late; "
                       f"latest allowed: {latest.strftime('%Y-%m-%dT%H:%M:%SZ')}")]
    return []


# ---- Amendment rules (R-024 – R-025) -------------------------------------

def _r024_amendment_invariants(manifest: dict, rule_meta: dict) -> list[Issue]:
    """
    If amendmentSequence is present, verify it is an integer ≥ 1.
    Cross-submission invariants (manifestId reuse, imoNumber/eta unchanged)
    cannot be verified without a prior-manifest store; that limitation is
    documented in ARCHITECTURE.md.
    """
    seq = manifest.get("amendmentSequence")
    if seq is None:
        return []   # Original filing; amendment rules do not apply.
    if not isinstance(seq, int) or seq < 1:
        return [_issue(rule_meta, "/amendmentSequence",
                       f"amendmentSequence must be an integer ≥ 1, got {seq!r}")]
    return []


def _r025_amendment_sequence_monotonic(manifest: dict, rule_meta: dict) -> list[Issue]:
    """
    First amendment must be sequence 1; each subsequent must increment by 1.
    Stateless check: verify amendmentSequence ≥ 1. Monotonicity across
    prior submissions cannot be verified without a manifest store.
    """
    seq = manifest.get("amendmentSequence")
    if seq is None:
        return []   # Original filing.
    if not isinstance(seq, int) or seq < 1:
        return [_issue(rule_meta, "/amendmentSequence",
                       f"amendmentSequence must start at 1 and increment by 1; "
                       f"got {seq!r}")]
    return []


# ---------------------------------------------------------------------------
# Handler dispatch table.
# This is the only place rule IDs are listed; everything else is driven by
# the catalog metadata loaded from rules.json above.
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Callable[[dict, dict], list[Issue]]] = {
    "R-001": _r001_manifest_id,
    "R-002": _r002_filer_id,
    "R-003": _r003_contact_email,
    "R-004": _r004_imo_check_digit,
    "R-005": _r005_vessel_name_chars,
    "R-006": _r006_gross_register_tons,
    "R-007": _r007_vessel_type_terminal,
    "R-008": _r008_container_id_uniqueness,
    "R-009": _r009_at_least_one_container,
    "R-010": _r010_ballast_exclusivity,
    "R-011": _r011_reserved_commodity_code,
    "R-012": _r012_vin_list_length,
    "R-013": _r013_class7_prior_auth,
    "R-014": _r014_hazmat_weight_proportion,
    "R-015": _r015_hazmat_warning,
    "R-016": _r016_declared_value_sum,
    "R-017": _r017_declared_value_cap,
    "R-018": _r018_container_value_precision,
    "R-019": _r019_exactly_one_master,
    "R-020": _r020_crew_age_range,
    "R-021": _r021_master_nationality,
    "R-022": _r022_not_too_early,
    "R-023": _r023_not_too_late,
    "R-024": _r024_amendment_invariants,
    "R-025": _r025_amendment_sequence_monotonic,
}
