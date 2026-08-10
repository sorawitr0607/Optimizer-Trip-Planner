"""Thin localhost HTTP transport for :class:`PlannerActions`."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import unquote, urlsplit

from travel_planner.actions import PlannerActions, PlannerRefusal
from travel_planner.copy import OPTIMIZER_CODE_TEXT, TEXT
from travel_planner.core import FrozenSnapshot
from travel_planner.credentials import load_local_credentials
from travel_planner.exporters import checklist_ics, plan_workbook_xlsx
from travel_planner.providers import (
    ProviderBudgetExceeded,
    ProviderUnavailable,
    RevisionInterpretationUnavailable,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "web"
WEB_DIST = WEB_ROOT / "dist"

# Literal by design. `save_plan_version` and `record_paid_call` must never be here.
ACTIONS = (
    "create_trip",
    "list_trips",
    "delete_trip",
    "travel_month_guide",
    "get_basemap",
    "refresh_basemap",
    "refresh_map_detail",
    "country_outline",
    "refresh_country_outline",
    "save_setup",
    "get_setup",
    "setup_vocabulary",
    "discover_places",
    "get_latest_discovery",
    "save_candidate_choice",
    "clear_candidate_choice",
    "list_candidate_choices",
    "rank_candidates",
    "check_paid_call",
    "enrich_place_card",
    "generate_plan_preview",
    "get_plan_preview",
    "activate_plan_preview",
    # WF-039. The acceptance path was dead by construction; these are what make
    # it reachable. accept_comfort_tradeoff carries the measured value it agreed
    # to, so a later, worse plan is not blessed by an earlier consent.
    "comfort_tradeoffs",
    "accept_comfort_tradeoff",
    "withdraw_comfort_tradeoff",
    "list_comfort_acceptances",
    "restore_plan_version",
    "get_active_plan",
    "build_export_snapshot",
    "checklist_vocabulary",
    "propose_checklist",
    "apply_checklist_proposal",
    "list_checklist_items",
    "save_checklist_item",
    "set_checklist_progress",
    "record_checklist_evidence",
    "set_checklist_dismissed",
    "checklist_readiness",
    "refresh_opening_hours",
    "opening_intervals",
    "confirm_opening_window",
    "get_accommodation_base",
    "confirm_accommodation_base",
    "refresh_timezone",
    "get_timezone_evidence",
    "refresh_routes",
    # WF-038. A local file read, so it is free and works offline, but it is a
    # mutation like any other refresh and belongs on the allowlist explicitly
    # rather than arriving through introspection.
    "refresh_transit_routes",
    # Free: Wikidata and Wikipedia, no key. A description and photo per place, which
    # is what google_places:card_details used to charge US$0.04 for.
    "refresh_place_summaries",
    "list_place_summaries",
    # WF-040. Ranks station neighbourhoods as places to stay. Free -- one Overpass
    # request for the whole shortlist -- but it does spend a (zero-priced) provider
    # call and writes the provider cache, so it is a mutation, not a read.
    "recommend_areas",
    # WF-046. A model-recalled opening window is an *assumption*, never evidence --
    # it replaces a hardcoded 09:00-21:00 and keeps status "assumed". Paid, so it is
    # owner-triggered like every other refresh.
    "refresh_assumed_windows",
    "list_assumed_windows",
    # WF-047. A read: what hours cost each way, and what the cheap way gives up.
    # It reports the trade rather than taking it -- verified and assumed are not
    # the same kind of thing, whatever they cost.
    "opening_evidence_options",
    # WF-045. A read: has the evidence under the activated plan moved, and did
    # anything break. It reports and never repairs -- regenerating would rewrite a
    # plan the owner may have printed.
    "active_plan_drift",
    # WF-044. Reads each venue's own page for a dated closure the weekly hours
    # cannot carry. Advisory only: stored under a kind _optimizer_input does not
    # read, so a notice can never remove a place from a plan.
    "scan_venue_notices",
    "list_venue_notices",
    "list_routes",
    "paid_usage_status",
    "set_paid_cap",
    "save_rate_snapshot",
    "get_rate_snapshot",
    "save_cost_item",
    "list_cost_items",
    "delete_cost_item",
    "cost_totals",
    "save_split_row",
    "list_split_rows",
    "set_split_voided",
    "split_summary",
    "set_split_settled",
    "quick_actions",
    "propose_revision",
    "interpret_revision",
    "get_revision_draft",
    "discard_revision_draft",
    "apply_revision",
    "list_revisions",
    "list_plan_versions",
    "journey",
)

REFUSAL_STATUS = {
    "unknown_trip": 404,
    "unknown_candidate": 404,
    "unknown_plan_variant": 404,
    "unknown_plan_version": 404,
    "unknown_checklist_item": 404,
    "unknown_split_row": 404,
    "unknown_traveller": 404,
    "setup_not_confirmed": 409,
    "setup_missing": 409,
    "discovery_missing": 409,
    "discovery_stale": 409,
    "discovery_empty": 409,
    "preview_missing": 409,
    "preview_stale": 409,
    "variant_not_ready": 409,
    "no_active_plan": 409,
    "no_places_chosen": 422,
    "place_not_chosen": 422,
    "insufficient_geocoded_places": 422,
    "invalid_time_window": 422,
    "accommodation_query_missing": 422,
    "invalid_paid_cap": 422,
    "revision_already_pending": 409,
    "no_pending_revision": 409,
    "revision_not_applicable": 409,
    "revision_base_moved": 409,
    "revision_no_variant": 409,
    "no_planning_time": 409,
    # WF-040. Area ranking needs a metro graph and at least one reachable place.
    "no_transit_graph_for_areas": 409,
    "no_area_reaches_any_place": 409,
    # WF-039. Accepting a comfort tradeoff.
    "unknown_comfort_code": 422,
    "comfort_value_not_a_number": 422,
    "no_comfort_threshold_set": 409,
    "comfort_value_within_threshold": 409,
    # WF-046. An assumed window is only read under allow_provisional_assumptions.
    "assumptions_not_used_by_this_trip": 409,
}


class BadRequest(ValueError):
    pass


def jsonable(value: Any) -> Any:
    """Convert domain records to their frozen JSON wire shapes."""

    if isinstance(value, FrozenSnapshot):
        return {"data": value.as_dict(), "sha256": value.sha256}
    if is_dataclass(value):
        return {field.name: jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def dispatch(actions: PlannerActions, method: str, payload: Mapping[str, Any]) -> Any:
    if method not in ACTIONS:
        raise PlannerRefusal("unknown_action")
    action = getattr(actions, method)
    try:
        inspect.signature(action).bind(**payload)
    except TypeError as error:
        raise BadRequest(str(error)) from error
    return jsonable(action(**payload))


def _labels(language: str) -> dict[str, str]:
    chosen = language if language in {"en", "th"} else "en"
    return TEXT[chosen] | OPTIMIZER_CODE_TEXT[chosen]


def _download(actions: PlannerActions, path: str) -> tuple[bytes, str, str]:
    match = re.fullmatch(r"/api/export/([^/]+)/(workbook\.xlsx|checklist\.ics)", path)
    if match is None:
        raise PlannerRefusal("unknown_download")
    trip_id, kind = unquote(match.group(1)), match.group(2)
    trip = actions.get_trip(trip_id)
    snapshot = actions.build_export_snapshot(trip_id).as_dict()
    labels = _labels(trip.language if trip else "en")
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", trip.name if trip else "trip").strip("-") or "trip"
    if kind == "workbook.xlsx":
        return (
            plan_workbook_xlsx(snapshot, labels),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{name}-plan.xlsx",
        )
    return checklist_ics(snapshot, labels), "text/calendar; charset=utf-8", f"{name}-readiness.ics"


class PlannerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        actions: PlannerActions,
        web_root: Path = WEB_DIST,
    ) -> None:
        self.actions = actions
        self.web_root = web_root
        super().__init__(address, PlannerHandler)


class PlannerHandler(SimpleHTTPRequestHandler):
    server: PlannerHTTPServer
    protocol_version = "HTTP/1.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(args[2].web_root), **kwargs)

    def _allowed_host(self) -> bool:
        port = self.server.server_port
        return self.headers.get("Host") in {
            "127.0.0.1",
            "localhost",
            f"127.0.0.1:{port}",
            f"localhost:{port}",
        }

    def _body(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: Any) -> None:
        self._body(
            status,
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _error(self, error: Exception) -> None:
        if isinstance(error, PlannerRefusal):
            if error.code == "unknown_action" or error.code == "unknown_download":
                self._json(404, {"code": error.code})
            else:
                self._json(
                    REFUSAL_STATUS.get(error.code, 409),
                    {"code": error.code, "detail": error.detail},
                )
        elif isinstance(error, BadRequest):
            self._json(400, {"code": "bad_request", "detail": {"message": str(error)}})
        elif isinstance(error, ProviderBudgetExceeded):
            self._json(402, {"code": "paid_cap_reached", "detail": {"message": str(error)}})
        elif isinstance(error, ProviderUnavailable):
            self._json(503, {"code": "provider_unavailable", "detail": {"message": str(error)}})
        elif isinstance(error, RevisionInterpretationUnavailable):
            self._json(503, {"code": error.cause, "detail": {"message": str(error)}})
        else:
            self.log_error("Unhandled API error: %s", error)
            self._json(500, {"code": "internal_error"})

    def do_POST(self) -> None:
        # SECURITY CONTROL: application/json is not CORS-safelisted. Do not relax.
        if self.headers.get("Content-Type") != "application/json":
            self.close_connection = True
            self._json(415, {"code": "unsupported_media_type"})
            return
        # Blocks DNS rebinding into the localhost process.
        if not self._allowed_host():
            self.close_connection = True
            self._json(421, {"code": "bad_host"})
            return
        path = urlsplit(self.path).path
        method = path.removeprefix("/api/") if path.startswith("/api/") else ""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, Mapping):
                raise BadRequest("request body must be a JSON object")
            self._json(200, dispatch(self.server.actions, method, payload))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
            self._error(BadRequest(str(error)) if not isinstance(error, PlannerRefusal) else error)
        except Exception as error:  # transport boundary
            self._error(error)

    def do_GET(self) -> None:
        if not self._allowed_host():
            self._json(421, {"code": "bad_host"})
            return
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            try:
                body, content_type, filename = _download(self.server.actions, path)
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except Exception as error:
                self._error(error)
            return

        target = self.server.web_root / path.lstrip("/")
        if path == "/" or not target.is_file():
            self.path = "/index.html"
        super().do_GET()


def ensure_web_build() -> None:
    index = WEB_DIST / "index.html"
    inputs = [
        WEB_ROOT / "index.html",
        WEB_ROOT / "package.json",
        WEB_ROOT / "package-lock.json",
        WEB_ROOT / "vite.config.ts",
        WEB_ROOT / "src",
        *WEB_ROOT.joinpath("src").rglob("*"),
        REPO_ROOT / "tokens.css",
        REPO_ROOT / "i18n" / "copy.json",
    ]
    stale = not index.exists() or any(
        path.exists() and path.stat().st_mtime > index.stat().st_mtime for path in inputs
    )
    if not stale:
        return
    if not (WEB_ROOT / "node_modules").is_dir():
        raise SystemExit("web/node_modules is missing; run `npm --prefix web install`")
    subprocess.run(["npm", "--prefix", str(WEB_ROOT), "run", "build"], check=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve the local Optimizer Trip Planner")
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1",))
    parser.add_argument("--port", type=int, default=int(os.environ.get("TOURIST_API_PORT", "8765")))
    args = parser.parse_args(argv)
    ensure_web_build()
    load_local_credentials()
    actions = PlannerActions(os.environ.get("TOURIST_DB_PATH", "data/tourist.sqlite3"))
    server = PlannerHTTPServer((args.host, args.port), actions)
    print(f"Serving Optimizer Trip Planner at http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


__all__ = (
    "ACTIONS",
    "PlannerHTTPServer",
    "dispatch",
    "ensure_web_build",
    "jsonable",
    "main",
)
