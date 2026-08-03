"""Broad discovery, then explainable ranking and the owner's choices."""

from __future__ import annotations

from urllib.parse import urlencode

import streamlit as st

from travel_planner.providers import (
    CARD_PHOTO_LIMIT,
    ProviderBudgetExceeded,
    ProviderUnavailable,
)
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
        # Named apart from the ranked "Browse all" below: this one is the raw
        # provider catalog with its evidence columns, that one is scored.
        with st.expander(copy["catalog_table"], expanded=False):
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
        st.info(f"{copy['ranking_wait']} ({shared.plain(error)})")
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
    lane = shared.translated_selectbox(
        copy["lane"],
        tuple(lane_entries),
        key=f"ranking_lane_{trip.trip_id}",
        format_func=lambda value: f"{copy[value]} ({len(lane_entries[value])})",
    )
    entries = lane_entries[lane]
    if not entries:
        st.info(copy["no_lane_cards"])
    else:
        entry_by_id = {entry["place_id"]: entry for entry in entries}
        card_id = shared.translated_selectbox(
            copy["select_card"],
            [entry["place_id"] for entry in entries],
            key=f"ranking_card_{trip.trip_id}_{lane}",
            format_func=lambda place_id: (
                f"{_candidate_name(candidate_by_id[place_id], language)} · "
                f"{ranking['cards'][place_id]['total_score']:.1f}/100"
            ),
        )
        candidate = candidate_by_id[card_id]
        card = ranking["cards"][card_id]
        entry = entry_by_id[card_id]
        local_name = candidate.get("names", {}).get("local")
        st.markdown(f"### {_candidate_name(candidate, language)}")
        if local_name and local_name != _candidate_name(candidate, language):
            st.caption(local_name)
        st.caption(_category_text(candidate["category"], language))
        best_for = card["matched_tags"] or card["candidate_tags"]
        st.markdown(f"**{copy['place_summary']}**")
        st.write(
            copy["place_summary_template"].format(
                name=_candidate_name(candidate, language),
                category=_category_text(candidate["category"], language),
                best_for=" · ".join(
                    TAG_TEXT[language].get(tag, tag) for tag in best_for[:4]
                ),
                reason=_explain(card["why_shown"][0], language),
                caution=" · ".join(
                    _explain(code, language) for code in card["cons"][:2]
                ),
            )
        )
        insight_key = f"place_insight_{trip.trip_id}_{card_id}"
        insight = st.session_state.get(insight_key)
        gallery = list((insight or {}).get("photo_gallery") or [])
        if not gallery and insight and insight.get("photo_uri"):
            gallery = [{**(insight.get("photo") or {}), "uri": insight["photo_uri"]}]
        if gallery:
            photo_index_key = f"photo_index_{trip.trip_id}_{card_id}"
            photo_index = int(st.session_state.get(photo_index_key, 0)) % len(gallery)
            photo = gallery[photo_index]
            credit = ", ".join(
                f"[{item['name']}]({item['uri']})"
                if item.get("name") and item.get("uri")
                else item.get("name") or ""
                for item in photo.get("authors") or []
            ).strip(", ")
            caption = copy["google_photo"] + (f" · {credit}" if credit else "")
            st.image(photo["uri"], caption=caption, width="stretch")
            if len(gallery) > 1:
                previous_column, count_column, next_column = st.columns([1, 2, 1])
                if previous_column.button(
                    f"← {copy['previous_photo']}",
                    key=f"previous_photo_{trip.trip_id}_{card_id}",
                    width="stretch",
                ):
                    st.session_state[photo_index_key] = (photo_index - 1) % len(gallery)
                    st.rerun()
                count_column.caption(
                    copy["photo_count"].format(
                        current=photo_index + 1, total=len(gallery)
                    )
                )
                if next_column.button(
                    f"{copy['next_photo']} →",
                    key=f"next_photo_{trip.trip_id}_{card_id}",
                    width="stretch",
                ):
                    st.session_state[photo_index_key] = (photo_index + 1) % len(gallery)
                    st.rerun()
        elif photo_url := _photo_url(candidate.get("photo_reference")):
            st.image(photo_url, caption=copy["photo_source"], width="stretch")
        else:
            st.caption(copy["photo_unavailable"])
            st.map(
                {
                    "lat": [candidate["latitude"]],
                    "lon": [candidate["longitude"]],
                },
                zoom=14,
                height=220,
            )
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

        st.markdown(f"**{copy['tourist_take']}**")
        st.write(
            f"**{copy['best_for']}:** "
            + " · ".join(
                TAG_TEXT[language].get(tag, tag) for tag in best_for[:4]
            )
        )
        st.caption(
            f"{copy['experience_fit']}: "
            f"{card['dimensions']['experience_value']['score']}/20 · "
            f"{copy['group_fit']}: "
            f"{card['dimensions']['group_preference_fit']['score']}/30"
        )
        for code in card["why_shown"][:2]:
            st.markdown(f"- {_explain(code, language)}")
        if card["cons"]:
            st.caption(
                f"{copy['check_before_going']}: "
                + " · ".join(_explain(code, language) for code in card["cons"][:2])
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
        if insight and insight.get("rating") is not None:
            rating_column.write(
                f"**{copy['source_rating']}:** {insight['rating']:.1f}/5 · "
                f"{insight.get('user_rating_count', 0):,} {copy['ratings']}"
            )
        else:
            rating_column.write(f"**{copy['source_rating']}:** {copy['not_enriched']}")
        alias = candidate["provider_aliases"][0]
        if alias.get("source_url"):
            st.markdown(f"[{copy['source']}]({alias['source_url']})")
        tripadvisor_url = "https://www.tripadvisor.com/Search?" + urlencode(
            {"q": f"{_candidate_name(candidate, 'en')} {trip.destination}"}
        )
        st.markdown(f"[{copy['open_tripadvisor']}]({tripadvisor_url})")

        if insight:
            summary = insight.get("review_summary") or {}
            if summary.get("text"):
                st.markdown(f"**{copy['review_summary']}**")
                st.write(summary["text"])
                if summary.get("disclosure"):
                    st.caption(summary["disclosure"])
                if summary.get("reviews_uri"):
                    st.markdown(f"[{copy['see_all_reviews']}]({summary['reviews_uri']})")
                if summary.get("flag_uri"):
                    st.markdown(f"[{copy['report_summary']}]({summary['flag_uri']})")
            if insight.get("reviews"):
                st.markdown(f"**{copy['visitor_reviews']}**")
                for review in insight["reviews"][:2]:
                    author = review.get("author") or copy["google_reviewer"]
                    if review.get("author_uri"):
                        author = f"[{author}]({review['author_uri']})"
                    context = " · ".join(
                        item
                        for item in (
                            f"{review['rating']:.0f}/5"
                            if review.get("rating") is not None
                            else None,
                            review.get("published"),
                        )
                        if item
                    )
                    st.markdown(f"{author}" + (f" · {context}" if context else ""))
                    st.write(review["text"])
            elif not summary.get("text"):
                st.caption(copy["no_reviews_returned"])
            if insight.get("google_maps_uri"):
                st.markdown(
                    f"[{copy['open_google_maps']}]({insight['google_maps_uri']})"
                )
            st.caption(copy["live_details_session_only"])
        else:
            details_cost = actions.check_paid_call(
                operation="google_places:card_details"
            )
            photo_cost = actions.check_paid_call(
                operation="google_places:photo", count=CARD_PHOTO_LIMIT
            )
            st.caption(
                shared.plain(
                    copy["live_details_cost"].format(
                        cost=details_cost["estimate_usd"] + photo_cost["estimate_usd"],
                        count=CARD_PHOTO_LIMIT,
                    )
                )
            )
            if st.button(
                copy["load_live_details"],
                key=f"enrich_card_{trip.trip_id}_{card_id}",
                width="stretch",
                disabled=not details_cost["allowed"],
            ):
                try:
                    st.session_state[insight_key] = actions.enrich_place_card(
                        trip.trip_id, card_id, language=language
                    )
                except (ProviderBudgetExceeded, ProviderUnavailable, ValueError) as error:
                    st.error(shared.plain(error))
                else:
                    st.rerun()

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
        clicked_action = None
        for column, action in zip(
            st.columns(3),
            ("must_do", "interested", "maybe"),
            strict=True,
        ):
            if column.button(
                copy[action],
                key=f"choice_{action}_{trip.trip_id}_{card_id}",
                width="stretch",
            ):
                clicked_action = action

        # Rejecting is the one action that carries a reason, so the reason lives
        # with it instead of sitting above all four buttons on every card.
        reason_options = (None, "too_crowded", "too_expensive", "too_tiring", "wrong_vibe", "weak_value", "already_seen")
        with st.expander(copy["not_for_trip"]):
            rejection_reason = shared.translated_selectbox(
                copy["rejection_reason"],
                reason_options,
                key=f"rejection_reason_{trip.trip_id}_{card_id}",
                format_func=lambda value: REJECTION_TEXT[language][value],
            )
            if st.button(
                copy["not_for_trip"],
                key=f"choice_not_for_trip_{trip.trip_id}_{card_id}",
                width="stretch",
            ):
                clicked_action = "not_for_trip"
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

    selected_choices = [
        choice
        for choice in saved_choices.values()
        if choice.action in {"must_do", "interested", "maybe"}
    ]
    if selected_choices and st.button(
        f"{copy['next_step']}: {copy['stage_evidence']}",
        key=f"continue_evidence_{trip.trip_id}",
        type="primary",
        width="stretch",
    ):
        st.switch_page("views/evidence.py")

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
