"""Test package.

Turning local secret loading off for the whole suite keeps the promise that
tests make no paid call: a test that somehow reached a real provider fails with
"not configured" rather than spending money.

The original reason was that `AppTest` imported `app.py`, which called
`load_local_credentials()` at module scope. Both went with the POC at S6, and
`api/__init__.py` calls it only from `main()`, so nothing in the suite loads
secrets by accident today. The line stays regardless: it costs nothing, and the
failure it prevents is a bill.
"""

from __future__ import annotations

import os

os.environ["TOURIST_LOCAL_SECRETS"] = "off"
