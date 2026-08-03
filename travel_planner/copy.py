"""Load the bilingual catalogue shared by Python exports and the webapp."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CATALOGUE_PATH = Path(__file__).resolve().parents[1] / "i18n" / "copy.json"
TABLE_NAMES = (
    "TEXT",
    "TAG_TEXT",
    "EXPLANATION_TEXT",
    "REJECTION_TEXT",
    "DIMENSION_TEXT",
    "ACCOMMODATION_TEXT",
    "CATEGORY_TEXT",
    "OPTIMIZER_CODE_TEXT",
)


def _load() -> dict[str, Any]:
    data = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    if set(data) != set(TABLE_NAMES):
        raise RuntimeError("copy.json must contain the eight declared copy tables")
    for name, table in data.items():
        if set(table) != {"en", "th"}:
            raise RuntimeError(f"{name} must contain en and th")
    # JSON has no null object key. Python's legacy POC uses None for "no reason".
    for language in ("en", "th"):
        table = data["REJECTION_TEXT"][language]
        table[None] = table.pop("null")
    return data


_CATALOGUE = _load()
TEXT = _CATALOGUE["TEXT"]
TAG_TEXT = _CATALOGUE["TAG_TEXT"]
EXPLANATION_TEXT = _CATALOGUE["EXPLANATION_TEXT"]
REJECTION_TEXT = _CATALOGUE["REJECTION_TEXT"]
DIMENSION_TEXT = _CATALOGUE["DIMENSION_TEXT"]
ACCOMMODATION_TEXT = _CATALOGUE["ACCOMMODATION_TEXT"]
CATEGORY_TEXT = _CATALOGUE["CATEGORY_TEXT"]
OPTIMIZER_CODE_TEXT = _CATALOGUE["OPTIMIZER_CODE_TEXT"]
