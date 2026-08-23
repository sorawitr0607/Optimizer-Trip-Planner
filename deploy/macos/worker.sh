#!/usr/bin/env bash
# Start the job worker against the hosted queue.
#
# The one command that has to be right, wrapped so it can be right once. Every
# rule this repo has learned about starting a worker is enforced here rather
# than remembered:
#
#   - `TOURIST_DB_URL` is read from `POSTGRES_URL_NON_POOLING`, because the
#     `TOURIST_DB_URL` line in `.env` is a *template* — the literal string
#     "$POSTGRES_URL_NON_POOLING" — and passing it through verbatim starts a
#     worker that loops on `missing "=" after ...` once per poll.
#   - It is passed to one process and never exported. An exported value
#     redirects anything that later builds a store, and it has twice written
#     test data into the owner's hosted database.
#   - A worker with no URL drains the *local file* and looks perfectly healthy
#     doing it, while the deployment's jobs sit until the client gives up at
#     `job_timeout`. So a missing or template URL is a hard failure here, not a
#     silent fallback.
#
# Run it directly to start a worker in the foreground, or let the launchd agent
# beside this file keep one running. Either way the secret stays in `.env`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENV_FILE="$ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "FAILED: no $ENV_FILE — the worker has no queue to drain." >&2
  exit 1
fi

URL="$(sed -n 's/^POSTGRES_URL_NON_POOLING=//p' "$ENV_FILE" | head -1 | tr -d '"')"

if [ -z "$URL" ]; then
  echo "FAILED: POSTGRES_URL_NON_POOLING is not set in $ENV_FILE." >&2
  exit 1
fi
case "$URL" in
  *'$'*)
    echo "FAILED: POSTGRES_URL_NON_POOLING still holds a shell template, not a URL." >&2
    exit 1
    ;;
  postgres://*|postgresql://*) ;;
  *)
    echo "FAILED: POSTGRES_URL_NON_POOLING is not a postgres URL." >&2
    exit 1
    ;;
esac

# `uv` is not on launchd's PATH, which is a bare /usr/bin:/bin:/usr/sbin:/sbin.
UV="$(command -v uv || true)"
for candidate in /opt/homebrew/bin/uv /usr/local/bin/uv "$HOME/.local/bin/uv"; do
  [ -n "$UV" ] && break
  [ -x "$candidate" ] && UV="$candidate"
done
if [ -z "$UV" ]; then
  echo "FAILED: uv not found. Install it or add it to PATH." >&2
  exit 1
fi

echo "starting worker from $ROOT with $UV"
exec env TOURIST_DB_URL="$URL" "$UV" run --locked python -m travel_planner.worker
