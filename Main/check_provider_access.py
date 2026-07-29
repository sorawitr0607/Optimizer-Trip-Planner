#!/usr/bin/env python3
"""Redacted capability check for the one-time worldwide provider stack."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRETS_FILE = ROOT / "secrets.local.json"
KEY_NAMES = (
    "OPENROUTESERVICE_API_KEY",
    "GOOGLE_MAPS_SERVER_KEY",
    "GOOGLE_MAPS_BROWSER_KEY",
    "OPENAI_API_KEY",
)


def tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not ssl.get_default_verify_paths().cafile:
        system_ca = Path("/etc/ssl/cert.pem")
        if system_ca.is_file():
            context.load_verify_locations(cafile=system_ca)
    return context


def load_keys() -> dict[str, str]:
    stored: dict[str, str] = {}
    if SECRETS_FILE.exists():
        raw = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{SECRETS_FILE.name} must contain a JSON object")
        stored = {str(key): str(value) for key, value in raw.items()}
    return {name: os.environ.get(name, stored.get(name, "")).strip() for name in KEY_NAMES}


def request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 20,
) -> dict:
    request = urllib.request.Request(
        url,
        data=body,
        headers={"User-Agent": "personal-itinerary-poc/0.1", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout, context=tls_context()) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError("provider returned a non-object JSON response")
    return result


def run_check(name: str, check) -> dict[str, str]:
    try:
        check()
        return {"provider": name, "status": "reachable"}
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        return {"provider": name, "status": "error", "detail": str(exc)[:180]}


def check_open_meteo() -> None:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=25.0330&longitude=121.5654&current=temperature_2m&timezone=auto"
    )
    if "current" not in request_json(url):
        raise ValueError("forecast response did not contain current weather")


def check_overpass() -> None:
    query = '[out:json][timeout:10];nwr(around:100,25.0330,121.5654)["name"];out ids 1;'
    body = urllib.parse.urlencode({"data": query}).encode()
    result = request_json(
        "https://overpass-api.de/api/interpreter",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=body,
    )
    if "elements" not in result:
        raise ValueError("Overpass response did not contain elements")


def check_openrouteservice(api_key: str) -> None:
    url = (
        "https://api.openrouteservice.org/v2/directions/foot-walking"
        "?start=121.5654,25.0330&end=121.5600,25.0375"
    )
    result = request_json(url, headers={"Authorization": api_key})
    if not result.get("features"):
        raise ValueError("route response did not contain a route")


def check_google_places(api_key: str) -> None:
    result = request_json(
        "https://places.googleapis.com/v1/places:searchText",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.id",
        },
        body=json.dumps({"textQuery": "Taipei 101"}).encode(),
    )
    if not result.get("places"):
        raise ValueError("Places response did not contain a place")


def check_google_routes(api_key: str) -> None:
    result = request_json(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
        },
        body=json.dumps(
            {
                "origin": {
                    "location": {"latLng": {"latitude": 25.0330, "longitude": 121.5654}}
                },
                "destination": {
                    "location": {"latLng": {"latitude": 25.0375, "longitude": 121.5600}}
                },
                "travelMode": "WALK",
            }
        ).encode(),
    )
    if not result.get("routes"):
        raise ValueError("Routes response did not contain a route")


def configured_status(provider: str, key: str) -> dict[str, str]:
    return {"provider": provider, "status": "configured" if key else "not_configured"}


def build_report(keys: dict[str, str], *, live_paid: bool) -> list[dict[str, str]]:
    report = [
        run_check("open_meteo", check_open_meteo),
        run_check("openstreetmap_overpass", check_overpass),
    ]
    ors_key = keys["OPENROUTESERVICE_API_KEY"]
    report.append(
        run_check("openrouteservice", lambda: check_openrouteservice(ors_key))
        if ors_key
        else configured_status("openrouteservice", "")
    )
    google_server_key = keys["GOOGLE_MAPS_SERVER_KEY"]
    if live_paid and google_server_key:
        report.append(run_check("google_places", lambda: check_google_places(google_server_key)))
        report.append(run_check("google_routes", lambda: check_google_routes(google_server_key)))
    else:
        report.append(configured_status("google_places", google_server_key))
        report.append(configured_status("google_routes", google_server_key))
    report.extend(
        [
            configured_status("google_maps_browser", keys["GOOGLE_MAPS_BROWSER_KEY"]),
            configured_status("openai_optional", keys["OPENAI_API_KEY"]),
        ]
    )
    return report


def self_test() -> None:
    missing = configured_status("example", "")
    configured = configured_status("example", "secret-value")
    assert missing == {"provider": "example", "status": "not_configured"}
    assert configured == {"provider": "example", "status": "configured"}
    assert "secret-value" not in json.dumps(configured)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-paid",
        action="store_true",
        help="make one potentially billable Google Places and one Routes request",
    )
    parser.add_argument("--self-test", action="store_true", help="run redaction/report checks")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("self-test: passed")
        return 0

    try:
        report = build_report(load_keys(), live_paid=args.live_paid)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"configuration": "error", "detail": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 1 if any(item["status"] == "error" for item in report) else 0


if __name__ == "__main__":
    sys.exit(main())
