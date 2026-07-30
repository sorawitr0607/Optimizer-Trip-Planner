"""Routes, destination time zone, opening hours, and paid usage."""

from __future__ import annotations

from datetime import time

import streamlit as st

from ui import shared
from travel_planner.providers import ProviderBudgetExceeded, ProviderUnavailable
from ui.shared import _optimizer_code

actions = shared.actions()
copy = shared.words()
language = shared.language()
trip = shared.trip()
if not shared.require("evidence", trip):
    st.stop()

# The stage holds three kinds of evidence, and one of its own cards is already
# titled "Walking routes"; naming the stage after that card described neither.
st.subheader(copy["stage_evidence"])
st.caption(copy["evidence_help"])
route_flash_key = f"route_flash_{trip.trip_id}"
if route_flash := st.session_state.pop(route_flash_key, None):
    st.success(route_flash)
hours_warning_key = f"hours_warning_{trip.trip_id}"
if hours_warning := st.session_state.pop(hours_warning_key, None):
    st.warning(hours_warning)

accommodation_base = actions.get_accommodation_base(trip.trip_id)
with st.container(border=True):
    st.markdown(f"**{copy['accommodation_base_title']}**")
    st.caption(copy["accommodation_base_help"])
    if accommodation_base:
        st.success(accommodation_base["name"])
        st.caption(accommodation_base.get("address") or "")
        st.map(
            {
                "latitude": [accommodation_base["latitude"]],
                "longitude": [accommodation_base["longitude"]],
            },
            latitude="latitude",
            longitude="longitude",
        )
    accommodation_query = st.text_input(
        copy["accommodation_query"],
        value=accommodation_base["name"] if accommodation_base else "",
        key=f"accommodation_query_{trip.trip_id}",
    )
    if st.button(
        copy["save_accommodation_base"],
        key=f"save_accommodation_base_{trip.trip_id}",
        width="stretch",
    ):
        try:
            actions.confirm_accommodation_base(trip.trip_id, accommodation_query)
        except (ProviderUnavailable, ValueError) as error:
            st.error(shared.plain(error))
        else:
            st.session_state[route_flash_key] = copy["accommodation_base_saved"]
            st.rerun()

zone_evidence = actions.get_timezone_evidence(trip.trip_id)
with st.container(border=True):
    if zone_evidence and zone_evidence.get("status") == "verified":
        st.markdown(
            f"**{copy['timezone_evidence']}: {zone_evidence['timezone']}** · "
            f"{zone_evidence['retrieved_at'][:10]}"
        )
    else:
        st.markdown(f"**{copy['timezone_evidence']}**")
        st.caption(copy["no_timezone"])
        st.caption(shared.plain(copy["timezone_cost"]))
        if st.button(
            copy["fetch_timezone"], key=f"fetch_tz_{trip.trip_id}", width="stretch"
        ):
            try:
                result = actions.refresh_timezone(trip.trip_id)
            except (ProviderBudgetExceeded, ProviderUnavailable, ValueError) as error:
                st.error(shared.plain(error))
            else:
                st.session_state[route_flash_key] = (
                    f"{copy['timezone_fetched']} {result['timezone']}"
                )
                st.rerun()

stored_routes = actions.list_routes(trip.trip_id)
verified_routes = [item for item in stored_routes if item["status"] == "verified"]
usage_status = actions.paid_usage_status()
st.caption(
    shared.plain(
        f"{copy['paid_usage']}: US${usage_status['estimated_usd']:.4f} / "
        f"US${usage_status['cap_usd']:.2f} {copy['paid_cap']} · "
        f"{usage_status['requests']} {copy['paid_requests']}"
    )
)
if usage_status["state"] == "stopped":
    st.error(copy["paid_stopped"])
elif usage_status["state"] == "warning":
    st.warning(copy["paid_warning"])

# Each paid enrichment is its own card: state first, then its cost, then the one
# button that spends money. Stacked full-width buttons with the costs in between
# read as a single wall in which nothing said what it would charge for.
intervals = actions.opening_intervals(trip.trip_id)
usable = [item for item in intervals.values() if item.get("interval")]
unusable = {pid: item["reason"] for pid, item in intervals.items() if not item.get("interval")}
choice_names = {
    choice.place_id: shared._candidate_name(choice.candidate.as_dict(), language)
    for choice in actions.list_candidate_choices(trip.trip_id)
    if choice.action in {"must_do", "interested", "maybe"}
}

with st.container(border=True):
    st.markdown(f"**{copy['opening_hours']}** · {copy['hours_usable']}: {len(usable)}")
    if unusable:
        st.caption(
            f"{copy['hours_unusable']}: "
            + ", ".join(
                f"{_optimizer_code(reason, language)}"
                for reason in sorted(set(unusable.values()))
            )
        )
    st.caption(shared.plain(copy["hours_cost"]))
    if st.button(copy["fetch_hours"], key=f"fetch_hours_{trip.trip_id}", width="stretch"):
        try:
            hours_report = actions.refresh_opening_hours(trip.trip_id)
        except (ProviderBudgetExceeded, ProviderUnavailable, ValueError) as error:
            st.error(shared.plain(error))
        else:
            st.session_state[route_flash_key] = (
                f"{copy['hours_fetched']} {copy['hours_usable']} "
                f"{hours_report['usable_intervals']} / {hours_report['places']}"
            )
            if hours_report["provider_errors"]:
                st.session_state[hours_warning_key] = " · ".join(
                    hours_report["provider_errors"]
                )
            st.rerun()

    for place_id, reason in unusable.items():
        if reason not in {
            "OPENING_NOT_FETCHED",
            "NO_PUBLISHED_HOURS",
            "EVIDENCE_EXPIRED",
            "EVIDENCE_NORMALIZER_OUTDATED",
        }:
            continue
        with st.expander(
            f"{choice_names.get(place_id, place_id)} · "
            f"{_optimizer_code(reason, language)}"
        ):
            st.caption(copy["hours_owner_help"])
            start_column, end_column = st.columns(2)
            owner_start = start_column.time_input(
                copy["start"],
                value=time(8, 0),
                key=f"owner_hours_start_{trip.trip_id}_{place_id}",
            )
            owner_end = end_column.time_input(
                copy["end"],
                value=time(18, 0),
                key=f"owner_hours_end_{trip.trip_id}_{place_id}",
            )
            if st.button(
                copy["confirm_hours"],
                key=f"confirm_hours_{trip.trip_id}_{place_id}",
                width="stretch",
            ):
                try:
                    actions.confirm_opening_window(
                        trip.trip_id,
                        place_id,
                        start=owner_start.strftime("%H:%M"),
                        end=owner_end.strftime("%H:%M"),
                    )
                except ValueError as error:
                    st.error(shared.plain(error))
                else:
                    st.session_state[route_flash_key] = copy["hours_confirmed"]
                    st.rerun()

with st.container(border=True):
    if verified_routes:
        st.markdown(f"**{copy['routes_available']}: {len(verified_routes)}**")
    else:
        st.markdown(f"**{copy['routes']}**")
        st.caption(copy["no_routes"])
    if st.button(copy["fetch_routes"], key=f"fetch_routes_{trip.trip_id}", width="stretch"):
        try:
            report = actions.refresh_routes(trip.trip_id)
        except ProviderBudgetExceeded as error:
            st.error(shared.plain(error))
        except ValueError as error:
            st.error(shared.plain(error))
        else:
            message = (
                f"{copy['routes_fetched']} {copy['routes_available']} "
                f"{report['routes_available']} / {copy['routes_needed']} "
                f"{report['pairs_needed']}"
            )
            if report["skipped_over_cap"]:
                message = f"{message} · {copy['routes_skipped']} {report['skipped_over_cap']}"
            if report["failed"]:
                message = f"{message} · {copy['routes_failed']} {report['failed']}"
            st.session_state[route_flash_key] = message
            st.rerun()

with st.expander(copy["raise_cap"]):
    new_cap = st.number_input(
        copy["cap_amount"], min_value=0.0, value=float(usage_status["cap_usd"]), step=1.0,
        key=f"cap_{trip.trip_id}",
    )
    if st.button(copy["save_cap"], key=f"save_cap_{trip.trip_id}"):
        actions.set_paid_cap(new_cap)
        st.session_state[route_flash_key] = copy["cap_saved"]
        st.rerun()

st.divider()
journey = shared.journey(trip)
gaps = journey.get("capability_gaps", [])
if gaps:
    st.warning(copy["evidence_blockers"])
    for gap in gaps:
        st.markdown(f"- {_optimizer_code(gap, language)}")
    if any(
        gap
        in {
            "ACCOMMODATION_BASE_UNCONFIRMED",
            "FREE_TEXT_HARD_CONSTRAINT_NEEDS_STRUCTURED_CONFIRMATION",
        }
        for gap in gaps
    ) and st.button(
        f"{copy['next_step']}: {copy['stage_setup']}",
        key=f"return_setup_{trip.trip_id}",
        width="stretch",
    ):
        st.switch_page("views/setup.py")
    if trip.planning_mode == "explore_first":
        st.info(copy["provisional_evidence_help"])
        if st.button(
            copy["continue_provisional"],
            key=f"continue_optimize_{trip.trip_id}",
            type="primary",
            width="stretch",
        ):
            st.switch_page("views/optimize.py")
else:
    if st.button(
        f"{copy['next_step']}: {copy['stage_optimize']}",
        key=f"continue_optimize_{trip.trip_id}",
        type="primary",
        width="stretch",
    ):
        st.switch_page("views/optimize.py")
