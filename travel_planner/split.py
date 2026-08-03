"""Group split ledger: who paid, who shares, and who owes whom.

Pure: no Streamlit, SQLite, provider, exporter, or model imports.

A row records money that already moved: one payer, the travellers it is shared
between, and the amount in its original currency.  Share amounts are never
stored -- they are recomputed on read, so there is exactly one rounding rule and
the screen, the workbook and the totals cannot disagree by a satang.

Settlement is a star through the trip's main cardholder with fronted cash netted
off, so every suggested payment has the cardholder at one end.  The cardholder
may end up owing a traveller rather than the reverse, and the wording has to be
able to say so.

Rates come from the cost ledger's snapshot, deliberately without its
``buffer_percent``: the buffer pads estimates, and these rows are history.  An
``actual_thb`` the owner recorded wins permanently and is never re-converted.

Balances are trip-to-date totals.  Settling up is never recorded, so a balance
is a suggestion rather than an outstanding debt, and it does not change after
someone pays it back.
"""

from __future__ import annotations

from typing import Any

# One currency validator across both ledgers: two would let the same code be
# accepted here and refused there.
from .costs import BASE_CURRENCY, CATEGORIES, _currency as currency_code


# `equal_all` and `selected` differ only in how the participant list was chosen;
# the arithmetic is one equal split either way.  `single_payer` is one traveller
# bearing the whole amount, which is that same split across a list of one.
MODES = ("equal_all", "selected", "single_payer")

# Artifact 023: the seven cost categories are the default tag vocabulary, so a
# tag that is one of them maps to itself and most trips need no mapping at all.
# An owner-invented tag falls here until it is assigned, and `other` will
# quietly absorb things -- that is the accepted cost of not blocking data entry.
DEFAULT_CATEGORY = "other"


def validate_row(
    row: dict[str, Any], travellers: tuple[str, ...] | None = None
) -> dict[str, Any]:
    """Reject a split row that breaks the agreed contract."""

    label = str(row.get("label") or "").strip()
    if not label:
        raise ValueError("A split row needs a label")
    mode = row.get("mode")
    if mode not in MODES:
        raise ValueError(f"Unsupported split mode: {mode}")
    payer = str(row.get("paid_by") or "").strip()
    if not payer:
        raise ValueError("A split row needs the traveller who paid")
    participants = [str(person).strip() for person in row.get("participants") or ()]
    if not participants:
        raise ValueError("A split row needs at least one participant")
    if len(participants) != len(set(participants)):
        raise ValueError("participants cannot repeat a traveller")
    if mode == "single_payer" and len(participants) != 1:
        raise ValueError("single_payer splits between exactly one traveller")
    # The roster lives in setup, so membership is only checkable where it is
    # known.  A participant is chosen, never typed, so settlement cannot
    # fracture on `Mum` versus `mum`.
    if travellers is not None:
        unknown = sorted({*participants, payer} - set(travellers))
        if unknown:
            raise ValueError(f"Unknown traveller ids: {', '.join(unknown)}")
    amount = float(row.get("original_amount") or 0)
    if amount < 0:
        raise ValueError("original_amount cannot be negative")
    recorded = row.get("actual_thb")
    if recorded not in (None, "") and float(recorded) < 0:
        raise ValueError("actual_thb cannot be negative")
    return {
        **row,
        "label": label,
        "mode": mode,
        "paid_by": payer,
        "participants": participants,
        "tag": str(row.get("tag") or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY,
        "original_currency": currency_code(row.get("original_currency")),
        "original_amount": round(amount, 2),
        "actual_thb": None if recorded in (None, "") else round(float(recorded), 2),
        "voided": bool(row.get("voided")),
        "cost_id": str(row["cost_id"]).strip() or None if row.get("cost_id") else None,
        "plan_day": row.get("plan_day") or None,
        "place_id": row.get("place_id") or None,
    }


def category_for_tag(tag: Any) -> str:
    """Map an owner-defined tag onto the seven cost categories."""

    key = str(tag or "").strip().lower()
    return key if key in CATEGORIES else DEFAULT_CATEGORY


def apply_rates(
    rows: list[dict[str, Any]], snapshot: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Resolve each row's THB against the cost ledger's snapshot, no buffer."""

    rates = (snapshot or {}).get("rates") or {}
    resolved = []
    for row in rows:
        currency = currency_code(row.get("original_currency"))
        rate = rates.get(currency)
        recorded = row.get("actual_thb")
        locked = recorded not in (None, "")
        converted = None
        if rate is not None:
            converted = round(float(row.get("original_amount") or 0) * float(rate), 2)
        resolved.append(
            {
                **row,
                "category": category_for_tag(row.get("tag")),
                "applied_rate": None if rate is None else float(rate),
                "applied_rate_date": (snapshot or {}).get("as_of"),
                "converted_thb": converted,
                "reported_thb": round(float(recorded), 2) if locked else converted,
                # A recorded charge needs no rate provenance, so it is not a gap.
                "rate_missing": rate is None and not locked,
            }
        )
    return resolved


def shares(row: dict[str, Any]) -> dict[str, float]:
    """One resolved row's THB split per participant."""

    reported = row.get("reported_thb")
    participants = list(row.get("participants") or ())
    if reported is None or not participants:
        return {}
    portions = _split_satang(reported, len(participants))
    return {
        person: round(satang / 100, 2)
        for person, satang in zip(participants, portions)
    }


def summary(
    rows: list[dict[str, Any]],
    *,
    travellers: tuple[str, ...],
    cardholder: str,
    settled: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Actual spend, per-traveller balances, and the star settlement."""

    live = [row for row in rows if not row.get("voided")]
    counted = [row for row in live if row.get("reported_thb") is not None]
    owed: dict[str, int] = {person: 0 for person in travellers}
    fronted: dict[str, int] = {person: 0 for person in travellers}
    by_category: dict[str, int] = {}
    for row in counted:
        # Satang integers accumulate exactly; the float rounding happens once.
        for person, amount in shares(row).items():
            owed[person] = owed.get(person, 0) + round(amount * 100)
        payer = str(row.get("paid_by") or "")
        total = round(float(row["reported_thb"]) * 100)
        fronted[payer] = fronted.get(payer, 0) + total
        key = str(row.get("category") or DEFAULT_CATEGORY)
        by_category[key] = by_category.get(key, 0) + total

    markers = settled or {}
    balances = []
    settlement = []
    for person in travellers:
        net = owed.get(person, 0) - fronted.get(person, 0)
        entry = {
            "traveller_id": person,
            "shares_thb": round(owed.get(person, 0) / 100, 2),
            "paid_out_thb": round(fronted.get(person, 0) / 100, 2),
            "net_thb": round(net / 100, 2),
        }
        balances.append(entry)
        if person == cardholder or net == 0:
            continue
        settlement.append(
            {
                **entry,
                "amount_thb": round(abs(net) / 100, 2),
                "direction": (
                    "traveller_pays_cardholder" if net > 0 else "cardholder_pays_traveller"
                ),
                # A marker records the amount the owner called settled, so any
                # change to the arithmetic silently supersedes it.  Hashes are
                # this repo's staleness mechanism; the amount is that here.
                "settled": _same_money(markers.get(person), net / 100),
            }
        )

    missing = [
        {
            "label": row.get("label"),
            "original_currency": row.get("original_currency"),
            "original_amount": row.get("original_amount"),
        }
        for row in live
        if row.get("rate_missing")
    ]
    return {
        "base_currency": BASE_CURRENCY,
        "cardholder": cardholder,
        "actual_thb": round(sum(by_category.values()) / 100, 2),
        "by_category": {
            key: round(value / 100, 2) for key, value in sorted(by_category.items())
        },
        "rows": len(rows),
        "voided_rows": len(rows) - len(live),
        "balances": balances,
        "settlement": settlement,
        "unconvertible_rows": len(missing),
        "missing_rates": sorted({str(row["original_currency"]) for row in missing}),
        "unconvertible": missing,
    }


# ponytail: 2-decimal floats at the boundary, matching costs.py, with the
# division done in integer satang so the remainder is exact. Move the stored
# values to integer minor units only if a real reconciliation error appears.
def _split_satang(total_thb: float, count: int) -> list[int]:
    """Equal split in satang, remainder one unit at a time from the front.

    The absorber is documented rather than incidental: the first ``remainder``
    participants in the row's own order each take one extra satang.  The donor
    dumped the whole remainder on the first person, which over-charges them by
    up to ``count - 1`` satang; spreading it caps the error at one.
    """

    total = round(float(total_thb) * 100)
    base, remainder = divmod(total, count)
    return [base + (1 if index < remainder else 0) for index in range(count)]


def _same_money(left: Any, right: Any) -> bool:
    if left in (None, ""):
        return False
    return round(float(left) * 100) == round(float(right) * 100)
