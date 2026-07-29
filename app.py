"""Local Streamlit entry point for the personal travel planner.

This script owns only what every stage shares: the language, the trip being
worked on, how far that trip has got, and the navigation between stages. Each
stage lives in `views/` and reads its context from `ui.shared`.

The journey used to be one long scroll, so reaching the itinerary meant passing
setup and discovery every time. The sidebar now carries the context and the
progress, and the app opens on the stage that actually needs attention.
"""

from __future__ import annotations

import streamlit as st

from ui import shared
from ui.text import TEXT

st.set_page_config(
    page_title="Personal Travel Planner",
    page_icon="🧭",
    layout="centered",
    initial_sidebar_state="expanded",
)

# Every label below depends on the language, but its control belongs at the foot
# of the sidebar: it is chosen once and then left alone. Reading the stored value
# here lets the widget be created last, so it renders last.
language = shared.language()
copy = TEXT[language]
actions = shared.actions()

# `st.navigation` always renders at the top of the sidebar, so the trip context
# sits directly beneath the stages it applies to.
trips = actions.list_trips()


def _trip_label(trip_id: str) -> str:
    """Name and destination, but never the same text twice.

    An unnamed trip takes its destination as its name, which read as
    "Kyoto, Japan — Kyoto, Japan" in the selector.
    """

    item = next(item for item in trips if item.trip_id == trip_id)
    if item.name == item.destination:
        return item.name
    return f"{item.name} — {item.destination}"


if trips:
    st.sidebar.selectbox(
        copy["resume"],
        options=[item.trip_id for item in trips],
        format_func=_trip_label,
        key=shared.TRIP_KEY,
    )
else:
    st.sidebar.info(copy["journey_needs_trip"])

trip = shared.trip()
journey = shared.journey(trip)

# Progress, so the owner sees what is done and what is next at a glance.
if trip is not None:
    st.sidebar.markdown(f"**{copy['journey']}**")
    for stage in journey["stages"]:
        mark = "✅" if stage["done"] else ("⏳" if stage["key"] == journey["next"] else "○")
        st.sidebar.caption(f"{mark} {copy['stage_' + stage['key']]}")
    if journey.get("capability_gaps"):
        st.sidebar.caption(
            f"⚠️ {copy['capability_gaps']}: {len(journey['capability_gaps'])}"
        )
    if actions.get_setup(trip.trip_id):
        board = actions.checklist_readiness(trip.trip_id)
        if board["counts"]["total"]:
            st.sidebar.caption(
                f"{copy['readiness']}: {copy[board['state']]} · "
                f"{board['counts']['open']} {copy['open_tasks']}"
            )
    spend = actions.paid_usage_status()
    st.sidebar.caption(
        shared.plain(
            f"{copy['paid_usage']}: US${spend['estimated_usd']:.4f} / "
            f"US${spend['cap_usd']:.2f}"
        )
    )

st.sidebar.divider()
st.sidebar.radio(
    "Language / ภาษา",
    options=("en", "th"),
    format_func=lambda value: "English" if value == "en" else "ไทย",
    horizontal=True,
    key=shared.LANGUAGE_KEY,
)

# Land on the stage that needs attention, so a returning owner sees the plan
# rather than the setup form.
LANDING = journey["next"] if trip is not None else "setup"
STAGES = (
    ("setup", "views/setup.py", "🧭"),
    ("places", "views/places.py", "📍"),
    ("evidence", "views/evidence.py", "🔎"),
    ("optimize", "views/optimize.py", "🧩"),
    ("itinerary", "views/itinerary.py", "🗓️"),
    ("readiness", "views/readiness.py", "✅"),
    ("costs", "views/costs.py", "🧾"),
    ("revise", "views/revise.py", "✏️"),
)
BUILD_STAGES = {"setup", "places", "evidence", "optimize"}
build, use = [], []
for key, path, icon in STAGES:
    page = st.Page(
        path,
        title=copy[f"stage_{key}"],
        icon=icon,
        url_path=key,
        default=key == LANDING,
    )
    (build if key in BUILD_STAGES else use).append(page)

st.navigation({copy["section_build"]: build, copy["section_use"]: use}).run()
