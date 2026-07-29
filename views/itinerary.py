"""The active plan: day summary, timeline, map, and offline exports."""

from __future__ import annotations

import streamlit as st

from ui import shared
from travel_planner.exports import half_day
from ui.shared import _day_poster, _optimizer_code, _plan_documents, _render_fallback, _render_plan_item

actions = shared.actions()
copy = shared.words()
language = shared.language()
trip = shared.trip()
if not shared.require("itinerary", trip):
    st.stop()

st.subheader(copy["use_title"])
st.caption(copy["use_help"])

if actions.get_active_plan(trip.trip_id) is None:
    st.info(copy["no_active_plan"])
else:
    export_snapshot = actions.build_export_snapshot(trip.trip_id, language=language)
    export = export_snapshot.as_dict()
    stamp = export["stamp"]
    readiness = export["readiness"]

    st.markdown(
        f"**{copy[stamp['variant_id']]}** · {copy['readiness']}: "
        f"{copy[readiness['state']]}"
    )
    st.caption(
        f"{copy['active_plan']} `{stamp['plan_version_id'][5:17]}` · "
        f"{copy['exported_at']} {stamp['exported_at'][:16]} · "
        f"{stamp['base_currency']} · {stamp['language'].upper()}"
    )
    if not stamp["is_active_plan"]:
        st.warning(copy["superseded_plan"])
    if readiness["capability_gaps"]:
        with st.expander(copy["capability_gaps"]):
            for gap in readiness["capability_gaps"]:
                st.markdown(f"- {_optimizer_code(gap, language)}")

    chosen_date = st.selectbox(
        copy["days"],
        options=[value["date"] for value in export["days"]],
        key=f"plan_day_{trip.trip_id}",
    )
    day = next(item for item in export["days"] if item["date"] == chosen_date)
    totals = day["totals"]
    st.markdown(
        f"**{day['start']}–{day['end']}** · {copy['scheduled_visits']} "
        f"{totals['scheduled_visits']} · {copy['visit_minutes']} "
        f"{totals['visit_minutes']} {copy['minutes']} · {copy['travel_minutes']} "
        f"{totals['travel_minutes']} {copy['minutes']}"
    )
    st.caption(
        f"{copy['walking_minutes']} {totals['walking_minutes']} {copy['minutes']} "
        f"({copy['rewarding_walking_minutes']} {totals['rewarding_walking_minutes']} · "
        f"{copy['plain_walking_minutes']} {totals['plain_walking_minutes']}) · "
        f"{copy['buffer_minutes']} {totals['buffer_minutes']} {copy['minutes']}"
    )
    if day["highest_risk"]:
        st.warning(
            f"{copy['highest_risk']}: "
            f"{copy['state_' + day['highest_risk']['status']]}"
        )

    timeline_tab, map_tab = st.tabs([copy["timeline"], copy["tab_map"]])
    with timeline_tab:
        if not day["items"]:
            st.warning(copy["no_schedule"])
        for part in ("morning", "afternoon"):
            part_items = [
                item for item in day["items"] if half_day(item["start"]) == part
            ]
            if not part_items:
                continue
            for plan_item in part_items:
                _render_plan_item(plan_item, language)
            for fallback in day["fallbacks"]:
                if fallback["half_day"] == part:
                    _render_fallback(fallback, language)
        for fallback in day["fallbacks"]:
            if fallback["half_day"] not in ("morning", "afternoon"):
                _render_fallback(fallback, language)
    with map_tab:
        anchor = export["accommodation"]["anchor"]
        points = [
            {
                "latitude": stop["latitude"],
                "longitude": stop["longitude"],
                "colour": "#B4532A" if stop["status"] == "locked" else "#2A6FB4",
                "radius": 90 if stop["status"] == "locked" else 60,
            }
            for stop in day["stops"]
            if stop["latitude"] is not None and stop["longitude"] is not None
        ]
        if anchor and anchor["latitude"] is not None and anchor["longitude"] is not None:
            points.append(
                {
                    "latitude": anchor["latitude"],
                    "longitude": anchor["longitude"],
                    "colour": "#E0A32E",
                    "radius": 120,
                }
            )
        if points:
            st.map(
                {key: [point[key] for point in points] for key in points[0]},
                latitude="latitude",
                longitude="longitude",
                color="colour",
                size="radius",
            )
        else:
            st.info(copy["map_no_coordinates"])
        # Text labels carry the same distinctions as the marker colours.
        if anchor:
            st.markdown(f"**{copy['hotel_anchor']}** · {anchor['display_name']}")
        for stop in day["stops"]:
            st.markdown(
                f"{copy['stop']} {stop['stop_number']} · {stop['display_name']} · "
                f"{copy['state_' + stop['status']]}"
            )

    st.markdown(f"#### {copy['downloads']}")
    version_tag = stamp["plan_version_id"][5:17]
    try:
        documents = _plan_documents(export, export_snapshot.sha256, language)
        poster = _day_poster(export, export_snapshot.sha256, language, day["date"])
    except ValueError as error:
        st.error(str(error))
    else:
        st.download_button(
            copy["poster"],
            data=poster,
            file_name=f"plan-{version_tag}-{day['date']}-poster.png",
            mime="image/png",
            key=f"poster_{trip.trip_id}",
            width="stretch",
        )
        st.download_button(
            copy["pdf"],
            data=documents["pdf"],
            file_name=f"plan-{version_tag}.pdf",
            mime="application/pdf",
            key=f"pdf_{trip.trip_id}",
            width="stretch",
        )
        st.download_button(
            copy["excel"],
            data=documents["xlsx"],
            file_name=f"plan-{version_tag}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"excel_{trip.trip_id}",
            width="stretch",
        )
        if export["checklist"]["items"]:
            st.download_button(
                copy["calendar"],
                data=documents["ics"],
                file_name=f"plan-{version_tag}-readiness.ics",
                mime="text/calendar",
                key=f"ics_{trip.trip_id}",
                width="stretch",
            )
        else:
            st.caption(copy["checklist_pending"])

    if export["unscheduled"]:
        with st.expander(f"{copy['unscheduled_choices']} ({len(export['unscheduled'])})"):
            st.dataframe(
                [
                    {
                        copy["name"]: item["display_name"],
                        copy["choice"]: copy.get(item["priority"], item["priority"]),
                        copy["reason"]: _optimizer_code(item["reason"], language),
                        copy["consequence"]: _optimizer_code(
                            item["consequence"], language
                        ),
                    }
                    for item in export["unscheduled"]
                ],
                hide_index=True,
                width="stretch",
            )

