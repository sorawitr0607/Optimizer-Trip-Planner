"""Quick actions and free-text revision, with preview and undo."""

from __future__ import annotations

import streamlit as st

from ui import shared
from travel_planner.providers import ProviderBudgetExceeded, RevisionInterpretationUnavailable
from ui.shared import _optimizer_code

actions = shared.actions()
copy = shared.words()
language = shared.language()
trip = shared.trip()
if not shared.require("itinerary", trip):
    st.stop()

st.subheader(copy["revision"])
st.caption(copy["revision_help"])
revision_flash_key = f"revision_flash_{trip.trip_id}"
if revision_flash := st.session_state.pop(revision_flash_key, None):
    st.success(revision_flash)

if actions.get_active_plan(trip.trip_id) is None:
    st.info(copy["revision_needs_plan"])
else:
    offered = actions.quick_actions(trip.trip_id)
    labels = {
        index: (
            copy.get(f"op_{item['operation']}", item["operation"])
            + (
                f" · {str(item['arguments'].get('place_id'))[:14]}"
                if item["arguments"].get("place_id")
                else ""
            )
        )
        for index, item in enumerate(offered)
    }
    chosen_index = st.selectbox(
        copy["quick_action"],
        options=list(labels),
        format_func=lambda value: labels[value],
        key=f"quick_action_{trip.trip_id}",
    )
    pending = actions.get_revision_draft(trip.trip_id)
    if st.button(copy["run_action"], key=f"run_action_{trip.trip_id}", width="stretch"):
        try:
            actions.propose_revision(
                trip_id=trip.trip_id,
                operation=offered[chosen_index],
                replace_pending=True,
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.rerun()

    if pending:
        with st.container(border=True):
            st.markdown(
                f"**{copy['pending_revision']}: "
                f"{copy.get('op_' + pending['operation'], pending['operation'])}**"
            )
            if pending.get("assumptions"):
                st.caption(
                    f"{copy['revision_assumptions']}: "
                    + ", ".join(
                        _optimizer_code(item, language) for item in pending["assumptions"]
                    )
                )
            if pending.get("explanation"):
                reasons = pending["explanation"]
                st.markdown(f"#### {copy['deterministic_reasons']}")
                st.caption(
                    f"{copy['variant']}: {copy.get(reasons['variant_id'], reasons['variant_id'])} · "
                    f"{copy[reasons['status']]}"
                )
                st.dataframe(
                    [
                        {copy["dimension"]: key, copy["points"]: value}
                        for key, value in reasons["metrics"].items()
                        if isinstance(value, (int, float))
                    ],
                    hide_index=True,
                    width="stretch",
                )
                for item in reasons["unscheduled"]:
                    st.markdown(
                        f"- {item['place_id'][:16]} · "
                        f"{_optimizer_code(item['reason'], language)}"
                    )
            change = pending.get("consequences")
            if change:
                if change["changed_dates"]:
                    st.caption(
                        f"{copy['changed_days']}: {', '.join(change['changed_dates'])}"
                    )
                else:
                    st.caption(copy["no_changes"])
                st.dataframe(
                    [
                        {
                            copy["dimension"]: key,
                            copy["before"]: item["before"],
                            copy["after"]: item["after"],
                            copy["delta"]: item["delta"],
                        }
                        for key, item in change["metrics"].items()
                    ],
                    hide_index=True,
                    width="stretch",
                )
                for label, entries in (
                    (copy["moved_items"], [f"{m['place_id'][:16]} {m['from']['date']} {m['from']['start']} → {m['to']['date']} {m['to']['start']}" for m in change["moved"]]),
                    (copy["added_items"], [item[:16] for item in change["added"]]),
                    (copy["removed_items"], [item[:16] for item in change["removed"]]),
                    (copy["shortened_items"], [f"{m['place_id'][:16]} {m['from_minutes']}→{m['to_minutes']} {copy['minutes']}" for m in change["shortened"]]),
                    (copy["lengthened_items"], [f"{m['place_id'][:16]} {m['from_minutes']}→{m['to_minutes']} {copy['minutes']}" for m in change["lengthened"]]),
                    (copy["displaced_items"], [f"{m['place_id'][:16]} · {_optimizer_code(m['reason'], language)}" for m in change["displaced"]]),
                    (copy["new_warnings"], [_optimizer_code(w, language) for w in change["warnings"]["new"]]),
                    (copy["cleared_warnings"], [_optimizer_code(w, language) for w in change["warnings"]["cleared"]]),
                ):
                    if entries:
                        st.markdown(f"**{label}**: " + " · ".join(entries))
                if not change["can_apply"]:
                    st.warning(copy["revision_blocked"])

            apply_column, cancel_column = st.columns(2)
            if apply_column.button(
                copy["apply_revision"],
                key=f"apply_revision_{trip.trip_id}",
                disabled=not pending.get("can_apply"),
                width="stretch",
            ):
                try:
                    actions.apply_revision(trip.trip_id)
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.session_state[revision_flash_key] = copy["revision_applied"]
                    st.rerun()
            if cancel_column.button(
                copy["cancel_revision"],
                key=f"cancel_revision_{trip.trip_id}",
                width="stretch",
            ):
                actions.discard_revision_draft(trip.trip_id)
                st.session_state[revision_flash_key] = copy["revision_discarded"]
                st.rerun()

    ai_enabled = st.checkbox(
        copy["ai_enabled"], value=False, key=f"ai_enabled_{trip.trip_id}"
    )
    if not ai_enabled:
        st.caption(copy["ai_disabled_note"])
    else:
        st.caption(copy["ai_cost"])
        st.caption(copy["ai_disclosure"])
        request_text = st.text_area(
            copy["free_text"], key=f"free_text_{trip.trip_id}", height=80
        )
        st.caption(copy["free_text_help"])
        if st.button(copy["interpret"], key=f"interpret_{trip.trip_id}", width="stretch"):
            try:
                outcome = actions.interpret_revision(
                    trip_id=trip.trip_id,
                    request_text=request_text,
                    language=language,
                    replace_pending=True,
                )
            except RevisionInterpretationUnavailable as error:
                st.error(copy.get(f"ai_{error.cause}", str(error)))
            except (ProviderBudgetExceeded, ValueError) as error:
                st.error(str(error))
            else:
                if not outcome["supported"]:
                    st.warning(
                        f"{copy['unsupported_request']}: {outcome['unsupported_reason']}"
                    )
                    if outcome["clarification"]:
                        st.info(f"{copy['clarification']}: {outcome['clarification']}")
                else:
                    st.session_state[revision_flash_key] = (
                        f"{copy['interpreted_as']} "
                        f"{copy.get('op_' + outcome['operation'], outcome['operation'])}"
                    )
                    st.rerun()

    history = actions.list_revisions(trip.trip_id)
    if history:
        with st.expander(f"{copy['revision_history']} ({len(history)})"):
            for record in reversed(history):
                st.markdown(
                    f"- {record['created_at'][:16]} · "
                    f"{copy.get('op_' + record['operation'], record['operation'])} · "
                    f"`{record['from_version_id'][5:17]}` → `{record['to_version_id'][5:17]}`"
                )
    versions = actions.list_plan_versions(trip.trip_id)
    if len(versions) > 1:
        with st.expander(f"{copy['active_plan']} ({len(versions)})"):
            for version in versions:
                if st.button(
                    f"{copy['restore_version']} `{version.version_id[5:17]}` · {version.cause}",
                    key=f"restore_{version.version_id}",
                ):
                    actions.restore_plan_version(
                        trip_id=trip.trip_id, version_id=version.version_id
                    )
                    st.session_state[revision_flash_key] = copy["version_restored"]
                    st.rerun()
