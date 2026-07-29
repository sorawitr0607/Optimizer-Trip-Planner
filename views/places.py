"""Broad discovery, then explainable ranking and the owner's choices."""

from __future__ import annotations

import streamlit as st

from ui import shared
from ui.shared import _empty_setup
from ui.shared import _candidate_name, _category_text, _explain, _photo_url
from ui.text import DIMENSION_TEXT, REJECTION_TEXT, TAG_TEXT

actions = shared.actions()
copy = shared.words()
language = shared.language()
trip = shared.trip()
if not shared.require("places", trip):
    st.stop()

setup = actions.get_setup(trip.trip_id)
setup_payload = setup.snapshot.as_dict() if setup else _empty_setup(trip.planning_mode)
latest = actions.get_latest_discovery(trip.trip_id)
# No discovery yet means an empty catalog, not a missing name.
catalog: list = []

st.subheader(copy["discover_title"])
st.caption(copy["discover_help"])
st.caption(copy["osm_notice"])

if setup and setup.confirmed:
    discover_column, refresh_column = st.columns(2)
    discover_clicked = discover_column.button(
        copy["discover"], key=f"discover_{trip.trip_id}", width="stretch"
    )
    refresh_clicked = refresh_column.button(
        copy["refresh"],
        key=f"refresh_{trip.trip_id}",
        width="stretch",
        disabled=latest is None,
    )
    if discover_clicked or refresh_clicked:
        with st.spinner(copy["discovering"]):
            latest = actions.discover_places(
                trip_id=trip.trip_id, force_refresh=refresh_clicked
            )
        st.success(copy["discovery_saved"])

if latest:
    report = latest.report.as_dict()
    catalog = latest.candidates.as_dict()["candidates"]
    if not setup or latest.setup_sha256 != setup.snapshot.sha256:
        st.warning(copy["stale_setup"])
    if latest.status in {"unavailable", "error", "stale"}:
        st.warning(copy["provider_gap"])
    st.markdown(f"#### {copy['coverage']}")
    # The status is a word, not a number: as a metric it rendered untranslated and
    # clipped to "unavaila…" in a quarter-width column.
    st.markdown(
        f"**{copy['provider_status']}:** "
        f"{copy.get('provider_' + latest.status, latest.status)}"
    )
    candidate_count, duplicate_count, cell_count = st.columns(3)
    candidate_count.metric(copy["candidates"], report["canonical_candidates"])
    duplicate_count.metric(copy["duplicates"], report["duplicates_merged"])
    cell_count.metric(copy["cells"], report["geographic_cells_with_candidates"])
    st.caption(copy["unranked"])
    if catalog:
        with st.expander(copy["browse_all"], expanded=False):
            rows = []
            for candidate in catalog:
                names = candidate.get("names", {})
                alias = candidate["provider_aliases"][0]
                rows.append(
                    {
                        copy["name"]: _candidate_name(candidate, language),
                        copy["local_name"]: names.get("local") or candidate["name"],
                        copy["category"]: _category_text(candidate["category"], language),
                        copy["opening"]: candidate["operational_evidence"]["opening_hours"][
                            "state"
                        ],
                        copy["source"]: alias.get("source_url"),
                    }
                )
            st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.info(copy["no_candidates"])
    if report.get("attribution"):
        st.markdown(
            f"[{report['attribution']}]({report['license_url']}) · {report['license']}"
        )
    with st.expander(copy["details"]):
        st.json(report)

st.divider()
st.subheader(copy["ranking_title"])
st.caption(copy["ranking_help"])
st.caption(copy["formula_note"])
flash_key = f"choice_flash_{trip.trip_id}"
if flash := st.session_state.pop(flash_key, None):
    st.success(copy[flash])

ranking = None
if catalog:
    try:
        ranking = actions.rank_candidates(trip.trip_id)
    except ValueError as error:
        st.info(f"{copy['ranking_wait']} ({error})")
else:
    st.info(copy["ranking_wait"])

if ranking:
    candidate_by_id = {candidate["place_id"]: candidate for candidate in catalog}
    saved_choices = {
        choice.place_id: choice for choice in actions.list_candidate_choices(trip.trip_id)
    }
    lane_entries = {
        "main_queue": ranking["lanes"]["main_queue"],
        "city_icons": [
            {"place_id": place_id, "role": "city_icon"}
            for place_id in ranking["lanes"]["city_icons"]
        ],
        "worth_it_if": [
            {"place_id": place_id, "role": "worth_it_if"}
            for place_id in ranking["lanes"]["worth_it_if"]
        ],
        "local_alternatives": [
            {**entry, "role": "local_alternative"}
            for entry in ranking["lanes"]["local_alternatives"]
        ],
        "browse_all": [
            {"place_id": place_id, "role": "browse_all"}
            for place_id in ranking["lanes"]["browse_all"]
        ],
    }
    lane = st.selectbox(
        copy["lane"],
        options=tuple(lane_entries),
        format_func=lambda value: f"{copy[value]} ({len(lane_entries[value])})",
        key=f"ranking_lane_{trip.trip_id}",
    )
    entries = lane_entries[lane]
    if not entries:
        st.info(copy["no_lane_cards"])
    else:
        entry_by_id = {entry["place_id"]: entry for entry in entries}
        card_id = st.selectbox(
            copy["select_card"],
            options=[entry["place_id"] for entry in entries],
            format_func=lambda place_id: (
                f"{_candidate_name(candidate_by_id[place_id], language)} · "
                f"{ranking['cards'][place_id]['total_score']:.1f}/100"
            ),
            key=f"ranking_card_{trip.trip_id}_{lane}",
        )
        candidate = candidate_by_id[card_id]
        card = ranking["cards"][card_id]
        entry = entry_by_id[card_id]
        local_name = candidate.get("names", {}).get("local")
        st.markdown(f"### {_candidate_name(candidate, language)}")
        if local_name and local_name != _candidate_name(candidate, language):
            st.caption(local_name)
        st.caption(_category_text(candidate["category"], language))
        if photo_url := _photo_url(candidate.get("photo_reference")):
            st.image(photo_url, caption=copy["photo_source"], width="stretch")
        else:
            st.caption(copy["photo_unavailable"])
        if entry["role"] == "protected_exploration":
            st.info(copy["exploration_card"])
        if card["is_city_icon"]:
            st.info(copy["icon_card"])
        if entry.get("alternative_to"):
            compared = candidate_by_id.get(entry["alternative_to"])
            if compared:
                st.caption(
                    f"{copy['local_alternatives']}: "
                    f"{_candidate_name(compared, language)}"
                )

        score_column, duration_column = st.columns(2)
        score_column.metric(copy["score"], f"{card['total_score']:.1f}/100")
        duration = card["duration_estimate"]
        duration_column.metric(
            copy["duration"],
            f"{duration['minimum_minutes']}–{duration['maximum_minutes']} {copy['minutes']}",
        )
        # "Not evaluated yet" clipped to "Not evaluate…" as a metric value.
        st.write(f"**{copy['feasibility']}:** {copy['not_evaluated']}")
        st.caption(copy["planner_estimate"])

        if card["matched_tags"]:
            st.write(
                f"**{copy['matched_tags']}:** "
                + " · ".join(
                    TAG_TEXT[language].get(tag, tag) for tag in card["matched_tags"]
                )
            )
        # Collapsed by default: three columns of prose per card pushed the decision
        # buttons a screen and a half down, so cards could not be compared.
        with st.expander(copy["card_detail"]):
            explanation_columns = st.columns(3)
            with explanation_columns[0]:
                st.markdown(f"**{copy['why']}**")
                for code in card["why_shown"]:
                    st.markdown(f"- {_explain(code, language)}")
            with explanation_columns[1]:
                st.markdown(f"**{copy['pros']}**")
                for code in card["pros"]:
                    st.markdown(f"- {_explain(code, language)}")
            with explanation_columns[2]:
                st.markdown(f"**{copy['cons']}**")
                for code in card["cons"]:
                    st.markdown(f"- {_explain(code, language)}")

        with st.expander(copy["breakdown"]):
            st.dataframe(
                [
                    {
                        copy["dimension"]: DIMENSION_TEXT[language][dimension],
                        copy["points"]: values["score"],
                        copy["maximum"]: values["max"],
                    }
                    for dimension, values in card["dimensions"].items()
                ],
                hide_index=True,
                width="stretch",
            )
            st.markdown(f"**{copy['deductions']}**")
            if card["deductions"]:
                for deduction in card["deductions"]:
                    st.markdown(
                        f"- −{deduction['points']:.1f}: "
                        f"{_explain(deduction['code'], language)}"
                    )
            else:
                st.caption(copy["no_deductions"])

        evidence_column, rating_column = st.columns(2)
        opening_state = candidate["operational_evidence"]["opening_hours"]["state"]
        evidence_column.write(f"**{copy['opening']}:** {opening_state}")
        evidence_column.write(f"**{copy['route_effort']}:** {copy['not_routed']}")
        rating_column.write(f"**{copy['source_rating']}:** {copy['not_enriched']}")
        alias = candidate["provider_aliases"][0]
        if alias.get("source_url"):
            st.markdown(f"[{copy['source']}]({alias['source_url']})")

        existing_choice = saved_choices.get(card_id)
        if existing_choice:
            st.caption(
                f"{copy['current_choice']}: {copy[existing_choice.action]}"
                + (
                    f" · {REJECTION_TEXT[language][existing_choice.reason]}"
                    if existing_choice.reason
                    else ""
                )
            )
        reason_options = (None, "too_crowded", "too_expensive", "too_tiring", "wrong_vibe", "weak_value", "already_seen")
        rejection_reason = st.selectbox(
            copy["rejection_reason"],
            options=reason_options,
            format_func=lambda value: REJECTION_TEXT[language][value],
            key=f"rejection_reason_{trip.trip_id}_{card_id}",
        )
        action_columns = st.columns(4)
        clicked_action = None
        for column, action in zip(
            action_columns,
            ("must_do", "interested", "maybe", "not_for_trip"),
            strict=True,
        ):
            if column.button(
                copy[action],
                key=f"choice_{action}_{trip.trip_id}_{card_id}",
                width="stretch",
            ):
                clicked_action = action
        if clicked_action:
            try:
                actions.save_candidate_choice(
                    trip_id=trip.trip_id,
                    place_id=card_id,
                    action=clicked_action,
                    reason=rejection_reason if clicked_action == "not_for_trip" else None,
                )
            except ValueError as error:
                st.error(shared.plain(error))
            else:
                st.session_state[flash_key] = "choice_saved"
                st.rerun()
        if existing_choice and st.button(
            copy["clear_choice"], key=f"clear_choice_{trip.trip_id}_{card_id}"
        ):
            actions.clear_candidate_choice(trip_id=trip.trip_id, place_id=card_id)
            st.session_state[flash_key] = "choice_cleared"
            st.rerun()

    with st.expander(copy["browse_all"], expanded=False):
        st.caption(copy["browse_notice"])
        st.dataframe(
            [
                {
                    copy["name"]: _candidate_name(candidate_by_id[place_id], language),
                    copy["local_name"]: candidate_by_id[place_id]
                    .get("names", {})
                    .get("local"),
                    copy["category"]: _category_text(
                        candidate_by_id[place_id]["category"], language
                    ),
                    copy["score"]: ranking["cards"][place_id]["total_score"],
                    copy["choice"]: copy[saved_choices[place_id].action]
                    if place_id in saved_choices
                    else "",
                    copy["feasibility"]: copy["not_evaluated"],
                }
                for place_id in ranking["lanes"]["browse_all"]
            ],
            hide_index=True,
            width="stretch",
        )

    with st.expander(copy["group_weights"], expanded=False):
        member_labels = {"owner": "Owner" if language == "en" else "เจ้าของทริป"}
        member_labels.update(
            {
                member["traveller_id"]: member["label"]
                for member in setup_payload.get("travellers", [])
            }
        )
        st.dataframe(
            [
                {
                    copy["member"]: member_labels.get(person, person),
                    "Base": weight,
                    "Effective": ranking["effective_group_weights"].get(person, 0),
                }
                for person, weight in ranking["base_group_weights"].items()
            ],
            hide_index=True,
            width="stretch",
        )
        st.json(
            {
                "formula_weights": ranking["formula_weights"],
                "learned_category_weights": ranking["learned_category_weights"],
            }
        )

    st.markdown(f"#### {copy['all_choices']}")
    if saved_choices:
        st.dataframe(
            [
                {
                    copy["name"]: _candidate_name(choice.candidate.as_dict(), language),
                    copy["choice"]: copy[choice.action],
                    copy["rejection_reason"]: REJECTION_TEXT[language][choice.reason]
                    if choice.reason
                    else "",
                }
                for choice in saved_choices.values()
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption(copy["no_selected"])

    st.markdown(f"#### {copy['reconciliation']}")
    st.caption(copy["reconciliation_help"])
    if ranking["reconciliation"]:
        st.dataframe(
            [
                {
                    copy["name"]: _candidate_name(
                        saved_choices[item["place_id"]].candidate.as_dict(), language
                    ),
                    copy["choice"]: copy[item["choice"]],
                    copy["feasibility"]: copy["pending_optimizer"],
                    copy["present_latest"]: "✓"
                    if item["present_in_latest_discovery"]
                    else "—",
                    copy["next_step"]: copy["run_optimizer"],
                }
                for item in ranking["reconciliation"]
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.info(copy["no_selected"])

st.divider()
