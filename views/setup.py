"""Trip basics, travellers, and confirmation. The first stage."""

from __future__ import annotations

import streamlit as st

from ui import shared
from datetime import time
from travel_planner.setup import ALSO_ENJOY_TAGS, AVOID_TAGS, COMFORT_TAGS, MAIN_STYLE_TAGS
from ui.shared import _date_value, _empty_setup, _time_value
from ui.text import ACCOMMODATION_TEXT, TAG_TEXT

actions = shared.actions()
copy = shared.words()
language = shared.language()
trip = shared.trip()

st.title(copy["title"])
st.caption(copy["caption"])

with st.expander(copy["new_trip"], expanded=trip is None):
    with st.form("create_trip"):
        name = st.text_input(copy["trip_name"], key="trip_name")
        destination = st.text_input(copy["destination"], key="destination")
        planning_mode = st.selectbox(
            copy["mode"],
            options=("explore_first", "ready_to_schedule"),
            format_func=lambda value: copy[value],
            key="planning_mode",
        )
        submitted = st.form_submit_button(copy["create"])
    if submitted:
        if not destination.strip():
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
if active_plan:
    st.caption(f"{copy['active_plan']}: {active_plan.version_id}")

# Overdue and due-soon work shows whenever the app opens.
if actions.get_setup(trip.trip_id):
    board = actions.checklist_readiness(trip.trip_id)
    for item in board["overdue"][:3]:
        st.warning(
            f"{copy['overdue']}: {display_title(item, copy)} · {item['due_date']}"
        )
    for item in board["due_soon"][:3]:
        st.info(
            f"{copy['due_soon']}: {display_title(item, copy)} · {item['due_date']}"
        )

setup = actions.get_setup(trip.trip_id)
setup_payload = setup.snapshot.as_dict() if setup else _empty_setup(trip.planning_mode)
basics = setup_payload["trip_basics"]
owner = setup_payload["owner"]
saved_members = setup_payload.get("travellers", [])

st.divider()
st.subheader(copy["setup"])
st.caption(copy["setup_help"])
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

all_member_tags = tuple(dict.fromkeys(MAIN_STYLE_TAGS + ALSO_ENJOY_TAGS + AVOID_TAGS + COMFORT_TAGS))
with st.form(f"setup_form_{trip.trip_id}"):
    st.markdown(f"#### {copy['trip_basics']}")
    has_dates = st.checkbox(
        copy["dates_known"],
        value=bool(basics.get("start_date") and basics.get("end_date")),
        key=f"has_dates_{trip.trip_id}",
    )
    start_column, end_column = st.columns(2)
    start_value = start_column.date_input(
        copy["start_date"],
        value=_date_value(basics.get("start_date")),
        disabled=not has_dates,
        key=f"start_date_{trip.trip_id}",
    )
    end_value = end_column.date_input(
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
        arrival_value = st.time_input(
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
        departure_value = st.time_input(
            copy["departure_time"],
            value=_time_value(basics.get("departure_time"), time(11, 0)),
            disabled=not has_departure,
            key=f"departure_time_{trip.trip_id}",
        )
    accommodation_options = ("unknown", "not_booked", "booked")
    accommodation_status = st.selectbox(
        copy["accommodation"],
        accommodation_options,
        index=accommodation_options.index(basics.get("accommodation_status", "unknown")),
        format_func=lambda value: ACCOMMODATION_TEXT[language][value],
        key=f"accommodation_{trip.trip_id}",
    )

    st.markdown(f"#### {copy['owner_style']}")
    owner_age = int(
        st.number_input(
            copy["owner_age"],
            min_value=0,
            max_value=120,
            value=int(owner.get("age") or 0),
            step=1,
            key=f"owner_age_{trip.trip_id}",
        )
    )
    main_style = st.multiselect(
        copy["main_style"],
        MAIN_STYLE_TAGS,
        default=owner.get("main_style", []),
        format_func=lambda value: TAG_TEXT[language][value],
        key=f"main_style_{trip.trip_id}",
    )
    also_enjoy = st.multiselect(
        copy["also_enjoy"],
        ALSO_ENJOY_TAGS,
        default=owner.get("also_enjoy", []),
        format_func=lambda value: TAG_TEXT[language][value],
        key=f"also_enjoy_{trip.trip_id}",
    )
    avoid = st.multiselect(
        copy["avoid"],
        AVOID_TAGS,
        default=owner.get("avoid", []),
        format_func=lambda value: TAG_TEXT[language][value],
        key=f"avoid_{trip.trip_id}",
    )
    comfort = st.multiselect(
        copy["comfort"],
        COMFORT_TAGS,
        default=owner.get("comfort", []),
        format_func=lambda value: TAG_TEXT[language][value],
        key=f"comfort_{trip.trip_id}",
    )
    owner_description = st.text_area(
        copy["description"],
        value=owner.get("description", ""),
        key=f"owner_description_{trip.trip_id}",
    )

    st.markdown(f"#### {copy['travellers']}")
    member_inputs = []
    for index in range(member_count):
        saved = saved_members[index] if index < len(saved_members) else {}
        with st.expander(f"{copy['member']} {index + 1}", expanded=index < 2):
            member_inputs.append(
                {
                    "traveller_id": saved.get("traveller_id", f"member_{index + 1}"),
                    "label": st.text_input(
                        copy["member_name"],
                        value=saved.get("label", f"Traveller {index + 1}"),
                        key=f"member_label_{trip.trip_id}_{index}",
                    ),
                    "age": int(
                        st.number_input(
                            copy["member_age"],
                            min_value=0,
                            max_value=120,
                            value=int(saved.get("age") or 0),
                            step=1,
                            key=f"member_age_{trip.trip_id}_{index}",
                        )
                    ),
                    "tags": st.multiselect(
                        copy["member_tags"],
                        all_member_tags,
                        default=saved.get("tags", []),
                        format_func=lambda value: TAG_TEXT[language][value],
                        key=f"member_tags_{trip.trip_id}_{index}",
                    ),
                    "description": st.text_area(
                        copy["member_notes"],
                        value=saved.get("description", ""),
                        key=f"member_notes_{trip.trip_id}_{index}",
                    ),
                    "must_respect": st.text_area(
                        copy["member_must"],
                        value="\n".join(saved.get("must_respect", [])),
                        key=f"member_must_{trip.trip_id}_{index}",
                    ).splitlines(),
                }
            )

    st.markdown(f"#### {copy['requirements']}")
    owner_must_respect = st.text_area(
        copy["owner_must"],
        value="\n".join(owner.get("must_respect", [])),
        key=f"owner_must_{trip.trip_id}",
    )
    save_draft, confirm_setup = st.columns(2)
    draft_submitted = save_draft.form_submit_button(copy["save_draft"])
    confirm_submitted = confirm_setup.form_submit_button(copy["confirm"])

if draft_submitted or confirm_submitted:
    if confirm_submitted and not main_style:
        st.error(copy["main_required"])
    else:
        try:
            setup = actions.save_setup(
                trip_id=trip.trip_id,
                owner_age=owner_age or None,
                main_style=main_style,
                also_enjoy=also_enjoy,
                avoid=avoid,
                comfort=comfort,
                owner_description=owner_description,
                owner_must_respect=owner_must_respect,
                travellers=member_inputs,
                start_date=start_value.isoformat() if has_dates else None,
                end_date=end_value.isoformat() if has_dates else None,
                arrival_time=arrival_value.strftime("%H:%M") if has_arrival else None,
                departure_time=departure_value.strftime("%H:%M") if has_departure else None,
                accommodation_status=accommodation_status,
                confirmed=confirm_submitted,
            )
        except ValueError as error:
            st.error(shared.plain(error))
        else:
            setup_payload = setup.snapshot.as_dict()
            st.success(copy["confirmed"] if setup.confirmed else copy["draft_saved"])

if setup:
    st.markdown(f"#### {copy['review']}")
    review_owner = setup_payload["owner"]
    review_basics = setup_payload["trip_basics"]
    setup_state, people, preference_count = st.columns(3)
    setup_state.metric(
        copy["setup_state"], copy["confirmed_setup"] if setup.confirmed else copy["draft_setup"]
    )
    people.metric(copy["people"], 1 + len(setup_payload.get("travellers", [])))
    preference_count.metric(
        copy["preferences"],
        len(review_owner["main_style"])
        + len(review_owner["also_enjoy"])
        + len(review_owner["avoid"])
        + len(review_owner["comfort"]),
    )
    st.write(" · ".join(TAG_TEXT[language][tag] for tag in review_owner["main_style"]))
    if not review_basics.get("start_date"):
        st.warning(copy["no_dates"])
