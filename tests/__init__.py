"""Test package.

`AppTest` imports `app.py`, which loads `secrets.local.json` into the
environment. Turning that off for the whole suite keeps the promise that tests
make no paid call: a test that somehow reached a real provider fails with
"not configured" rather than spending money.
"""

from __future__ import annotations

import os

os.environ["TOURIST_LOCAL_SECRETS"] = "off"
