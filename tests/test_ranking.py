from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


from travel_planner.actions import PlannerActions
from travel_planner.providers import GooglePlacesCardProvider, ProviderUnavailable
from travel_planner.ranking import FORMULA_WEIGHTS, build_ranking
from travel_planner.setup import build_setup_payload


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
        "signals": {
            "wikidata": f"Q{index}",
            "wikipedia": f"en:Place {index}",
        }
        if icon
        else {},
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

        wikidata_only = candidate("minor", "historic", 99)
        wikidata_only["signals"] = {"wikidata": "Q99"}
        minor = build_ranking(
            setup=setup_payload(),
            candidates=[wikidata_only],
            choices=[],
            discovery_status="verified",
        )
        self.assertFalse(minor["cards"]["minor"]["is_city_icon"])

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
                        "signals": {
                            "wikidata": f"Q{index}",
                            "wikipedia": f"en:Candidate {index}",
                        }
                        if index == 1
                        else {},
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


class FakeCardProvider:
    name = "google_places"
    details_operation = "google_places:card_details"
    photo_operation = "google_places:photo"

    def details(self, place, *, destination, language):
        return {
            "provider": "Google Maps",
            "provider_place_id": "ChIJcard",
            "matched_name": place["name"],
            "match_distance_metres": 12,
            "rating": 4.7,
            "user_rating_count": 321,
            "google_maps_uri": "https://maps.example.test/place",
            "review_summary": {
                "text": "Visitors praise the skyline view and easy photo opportunities.",
                "disclosure": "Summarized with Gemini",
                "reviews_uri": "https://maps.example.test/reviews",
                "flag_uri": "https://maps.example.test/report",
            },
            "reviews": [
                {
                    "text": "The sunset view was the highlight of our trip.",
                    "original_text": None,
                    "rating": 5.0,
                    "published": "a month ago",
                    "author": "Traveller",
                    "author_uri": "https://maps.example.test/traveller",
                    "review_uri": "https://maps.example.test/review",
                }
            ],
            "photos": [
                {"name": f"places/ChIJcard/photos/photo{index}", "authors": []}
                for index in range(1, 7)
            ],
            "photo": {"name": "places/ChIJcard/photos/photo1", "authors": []},
        }

    def photo_uri(self, photo_name):
        return f"https://images.example.test/{photo_name.rsplit('/', 1)[-1]}.jpg"


class CardEnrichmentTest(unittest.TestCase):
    def test_live_search_prefers_the_local_name(self) -> None:
        captured = {}
        place = {
            "place_id": "p1",
            "name": "Dailaokengshan",
            "names": {"en": "Dailaokengshan", "local": "待老坑山"},
            "category": "peak",
            "latitude": 24.9668463,
            "longitude": 121.5744771,
        }
        payload = {
            "places": [
                {
                    "id": "mountain",
                    "displayName": {"text": "待老坑山"},
                    "primaryType": "mountain_peak",
                    "location": {"latitude": 24.96685, "longitude": 121.57448},
                }
            ]
        }

        def response(request, timeout):
            captured.update(json.loads(request.data))
            return BytesIO(json.dumps(payload).encode("utf-8"))

        with patch.dict(os.environ, {"GOOGLE_MAPS_SERVER_KEY": "test"}), patch(
            "travel_planner.providers.urlopen", side_effect=response
        ):
            GooglePlacesCardProvider().details(
                place, destination="Taipei, Taiwan", language="en"
            )

        self.assertEqual("待老坑山 peak, Taipei, Taiwan", captured["textQuery"])

    def test_google_payload_is_normalized_and_a_distant_match_is_refused(self) -> None:
        place = {"place_id": "p1", "name": "Tower", "latitude": 25.04, "longitude": 121.57}
        payload = {
            "places": [
                {
                    "id": "ChIJcard",
                    "displayName": {"text": "Tower"},
                    "location": {"latitude": 25.0401, "longitude": 121.5701},
                    "rating": 4.6,
                    "userRatingCount": 120,
                    "reviews": [
                        {
                            "rating": 5,
                            "text": {"text": "Excellent city view."},
                            "authorAttribution": {"displayName": "A visitor"},
                        }
                    ],
                    "photos": [
                        {"name": f"places/ChIJcard/photos/p{index}"}
                        for index in range(1, 7)
                    ],
                }
            ]
        }

        result = GooglePlacesCardProvider.normalize(payload, place=place)
        self.assertEqual(4.6, result["rating"])
        self.assertEqual("Excellent city view.", result["reviews"][0]["text"])
        self.assertEqual("places/ChIJcard/photos/p1", result["photo"]["name"])
        self.assertEqual(5, len(result["photos"]))

        payload["places"][0]["location"] = {"latitude": 25.2, "longitude": 121.7}
        with self.assertRaisesRegex(ProviderUnavailable, "No exact Google Maps match"):
            GooglePlacesCardProvider.normalize(payload, place=place)

        payload["places"][0]["location"] = {"latitude": 25.0401, "longitude": 121.5701}
        payload["places"][0]["displayName"] = {"text": "Different Library"}
        with self.assertRaisesRegex(ProviderUnavailable, "No exact Google Maps match"):
            GooglePlacesCardProvider.normalize(payload, place=place)

    def test_google_match_avoids_a_wrong_subplace_category(self) -> None:
        place = {
            "place_id": "p1",
            "name": "Taipei 101",
            "category": "attraction",
            "latitude": 25.034,
            "longitude": 121.5645,
        }
        payload = {
            "places": [
                {
                    "id": "mall",
                    "displayName": {"text": "Taipei 101 Shopping Center"},
                    "primaryType": "shopping_mall",
                    "location": {"latitude": 25.0341, "longitude": 121.5645},
                },
                {
                    "id": "observatory",
                    "displayName": {"text": "Taipei 101 Observatory"},
                    "primaryType": "tourist_attraction",
                    "location": {"latitude": 25.0338, "longitude": 121.5646},
                },
            ]
        }

        result = GooglePlacesCardProvider.normalize(payload, place=place)

        self.assertEqual("observatory", result["provider_place_id"])
        self.assertEqual("tourist_attraction", result["matched_primary_type"])

    def test_live_card_content_is_billed_but_never_persisted(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "card.sqlite3"
            actions = PlannerActions(
                path,
                place_provider=RankingActionsTest.Provider(),
                card_provider=FakeCardProvider(),
            )
            trip = actions.create_trip(name="Taipei", destination="Taipei")
            actions.save_setup(
                trip_id=trip.trip_id, main_style=["sightseeing"], confirmed=True
            )
            actions.discover_places(trip_id=trip.trip_id)
            place_id = actions.rank_candidates(trip.trip_id)["lanes"]["browse_all"][0]

            result = actions.enrich_place_card(trip.trip_id, place_id)

            self.assertEqual(4.7, result["rating"])
            self.assertEqual("https://images.example.test/photo1.jpg", result["photo_uri"])
            self.assertEqual(5, len(result["photo_gallery"]))
            usage = actions.paid_usage_status()["by_operation"]
            self.assertEqual(1, usage["google_places:card_details"]["requests"])
            self.assertEqual(5, usage["google_places:photo"]["requests"])
            self.assertEqual([], actions.store.list_place_evidence(trip.trip_id, "card_details"))


if __name__ == "__main__":
    unittest.main()
