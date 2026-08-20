"""Domain records to their JSON wire shapes.

Pure: no Streamlit, SQLite, provider, exporter or transport imports.

This lived in the HTTP layer, which was fine while HTTP was the only way a result
reached a client. The job queue is a second way, and it did not have this -- it
stored what the action returned through `json.dumps(..., default=str)`, so a
dataclass arrived at the browser as its own Python repr *in a string*. The screen
read `.candidates.data` off that and said "Cannot read properties of undefined".

So it belongs to the core: how a `FrozenSnapshot` becomes JSON is the core's
business, and both callers now ask the same function rather than one of them
approximating it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any

from .core import FrozenSnapshot


def jsonable(value: Any) -> Any:
    """Convert domain records to their frozen JSON wire shapes."""

    if isinstance(value, FrozenSnapshot):
        # The sha256 travels with the data, because a snapshot's identity is the
        # digest of exactly these bytes and the screen re-checks it.
        return {"data": value.as_dict(), "sha256": value.sha256}
    if is_dataclass(value):
        return {field.name: jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value
