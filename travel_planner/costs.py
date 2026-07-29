"""Owner-recorded trip costs in THB plus their original currency.

Pure: no Streamlit, SQLite, provider, exporter, or model imports.

Thai baht is the reporting currency, but every expense keeps its original
amount and ISO currency.  Conversion uses a sourced, timestamped rate snapshot
the owner may edit or buffer.  A missing rate stays a visible gap; a rate is
never invented.  Once an expense is paid its actual THB charge is locked, so a
later rate cannot rewrite what was already spent.
"""

from __future__ import annotations

from typing import Any


BASE_CURRENCY = "THB"
CATEGORIES = (
    "transport",
    "accommodation",
    "activity",
    "food",
    "fees",
    "shopping",
    "other",
)
# An estimate may be re-converted; a paid charge is history.
PAYMENT_STATES = ("estimate", "committed", "paid")
LOCKED_STATES = frozenset({"paid"})


def new_rate_snapshot(
    *,
    rates: dict[str, Any],
    as_of: str,
    source: str,
    buffer_percent: float = 0.0,
) -> dict[str, Any]:
    """One timestamped set of THB-per-unit rates, with an optional buffer."""

    if not str(as_of or "").strip():
        raise ValueError("An exchange-rate snapshot needs its as-of date")
    if not str(source or "").strip():
        raise ValueError("An exchange-rate snapshot needs its source")
    if float(buffer_percent) < 0 or float(buffer_percent) > 50:
        raise ValueError("buffer_percent must be between 0 and 50")
    clean: dict[str, float] = {BASE_CURRENCY: 1.0}
    for currency, rate in (rates or {}).items():
        code = _currency(currency)
        value = float(rate)
        if value <= 0:
            raise ValueError(f"Rate for {code} must be positive")
        clean[code] = value
    return {
        "rates": dict(sorted(clean.items())),
        "as_of": str(as_of).strip(),
        "source": str(source).strip(),
        "buffer_percent": round(float(buffer_percent), 2),
    }


def validate_cost(item: dict[str, Any]) -> dict[str, Any]:
    """Reject a cost row that breaks the agreed contract."""

    label = str(item.get("label") or "").strip()
    if not label:
        raise ValueError("A cost needs a label")
    if item.get("category") not in CATEGORIES:
        raise ValueError(f"Unsupported cost category: {item.get('category')}")
    state = item.get("payment_state")
    if state not in PAYMENT_STATES:
        raise ValueError(f"Unsupported payment state: {state}")
    amount = float(item.get("original_amount") or 0)
    if amount < 0:
        raise ValueError("original_amount cannot be negative")
    currency = _currency(item.get("original_currency"))
    actual = item.get("actual_thb")
    if state in LOCKED_STATES and actual in (None, ""):
        raise ValueError("A paid cost needs its actual THB charge")
    if actual not in (None, "") and float(actual) < 0:
        raise ValueError("actual_thb cannot be negative")
    return {
        **item,
        "label": label,
        "original_currency": currency,
        "original_amount": round(amount, 2),
        "actual_thb": None if actual in (None, "") else round(float(actual), 2),
    }


def apply_rates(
    items: list[dict[str, Any]], snapshot: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Resolve each row's THB value against one rate snapshot."""

    rates = (snapshot or {}).get("rates") or {}
    buffer_percent = float((snapshot or {}).get("buffer_percent") or 0.0)
    resolved = []
    for item in items:
        currency = _currency(item.get("original_currency"))
        rate = rates.get(currency)
        locked = item.get("payment_state") in LOCKED_STATES
        converted = None
        if rate is not None:
            amount = float(item.get("original_amount") or 0)
            factor = 1.0 if currency == BASE_CURRENCY else 1 + buffer_percent / 100
            converted = round(amount * float(rate) * factor, 2)
        resolved.append(
            {
                **item,
                "applied_rate": None if rate is None else float(rate),
                "applied_rate_date": (snapshot or {}).get("as_of"),
                "applied_buffer_percent": (
                    0.0 if currency == BASE_CURRENCY else round(buffer_percent, 2)
                ),
                "converted_thb": converted,
                # A paid charge reports itself, never a re-conversion.
                "reported_thb": item.get("actual_thb") if locked else converted,
                "rate_missing": rate is None,
            }
        )
    return resolved


def totals(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimated and paid THB totals, plus the rows no rate could cover."""

    resolved = [item for item in items if item.get("reported_thb") is not None]
    paid = [item for item in resolved if item.get("payment_state") in LOCKED_STATES]
    unpaid = [item for item in resolved if item.get("payment_state") not in LOCKED_STATES]
    by_category: dict[str, float] = {}
    for item in resolved:
        key = str(item.get("category") or "other")
        by_category[key] = round(
            by_category.get(key, 0.0) + float(item["reported_thb"]), 2
        )
    missing = [
        {
            "label": item.get("label"),
            "original_currency": item.get("original_currency"),
            "original_amount": item.get("original_amount"),
        }
        for item in items
        if item.get("rate_missing")
    ]
    return {
        "base_currency": BASE_CURRENCY,
        "estimated_thb": round(sum(float(item["reported_thb"]) for item in unpaid), 2),
        "paid_thb": round(sum(float(item["reported_thb"]) for item in paid), 2),
        "total_thb": round(sum(float(item["reported_thb"]) for item in resolved), 2),
        "by_category": dict(sorted(by_category.items())),
        "rows": len(items),
        "unconvertible_rows": len(missing),
        "missing_rates": sorted(
            {str(item["original_currency"]) for item in missing}
        ),
        "unconvertible": missing,
    }


def _currency(value: Any) -> str:
    code = str(value or BASE_CURRENCY).strip().upper()
    if not code.isalpha() or len(code) != 3:
        raise ValueError(f"Currency must be a three-letter ISO code: {value!r}")
    return code
