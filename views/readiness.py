"""The pre-trip readiness board."""

from __future__ import annotations

import streamlit as st

from ui import shared
from travel_planner.checklist import CATEGORIES as CHECKLIST_CATEGORIES, REQUIREMENT_LEVELS as CHECKLIST_LEVELS, TIMING_BUCKETS as CHECKLIST_TIMING, display_title
from ui.shared import _render_checklist_item

actions = shared.actions()
copy = shared.words()
language = shared.language()
trip = shared.trip()
if not shared.require("setup", trip):
    st.stop()

st.subheader(copy["checklist"])
st.caption(copy["checklist_help"])
checklist_flash_key = f"checklist_flash_{trip.trip_id}"
if checklist_flash := st.session_state.pop(checklist_flash_key, None):
    st.success(checklist_flash)

if not actions.get_setup(trip.trip_id):
    st.info(copy["checklist_needs_setup"])
else:
    preview = actions.propose_checklist(trip.trip_id)
    pending = (
        len(preview["additions"])
        + len(preview["removals"])
        + len(preview["deadline_changes"])
    )
    if pending:
        # Nothing is applied silently: additions, removals, and deadline moves
        # are previewed first.
        with st.expander(f"{copy['checklist_preview']} ({pending})", expanded=True):
            for item in preview["additions"]:
                st.markdown(
                    f"➕ {display_title(item, copy)} · {copy[item['timing']]}"
                )
            for item in preview["removals"]:
                st.markdown(
                    f"➖ {display_title(item, copy)} · {copy['will_be_dismissed']}"
                )
            for change in preview["deadline_changes"]:
                st.markdown(
                    f"📅 {change['title']} · {change['from']['due_date'] or '—'} → "
                    f"{change['to']['due_date'] or '—'}"
                )
            if st.button(
                copy["apply_checklist"],
                key=f"apply_checklist_{trip.trip_id}",
                width="stretch",
            ):
                result = actions.apply_checklist_proposal(trip.trip_id)
                st.session_state[checklist_flash_key] = (
                    f"{copy['checklist_applied']} "
                    f"+{result['added']} / ~{result['deadlines_changed']} / "
                    f"-{result['dismissed']}"
                )
                st.rerun()
    else:
        st.caption(copy["checklist_current"])

    items = actions.list_checklist_items(trip.trip_id)
    active_items = [item for item in items if not item["dismissed"]]
    category_filter = st.multiselect(
        copy["category"],
        options=sorted({item["category"] for item in active_items}),
        format_func=lambda value: copy.get(value, value),
        key=f"checklist_categories_{trip.trip_id}",
    )
    shown = [
        item
        for item in active_items
        if not category_filter or item["category"] in category_filter
    ]

    for bucket in CHECKLIST_TIMING:
        bucket_items = [item for item in shown if item["timing"] == bucket]
        if not bucket_items:
            continue
        st.markdown(f"#### {copy[bucket]}")
        for item in sorted(bucket_items, key=lambda value: display_title(value, copy)):
            _render_checklist_item(actions, trip, item, language, checklist_flash_key)

    with st.expander(copy["add_task"]):
        new_title = st.text_input(copy["task_title"], key=f"task_title_{trip.trip_id}")
        new_category = st.selectbox(
            copy["category"],
            options=CHECKLIST_CATEGORIES,
            format_func=lambda value: copy.get(value, value),
            key=f"task_category_{trip.trip_id}",
        )
        new_timing = st.selectbox(
            copy["timing"],
            options=CHECKLIST_TIMING,
            format_func=lambda value: copy[value],
            key=f"task_timing_{trip.trip_id}",
        )
        new_level = st.selectbox(
            copy["requirement_level"],
            options=CHECKLIST_LEVELS,
            format_func=lambda value: copy[value],
            key=f"task_level_{trip.trip_id}",
        )
        new_consequence = st.text_input(
            copy["consequence"], key=f"task_consequence_{trip.trip_id}"
        )
        if st.button(copy["add_task"], key=f"add_task_{trip.trip_id}", width="stretch"):
            try:
                actions.save_checklist_item(
                    trip_id=trip.trip_id,
                    item={
                        "title": new_title,
                        "category": new_category,
                        "timing": new_timing,
                        "requirement_level": new_level,
                        "consequence": new_consequence,
                    },
                )
            except ValueError as error:
                st.error(shared.plain(error))
            else:
                st.session_state[checklist_flash_key] = copy["task_added"]
                st.rerun()

    dismissed = [item for item in items if item["dismissed"]]
    if dismissed:
        with st.expander(f"{copy['dismissed_history']} ({len(dismissed)})"):
            for item in dismissed:
                st.markdown(
                    f"- {display_title(item, copy)} · {copy[item['timing']]}"
                )
                if st.button(
                    copy["restore_task"],
                    key=f"restore_{item['item_id']}",
                ):
                    actions.set_checklist_dismissed(
                        trip_id=trip.trip_id, item_id=item["item_id"], dismissed=False
                    )
                    st.session_state[checklist_flash_key] = copy["task_restored"]
                    st.rerun()

