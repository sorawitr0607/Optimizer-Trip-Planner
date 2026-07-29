"""Owner-recorded costs in baht and their original currency."""

from __future__ import annotations

import streamlit as st

from ui import shared
from datetime import date
from travel_planner.costs import (
    CATEGORIES as COST_CATEGORIES,
    COMMON_CURRENCIES,
    PAYMENT_STATES as COST_STATES,
)

actions = shared.actions()
copy = shared.words()
language = shared.language()
trip = shared.trip()
if not shared.require("setup", trip):
    st.stop()

st.subheader(copy["costs"])
st.caption(copy["costs_help"])
cost_flash_key = f"cost_flash_{trip.trip_id}"
if cost_flash := st.session_state.pop(cost_flash_key, None):
    st.success(cost_flash)

rate_snapshot = actions.get_rate_snapshot(trip.trip_id)
with st.expander(copy["rate_snapshot"], expanded=not rate_snapshot):
    if not rate_snapshot:
        st.info(copy["no_rates"])
    else:
        st.caption(
            f"{rate_snapshot['as_of']} · {rate_snapshot['source']}"
            + (f" · +{rate_snapshot['buffer_percent']}%" if rate_snapshot["buffer_percent"] else "")
        )
        st.dataframe(
            [
                {copy["rate_currency"]: code, copy["rate_value"]: value}
                for code, value in rate_snapshot["rates"].items()
            ],
            hide_index=True,
            width="stretch",
        )
    # `accept_new_options` keeps every ISO code reachable while still offering the
    # common ones, so nobody has to remember whether it is "NT$" or "TWD".
    rate_currency = st.selectbox(
        copy["rate_currency"],
        options=COMMON_CURRENCIES,
        index=COMMON_CURRENCIES.index("CNY"),
        accept_new_options=True,
        key=f"rate_cur_{trip.trip_id}",
    )
    rate_value = st.number_input(
        copy["rate_value"], min_value=0.0, value=5.0, step=0.01, key=f"rate_val_{trip.trip_id}"
    )
    # A typed date could be any format; the picker can only produce a real one.
    rate_as_of = st.date_input(
        copy["rate_as_of"], value=date.today(), key=f"rate_as_of_{trip.trip_id}"
    ).isoformat()
    rate_source = st.text_input(
        copy["rate_source"], value="", key=f"rate_src_{trip.trip_id}"
    )
    rate_buffer = st.number_input(
        copy["rate_buffer"], min_value=0.0, max_value=50.0, value=0.0, step=0.5,
        key=f"rate_buf_{trip.trip_id}",
    )
    if st.button(copy["save_rates"], key=f"save_rates_{trip.trip_id}", width="stretch"):
        merged = dict((rate_snapshot or {}).get("rates", {}))
        merged[rate_currency.strip().upper()] = rate_value
        try:
            actions.save_rate_snapshot(
                trip_id=trip.trip_id,
                rates=merged,
                as_of=rate_as_of,
                source=rate_source,
                buffer_percent=rate_buffer,
            )
        except ValueError as error:
            st.error(shared.plain(error))
        else:
            st.session_state[cost_flash_key] = copy["rates_saved"]
            st.rerun()

cost_items = actions.list_cost_items(trip.trip_id)
if cost_items:
    totals = actions.cost_totals(trip.trip_id)
    st.markdown(
        f"**{copy['total_thb']} {totals['total_thb']:,.2f}** · "
        f"{copy['estimated_thb']} {totals['estimated_thb']:,.2f} · "
        f"{copy['paid_thb']} {totals['paid_thb']:,.2f}"
    )
    if totals["missing_rates"]:
        st.warning(f"{copy['rate_missing']}: {', '.join(totals['missing_rates'])}")
    for item in cost_items:
        with st.container(border=True):
            reported = item.get("reported_thb")
            headline = f"**{item['label']}** · {item['original_amount']:,.2f} {item['original_currency']}"
            if reported is not None:
                headline = f"{headline} → {reported:,.2f} THB"
            st.markdown(headline)
            marks = [copy.get(item["payment_state"], item["payment_state"]), copy.get(item["category"], item["category"])]
            if item["payment_state"] == "paid":
                marks.append(copy["locked_charge"])
            if item["rate_missing"]:
                marks.append(copy["rate_missing"])
            st.caption(" · ".join(marks))
            if st.button(copy["remove_cost"], key=f"rm_cost_{item['cost_id']}"):
                actions.delete_cost_item(trip_id=trip.trip_id, cost_id=item["cost_id"])
                st.session_state[cost_flash_key] = copy["cost_removed"]
                st.rerun()

with st.expander(copy["add_cost"]):
    cost_label = st.text_input(copy["cost_label"], key=f"cost_label_{trip.trip_id}")
    cost_amount = st.number_input(
        copy["cost_amount"], min_value=0.0, value=0.0, step=1.0, key=f"cost_amt_{trip.trip_id}"
    )
    # Flagging the unrated codes here shows the conversion gap while the cost is
    # being entered, instead of as a warning after it is saved.
    rated = set((rate_snapshot or {}).get("rates") or {"THB": 1.0})
    cost_currency = shared.translated_selectbox(
        copy["cost_currency"],
        COMMON_CURRENCIES,
        key=f"cost_cur_{trip.trip_id}",
        index=COMMON_CURRENCIES.index("THB"),
        format_func=lambda code: (
            code if code in rated else f"{code} · {copy['rate_missing']}"
        ),
        accept_new_options=True,
    )
    cost_category = shared.translated_selectbox(
        copy["category"],
        COST_CATEGORIES,
        key=f"cost_cat_{trip.trip_id}",
        format_func=lambda value: copy.get(
            "accommodation_cost" if value == "accommodation" else
            "shopping_cost" if value == "shopping" else value, value
        ),
    )
    cost_state = shared.translated_selectbox(
        copy["cost_state"],
        COST_STATES,
        key=f"cost_state_{trip.trip_id}",
        format_func=lambda value: copy.get(value, value),
    )
    # Only a paid charge carries an actual THB amount, and leaving the field on
    # screen for the other states invited the "a paid cost needs its actual THB
    # charge" error from the opposite direction.
    cost_actual = (
        st.number_input(
            copy["cost_actual"],
            min_value=0.0,
            value=0.0,
            step=1.0,
            key=f"cost_act_{trip.trip_id}",
        )
        if cost_state == "paid"
        else None
    )
    if st.button(copy["add_cost"], key=f"add_cost_{trip.trip_id}", width="stretch"):
        try:
            actions.save_cost_item(
                trip_id=trip.trip_id,
                item={
                    "label": cost_label,
                    "original_amount": cost_amount,
                    "original_currency": cost_currency,
                    "category": cost_category,
                    "payment_state": cost_state,
                    "actual_thb": cost_actual,
                },
            )
        except ValueError as error:
            st.error(shared.plain(error))
        else:
            st.session_state[cost_flash_key] = copy["cost_added"]
            st.rerun()

