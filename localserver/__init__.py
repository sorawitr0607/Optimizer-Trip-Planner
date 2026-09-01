"""Thin localhost HTTP transport for :class:`PlannerActions`."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
import gzip
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hmac
import inspect
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from travel_planner.actions import PlannerActions, PlannerRefusal
from travel_planner.copy import OPTIMIZER_CODE_TEXT, TEXT
from travel_planner.core import FrozenSnapshot
from travel_planner.credentials import load_local_credentials
from travel_planner.owners import claim_unowned
from travel_planner.wire import jsonable
from travel_planner.exporters import (
    checklist_ics,
    money_workbook_xlsx,
    plan_workbook_xlsx,
)
from travel_planner.providers import (
    ProviderBudgetExceeded,
    ProviderNoMatch,
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
    "route_shapes",
    "trip_forecast",
    "save_setup",
    "get_setup",
    "setup_vocabulary",
    "discover_places",
    "get_latest_discovery",
    "get_ranked_discovery",
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
    "build_money_snapshot",
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
    "confirm_default_opening_windows",
    "confirm_places_selection",
    "accept_provisional_base",
    "accept_route_estimates",
    "get_accommodation_base",
    "confirm_accommodation_base",
    "refresh_timezone",
    "resolve_default_terminal",
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
    "cost_categories",
    "set_cost_categories",
    "save_split_row",
    "list_split_rows",
    "set_split_voided",
    "split_summary",
    "set_split_settled",
    "get_split_cardholder",
    "set_split_cardholder",
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

# Methods whose effect is deployment-wide, so trip ownership cannot scope them.
# `set_paid_cap` is the only member: the cap is global, and its docstring has
# promised "only the owner" since it was written.
OWNER_ONLY_ACTIONS = frozenset({"set_paid_cap"})

REFUSAL_STATUS = {
    "not_admin": 403,
    "not_your_trip": 403,
    "place_not_in_provider": 404,
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
    # Editable expense categories. A built-in is never removable and a category
    # still on a row cannot be dropped, or its money silently re-files as `other`.
    "category_label_missing": 422,
    "category_code_repeated": 422,
    "category_still_in_use": 409,
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


def dispatch(
    actions: PlannerActions,
    method: str,
    payload: Mapping[str, Any],
    *,
    owner: str | None = None,
    admin_key: str | None = None,
) -> Any:
    """Run one allowlisted method, scoped to its caller.

    `owner` is the one place ten people sharing a deployment are kept apart. It is
    checked here rather than in the methods because 108 of them take a `trip_id` and
    every one of those is the same question -- and a check written 108 times is a
    check that will be missing from the 109th. `payload` carries the trip id for all
    of them, so one comparison covers the surface.

    Omitting `owner` scopes nothing, which is what a local single-user run, the
    exporters and the gates all want.
    """

    if method not in ACTIONS:
        raise PlannerRefusal("unknown_action")
    action = getattr(actions, method)

    if method in OWNER_ONLY_ACTIONS:
        # The cap is global, so raising it is the one action that must never answer
        # to an anonymous visitor — its docstring has said "only the owner" since it
        # was written, and nothing enforced it. The owner's browser presents
        # `X-Planner-Admin`; the deployment compares it against `TOURIST_ADMIN_KEY`.
        # A local single-user run without the variable keeps working: the only
        # person who can reach that server is its operator. `api/rpc.py` adds the
        # hosted half — there, an unset variable refuses outright, because a
        # deployment with no key configured has nothing to compare against.
        expected = os.environ.get("TOURIST_ADMIN_KEY", "").strip()
        presented = (admin_key or "").strip()
        if expected and (not presented or not hmac.compare_digest(presented, expected)):
            raise PlannerRefusal("not_admin")

    if owner:
        # Trips that predate owners belong to whoever arrives first: this deployment's
        # owner is the person who deployed it, so opening the site once before sharing
        # the link is what settles them. A second caller finds nothing to claim.
        if method == "list_trips":
            claim_unowned(actions.store, owner)
        trip_id = payload.get("trip_id")
        if isinstance(trip_id, str) and trip_id:
            held = actions.store.trip_owner(trip_id)
            if held is None:
                actions.store.set_trip_owner(trip_id, owner)
            elif held != owner:
                # Not `unknown_trip`: saying "no such trip" to hide the difference
                # would be a lie the URL already contradicts.
                raise PlannerRefusal("not_your_trip", trip_id=trip_id)
        if method == "list_trips":
            return jsonable(action(owner=owner))

    try:
        inspect.signature(action).bind(**payload)
    except TypeError as error:
        raise BadRequest(str(error)) from error
    result = action(**payload)
    if owner and method == "create_trip" and getattr(result, "trip_id", None):
        actions.store.set_trip_owner(result.trip_id, owner)
    return jsonable(result)


def _labels(language: str) -> dict[str, str]:
    chosen = language if language in {"en", "th"} else "en"
    return TEXT[chosen] | OPTIMIZER_CODE_TEXT[chosen]


def error_response(error: Exception) -> tuple[int, dict[str, Any]]:
    """Map one exception to its status and body.

    Shared with `api/rpc.py`, which serves the same contract from a serverless
    function. It lived as a method on the local handler until the hosted entry
    point grew its own copy, and the copy was already wrong in a way that mattered:
    `ProviderBudgetExceeded` is not a `PlannerRefusal`, so it fell to the generic
    500 and the screen said "internal_error" when the truth was that the paid cap
    had been reached. A budget stop the operator cannot see is the one failure this
    application must never have.
    """

    if isinstance(error, PlannerRefusal):
        if error.code in ("unknown_action", "unknown_download"):
            return 404, {"code": error.code}
        return REFUSAL_STATUS.get(error.code, 409), {
            "code": error.code,
            "detail": error.detail,
        }
    if isinstance(error, BadRequest):
        return 400, {"code": "bad_request", "detail": {"message": str(error)}}
    if isinstance(error, ProviderBudgetExceeded):
        return 402, {"code": "paid_cap_reached", "detail": {"message": str(error)}}
    # Before `ProviderUnavailable`, which it subclasses: a reachable provider with no
    # record of a place is a 404, not an outage, and saying "unavailable" invited
    # pressing a paid button again to be told the same thing twice.
    if isinstance(error, ProviderNoMatch):
        return 404, {"code": "place_not_in_provider", "detail": {"message": str(error)}}
    if isinstance(error, ProviderUnavailable):
        return 503, {"code": "provider_unavailable", "detail": {"message": str(error)}}
    if isinstance(error, RevisionInterpretationUnavailable):
        return 503, {"code": error.cause, "detail": {"message": str(error)}}
    return 500, {"code": "internal_error"}


#: The three files a trip can be downloaded as. Named once, because both ways of
#: asking for one have to agree about what is allowed.
DOWNLOAD_KINDS = ("workbook.xlsx", "money.xlsx", "checklist.ics")


#: Types the standard library does not know, and a browser is strict about.
_EXTRA_TYPES = {".woff2": "font/woff2", ".webmanifest": "application/manifest+json"}

#: Widened with a charset, because a browser guesses latin-1 otherwise and the
#: catalogue is bilingual.
_TEXTUAL = {"application/javascript", "application/json", "image/svg+xml"}


def static_response(path: str, root: Path | None = None) -> tuple[int, bytes, str, str]:
    """Serve one file from the built frontend: (status, body, type, cache).

    Shared with `api/rpc.py`. On Vercel this application is a single Python
    entrypoint, and the documentation is plain about what that means -- "Vercel
    then runs your app as Vercel Functions and routes every request to it" -- so
    the function is asked for the stylesheet and the favicon as well as the API.
    There is no configuration that splits them: file-based functions under /api,
    which would have left the static build on the CDN, are not offered to this
    project. Rather than a second, subtly different copy of the rules, both
    callers use this one.

    `assets/` is content-hashed by the build, so it is immutable and the edge can
    keep it for a year -- which is what stops a function invocation per asset per
    request. Everything else revalidates.
    """

    root = (root or WEB_DIST).resolve()
    target = (root / path.lstrip("/")).resolve()
    # The SPA fallback is for *routes*, and a route has no file extension. Sending
    # index.html for every miss meant `/favicon.ico` answered 200 with the whole
    # application as its body -- which a browser discards, so the tab kept the
    # blank default and the app looked unfinished for a reason no log showed.
    if path == "/" or (not target.is_file() and not PurePosixPath(path).suffix):
        target = root / "index.html"
    try:
        relative = target.relative_to(root)
    except ValueError:
        # `..` climbing out of the build directory.
        return 404, b"not found", "text/plain; charset=utf-8", "no-store"
    if not target.is_file():
        return 404, b"not found", "text/plain; charset=utf-8", "no-store"

    suffix = target.suffix.lower()
    content_type = _EXTRA_TYPES.get(suffix) or mimetypes.guess_type(str(target))[0] \
        or "application/octet-stream"
    if content_type.startswith("text/") or content_type in _TEXTUAL:
        content_type += "; charset=utf-8"
    cache = ("public, max-age=31536000, immutable"
             if relative.parts[:1] == ("assets",) else "no-cache")
    return 200, target.read_bytes(), content_type, cache


def _download(actions: PlannerActions, target: str) -> tuple[bytes, str, str]:
    """Build one export. `target` is a request path, with or without its query.

    Two spellings are accepted for the same download:

        /api/export/<trip>/workbook.xlsx        the path form
        /api/export?trip=<trip>&kind=workbook.xlsx    the query form

    The path form is the honest one and the local server only ever produces it.
    The query form exists because a hosted deployment routes every /api/* through
    a single function with a rewrite, and a rewrite replaces the path -- so a
    download whose path carries the trip and the format arrives asking for
    nothing. RPC calls survive that on a header; a download cannot, because it is
    an `<a download>` link the browser follows with no headers of ours on it.
    A query string is not rewritten, so it still says which file was wanted.
    """

    split = urlsplit(target)
    match = re.fullmatch(
        r"/api/export/([^/]+)/(workbook\.xlsx|money\.xlsx|checklist\.ics)", split.path
    )
    if match is not None:
        trip_id, kind = unquote(match.group(1)), match.group(2)
    else:
        query = parse_qs(split.query)
        trip_id = (query.get("trip") or [""])[0]
        kind = (query.get("kind") or [""])[0]
        if not trip_id or kind not in DOWNLOAD_KINDS:
            raise PlannerRefusal("unknown_download")
    trip = actions.get_trip(trip_id)
    labels = _labels(trip.language if trip else "en")
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", trip.name if trip else "trip").strip("-") or "trip"
    XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    # The money file is built from its own snapshot and never touches the plan's.
    # Not a tidiness point: `build_export_snapshot` refuses without an active plan,
    # so building it here first would have made the shareable file unavailable for
    # exactly the stretch of a trip when people are paying for things.
    if kind == "money.xlsx":
        return (
            money_workbook_xlsx(actions.build_money_snapshot(trip_id).as_dict(), labels),
            XLSX,
            f"{name}-money.xlsx",
        )
    snapshot = actions.build_export_snapshot(trip_id).as_dict()
    if kind == "workbook.xlsx":
        return plan_workbook_xlsx(snapshot, labels), XLSX, f"{name}-plan.xlsx"
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

    def _body(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        cache_control: str = "no-store",
        content_encoding: str | None = None,
        vary_accept_encoding: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        if content_encoding:
            self.send_header("Content-Encoding", content_encoding)
        if vary_accept_encoding:
            self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        self.wfile.write(body)

    def _accepts_gzip(self) -> bool:
        qualities: dict[str, float] = {}
        for item in self.headers.get("Accept-Encoding", "").lower().split(","):
            encoding, *parameters = (part.strip() for part in item.split(";"))
            if not encoding:
                continue
            quality = 1.0
            for parameter in parameters:
                if parameter.startswith("q="):
                    try:
                        quality = float(parameter.removeprefix("q="))
                    except ValueError:
                        quality = 0.0
            qualities[encoding] = quality
        return qualities.get("gzip", qualities.get("*", 0.0)) > 0

    def _encoded(self, body: bytes) -> tuple[bytes, str | None]:
        if self._accepts_gzip() and len(body) >= 1024:
            return gzip.compress(body, mtime=0), "gzip"
        return body, None

    def _json(self, status: int, value: Any) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        # The Places screen's immutable discovery and ranking snapshots are large but
        # highly repetitive. Narrowing either would make its exposed sha256 describe
        # different bytes from the payload. HTTP compression preserves that contract
        # and cuts the real pilot responses by about 93%, using only the stdlib.
        encoded, encoding = self._encoded(body)
        self._body(
            status,
            encoded,
            "application/json; charset=utf-8",
            content_encoding=encoding,
            vary_accept_encoding=True,
        )

    def _error(self, error: Exception) -> None:
        status, body = error_response(error)
        if status == 500:
            self.log_error("Unhandled API error: %s", error)
        self._json(status, body)

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
            owner = (self.headers.get("X-Planner-Owner") or "").strip() or None
            admin_key = (self.headers.get("X-Planner-Admin") or "").strip() or None
            self._json(
                200,
                dispatch(
                    self.server.actions, method, payload, owner=owner, admin_key=admin_key
                ),
            )
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
                body, content_type, filename = _download(self.server.actions, self.path)
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

        root = self.server.web_root.resolve()
        target = (root / path.lstrip("/")).resolve()
        # The SPA fallback is for *routes*, and a route has no file extension. Sending
        # index.html for every miss meant `/favicon.ico` answered 200 with the whole
        # application as its body — which a browser discards, so the tab kept the
        # blank default and the app looked unfinished for a reason no log showed.
        # A missing asset is now a 404, which is what a missing asset is.
        if path == "/" or (not target.is_file() and not PurePosixPath(path).suffix):
            target = root / "index.html"
        try:
            relative = target.relative_to(root)
        except ValueError:
            self.send_error(404)
            return
        if not target.is_file():
            super().do_GET()
            return

        body = target.read_bytes()
        content_type = self.guess_type(str(target))
        compressible = content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
            "image/svg+xml",
        }
        encoded, encoding = self._encoded(body) if compressible else (body, None)
        cache_control = (
            "public, max-age=31536000, immutable"
            if relative.parts[:1] == ("assets",)
            else "no-cache"
        )
        self._body(
            200,
            encoded,
            content_type,
            cache_control=cache_control,
            content_encoding=encoding,
            vary_accept_encoding=compressible,
        )


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
    "OWNER_ONLY_ACTIONS",
    "error_response",
    "PlannerHTTPServer",
    "dispatch",
    "ensure_web_build",
    "jsonable",
    "main",
)
