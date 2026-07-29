from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from travel_planner.actions import PlannerActions
from travel_planner.ranking import FORMULA_WEIGHTS, build_ranking
from travel_planner.setup import build_setup_payload


ROOT = Path(__file__).resolve().parents[1]


def candidate(
    place_id: str,
    category: str,
    index: int,
    *,
    icon: bool = False,
    opening: bool = False,
) -> dict:
    return {
        "place_id": place_id,
        "name": f"Place {index:02d}",
        "names": {"en": f"Place {index:02d}", "local": f"สถานที่ {index:02d}"},
        "latitude": 25.0 + index / 1000,
        "longitude": 121.5 + index / 1000,
        "category": category,
        "address": None,
        "website": "https://example.test" if index % 2 == 0 else None,
        "signals": {"wikidata": f"Q{index}"} if icon else {},
        "photo_reference": None,
        "possible_duplicate": False,
        "provider_aliases": [
            {
                "provider": "fake",
                "provider_place_id": f"node/{index}",
                "source_url": f"https://example.test/{index}",
            }
        ],
        "evidence": [{"status": "verified"}],
        "operational_evidence": {
            "opening_hours": {
                "value": "09:00-18:00" if opening else None,
                "state": "regular_schedule_only" if opening else "unconfirmed",
            },
            "best_time": {"value": None, "state": "unconfirmed"},
            "access": {"value": None, "state": "unconfirmed"},
        },
    }


def setup_payload(*, ages=(26, 19, 50), member_tags=True) -> dict:
    return build_setup_payload(
        planning_mode="ready_to_schedule",
        owner_age=ages[0],
        main_style=["sightseeing", "culture"],
        also_enjoy=["local_street_food", "photography"],
        avoid=["tourist_traps", "plain_long_walks"],
        comfort=["balanced_pace", "rewarding_walks"],
        travellers=[
            {
                "traveller_id": "teen",
                "label": "Teen",
                "age": ages[1],
                "tags": ["sightseeing", "night_view"] if member_tags else [],
            },
            {
                "traveller_id": "mother",
                "label": "Mother",
                "age": ages[2],
                "tags": ["culture", "nature", "photography"] if member_tags else [],
            },
        ],
        confirmed=True,
    )


class RankingCoreTest(unittest.TestCase):
    def setUp(self) -> None:
        categories = [
            "museum",
            "viewpoint",
            "park",
            "marketplace",
            "historic",
            "garden",
            "tower",
            "mall",
            "place_of_worship",
            "theme_park",
            "gallery",
            "attraction",
        ]
        self.candidates = [
            candidate(
                f"place_{index}",
                category,
                index,
                icon=index in {1, 7},
                opening=index % 3 == 0,
            )
            for index, category in enumerate(categories, start=1)
        ]

    def test_all_candidates_are_ranked_with_exact_formula_and_protected_exploration(self) -> None:
        first = build_ranking(
            setup=setup_payload(),
            candidates=self.candidates,
            choices=[],
            discovery_status="verified",
        )
        second = build_ranking(
            setup=setup_payload(),
            candidates=list(reversed(self.candidates)),
            choices=[],
            discovery_status="verified",
        )

        self.assertEqual(first, second)
        self.assertEqual(
            {
                "group_preference_fit": 30,
                "experience_value": 20,
                "reward_vs_effort": 20,
                "time_fit": 10,
                "route_compatibility": 15,
                "evidence_quality": 5,
            },
            FORMULA_WEIGHTS,
        )
        self.assertEqual(12, first["coverage"]["retrieved_candidates"])
        self.assertEqual(12, len(first["lanes"]["browse_all"]))
        self.assertEqual(set(first["cards"]), set(first["lanes"]["browse_all"]))
        self.assertEqual({"place_1", "place_7"}, set(first["lanes"]["city_icons"]))

        queue = first["lanes"]["main_queue"]
        self.assertEqual("protected_exploration", queue[4]["role"])
        self.assertEqual("protected_exploration", queue[9]["role"])
        for card in first["cards"].values():
            positive = sum(item["score"] for item in card["dimensions"].values())
            deductions = sum(item["points"] for item in card["deductions"])
            self.assertEqual(card["total_score"], round(max(0, positive - deductions), 1))
            self.assertEqual("not_evaluated", card["feasibility"]["state"])

    def test_age_alone_does_not_change_ranking_and_missing_member_detail_renormalizes(self) -> None:
        with_ages = build_ranking(
            setup=setup_payload(ages=(26, 19, 50)),
            candidates=self.candidates,
            choices=[],
            discovery_status="verified",
        )
        different_ages = build_ranking(
            setup=setup_payload(ages=(60, 12, 90)),
            candidates=self.candidates,
            choices=[],
            discovery_status="verified",
        )
        owner_only = build_ranking(
            setup=setup_payload(member_tags=False),
            candidates=self.candidates,
            choices=[],
            discovery_status="verified",
        )

        self.assertEqual(with_ages, different_ages)
        self.assertEqual({"owner": 1.0}, owner_only["effective_group_weights"])
        self.assertEqual(
            {"owner": 0.5, "teen": 0.25, "mother": 0.25},
            with_ages["base_group_weights"],
        )


class RankingActionsTest(unittest.TestCase):
    class Provider:
        name = "ranking_fake"
        cache_ttl_days = 7

        def cache_descriptor(self, destination):
            return {"provider": self.name, "destination": destination, "version": 1}

        def discover(self, destination):
            return {
                "items": [
                    {
                        "provider_place_id": f"node/{index}",
                        "name": f"Candidate {index}",
                        "names": {"en": f"Candidate {index}", "local": f"地點 {index}"},
                        "latitude": 25 + index / 1000,
                        "longitude": 121.5 + index / 1000,
                        "category": category,
                        "signals": {"wikidata": f"Q{index}"} if index == 1 else {},
                        "photo_reference": f"File:Candidate {index}.jpg",
                        "source_url": f"https://example.test/{index}",
                    }
                    for index, category in enumerate(
                        ["museum", "viewpoint", "park", "marketplace", "historic", "garden"],
                        start=1,
                    )
                ],
                "coverage": {"searched_categories": ["baseline"]},
                "attribution": "Fake",
                "license": "Test",
                "license_url": "https://example.test",
            }

    def test_choices_persist_reorder_only_unseen_and_reconcile_without_fake_feasibility(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ranking.sqlite3"
            actions = PlannerActions(path, place_provider=self.Provider())
            trip = actions.create_trip(name="Taipei", destination="Taipei")
            actions.save_setup(
                trip_id=trip.trip_id,
                main_style=["sightseeing", "culture"],
                travellers=[{"label": "Member", "age": 19, "tags": ["nature"]}],
                confirmed=True,
            )
            actions.discover_places(trip_id=trip.trip_id)
            before = actions.rank_candidates(trip.trip_id)
            chosen_id = before["lanes"]["main_queue"][0]["place_id"]

            actions.save_candidate_choice(
                trip_id=trip.trip_id, place_id=chosen_id, action="interested"
            )
            resumed = PlannerActions(path)
            after = resumed.rank_candidates(trip.trip_id)

            self.assertNotIn(
                chosen_id, [item["place_id"] for item in after["lanes"]["main_queue"]]
            )
            self.assertIn(chosen_id, after["lanes"]["browse_all"])
            self.assertEqual(6, after["coverage"]["browse_all_candidates"])
            self.assertEqual("pending_optimizer", after["reconciliation"][0]["status"])
            self.assertEqual(
                "kept_for_whole_trip_optimization",
                after["reconciliation"][0]["consequence"],
            )
            category = resumed.list_candidate_choices(trip.trip_id)[0].candidate.as_dict()[
                "category"
            ]
            self.assertGreater(after["learned_category_weights"][category], 0)

            resumed.save_candidate_choice(
                trip_id=trip.trip_id,
                place_id=chosen_id,
                action="not_for_trip",
                reason="wrong_vibe",
            )
            self.assertEqual(
                "wrong_vibe", resumed.list_candidate_choices(trip.trip_id)[0].reason
            )
            resumed.clear_candidate_choice(trip_id=trip.trip_id, place_id=chosen_id)
            self.assertEqual([], resumed.list_candidate_choices(trip.trip_id))


class RankingUiTest(unittest.TestCase):
    def test_interested_choice_persists_and_ranking_renders_in_thai(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ranking-ui.sqlite3"
            actions = PlannerActions(path, place_provider=RankingActionsTest.Provider())
            trip = actions.create_trip(name="Taipei", destination="Taipei")
            actions.save_setup(
                trip_id=trip.trip_id,
                main_style=["sightseeing", "culture"],
                travellers=[{"label": "Member", "age": 19, "tags": ["nature"]}],
                confirmed=True,
            )
            actions.discover_places(trip_id=trip.trip_id)

            with patch.dict(os.environ, {"TOURIST_DB_PATH": str(path)}):
                app = AppTest.from_file(ROOT / "app.py", default_timeout=10)
                app.switch_page("views/places.py")
                app.run()
                self.assertFalse(app.exception)
                self.assertIn("Personalized place cards", [item.value for item in app.subheader])
                card_widget = app.selectbox(
                    key=f"ranking_card_{trip.trip_id}_main_queue__en"
                )
                card_id = card_widget.value

                app.button(key=f"choice_interested_{trip.trip_id}_{card_id}").click().run()

                self.assertFalse(app.exception)
                self.assertEqual(
                    "interested", PlannerActions(path).list_candidate_choices(trip.trip_id)[0].action
                )
                self.assertIn(
                    "Choice saved. Unseen cards were reordered; Browse All still retains everything.",
                    [item.value for item in app.success],
                )

                app.radio[0].set_value("th").run()
                self.assertFalse(app.exception)
                self.assertIn(
                    "การ์ดสถานที่ที่เหมาะกับทริป", [item.value for item in app.subheader]
                )


if __name__ == "__main__":
    unittest.main()
