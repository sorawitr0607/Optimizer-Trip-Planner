"""Paid-provider usage ledger and the monthly spend cap.

Pure: no Streamlit, SQLite, provider, exporter, or model imports.

The locked budget rule is a warning at US$8 and a hard stop at US$10 for new
paid calls in a calendar month, unless the owner raises the cap.  Free-tier
operations are still recorded, priced at zero, so the ledger reconciles calls as
well as spend.
"""

from __future__ import annotations

from typing import Any


WARN_USD = 8.0
CAP_USD = 10.0

OK = "ok"
WARNING = "warning"
STOPPED = "stopped"

# Estimated unit price per request. Free-tier operations are priced at zero and
# still recorded, so call counts stay reconcilable.
PRICES_USD = {
    "openstreetmap:discover": 0.0,
    "openrouteservice:directions": 0.0,
    "openrouteservice:matrix": 0.0,
    "google_places:details": 0.017,
    # Current Text Search Enterprise + Atmosphere and Place Photo list prices,
    # conservatively tracked even when the account is still inside its free cap.
    "google_places:card_details": 0.040,
    "google_places:photo": 0.007,
    # Text search carrying opening hours falls in the dearer field tier. Priced
    # high rather than low: an over-estimate protects the cap, an
    # under-estimate spends past it.
    "google_places:search_text": 0.025,
    "google_routes:compute": 0.005,
    "google_timezone:lookup": 0.005,
    # One small structured-output call. Priced conservatively above the
    # token cost of a short request and reply.
    "openai:interpret_revision": 0.002,
    "openai:explain_revision": 0.004,
}


def price_for(operation: str, count: int = 1) -> float:
    """Estimated cost of `count` requests, or a refusal for an unknown operation."""

    if operation not in PRICES_USD:
        raise ValueError(f"Unpriced paid operation: {operation}")
    if count < 0:
        raise ValueError("count cannot be negative")
    return round(PRICES_USD[operation] * count, 6)


def month_of(timestamp: str) -> str:
    text = str(timestamp or "")
    if len(text) < 7:
        raise ValueError(f"Cannot read a month from {timestamp!r}")
    return text[:7]


def totals(entries: list[dict[str, Any]], *, month: str) -> dict[str, Any]:
    """Spend and call counts for one calendar month, per operation."""

    scoped = [item for item in entries if month_of(item["created_at"]) == month]
    by_operation: dict[str, dict[str, Any]] = {}
    for item in scoped:
        key = str(item["operation"])
        bucket = by_operation.setdefault(key, {"requests": 0, "estimated_usd": 0.0})
        bucket["requests"] += int(item.get("request_count") or 0)
        bucket["estimated_usd"] = round(
            bucket["estimated_usd"] + float(item.get("estimated_usd") or 0.0), 6
        )
    return {
        "month": month,
        "requests": sum(int(item.get("request_count") or 0) for item in scoped),
        "estimated_usd": round(
            sum(float(item.get("estimated_usd") or 0.0) for item in scoped), 6
        ),
        "by_operation": dict(sorted(by_operation.items())),
        "entries": len(scoped),
    }


def status(spent_usd: float, *, cap_usd: float = CAP_USD) -> dict[str, Any]:
    """Where this month sits against the warning threshold and the cap."""

    spent = round(float(spent_usd), 6)
    cap = float(cap_usd)
    warn_at = min(WARN_USD, cap)
    if spent >= cap:
        state = STOPPED
    elif spent >= warn_at:
        state = WARNING
    else:
        state = OK
    return {
        "state": state,
        "spent_usd": spent,
        "cap_usd": round(cap, 2),
        "warn_at_usd": round(warn_at, 2),
        "remaining_usd": round(max(0.0, cap - spent), 6),
    }


def check_allowed(
    *, operation: str, count: int, spent_usd: float, cap_usd: float = CAP_USD
) -> dict[str, Any]:
    """Decide one prospective paid call before it is made.

    A free-tier operation is always allowed: it costs nothing, so the cap has
    nothing to protect. A priced call is refused when it would cross the cap.
    """

    estimate = price_for(operation, count)
    current = status(spent_usd, cap_usd=cap_usd)
    projected = round(current["spent_usd"] + estimate, 6)
    if estimate == 0.0:
        return {**current, "allowed": True, "estimate_usd": 0.0, "projected_usd": current["spent_usd"], "reason": None}
    if current["state"] == STOPPED:
        return {
            **current,
            "allowed": False,
            "estimate_usd": estimate,
            "projected_usd": projected,
            "reason": (
                f"Monthly paid cap of US${current['cap_usd']:.2f} reached; "
                "raise the cap to continue"
            ),
        }
    if projected > current["cap_usd"]:
        return {
            **current,
            "allowed": False,
            "estimate_usd": estimate,
            "projected_usd": projected,
            "reason": (
                f"This call would reach US${projected:.4f}, above the "
                f"US${current['cap_usd']:.2f} cap"
            ),
        }
    return {
        **current,
        "allowed": True,
        "estimate_usd": estimate,
        "projected_usd": projected,
        "reason": None,
    }


def new_entry(
    *,
    operation: str,
    count: int,
    created_at: str,
    trip_id: str | None = None,
    outcome: str = "success",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One ledger row. Detail never carries a key, only redacted context."""

    if outcome not in {"success", "error", "cached"}:
        raise ValueError(f"Unsupported usage outcome: {outcome}")
    provider = operation.split(":", 1)[0]
    # A cached read makes no request, so it costs nothing but is still recorded.
    billable = 0 if outcome == "cached" else count
    return {
        "operation": operation,
        "provider": provider,
        "trip_id": trip_id,
        "request_count": billable,
        "estimated_usd": price_for(operation, billable),
        "outcome": outcome,
        "created_at": created_at,
        "detail": dict(detail or {}),
    }
