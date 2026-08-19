#!/usr/bin/env bash
# Install the job worker as a systemd service on a fresh Ubuntu VM.
#
# The worker is the piece Vercel cannot host: discover_places takes 30-90s and a
# serverless function is capped at 60, which is why those three operations are
# queued rather than run. Without something draining that queue the client polls
# for five minutes and gives up with `job_timeout`.
#
# Safe to re-run: it updates the checkout and restarts the service.
#
#   curl -fsSL https://raw.githubusercontent.com/sorawitr0607/Optimizer-Trip-Planner/main/deploy/oracle/setup.sh | bash
#
# Or clone first and run it. Either way it stops and tells you what to do if the
# environment file is missing, rather than starting a worker that cannot connect.

set -euo pipefail

REPO="https://github.com/sorawitr0607/Optimizer-Trip-Planner.git"
ENV_FILE="/etc/optimizer-worker.env"
SERVICE="optimizer-worker"
# The invoking user, not root: the service has no reason to run privileged, and
# `sudo bash` would otherwise install everything into /root.
RUN_USER="${SUDO_USER:-$(id -un)}"
HOME_DIR="$(getent passwd "$RUN_USER" | cut -d: -f6)"
CHECKOUT="$HOME_DIR/optimizer-worker"

say() { printf '\n=== %s\n' "$1"; }

say "packages"
sudo apt-get update -qq
# python3-venv is separate from python3 on Ubuntu and the venv fails without it.
sudo apt-get install -y -qq git python3-venv python3-pip

say "checkout at $CHECKOUT"
if [ -d "$CHECKOUT/.git" ]; then
  sudo -u "$RUN_USER" git -C "$CHECKOUT" fetch --quiet origin main
  sudo -u "$RUN_USER" git -C "$CHECKOUT" reset --quiet --hard origin/main
else
  # Partial and sparse: the repository carries 248 MB of reference itineraries
  # that the worker never opens. This takes about 2.5 MB.
  sudo -u "$RUN_USER" git clone --quiet --filter=blob:none --sparse "$REPO" "$CHECKOUT"
  sudo -u "$RUN_USER" git -C "$CHECKOUT" sparse-checkout set travel_planner i18n
fi

say "python environment"
sudo -u "$RUN_USER" python3 -m venv "$CHECKOUT/.venv"
sudo -u "$RUN_USER" "$CHECKOUT/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$RUN_USER" "$CHECKOUT/.venv/bin/pip" install --quiet -r "$CHECKOUT/requirements.txt"

if [ ! -f "$ENV_FILE" ]; then
  say "environment file"
  sudo tee "$ENV_FILE" >/dev/null <<'TEMPLATE'
# Fill these in, then re-run this script. Root-readable only.
#
# TOURIST_DB_URL is the DIRECT connection (port 5432), not the pooled one. This
# is a single long-lived process holding its own pool, so it does not want
# pgbouncer in front. In Supabase that is POSTGRES_URL_NON_POOLING.
TOURIST_DB_URL=

# The worker makes the provider calls, not the web function, so the keys live
# here. Leave one blank and the operations needing it refuse; the free ones still
# run.
OPENAI_API_KEY=
GOOGLE_MAPS_SERVER_KEY=
OPENROUTESERVICE_API_KEY=

# Not optional in practice: Nominatim and Overpass block clients that do not
# identify themselves, and place discovery is built on both.
TOURIST_USER_AGENT=TouristPlannerPersonalPOC/0.2 (local personal use)
TOURIST_OVERPASS_URL=https://overpass-api.de/api/interpreter,https://maps.mail.ru/osm/tools/overpass/api/interpreter
TEMPLATE
  sudo chmod 600 "$ENV_FILE"
  echo "Created $ENV_FILE with blank values."
  echo "Fill in TOURIST_DB_URL and the keys, then run this script again."
  exit 1
fi

if ! sudo grep -qE '^TOURIST_DB_URL=.+' "$ENV_FILE"; then
  echo "TOURIST_DB_URL is empty in $ENV_FILE. Fill it in and re-run." >&2
  exit 1
fi

say "service"
sudo tee "/etc/systemd/system/$SERVICE.service" >/dev/null <<UNIT
[Unit]
Description=Optimizer Trip Planner job worker
After=network-online.target
Wants=network-online.target

[Service]
User=$RUN_USER
WorkingDirectory=$CHECKOUT
EnvironmentFile=$ENV_FILE
ExecStart=$CHECKOUT/.venv/bin/python -m travel_planner.worker
Restart=always
RestartSec=5
# Shutdown is cooperative: the worker finishes the job in hand rather than
# abandoning it as `running` for the reaper to find 15 minutes later. Discovery
# can take 90s, so systemd has to be willing to wait.
KillSignal=SIGTERM
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --quiet --now "$SERVICE"
sudo systemctl restart "$SERVICE"

say "running"
sleep 2
sudo systemctl is-active "$SERVICE" && echo "Watch it work:  journalctl -fu $SERVICE"
echo "Expect a line reading: worker <id> draining PostgresStore"
echo "If it says SQLiteStore instead, TOURIST_DB_URL did not reach the process."
