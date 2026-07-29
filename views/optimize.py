"""Three whole-trip variants, validation, and activation."""

from __future__ import annotations

import streamlit as st

from ui import shared
from ui.shared import _optimizer_code, _plan_item_name

actions = shared.actions()
copy = shared.words()
language = shared.language()
trip = shared.trip()
if not shared.require("optimize", trip):
    st.stop()

st.subheader(copy["optimizer_title"])
st.caption(copy["optimizer_help"])
optimizer_flash_key = f"optimizer_flash_{trip.trip_id}"
if optimizer_flash := st.session_state.pop(optimizer_flash_key, None):
    st.success(copy[optimizer_flash])

selected_for_optimizer = [
    choice
    for choice in actions.list_candidate_choices(trip.trip_id)
    if choice.action in {"must_do", "interested", "maybe"}
]
generate_plan = st.button(
    copy["generate_plan"],
    key=f"generate_plan_{trip.trip_id}",
    width="stretch",
    disabled=not selected_for_optimizer,
)
if not selected_for_optimizer:
    st.info(copy["choose_before_plan"])
if generate_plan:
    try:
        with st.spinner(copy["optimizing"]):
            actions.generate_plan_preview(trip.trip_id)
    except ValueError as error:
        st.error(shared.plain(error))
    else:
        st.session_state[optimizer_flash_key] = "preview_saved"
        st.rerun()

preview = actions.get_plan_preview(trip.trip_id)
if preview:
    proposal = preview.proposal.as_dict()
    if proposal["mode"] == "stay_recommendation":
        st.markdown(f"#### {copy['stay_recommendation']}")
        st.dataframe(
            [
                {
                    copy["stay_option"]: copy.get(item["id"], item["id"]),
                    copy["days"]: item["days"],
                    copy["daily_capacity"]: f"{item['daily_capacity_minutes']} {copy['minutes']}",
                }
                for item in proposal["stay_recommendations"]
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        variants = proposal["variants"]
        variant_id = shared.translated_selectbox(
            copy["variant"],
            [item["variant_id"] for item in variants],
            key=f"plan_variant_{trip.trip_id}",
            format_func=lambda value: copy[value],
        )
        variant = next(item for item in variants if item["variant_id"] == variant_id)
        st.markdown(f"#### {copy[variant_id]} · {copy[variant['status']]}")
        # Three per row, not five: at a fifth of a centered page these labels
        # clipped the same way "Not evaluated yet" and "unavailable" did.
        metric_labels = (
            "scheduled_visits",
            "travel_minutes",
            "walking_minutes",
            "plain_walking_minutes",
            "buffer_minutes",
        )
        for row_start in (0, 3):
            row_labels = metric_labels[row_start : row_start + 3]
            for column, label in zip(st.columns(3), row_labels, strict=False):
                column.metric(copy[label], variant["metrics"][label])
        if (
            variant["metrics"]["scheduled_visits"]
            and variant["objective_improved_or_equal_to_greedy"]
        ):
            st.success(copy["greedy_check"])
        if variant["stopped_at_limit"]:
            st.warning(copy["optimizer_limit"])

        if variant["warnings"]:
            with st.expander(copy["optimizer_warning"], expanded=True):
                for warning in variant["warnings"]:
                    st.markdown(f"- {_optimizer_code(warning, language)}")

        st.markdown(f"#### {copy['optimizer_reconciliation']}")
        st.dataframe(
            [
                {
                    copy["name"]: item.get("names", {}).get(language)
                    or item.get("names", {}).get("en")
                    or item.get("names", {}).get("local")
                    or item["name"],
                    copy["choice"]: copy.get(item["priority"], item["priority"]),
                    copy["feasibility"]: copy[item["status"]],
                    copy["reason"]: _optimizer_code(item["reason"], language),
                    copy["consequence"]: _optimizer_code(
                        item["consequence"], language
                    ),
                }
                for item in variant["reconciliation"]
            ],
            hide_index=True,
            width="stretch",
        )

        timeline_rows = [
            {
                copy["days"]: day["date"],
                copy["start"]: item["start"],
                copy["end"]: item["end"],
                copy["item_type"]: item["type"],
                copy["place_or_leg"]: _plan_item_name(item, language),
                copy["duration"]: f"{item['duration_minutes']} {copy['minutes']}",
            }
            for day in variant["days"]
            for item in day["items"]
        ]
        if timeline_rows:
            st.markdown(f"#### {copy['timeline']}")
            st.dataframe(timeline_rows, hide_index=True, width="stretch")
        else:
            st.warning(copy["no_schedule"])

        if variant["status"] != "ready":
            st.caption(copy["activation_disabled"])
        activate = st.button(
            copy["activate_plan"],
            key=f"activate_plan_{trip.trip_id}_{variant_id}",
            width="stretch",
            disabled=variant["status"] != "ready",
        )
        if activate:
            try:
                actions.activate_plan_preview(
                    trip_id=trip.trip_id, variant_id=variant_id
                )
            except ValueError as error:
                st.error(shared.plain(error))
            else:
                st.session_state[optimizer_flash_key] = "plan_activated"
                st.rerun()

