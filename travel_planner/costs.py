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
# The defaults, not the whole of it, as of 2026-08-11. Artifact 023 made these
# seven the fixed vocabulary shared by the cost ledger, the split ledger and both
# workbooks; the donor let a trip edit its own list, and a trip that hires skis or
# pays a visa agent has nowhere to put that but `other`. A trip may now add to
# these -- see `PlannerActions.cost_categories` -- and every seven stays, because
# they are what an unassigned tag falls back to and what the reference workbooks
# are matched against.
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
# Picker convenience for the costs form, not a restriction: `_currency` still
# accepts any three-letter ISO code, so a trip outside this list can record its
# own currency by typing it.
COMMON_CURRENCIES = (
    "THB",
    "TWD",
    "JPY",
    "KRW",
    "CNY",
    "HKD",
    "SGD",
    "MYR",
    "VND",
    "IDR",
    "PHP",
    "INR",
    "AED",
    "USD",
    "EUR",
    "GBP",
    "CHF",
    "CZK",
    "TRY",
    "CAD",
    "MXN",
    "BRL",
    "ARS",
    "AUD",
    "NZD",
)


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


def validate_cost(
    item: dict[str, Any], allowed: tuple[str, ...] | None = None
) -> dict[str, Any]:
    """Reject a cost row that breaks the agreed contract.

    `allowed` is the trip's own category vocabulary. It defaults to the seven so
    every existing caller and fixture is unaffected, and so this module stays
    usable without a trip in hand.
    """

    vocabulary = tuple(allowed) if allowed else CATEGORIES
    label = str(item.get("label") or "").strip()
    if not label:
        raise ValueError("A cost needs a label")
    if item.get("category") not in vocabulary:
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

    # THB is already the reporting currency; it never needs an exchange-rate snapshot.
    rates = {BASE_CURRENCY: 1.0, **((snapshot or {}).get("rates") or {})}
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


def totals(
    items: list[dict[str, Any]],
    split_rows: list[dict[str, Any]] | None = None,
    headcount: int | None = None,
) -> dict[str, Any]:
    """Estimated and paid THB totals, plus the rows no rate could cover.

    ``planned_thb`` and ``actual_thb`` are additions, not redefinitions.
    ``estimated_thb`` remains the sum of non-paid rows -- what is still to pay --
    which is why it cannot serve as the plan figure once a row is marked paid.

    A split row claims a cost row through its ``cost_id``, and a claimed row
    defers its actual to the split side.  So a paid cost row either supplies its
    own actual or a split row does, never both, and double counting is
    structurally impossible rather than merely avoided.
    """

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

    # Claimed-ness is derived here and nowhere else, so there is no second state
    # to keep in sync. Voiding a split row releases its claim by the same rule.
    live_split = [row for row in (split_rows or ()) if not row.get("voided")]
    claimed = {str(row["cost_id"]) for row in live_split if row.get("cost_id")}
    counted_split = [row for row in live_split if row.get("reported_thb") is not None]
    unclaimed_paid = [
        item for item in paid if str(item.get("cost_id") or "") not in claimed
    ]
    # The plan figure is every row's estimate at the current rate, including
    # rows later marked paid -- not `reported_thb`, which for a paid row is the
    # locked charge and so would compare the actual against itself.
    planned_rows = [item for item in items if item.get("converted_thb") is not None]

    planned_by: dict[str, list[float]] = {}
    for item in planned_rows:
        planned_by.setdefault(str(item.get("category") or "other"), []).append(
            float(item["converted_thb"])
        )
    actual_by: dict[str, list[float]] = {}
    for row in counted_split:
        actual_by.setdefault(str(row.get("category") or "other"), []).append(
            float(row["reported_thb"])
        )
    for item in unclaimed_paid:
        actual_by.setdefault(str(item.get("category") or "other"), []).append(
            float(item["reported_thb"])
        )
    comparison = {}
    for key in sorted(set(planned_by) | set(actual_by)):
        planned_value = round(sum(planned_by.get(key, ())), 2)
        actual_value = round(sum(actual_by.get(key, ())), 2)
        comparison[key] = {
            "planned_thb": planned_value,
            "actual_thb": actual_value,
            "difference_thb": round(actual_value - planned_value, 2),
            # A category with a plan and no spend is not the same as one with
            # spend and no plan; a zero in either column would say it was.
            "planned": key in planned_by,
            "actual": key in actual_by,
        }

    planned_total = round(sum(float(item["converted_thb"]) for item in planned_rows), 2)
    actual_total = round(
        sum(float(row["reported_thb"]) for row in counted_split)
        + sum(float(item["reported_thb"]) for item in unclaimed_paid),
        2,
    )
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
        "planned_thb": planned_total,
        "actual_thb": actual_total,
        "by_category_comparison": comparison,
        "claimed_cost_ids": sorted(claimed),
        # Paid rows nobody is sharing. Their money counts as actual, so it is
        # not double counted -- the gap is that it is not being split.
        "unclaimed_paid_rows": len(unclaimed_paid),
        "categories_without_plan": [
            key for key, entry in comparison.items() if not entry["planned"]
        ],
        # An estimate has no participants, so headcount is all there is. The
        # actual per person comes from split.py's resolved shares instead, and
        # the two must never be presented as the same kind of number.
        # None means the caller did not ask. A trip with no members recorded
        # still divides by one rather than vanishing.
        "planned_per_person_thb": (
            None
            if headcount is None
            else round(planned_total / max(int(headcount), 1), 2)
        ),
    }


def _currency(value: Any) -> str:
    code = str(value or BASE_CURRENCY).strip().upper()
    if not code.isalpha() or len(code) != 3:
        raise ValueError(f"Currency must be a three-letter ISO code: {value!r}")
    return code
