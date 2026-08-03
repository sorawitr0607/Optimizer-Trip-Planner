"""Shared presentation state and renderers used by every view.

The entry script resolves the language, the actions object, and the selected
trip once per run and puts them here; each view reads them rather than rebuilding
them. `journey()` computes which stage the trip has reached, so a view can say
what is missing instead of failing, and the sidebar can show progress.
"""

from __future__ import annotations

from datetime import date, time
import os
from urllib.parse import quote

import streamlit as st

from travel_planner import PlannerActions
from travel_planner.actions import PlannerRefusal
from travel_planner.checklist import (
    display_consequence,
    display_title,
    AUTHORITY_TYPES as CHECKLIST_AUTHORITIES,
    PROGRESS_STATES as CHECKLIST_PROGRESS,
)
from travel_planner.exporters import (
    checklist_ics,
    plan_workbook_xlsx,
)
from ui.text import (
    ACCOMMODATION_TEXT,
    CATEGORY_TEXT,
    DIMENSION_TEXT,
    EXPLANATION_TEXT,
    OPTIMIZER_CODE_TEXT,
    REJECTION_TEXT,
    TAG_TEXT,
    TEXT,
)

LANGUAGE_KEY = "language"
TRIP_KEY = "selected_trip_id"
NEW_TRIP_KEY = "creating_trip_slot"
PENDING_TRIP_KEY = "_select_trip_on_next_run"


def actions() -> PlannerActions:
    """One actions object per run, shared by the sidebar and every view."""

    existing = st.session_state.get("_actions")
    if existing is None:
        existing = PlannerActions(
            os.environ.get("TOURIST_DB_PATH", "data/tourist.sqlite3")
        )
        st.session_state["_actions"] = existing
    return existing


def plain(value: object) -> str:
    """Text that must survive Streamlit's markdown, e.g. money and error text.

    A pair of dollar signs in one block is read as inline LaTeX, which silently
    swallowed the amounts in `US$0.1300 / US$10.00`. Nothing in this app is ever
    meant as maths, so any string built from numbers or exception text goes
    through here.
    """

    if isinstance(value, PlannerRefusal):
        value = OPTIMIZER_CODE_TEXT[language()].get(value.code, f"⚠ {value.code}")
    return str(value).replace("$", r"\$")


def language() -> str:
    return st.session_state.get(LANGUAGE_KEY, "en")


def words() -> dict:
    return TEXT[language()]


def _language_key(base_key: str) -> str:
    return f"{base_key}__{language()}"


def chosen(base_key: str, default=None):
    """Current value of a `translated_*` widget, by its language-free name.

    The widget key carries the language, so read the live widget value first and
    fall back to what the last render stored. A callback fires after the widget
    it belongs to has rendered, so the first branch is the one that matters.
    """

    if _language_key(base_key) in st.session_state:
        return st.session_state[_language_key(base_key)]
    return st.session_state.get(f"{base_key}__choice", default)


def _remember(base_key: str, picked):
    st.session_state[f"{base_key}__choice"] = picked
    return picked


def _seed(base_key: str, values: list, *, accept_new: bool):
    """The stored choice, kept selectable across a language switch."""

    saved = st.session_state.get(f"{base_key}__choice")
    if saved is not None and accept_new and saved not in values:
        # A typed-in option is not in the table; keep it rather than dropping the
        # owner's own entry the moment they change language.
        values.append(saved)
    return saved


def translated_selectbox(label: str, options, *, key: str, index: int | None = 0, **kwargs):
    """A selectbox whose shown option survives a language switch.

    Streamlit caches the selected option's rendered text in the browser, so a
    widget whose `format_func` depends on the language keeps displaying the old
    wording: the dropdown list updates, the closed control does not. Giving the
    widget a per-language key rebuilds it, and carrying the choice in a
    language-free key means switching language changes only the wording.
    """

    values = list(options)
    saved = _seed(key, values, accept_new=bool(kwargs.get("accept_new_options")))
    if saved in values:
        index = values.index(saved)
    return _remember(
        key, st.selectbox(label, values, index=index, key=_language_key(key), **kwargs)
    )


def translated_multiselect(label: str, options, *, key: str, default=(), **kwargs):
    """A multiselect whose chips survive a language switch. See above."""

    values = list(options)
    saved = _seed(key, values, accept_new=bool(kwargs.get("accept_new_options")))
    start = [item for item in (default if saved is None else saved) if item in values]
    # Streamlit's built-in placeholder is English, so an empty multiselect read
    # "Choose options" next to a Thai label. Every translated one passes here.
    kwargs.setdefault("placeholder", words()["choose_options"])
    return _remember(
        key, st.multiselect(label, values, default=start, key=_language_key(key), **kwargs)
    )


def trip():
    """The selected trip, or None when the owner has not created one yet."""

    planner = actions()
    trips = planner.list_trips()
    if not trips:
        return None
    selected = st.session_state.get(TRIP_KEY)
    for candidate in trips:
        if candidate.trip_id == selected:
            return candidate
    st.session_state[TRIP_KEY] = trips[0].trip_id
    return trips[0]


def journey(current_trip) -> dict:
    """Compatibility shim while the Streamlit POC remains in the tree."""

    if current_trip is None:
        return {
            "stages": [{"key": "setup", "done": False, "blocked_by": None}],
            "next": "setup",
        }
    return actions().journey(current_trip.trip_id)


def require(stage_key: str, current_trip, *, journey_state: dict | None = None) -> bool:
    """Render one clear next step when a stage is not reachable yet.

    Returns True when the view may draw itself.
    """

    copy = words()
    if current_trip is None:
        st.info(copy["journey_needs_trip"])
        return False
    state = journey_state or journey(current_trip)
    stage = next((item for item in state["stages"] if item["key"] == stage_key), None)
    if stage is None or stage["blocked_by"] is None:
        return True
    st.info(
        f"{copy['journey_blocked']} {copy['stage_' + stage['blocked_by']]}"
    )
    return False



def _category_text(category: str, language: str) -> str:
    return CATEGORY_TEXT[language].get(category, category.replace("_", " ").title())


def _explain(code: str, language: str) -> str:
    return EXPLANATION_TEXT[language].get(code, f"⚠ {code}")


def _optimizer_code(code: str, language: str) -> str:
    return OPTIMIZER_CODE_TEXT.get(language, {}).get(code, f"⚠ {code}")


def _plan_item_name(item: dict, language: str) -> str:
    if item["type"] == "travel":
        return f"{item.get('origin_id') or 'start'} → {item['destination_id']} · {item.get('mode') or '?'}"
    if item["type"] == "buffer":
        return _optimizer_code(item.get("reason", "buffer"), language)
    names = item.get("names", {})
    return names.get(language) or names.get("en") or names.get("local") or item["name"]


def _candidate_name(candidate: dict, language: str) -> str:
    names = candidate.get("names", {})
    return names.get(language) or names.get("en") or names.get("local") or candidate["name"]


def _photo_url(reference: str | None) -> str | None:
    if not reference:
        return None
    if reference.startswith(("https://", "http://")):
        return reference
    if reference.startswith("File:"):
        return "https://commons.wikimedia.org/wiki/Special:Redirect/file/" + quote(
            reference.removeprefix("File:")
        )
    return None


def _empty_setup(mode: str) -> dict:
    return {
        "planning_mode": mode,
        "trip_basics": {
            "start_date": None,
            "end_date": None,
            "arrival_time": None,
            "departure_time": None,
            "accommodation_status": "unknown",
        },
        "owner": {
            "age": None,
            "main_style": [],
            "also_enjoy": [],
            "avoid": [],
            "comfort": [],
            "description": "",
            "must_respect": [],
        },
        "travellers": [],
    }


def _date_value(value: str | None) -> date:
    return date.fromisoformat(value) if value else date.today()


def _time_value(value: str | None, fallback: time) -> time:
    return time.fromisoformat(value) if value else fallback


def _export_labels(language: str) -> dict:
    """Interface copy plus optimizer-code wording, so documents match the app."""

    return TEXT[language] | OPTIMIZER_CODE_TEXT.get(language, {})


@st.cache_data(show_spinner=False)
def _plan_documents(_snapshot: dict, sha256: str, language: str) -> dict[str, bytes]:
    """Cached per plan-version snapshot and language; exporters are pure."""

    labels = _export_labels(language)
    return {
        "xlsx": plan_workbook_xlsx(_snapshot, labels),
        "ics": checklist_ics(_snapshot, labels),
    }



def _render_checklist_item(
    actions, trip, item: dict, language: str, flash_key: str
) -> None:
    """One board row: state, deadline, consequence, and its evidence controls."""

    words = TEXT[language]
    with st.container(border=True):
        badge = words[f"progress_{item['progress']}"]
        evidence = words[f"evidence_{item['evidence_state']}"]
        st.markdown(f"**{display_title(item, words)}**")
        line = f"{words[item['requirement_level']]} · {badge} · {evidence}"
        if item.get("due_date"):
            line = f"{line} · {words['due']} {item['due_date']}"
        st.caption(line)
        consequence = display_consequence(item, words)
        if consequence:
            st.caption(f"{words['consequence']}: {consequence}")

        progress = translated_selectbox(
            words["progress"],
            CHECKLIST_PROGRESS,
            key=f"progress_{item['item_id']}",
            index=CHECKLIST_PROGRESS.index(item["progress"]),
            format_func=lambda value: words[f"progress_{value}"],
        )
        note = ""
        if progress == "not_applicable":
            note = st.text_input(
                words["not_applicable_reason"],
                value=item.get("note") or "",
                key=f"note_{item['item_id']}",
            )
        if progress != item["progress"] or (note and note != (item.get("note") or "")):
            if st.button(words["save_task"], key=f"save_{item['item_id']}"):
                try:
                    actions.set_checklist_progress(
                        trip_id=trip.trip_id,
                        item_id=item["item_id"],
                        progress=progress,
                        note=note or None,
                    )
                except ValueError as error:
                    st.error(plain(error))
                else:
                    st.session_state[flash_key] = words["task_saved"]
                    st.rerun()

        with st.expander(words["evidence"]):
            if item.get("expected_authority"):
                st.caption(
                    f"{words['expected_authority']}: "
                    f"{words.get(item['expected_authority'], item['expected_authority'])}"
                )
            if item["evidence_state"] == "verified":
                st.markdown(f"{item.get('source_url')}")
                st.caption(f"{words['last_checked']}: {item.get('last_checked_at')}")
            else:
                st.caption(words["evidence_verification_needed_help"])
            url = st.text_input(
                words["source_url"],
                value=item.get("source_url") or "",
                key=f"url_{item['item_id']}",
            )
            authority = translated_selectbox(
                words["authority_type"],
                CHECKLIST_AUTHORITIES,
                key=f"authority_{item['item_id']}",
                index=(
                    CHECKLIST_AUTHORITIES.index(item["authority_type"])
                    if item.get("authority_type") in CHECKLIST_AUTHORITIES
                    else 0
                ),
                format_func=lambda value: words.get(value, value),
            )
            if st.button(words["record_evidence"], key=f"verify_{item['item_id']}"):
                try:
                    actions.record_checklist_evidence(
                        trip_id=trip.trip_id,
                        item_id=item["item_id"],
                        source_url=url,
                        authority_type=authority,
                    )
                except ValueError as error:
                    st.error(plain(error))
                else:
                    st.session_state[flash_key] = words["evidence_recorded"]
                    st.rerun()

        if st.button(words["dismiss_task"], key=f"dismiss_{item['item_id']}"):
            actions.set_checklist_dismissed(
                trip_id=trip.trip_id, item_id=item["item_id"], dismissed=True
            )
            st.session_state[flash_key] = words["task_dismissed"]
            st.rerun()


def _render_fallback(fallback: dict, language: str) -> None:
    """The half-day's fallback, with its trigger, swap, and displaced selection."""

    words = TEXT[language]
    with st.container(border=True):
        st.markdown(
            f"**{words['fallback']}** · {words['fallback_trigger']}: "
            f"{_optimizer_code(fallback.get('trigger') or 'unknown', language)}"
        )
        st.caption(
            f"{fallback['primary_name']} → {fallback['replacement_name']}"
            + (f" · {fallback['replacement_start']}" if fallback.get("replacement_start") else "")
            + (f" · {words['day_reoptimized']}" if fallback.get("day_reoptimized") else "")
        )
        if fallback.get("displaced_consequence"):
            st.caption(
                f"{words['consequence']}: "
                f"{_optimizer_code(fallback['displaced_consequence'], language)}"
            )


def _render_plan_item(item: dict, language: str) -> None:
    """One compact export-snapshot row; details stay behind progressive disclosure."""

    words = TEXT[language]
    clock = f"{item['start']}–{item['end']}"
    length = f"{item['duration_minutes']} {words['minutes']}"
    state = words[f"state_{item['status']}"]
    if item["type"] == "visit":
        st.markdown(
            f"**{clock}** · {words['stop']} {item['stop_number']} · {item['display_name']}"
        )
        local = f" · {item['local_name']}" if item.get("local_name") else ""
        st.caption(f"{state} · {length}{local}")
        with st.expander(words["details"]):
            st.markdown(
                f"- {words['choice']}: {words.get(item['priority'], item['priority'])}"
            )
            if item.get("address"):
                st.markdown(f"- {item['address']}")
            if not item["opening_verified"]:
                st.markdown(f"- {words['opening_unverified']}")
    elif item["type"] == "travel":
        st.markdown(f"{clock} · {item['origin_name']} → {item['destination_name']}")
        st.caption(
            f"{state} · {words['travel_mode']} {item.get('mode') or '?'} · {length} · "
            f"{words['walk_portion']} {item['walking_minutes']} {words['minutes']}"
        )
        with st.expander(words["details"]):
            st.markdown(
                "- "
                + (
                    words["sightseeing_walk"]
                    if item["sightseeing_walk"]
                    else words["plain_transfer"]
                )
            )
            if item.get("distance_m"):
                st.markdown(f"- {words['distance']}: {item['distance_m']} m")
            if item.get("transfers") is not None:
                st.markdown(f"- {words['transfers']}: {item['transfers']}")
            if item["boarding_buffer_minutes"]:
                st.markdown(
                    f"- {words['boarding_buffer']}: "
                    f"{item['boarding_buffer_minutes']} {words['minutes']}"
                )
    elif item["type"] in {"meal", "preparation", "logistics"}:
        st.markdown(f"**{clock}** · {item['display_name']}")
        st.caption(
            f"{state} · {words.get('type_' + item['type'], item['type'])} · {length}"
        )
        with st.expander(words["details"]):
            if item.get("from_name") or item.get("to_name"):
                st.markdown(
                    f"- {item.get('from_name') or '?'} → {item.get('to_name') or '?'}"
                )
            if item.get("mode"):
                st.markdown(f"- {words['travel_mode']}: {item['mode']}")
            st.markdown(f"- {item['notes']}")
            st.markdown(f"- {words['confirmation_needed']}")
    else:
        reason = _optimizer_code(item.get("reason") or "buffer", language)
        st.caption(f"{clock} · {reason} · {length}")
