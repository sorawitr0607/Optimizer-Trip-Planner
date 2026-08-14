from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from itertools import groupby
import unittest
from unittest.mock import patch


from travel_planner import ranking
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

    def test_an_official_designation_breaks_a_tie_between_identical_museums(self) -> None:
        """`WF-037` phase two. Heritage listing was collected and scored at nothing.

        `_city_icon` folded it into a boolean and kept the basis for display, so on the
        real Taipei catalogue the National Taiwan Museum tied at exactly 65.0 with the
        Postal Museum, and Taipei's four city gates sat below both. Within one category
        every other term is identical, so a designation is the only discriminator the
        data offers.

        It inherits OpenStreetMap's tagging unevenness, which is recorded in the
        ticket: 19 of 126 `historic` places carry the tag but only 1 of 307
        `place_of_worship`, so Lungshan Temple -- a designated site in Taiwanese law --
        gains nothing.
        """

        owner = build_setup_payload(
            planning_mode="explore_first",
            owner_age=40,
            main_style=["sightseeing"],
            also_enjoy=[],
            avoid=[],
            comfort=[],
            owner_description="",
            owner_must_respect=[],
            travellers=[],
            start_date=None,
            end_date=None,
            arrival_time=None,
            departure_time=None,
            accommodation_status="unknown",
            confirmed=True,
        )
        # Both even: `candidate()` gives a website only to even indices and
        # `_evidence_score` pays 0.5 for one, so odd-versus-even would measure the
        # fixture rather than the designation. That cost one wrong reading already.
        plain = candidate("plain", "museum", 2, icon=True, opening=True)
        listed = candidate("listed", "museum", 4, icon=True, opening=True)
        listed["signals"]["heritage"] = "yes"
        ranking = build_ranking(
            setup=owner,
            candidates=[plain, listed],
            choices=[],
            discovery_status="verified",
        )
        cards = ranking["cards"]
        self.assertGreater(
            cards["listed"]["total_score"],
            cards["plain"]["total_score"],
            "a designated museum must outrank an identical undesignated one",
        )
        self.assertIn("heritage", cards["listed"]["city_icon_basis"])
        # Two points, not more: enough to break a tie, not enough for one tag to
        # outweigh a dimension.
        self.assertAlmostEqual(
            2.0,
            cards["listed"]["total_score"] - cards["plain"]["total_score"],
            places=1,
        )

    def test_a_landmark_is_not_buried_by_a_richer_tag_vocabulary(self) -> None:
        """`WF-037`. The ranker's output ordering had no test at all.

        `group_preference_fit` divided the owner's matched styles by how many styles
        they *named*, so a category carrying more tags won more overlap for the same
        place. `peak` carries four tags and `attraction` -- where OSM puts Taipei 101
        -- carries two, so on the real 832-candidate Taipei catalogue a nameless hill
        scored 27 of 30 against Taipei 101's 12.8 and the top 50 came out as 49 peaks
        and one park. Taipei 101 ranked 363rd of 832.

        Nothing caught it because the suite asserted the score was internally
        consistent, which holds under any weighting, and never what the ranking
        actually recommended.
        """

        owner = build_setup_payload(
            planning_mode="explore_first",
            owner_age=40,
            main_style=["sightseeing", "nature", "chill"],
            also_enjoy=[],
            avoid=[],
            comfort=[],
            owner_description="",
            owner_must_respect=[],
            travellers=[],
            start_date=None,
            end_date=None,
            arrival_time=None,
            departure_time=None,
            accommodation_status="unknown",
            confirmed=True,
        )
        # Twenty near-identical peaks, which carry nature+sightseeing and so match
        # two of the three stated styles, against one prominent attraction that
        # carries only sightseeing.
        peaks = [candidate(f"peak-{n}", "peak", n) for n in range(20)]
        landmark = candidate("landmark", "attraction", 99, icon=True, opening=True)
        ranking = build_ranking(
            setup=owner,
            candidates=peaks + [landmark],
            choices=[],
            discovery_status="verified",
        )
        cards = ranking["cards"]
        order = sorted(cards, key=lambda pid: -cards[pid]["total_score"])
        peak_best = max(cards[f"peak-{n}"]["total_score"] for n in range(20))

        self.assertGreater(
            cards["landmark"]["total_score"],
            peak_best,
            "a prominent attraction must outrank twenty interchangeable peaks",
        )
        self.assertEqual("landmark", order[0])
        self.assertTrue(cards["landmark"]["is_city_icon"])

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


class CategoryVarietyTest(unittest.TestCase):
    """`WF-048`. The deck kept offering the same kind of place over and over.

    `_learned_category_weights` only ever argued for *more* of what was already
    chosen: pick three temples and temples rose, so the fourth and fifth temple led
    every lane. Right while it is still learning a taste, wrong once the taste is
    known — the reason to keep swiping is to find what you have not seen.
    """

    @staticmethod
    def _picks(category: str, count: int, action: str = "must_do"):
        return [{"action": action, "candidate": {"category": category}} for _ in range(count)]

    def test_the_first_choices_still_teach_what_the_owner_likes(self) -> None:
        # Unchanged below saturation: this is the signal that discovers a taste.
        weights = ranking._learned_category_weights(self._picks("museum", 1))

        self.assertEqual(2.0, weights["museum"])

    def test_a_category_chosen_repeatedly_is_pushed_down_not_up(self) -> None:
        weights = ranking._learned_category_weights(self._picks("place_of_worship", 4))

        self.assertLess(weights["place_of_worship"], 0.0)

    def test_the_penalty_is_bounded_so_a_category_stays_reachable(self) -> None:
        # Ten must_do temples must not drive every temple out of the catalogue -- the
        # owner may simply be on a temple trip, and Browse All has to still work.
        weights = ranking._learned_category_weights(self._picks("place_of_worship", 10))

        self.assertEqual(ranking.VARIETY_FLOOR, weights["place_of_worship"])

    def test_variety_is_per_category_not_global(self) -> None:
        choices = self._picks("place_of_worship", 5) + self._picks("museum", 1)
        weights = ranking._learned_category_weights(choices)

        self.assertLess(weights["place_of_worship"], 0.0)
        self.assertGreater(weights["museum"], 0.0)

    def test_a_rejection_neither_teaches_nor_saturates(self) -> None:
        # `not_for_trip` carries no action bonus, so rejecting ten temples must not
        # read as having chosen them.
        weights = ranking._learned_category_weights(
            self._picks("place_of_worship", 10, action="not_for_trip")
        )

        self.assertEqual(0.0, weights.get("place_of_worship", 0.0))


if __name__ == "__main__":
    unittest.main()

class LaneVarietyTest(unittest.TestCase):
    """Ten museums in a row.

    `main_queue` has had `WF-005`'s 4:1 ranked-to-exploration rule since it was built,
    but the deck deals from whichever lane is picked and defaults to **City Icons**,
    which was plain score order. Museums score alike, so on the owner's 1108-place Hong
    Kong catalogue City Icons opened with twelve museums and ran to **70 of the same
    category** unbroken.
    """

    def _cards(self, families: list[str]) -> tuple[list[str], dict]:
        ids = [f"p{index}" for index, _ in enumerate(families)]
        cards = {
            place_id: {
                "candidate_tags": {family},
                "total_score": 100.0 - index,
            }
            for index, (place_id, family) in enumerate(zip(ids, families))
        }
        return ids, cards

    def test_a_run_of_one_family_is_broken_up(self) -> None:
        ids, cards = self._cards(["culture"] * 5 + ["nature"] * 5)

        spread = ranking._spread_families(ids, cards)
        families = [ranking._family(cards[place_id]) for place_id in spread]

        self.assertEqual(sorted(ids), sorted(spread), "every candidate must survive")
        self.assertEqual(ids[0], spread[0], "the best-scoring card still leads")
        longest = max(len(list(group)) for _, group in groupby(families))
        self.assertLessEqual(longest, 2)

    def test_a_catalogue_of_one_kind_degrades_to_score_order(self) -> None:
        """Not to nothing, and not to an arbitrary order."""

        ids, cards = self._cards(["culture"] * 6)

        self.assertEqual(ids, ranking._spread_families(ids, cards))

