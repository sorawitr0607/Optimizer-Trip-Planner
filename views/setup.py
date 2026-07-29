"""Trip basics, travellers, and confirmation. The first stage.

Five short editable steps rather than one long form, as `Prototype the owner-led
setup and confirmation flow` specifies. Each `Save & continue` autosaves a draft
locally and calls no provider, so the owner can leave and resume at any step.

Three structural notes:

- There is no `st.form` here. The city list depends on the chosen country, and a
  form defers every value until submit, which would leave the city dropdown
  showing the previous country's cities. Plain widgets rerun on change instead.
- A step reads its initial values from the saved draft, not from session state.
  Streamlit drops widget state once a widget stops being rendered, so the draft
  in SQLite is the only thing that survives moving between steps.
- Moving between steps happens in an `on_click` callback rather than through
  `st.rerun()`. A callback runs after the widget values are committed but before
  the script reruns, so it saves what the owner can actually see — a closure
  captured at render time would miss an edit made just before the click. It also
  keeps exactly one step in each run, which `st.rerun()` mid-script does not.
"""

from __future__ import annotations

import streamlit as st

from ui import shared
from datetime import time
from travel_planner import destinations
from travel_planner.checklist import display_title
from travel_planner.setup import ALSO_ENJOY_TAGS, AVOID_TAGS, COMFORT_TAGS, MAIN_STYLE_TAGS
from ui.shared import _date_value, _empty_setup, _time_value
from ui.text import ACCOMMODATION_TEXT, TAG_TEXT

actions = shared.actions()
copy = shared.words()
language = shared.language()
trip = shared.trip()

STEP_COUNT = 5

st.title(copy["title"])
st.caption(copy["caption"])

with st.expander(copy["new_trip"], expanded=trip is None):
    # Outside a form: choosing a country must refresh the city list immediately,
    # and the resulting geocoder query is shown before the trip is created.
    # Both dropdowns accept a typed value, so every worldwide destination stays
    # reachable without a separate "Other" branch. Neither is pre-selected: a
    # silently defaulted country would become somebody's trip.
    country_column, city_column = st.columns(2)
    with country_column:
        country = shared.translated_selectbox(
            copy["country"],
            destinations.country_options(),
            key="country",
            index=None,
            placeholder=copy["choose_country"],
            format_func=lambda value: destinations.country_label(value, language),
            accept_new_options=True,
        )
    with city_column:
        city = shared.translated_selectbox(
            copy["city"],
            destinations.city_options(country or ""),
            key="city",
            index=None,
            placeholder=copy["choose_city"],
            accept_new_options=True,
        )

    country = (country or "").strip()
    city = (city or "").strip()
    try:
        destination = destinations.destination_text(country, city)
    except ValueError:
        destination = ""
    if destination:
        st.caption(f"{copy['destination_preview']}: {destination}")

    name = st.text_input(copy["trip_name"], key="trip_name")
    planning_mode = shared.translated_selectbox(
        copy["mode"],
        ("explore_first", "ready_to_schedule"),
        key="planning_mode",
        format_func=lambda value: copy[value],
    )
    if st.button(copy["create"], key="create_trip", type="primary"):
        if not destination:
            st.error(copy["destination_required"])
        else:
            try:
                created = actions.create_trip(
                    name=name,
                    destination=destination,
                    planning_mode=planning_mode,
                    language=language,
                )
            except ValueError as error:
                st.error(shared.plain(error))
            else:
                st.session_state[shared.TRIP_KEY] = created.trip_id
                st.success(copy["created"])
                st.rerun()

if trip is None:
    # The creation form above is the whole page; the sidebar already says so.
    st.stop()

active_plan = actions.get_active_plan(trip.trip_id)
status_column, mode_column = st.columns(2)
status_column.metric(copy["status"], copy["ready"] if active_plan else copy["draft"])
mode_column.metric(copy["mode_label"], copy[trip.planning_mode])
st.caption(f"{copy['destination']}: {trip.destination}")
if active_plan:
    st.caption(f"{copy['active_plan']}: {active_plan.version_id}")

setup = actions.get_setup(trip.trip_id)
setup_payload = setup.snapshot.as_dict() if setup else _empty_setup(trip.planning_mode)
already_confirmed = bool(setup and setup.confirmed)

# Overdue and due-soon work shows whenever the app opens, above the stepper: a
# deadline matters regardless of which setup step is open.
if setup:
    board = actions.checklist_readiness(trip.trip_id)
    for item in board["overdue"][:3]:
        st.warning(f"{copy['overdue']}: {display_title(item, copy)} · {item['due_date']}")
    for item in board["due_soon"][:3]:
        st.info(f"{copy['due_soon']}: {display_title(item, copy)} · {item['due_date']}")

st.divider()
st.subheader(copy["setup"])
st.caption(copy["setup_help"])

STEP_KEY = f"setup_step_{trip.trip_id}"
FLASH_KEY = f"setup_flash_{trip.trip_id}"
step = min(max(int(st.session_state.get(STEP_KEY, 1)), 1), STEP_COUNT)

# A callback cannot draw anything, so it leaves its outcome here for this run.
flash = st.session_state.pop(FLASH_KEY, None)
if flash:
    level, message = flash
    getattr(st, level)(shared.plain(message))

basics = setup_payload["trip_basics"]
owner = setup_payload["owner"]
saved_members = setup_payload.get("travellers", [])


def _saved_values() -> dict:
    """Every save_setup argument as currently stored in the draft.

    The step being left overrides its own entries; everything else is written
    back unchanged, so saving step 1 cannot wipe the tags saved in step 2.
    """

    return {
        "owner_age": owner.get("age"),
        "main_style": owner.get("main_style", []),
        "also_enjoy": owner.get("also_enjoy", []),
        "avoid": owner.get("avoid", []),
        "comfort": owner.get("comfort", []),
        "owner_description": owner.get("description", ""),
        "owner_must_respect": owner.get("must_respect", []),
        "travellers": saved_members,
        "start_date": basics.get("start_date"),
        "end_date": basics.get("end_date"),
        "arrival_time": basics.get("arrival_time"),
        "departure_time": basics.get("departure_time"),
        "accommodation_status": basics.get("accommodation_status", "unknown"),
    }


def _edited_values(step_number: int) -> dict:
    """What the widgets of one step currently hold.

    Read from session state inside the callback rather than from local variables,
    so a value typed immediately before the click is included.
    """

    trip_id = trip.trip_id
    get = st.session_state.get
    # Translated widgets key themselves by language, so their values are read
    # through `shared.chosen` rather than straight from session state.
    picked = shared.chosen
    if step_number == 1:
        start = get(f"start_date_{trip_id}")
        end = get(f"end_date_{trip_id}")
        arrival = get(f"arrival_time_{trip_id}")
        departure = get(f"departure_time_{trip_id}")
        known = bool(get(f"has_dates_{trip_id}"))
        return {
            "start_date": start.isoformat() if known and start else None,
            "end_date": end.isoformat() if known and end else None,
            "arrival_time": (
                arrival.strftime("%H:%M") if get(f"has_arrival_{trip_id}") and arrival else None
            ),
            "departure_time": (
                departure.strftime("%H:%M")
                if get(f"has_departure_{trip_id}") and departure
                else None
            ),
            "accommodation_status": picked(f"accommodation_{trip_id}") or "unknown",
        }
    if step_number == 2:
        return {
            "owner_age": get(f"owner_age_{trip_id}") or None,
            "main_style": picked(f"main_style_{trip_id}") or [],
            "also_enjoy": picked(f"also_enjoy_{trip_id}") or [],
            "avoid": picked(f"avoid_{trip_id}") or [],
            "comfort": picked(f"comfort_{trip_id}") or [],
            "owner_description": get(f"owner_description_{trip_id}") or "",
        }
    if step_number == 3:
        count = int(get(f"member_count_{trip_id}") or 0)
        return {
            "travellers": [
                {
                    "traveller_id": (
                        saved_members[index].get("traveller_id")
                        if index < len(saved_members)
                        else f"member_{index + 1}"
                    ),
                    "label": get(f"member_label_{trip_id}_{index}")
                    or f"Traveller {index + 1}",
                    "age": int(get(f"member_age_{trip_id}_{index}") or 0),
                    "tags": picked(f"member_tags_{trip_id}_{index}") or [],
                    "description": get(f"member_notes_{trip_id}_{index}") or "",
                    "must_respect": str(
                        get(f"member_must_{trip_id}_{index}") or ""
                    ).splitlines(),
                }
                for index in range(count)
            ]
        }
    if step_number == 4:
        return {"owner_must_respect": get(f"owner_must_{trip_id}") or ""}
    # Step 5 reviews the draft and edits nothing.
    return {}


def _save(step_number: int, *, confirmed: bool) -> bool:
    """Autosave the open step. False when the draft refused the values."""

    try:
        actions.save_setup(
            trip_id=trip.trip_id,
            confirmed=confirmed,
            **(_saved_values() | _edited_values(step_number)),
        )
    except ValueError as error:
        st.session_state[FLASH_KEY] = ("error", str(error))
        return False
    return True


def _go(target: int, *, leaving: int) -> None:
    """Save the open step, then move. Nothing typed is lost by navigating."""

    if _save(leaving, confirmed=already_confirmed):
        st.session_state[STEP_KEY] = min(max(target, 1), STEP_COUNT)


def _confirm() -> None:
    if not owner["main_style"]:
        st.session_state[FLASH_KEY] = ("error", copy["main_required"])
        return
    if _save(STEP_COUNT, confirmed=True):
        st.session_state[FLASH_KEY] = ("success", copy["confirmed"])


def _save_here(step_number: int) -> None:
    if _save(step_number, confirmed=already_confirmed):
        st.session_state[FLASH_KEY] = ("success", copy["step_saved"])


STEP_TITLES = (
    copy["trip_basics"],
    copy["owner_style"],
    copy["travellers"],
    copy["requirements"],
    copy["review"],
)

st.progress(step / STEP_COUNT)
st.caption(copy["step_of"].format(current=step, total=STEP_COUNT))
st.markdown(f"#### {STEP_TITLES[step - 1]}")

if step == 1:
    has_dates = st.checkbox(
        copy["dates_known"],
        value=bool(basics.get("start_date") and basics.get("end_date")),
        key=f"has_dates_{trip.trip_id}",
    )
    start_column, end_column = st.columns(2)
    start_column.date_input(
        copy["start_date"],
        value=_date_value(basics.get("start_date")),
        disabled=not has_dates,
        key=f"start_date_{trip.trip_id}",
    )
    end_column.date_input(
        copy["end_date"],
        value=_date_value(basics.get("end_date")),
        disabled=not has_dates,
        key=f"end_date_{trip.trip_id}",
    )
    arrival_column, departure_column = st.columns(2)
    with arrival_column:
        has_arrival = st.checkbox(
            copy["arrival_known"],
            value=bool(basics.get("arrival_time")),
            key=f"has_arrival_{trip.trip_id}",
        )
        st.time_input(
            copy["arrival_time"],
            value=_time_value(basics.get("arrival_time"), time(17, 0)),
            disabled=not has_arrival,
            key=f"arrival_time_{trip.trip_id}",
        )
    with departure_column:
        has_departure = st.checkbox(
            copy["departure_known"],
            value=bool(basics.get("departure_time")),
            key=f"has_departure_{trip.trip_id}",
        )
        st.time_input(
            copy["departure_time"],
            value=_time_value(basics.get("departure_time"), time(11, 0)),
            disabled=not has_departure,
            key=f"departure_time_{trip.trip_id}",
        )
    accommodation_options = ("unknown", "not_booked", "booked")
    shared.translated_selectbox(
        copy["accommodation"],
        accommodation_options,
        key=f"accommodation_{trip.trip_id}",
        index=accommodation_options.index(basics.get("accommodation_status", "unknown")),
        format_func=lambda value: ACCOMMODATION_TEXT[language][value],
    )
    if not has_dates:
        st.caption(copy["no_dates"])

elif step == 2:
    st.number_input(
        copy["owner_age"],
        min_value=0,
        max_value=120,
        value=int(owner.get("age") or 0),
        step=1,
        key=f"owner_age_{trip.trip_id}",
    )
    # The tags lead; the description follows them as extra nuance.
    for tag_key, tag_options in (
        ("main_style", MAIN_STYLE_TAGS),
        ("also_enjoy", ALSO_ENJOY_TAGS),
        ("avoid", AVOID_TAGS),
        ("comfort", COMFORT_TAGS),
    ):
        shared.translated_multiselect(
            copy[tag_key],
            tag_options,
            key=f"{tag_key}_{trip.trip_id}",
            default=owner.get(tag_key, []),
            format_func=lambda value: TAG_TEXT[language][value],
        )
    st.text_area(
        copy["description"],
        value=owner.get("description", ""),
        key=f"owner_description_{trip.trip_id}",
    )

elif step == 3:
    all_member_tags = tuple(
        dict.fromkeys(MAIN_STYLE_TAGS + ALSO_ENJOY_TAGS + AVOID_TAGS + COMFORT_TAGS)
    )
    member_count = int(
        st.number_input(
            copy["member_count"],
            min_value=0,
            max_value=8,
            value=len(saved_members),
            step=1,
            key=f"member_count_{trip.trip_id}",
        )
    )
    for index in range(member_count):
        saved = saved_members[index] if index < len(saved_members) else {}
        with st.expander(f"{copy['member']} {index + 1}", expanded=index < 2):
            st.text_input(
                copy["member_name"],
                value=saved.get("label", f"Traveller {index + 1}"),
                key=f"member_label_{trip.trip_id}_{index}",
            )
            st.number_input(
                copy["member_age"],
                min_value=0,
                max_value=120,
                value=int(saved.get("age") or 0),
                step=1,
                key=f"member_age_{trip.trip_id}_{index}",
            )
            shared.translated_multiselect(
                copy["member_tags"],
                all_member_tags,
                key=f"member_tags_{trip.trip_id}_{index}",
                default=saved.get("tags", []),
                format_func=lambda value: TAG_TEXT[language][value],
            )
            st.text_area(
                copy["member_notes"],
                value=saved.get("description", ""),
                key=f"member_notes_{trip.trip_id}_{index}",
            )
            st.text_area(
                copy["member_must"],
                value="\n".join(saved.get("must_respect", [])),
                key=f"member_must_{trip.trip_id}_{index}",
            )

elif step == 4:
    st.text_area(
        copy["owner_must"],
        value="\n".join(owner.get("must_respect", [])),
        key=f"owner_must_{trip.trip_id}",
    )

else:
    setup_state, people, preference_count = st.columns(3)
    setup_state.metric(
        copy["setup_state"],
        copy["confirmed_setup"] if already_confirmed else copy["draft_setup"],
    )
    people.metric(copy["people"], 1 + len(saved_members))
    preference_count.metric(
        copy["preferences"],
        len(owner["main_style"])
        + len(owner["also_enjoy"])
        + len(owner["avoid"])
        + len(owner["comfort"]),
    )

    # One scannable row per step, each with the control that jumps back to it.
    dates = (
        f"{basics['start_date']} → {basics['end_date']}"
        if basics.get("start_date") and basics.get("end_date")
        else copy["no_dates"]
    )
    summary = (
        (1, copy["trip_basics"], dates),
        (
            2,
            copy["owner_style"],
            " · ".join(TAG_TEXT[language][tag] for tag in owner["main_style"]) or "—",
        ),
        (
            3,
            copy["travellers"],
            ", ".join(member["label"] for member in saved_members) or "—",
        ),
        (4, copy["requirements"], ", ".join(owner["must_respect"]) or "—"),
    )
    for target, label, value in summary:
        row, control = st.columns([4, 1])
        row.markdown(f"**{label}**")
        row.caption(shared.plain(value))
        control.button(
            copy["edit"],
            key=f"edit_step_{target}_{trip.trip_id}",
            on_click=_go,
            args=(target,),
            kwargs={"leaving": STEP_COUNT},
        )

    if not owner["main_style"]:
        st.warning(copy["main_required"])

st.divider()
back_column, draft_column, forward_column = st.columns(3)

if step > 1:
    back_column.button(
        copy["back"],
        key=f"back_{trip.trip_id}",
        on_click=_go,
        args=(step - 1,),
        kwargs={"leaving": step},
    )

# Continue autosaves too, so this only matters when the owner stops mid-step.
draft_column.button(
    copy["save_draft"],
    key=f"save_draft_{trip.trip_id}",
    on_click=_save_here,
    args=(step,),
)

if step < STEP_COUNT:
    forward_column.button(
        copy["save_continue"],
        key=f"continue_{trip.trip_id}",
        type="primary",
        on_click=_go,
        args=(step + 1,),
        kwargs={"leaving": step},
    )
else:
    forward_column.button(
        copy["confirm"], key=f"confirm_{trip.trip_id}", type="primary", on_click=_confirm
    )
