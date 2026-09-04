"""Proactive plan review: the model suggests typed revision operations.

Beside `interpret`, which turns one free-text request into one operation: the
reviewer reads the active plan unprompted and returns a *list* of suggestions,
each a fully typed operation the owner may propose one at a time through the
normal revision draft flow.

Suggestions only. Every item is validated here before it is returned, nothing
is applied, and the schema carries no time, date, route, hour, fare or closure
-- the same guarantee `interpret` makes, so a future model that only chooses
among these operations still cannot invent an operational fact. A suggestion
without a concrete value (a duration with no minutes) is unactionable and is
dropped rather than clarified: there is no request to attach a question to.
"""

from __future__ import annotations

from typing import Any

from . import interpret, revision


SCHEMA_VERSION = 1
LANGUAGES = ("en", "th")
MAX_SUGGESTIONS = 6
MAX_RATIONALE_CHARS = 280

#: Per-place operations only. Systemic threshold changes already have quick
#: actions; the reviewer's judgment is about places, and every operation here
#: carries a place_id the reply can be confined to.
REVIEW_OPERATIONS = ("adjust_duration", "drop_place", "lock_item")


def response_schema() -> dict[str, Any]:
    """Strict structured-output schema: a short list of typed suggestions."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["suggestions"],
        "properties": {
            "suggestions": {
                "type": "array",
                "maxItems": MAX_SUGGESTIONS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["operation", "arguments", "rationale"],
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": list(REVIEW_OPERATIONS),
                        },
                        "arguments": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["place_id", "minutes"],
                            "properties": {
                                "place_id": {"type": ["string", "null"]},
                                "minutes": {"type": ["integer", "null"]},
                            },
                        },
                        "rationale": {"type": ["string", "null"]},
                    },
                },
            }
        },
    }


def build_payload(*, plan: dict[str, Any], language: str) -> dict[str, Any]:
    """The same smallest plan slice `interpret` sends, and nothing else."""

    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "app_language": language,
        "supported_operations": list(REVIEW_OPERATIONS),
        "plan": interpret.plan_slice(plan),
    }
    interpret._assert_clean(payload)
    return payload


def validate_reply(response: Any, *, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a model reply into suggestions, skipping what is not one.

    Each surviving item passed `revision.validate_operation` and names a place
    the payload actually showed, so it can go straight into `propose_revision`.
    Invalid items are counted, not fatal: suggestions are independent, and one
    bad apple must not eat the call. An empty list is a valid answer -- the
    reviewer found nothing -- while a reply with no list at all is malformed.
    """

    if not isinstance(response, dict):
        raise ValueError("Model reply was not an object")
    raw = response.get("suggestions")
    if not isinstance(raw, list):
        raise ValueError("Model reply carried no suggestions list")
    allowed = interpret.allowed_place_ids(payload)
    locked = {
        str(lock) for lock in payload.get("plan", {}).get("locks", []) if lock
    }
    suggestions: list[dict[str, Any]] = []
    dropped = max(0, len(raw) - MAX_SUGGESTIONS)
    for item in raw[:MAX_SUGGESTIONS]:
        if not isinstance(item, dict):
            dropped += 1
            continue
        if str(item.get("operation") or "") not in REVIEW_OPERATIONS:
            dropped += 1
            continue
        args = item.get("arguments")
        if not isinstance(args, dict):
            dropped += 1
            continue
        place_id = args.get("place_id")
        if place_id is None or str(place_id) not in allowed:
            # The model may only act on entities it was actually given.
            dropped += 1
            continue
        if str(item.get("operation")) == "lock_item" and str(place_id) in locked:
            dropped += 1
            continue
        try:
            clean = revision.validate_operation(
                {
                    "operation": item.get("operation"),
                    "arguments": {
                        key: value
                        for key, value in args.items()
                        if value is not None and key in {"place_id", "minutes"}
                    },
                }
            )
        except ValueError:
            dropped += 1
            continue
        rationale = str(item.get("rationale") or "").strip() or None
        suggestions.append(
            {
                "operation": clean["operation"],
                "arguments": clean["arguments"],
                "rationale": rationale[:MAX_RATIONALE_CHARS] if rationale else None,
            }
        )
    return {"suggestions": suggestions, "dropped": dropped}
