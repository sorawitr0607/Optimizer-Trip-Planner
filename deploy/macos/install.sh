#!/usr/bin/env bash
# Keep the job worker running on this Mac, across crashes, sleeps and logins.
#
# The worker is the piece Vercel cannot host — discover_places takes 30-90s
# against a 60s function cap, which is why those operations are queued. Nothing
# drains that queue but this process, and when it is down the deployment cannot
# complete a single job: the client polls for five minutes and gives up with
# `job_timeout`, which looks like an application fault and is not one. That
# happened on 2026-08-23 and is the reason this file exists.
#
#   deploy/macos/install.sh            install and start
#   deploy/macos/install.sh status     is it running, and on which store
#   deploy/macos/install.sh logs       follow its output
#   deploy/macos/install.sh restart    pick up a code change
#   deploy/macos/install.sh stop       stop it for now (returns at next login)
#   deploy/macos/install.sh start      start it again after a stop
#   deploy/macos/install.sh uninstall  stop it for good and remove the agent
#
# `stop` and `uninstall` are a real distinction, not two words for one thing.
# Both unload the agent, but `uninstall` deletes the plist and `stop` leaves it
# in `~/Library/LaunchAgents` — where launchd loads it again at the next login.
# So `stop` is "not right now", and only `uninstall` is "not any more".
#
# The database URL is never written here. `worker.sh` reads it from `.env` at
# start, so the secret stays in the one file that already holds it, mode 600 and
# gitignored — a plist in ~/Library/LaunchAgents is world-readable.
#
# **Prerequisite, once per machine: `/bin/bash` needs Full Disk Access.** The
# repo is under `~/Documents` and a launchd agent gets no access there. See the
# note above the plist below; `status` says so too when it happens.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LABEL="com.optimizer-trip-planner.worker"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/optimizer-worker.log"
ACTION="${1:-install}"

case "$ACTION" in
  status)
    echo "agent:"
    launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -E "state|pid|last exit" | sed 's/^/  /' || echo "  not loaded"
    echo "processes:"
    pgrep -f "travel_planner.worker" | while read -r p; do
      # The `uv run` wrapper always reads as 0; the python child is the one that
      # holds the connections, and checking the wrapper is a standing trap.
      echo "  PID $p psycopg=$(lsof -p "$p" 2>/dev/null | grep -c psycopg)"
    done || echo "  none"
    echo "store (the line that actually answers it):"
    # The *last* draining line, not the first: the log accumulates across
    # restarts, and the first one answers for a worker that may be long dead.
    grep draining "$LOG" 2>/dev/null | tail -1 | sed 's/^/  /' || echo "  no 'draining' line in $LOG yet"
    # 126 is not a bug in worker.sh. It is macOS refusing launchd the repo.
    # Warn only when the refusal is the *latest* news — the errors from before
    # the Full Disk Access grant stay in the log for good, and reporting a
    # solved problem beside a healthy worker is its own kind of wrong.
    # `|| true` on both: under `set -euo pipefail` a grep that matches nothing
    # fails the whole pipeline, and an assignment from a failed substitution
    # ends the script — so `status` on a log with no `draining` line yet, which
    # is every fresh install, exited silently right here.
    denied=$(grep -n "Operation not permitted" "$LOG" 2>/dev/null | tail -1 | cut -d: -f1) || true
    drained=$(grep -n draining "$LOG" 2>/dev/null | tail -1 | cut -d: -f1) || true
    if [ -n "$denied" ] && [ "$denied" -gt "${drained:-0}" ]; then
      echo
      echo "  Exit 126 / 'Operation not permitted' is macOS TCC, not the script:"
      echo "  the repo is under ~/Documents and launchd has no grant for it."
      echo "  Fix: System Settings > Privacy & Security > Full Disk Access > +"
      echo "       Cmd+Shift+G, type /bin/bash, add it, then re-run install.sh."
    fi
    exit 0
    ;;
  logs)
    exec tail -f "$LOG"
    ;;
  restart)
    # `kickstart -k` and not stop/start: `launchctl stop` against a KeepAlive
    # job is a race with launchd's own respawn, which is how you get two
    # workers or none.
    launchctl kickstart -k "gui/$(id -u)/$LABEL"
    echo "restarted — check: deploy/macos/install.sh status"
    exit 0
    ;;
  stop)
    # `bootout`, not `launchctl stop`: KeepAlive means a stopped job is
    # restarted within seconds, so the only way to actually stop it is to
    # unload the agent. The plist stays, so a login brings it back.
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    echo "stopped. It returns at your next login, or run: deploy/macos/install.sh start"
    exit 0
    ;;
  start)
    if [ ! -f "$PLIST" ]; then
      echo "no agent installed — run: deploy/macos/install.sh" >&2
      exit 1
    fi
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    echo "started — check: deploy/macos/install.sh status"
    exit 0
    ;;
  uninstall)
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "removed $PLIST — nothing is draining the queue now."
    exit 0
    ;;
  install) ;;
  *) echo "usage: install.sh [install|status|logs|restart|stop|start|uninstall]" >&2; exit 2 ;;
esac

chmod +x "$ROOT/deploy/macos/worker.sh"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

# KeepAlive rather than RunAtLoad alone: the failure this guards against is the
# worker dying quietly hours later, not failing to start. ThrottleInterval keeps
# a genuinely broken config from respawning in a tight loop — with a bad URL
# `worker.sh` exits non-zero immediately, and 30s between attempts leaves a
# readable log instead of a scrolling one.
#
# `/bin/bash` is named explicitly rather than letting launchd exec the script
# through its shebang, and that is the whole reason this works. The repo is
# under `~/Documents`, which macOS protects: an agent gets no access to it and
# no prompt either, so the first attempt failed with exit 126 and
# `Operation not permitted` on a script that runs fine from a terminal --
# Terminal holds the grant, launchd does not. The grant is attributed to the
# binary launchd spawns, so the plist must spawn the binary that has it. With
# `#!/usr/bin/env bash` the image is chosen by PATH at exec time, which is not
# a thing to leave to a lookup.
cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT/deploy/macos/worker.sh</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "installed $PLIST"
echo "logging to $LOG"
echo
echo "Give it a few seconds, then:  deploy/macos/install.sh status"
echo "It is healthy when the log says 'draining PostgresStore'."
echo "'draining SQLiteStore' means it is on the local file and the deployment's"
echo "jobs will sit until the client times out."
