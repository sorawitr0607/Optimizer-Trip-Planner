"""Load gitignored local credentials into the environment.

Pure apart from `os.environ` and reading one file: no Streamlit, SQLite,
provider, exporter or LLM imports.

Providers read keys from the environment and nothing else, which is the rule
that keeps a key out of every snapshot, export and log. This module does not
change that rule; it only lets the owner keep the values in
`secrets.local.json` instead of exporting four variables in every new shell.

An already-set variable always wins, so an explicit `export` still overrides the
file. Names are returned so a caller can say what it loaded; values never are,
and nothing here logs, prints or persists them.

Not named `secrets.py`: `from . import secrets` would shadow the standard
library module for anything inside this package.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_PATH = "secrets.local.json"

# The test suite sets this to "off" in `tests/__init__.py`. `AppTest` imports
# `app.py`, so without the switch every test would run holding real keys, and a
# test that reached a real provider would bill instead of failing fast with
# "not configured".
SWITCH = "TOURIST_LOCAL_SECRETS"

# A template ships with empty strings, and an owner half-filling it should not
# look configured. Anything matching these is treated as not set.
PLACEHOLDERS = frozenset({"", "replace_me", "changeme", "your_key_here", "todo"})


def load_local_credentials(path: str | Path = DEFAULT_PATH) -> list[str]:
    """Copy flat string values into `os.environ`; return the names set.

    A missing file is not an error: the environment may already carry the keys,
    which is how CI and a plain `export` are meant to work.
    """

    if os.environ.get(SWITCH, "").strip().casefold() == "off":
        return []
    source = Path(path)
    if not source.is_file():
        return []
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        # Name the file and the reason, never a fragment of its contents.
        raise ValueError(
            f"{source} is not readable JSON: {error.__class__.__name__}"
        ) from error
    if not isinstance(payload, dict):
        raise ValueError(f"{source} must hold a flat object of name to value")

    loaded = []
    for name, value in payload.items():
        key = str(name).strip()
        if not key or not isinstance(value, str):
            # Nested objects and numbers are not environment values; skipping
            # them beats coercing a shape the owner did not intend.
            continue
        if value.strip().casefold() in PLACEHOLDERS:
            continue
        if os.environ.get(key, "").strip():
            continue
        os.environ[key] = value
        loaded.append(key)
    return sorted(loaded)
