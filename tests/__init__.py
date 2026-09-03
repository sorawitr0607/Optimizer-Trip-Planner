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

# And the same promise about the database, for the same reason: a test must never
# be able to reach a real one. `open_store` selects Postgres from any of
# `HOSTED_URL_VARIABLES` and ignores the path it was handed, so a shell that happens to export that
# variable silently redirects every test away from its temp file. That is not a
# hypothetical -- it happened while building the port, and 96 test trips plus
# their setups, choices, discovery runs and split rows were written into the
# owner's hosted database before anyone noticed. The suite clears the variable so
# the redirect cannot reach it.
# Cleared through the store's own list rather than by name, so adding a variable to
# `HOSTED_URL_VARIABLES` cannot leave the suite reachable. `test_store` pins that.
from travel_planner.store import forget_hosted_database  # noqa: E402

forget_hosted_database()
