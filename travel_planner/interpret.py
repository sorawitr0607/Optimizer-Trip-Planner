"""Free text to one typed revision operation.

Pure: no Streamlit, SQLite, provider, exporter, or HTTP imports.

The model only ever *chooses* among the operations in `revision.OPERATIONS` and
supplies their arguments. It cannot name a place that was not sent to it, and it
cannot return an opening time, route, fare or closure, because no operation
carries such a field. Everything the model returns is validated here before any
optimizer run, so a refusal, a malformed reply, or an unsupported request leaves
the plan untouched.
"""

from __future__ import annotations

from typing import Any

from . import revision


SCHEMA_VERSION = 1
UNSUPPORTED = "unsupported"
LANGUAGES = ("en", "th")

# A model should not be asked to invent a magnitude. Where a safe default
# exists, the app supplies it and shows it as a visible assumption; where the
# value is the whole point of the request, one clarification is asked instead.
ASSUMED_DEFAULTS = {
    "reduce_walking": {"factor": 0.7},
    "reduce_daily_load": {"factor": 0.7},
    "fix_meal_timing": {"start": "12:00", "end": "13:30"},
}

# Never sent to a model, whatever the plan slice happens to contain.
FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "api_key",
        "access_token",
        "authorization",
        "password",
        "passport_number",
        "passport_document",
        "booking_document",
        "google_maps_server_key",
        "google_maps_browser_key",
        "openai_api_key",
        "travellers",
        "owner",
        "reviews",
        "review_text",
        "photo_reference",
    }
)


def response_schema() -> dict[str, Any]:
    """Strict structured-output schema, derived from the operation set itself."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["operation", "arguments", "clarification", "unsupported_reason"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": [*sorted(revision.OPERATIONS), UNSUPPORTED],
            },
            "arguments": {
                "type": "object",
                "additionalProperties": False,
                "required": ["place_id", "factor", "minutes", "start", "end"],
                "properties": {
                    "place_id": {"type": ["string", "null"]},
                    "factor": {"type": ["number", "null"]},
                    "minutes": {"type": ["integer", "null"]},
                    "start": {"type": ["string", "null"]},
                    "end": {"type": ["string", "null"]},
                },
            },
            "clarification": {"type": ["string", "null"]},
            "unsupported_reason": {"type": ["string", "null"]},
        },
    }


def build_payload(
    *, plan: dict[str, Any], request_text: str, language: str
) -> dict[str, Any]:
    """The smallest slice that can answer the request, and nothing else."""

    text = str(request_text or "").strip()
    if not text:
        raise ValueError("A revision request needs some text")
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    variant = plan.get("variant") or {}
    planner_input = plan.get("optimizer_input") or {}
    days = []
    for day in variant.get("days", []):
        days.append(
            {
                "date": day["date"],
                "items": [
                    {
                        "place_id": item["subject_id"],
                        "name": item.get("name"),
                        "start": item["start"],
                        "end": item["end"],
                        "duration_minutes": item["duration_minutes"],
                    }
                    for item in day.get("items", [])
                    if item.get("type") == "visit"
                ],
            }
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "request": text,
        "app_language": language,
        "supported_operations": sorted(revision.OPERATIONS),
        "plan": {
            "variant_id": variant.get("variant_id"),
            "days": days,
            "thresholds": dict(planner_input.get("thresholds") or {}),
            "locks": [
                str(lock.get("subject_id"))
                for lock in planner_input.get("locks") or []
            ],
            "warnings": sorted(set(variant.get("warnings") or [])),
            "unscheduled": [
                {"place_id": item["place_id"], "reason": item["reason"]}
                for item in variant.get("reconciliation") or []
                if item.get("status") == "cannot_currently_fit"
            ],
        },
    }
    _assert_clean(payload)
    return payload


def allowed_place_ids(payload: dict[str, Any]) -> set[str]:
    """The stable IDs the model was shown; it may name no other."""

    return {
        str(item["place_id"])
        for day in payload["plan"]["days"]
        for item in day["items"]
    } | {str(item["place_id"]) for item in payload["plan"]["unscheduled"]}


def interpret_response(
    response: Any, *, payload: dict[str, Any]
) -> dict[str, Any]:
    """Validate a model reply into a typed operation, or a refusal."""

    if not isinstance(response, dict):
        raise ValueError("Model reply was not an object")
    operation = str(response.get("operation") or "")
    if not operation:
        raise ValueError("Model reply named no operation")
    if operation == UNSUPPORTED:
        return {
            "operation": None,
            "arguments": {},
            "supported": False,
            "clarification": _text(response.get("clarification")),
            "unsupported_reason": _text(response.get("unsupported_reason"))
            or "UNSUPPORTED_REQUEST",
            "assumptions": [],
        }
    if operation not in revision.OPERATIONS:
        raise ValueError(f"Model reply named an unknown operation: {operation}")

    raw = response.get("arguments") or {}
    if not isinstance(raw, dict):
        raise ValueError("Model arguments were not an object")
    arguments = {
        key: value
        for key, value in raw.items()
        if value is not None and key in {"place_id", "factor", "minutes", "start", "end"}
    }
    place_id = arguments.get("place_id")
    if place_id is not None and str(place_id) not in allowed_place_ids(payload):
        # The model may only act on entities it was actually given.
        raise ValueError(f"Model named a place outside the plan: {place_id}")
    assumptions = []
    for key, default in ASSUMED_DEFAULTS.get(operation, {}).items():
        if key not in arguments:
            arguments[key] = default
            assumptions.append(f"ASSUMED_{key.upper()}_{default}")

    try:
        typed = revision.validate_operation(
            {"operation": operation, "arguments": arguments}
        )
    except ValueError as error:
        message = str(error)
        if " needs " not in message:
            # A malformed value is a bad reply, not a question for the owner.
            raise
        return {
            "operation": None,
            "arguments": {},
            "supported": False,
            "clarification": _text(response.get("clarification"))
            or f"Which value should apply? {message}",
            "unsupported_reason": "NEEDS_CLARIFICATION",
            "assumptions": [],
        }
    return {
        **typed,
        "supported": True,
        "clarification": _text(response.get("clarification")),
        "unsupported_reason": None,
        "assumptions": assumptions,
    }


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _assert_clean(value: Any, path: str = "payload") -> None:
    """Refuse to send a payload carrying anything on the exclusion list."""

    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in FORBIDDEN_PAYLOAD_KEYS or normalized.endswith(
                ("_api_key", "_secret", "_token", "_credential")
            ):
                raise ValueError(f"{path}.{key} must never be sent to a model")
            _assert_clean(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_clean(child, f"{path}[{index}]")
