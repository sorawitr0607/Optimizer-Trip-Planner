"""Routes, destination time zone, opening hours, and paid usage."""

from __future__ import annotations

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

st.subheader(copy["routes"])
st.caption(copy["routes_help"])
route_flash_key = f"route_flash_{trip.trip_id}"
if route_flash := st.session_state.pop(route_flash_key, None):
    st.success(route_flash)

zone_evidence = actions.get_timezone_evidence(trip.trip_id)
if zone_evidence and zone_evidence.get("status") == "verified":
    st.markdown(
        f"**{copy['timezone_evidence']}: {zone_evidence['timezone']}** · "
        f"{zone_evidence['retrieved_at'][:10]}"
    )
else:
    st.info(copy["no_timezone"])
    st.caption(shared.plain(copy["timezone_cost"]))
    if st.button(copy["fetch_timezone"], key=f"fetch_tz_{trip.trip_id}", width="stretch"):
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

if verified_routes:
    st.markdown(f"**{copy['routes_available']}: {len(verified_routes)}**")
else:
    st.info(copy["no_routes"])
intervals = actions.opening_intervals(trip.trip_id)
usable = [item for item in intervals.values() if item.get("interval")]
st.markdown(f"**{copy['opening_hours']}** · {copy['hours_usable']}: {len(usable)}")
unusable = {pid: item["reason"] for pid, item in intervals.items() if not item.get("interval")}
if unusable:
    st.caption(
        f"{copy['hours_unusable']}: "
        + ", ".join(f"{_optimizer_code(reason, language)}" for reason in sorted(set(unusable.values())))
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
        st.rerun()

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
        copy["raise_cap"], min_value=0.0, value=float(usage_status["cap_usd"]), step=1.0,
        key=f"cap_{trip.trip_id}",
    )
    if st.button(copy["save_cap"], key=f"save_cap_{trip.trip_id}"):
        actions.set_paid_cap(new_cap)
        st.session_state[route_flash_key] = copy["cap_saved"]
        st.rerun()

