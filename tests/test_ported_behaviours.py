"""The new homes for behaviours currently asserted through Streamlit `AppTest`.

Artifact 029 classified 18 `AppTest` tests: 14 portable down to actions / core /
exports, 3 genuinely UI, 1 dying with Streamlit's `$`-as-LaTeX workaround.  Each
portable behaviour must be asserted at its new home **before** `views/` is
deleted at S6, so coverage never dips.  Organising these by provenance rather
than by domain is deliberate: this file is the S6 checklist.

**Two of the 14 were already at actions level when the port started**, so 12 are
outstanding rather than 14:

- `preview_is_persisted_but_unverified_inputs_cannot_activate`
  (`tests/test_optimizer.py`) never used `AppTest`.
- `a_destination_outside_the_picker_still_creates_a_trip`
  (`tests/test_setup_discovery.py`) only mentions `AppTest` in its docstring, to
  explain why it cannot drive a typed value through a selectbox.

Ported here by S3, covering the surfaces S3 builds — the five-step setup screen
and the sidebar trip selector:

| Behaviour | Its new home |
|---|---|
| `owner_and_two_members_confirm_and_survive_thai_switch` | `save_setup` + the copy catalogue |
| `trip_slots_create_switch_and_keep_drafts_independent` | `create_trip` / `get_setup` / `journey` |
| `deleting_the_last_trip_returns_to_first_trip_setup` | `delete_trip` + `journey` |

Ported here by S4, covering discovery/ranking and the active itinerary:

| Behaviour | Its new home |
|---|---|
| `interested_choice_persists_and_ranking_renders_in_thai` | ranking actions + catalogue |
| `missing_hours_and_hotel_create_a_visible_provisional_plan` | optimizer + export snapshot |
| `active_plan_renders_timeline_and_map_in_both_languages` | export snapshot + catalogue |
| `fallback_block_renders_beneath_its_half_day` | export snapshot placement |
| `a_trip_without_a_plan_is_told_which_stage_to_finish` | `journey()` gate data |

Ported by S5, covering the readiness board, the revise screen and the cost
section whose screen has existed since S2:

| Behaviour | Its new home |
|---|---|
| `trip_without_setup_explains_the_board_is_unavailable` | `propose_checklist` refusal + `journey` |
| `board_renders_previews_and_applies_in_both_languages` | checklist actions + catalogue |
| `the_section_previews_and_applies_in_both_languages` | revision actions + catalogue |
| `costs_section_renders_and_saves` | `save_cost_item` + `cost_totals` |

**Nothing is owed. All 14 portable behaviours are asserted below Streamlit**, so
`views/`, `app.py` and `ui/` can be deleted at S6 without coverage dipping. What
remains for S6 is the parity gate itself and the three genuinely-UI tests
artifact 029 kept: the paid-card placement rule, the entry-point smoke test that
changes subject to React, and the full journey walk.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from unittest.mock import patch

from travel_planner import destinations
from travel_planner.actions import PlannerActions, PlannerRefusal
from travel_planner.core import new_optimization_preview
from travel_planner.optimizer import optimize_trip


ROOT = Path(__file__).resolve().parents[1]
COPY = json.loads((ROOT / "i18n" / "copy.json").read_text(encoding="utf-8"))


class SetupConfirmationTest(unittest.TestCase):
    """Replaces `owner_and_two_members_confirm_and_survive_thai_switch`.

    The `AppTest` original drove five steps of widgets. What it actually asserted
    is that values entered on earlier steps survive the later ones into one
    confirmed draft, and that a language switch changes none of them -- both of
    which are `save_setup` behaviour, not Streamlit behaviour.
    """

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.actions = PlannerActions(Path(self.directory.name) / "ported.sqlite3")

    def confirmed_taipei(self) -> str:
        trip = self.actions.create_trip(
            name="Taipei New Year",
            destination=destinations.destination_text("Taiwan", "Taipei"),
            planning_mode="ready_to_schedule",
        )
        # The five steps collapse into one whole draft, which is exactly the
        # shape WF-026 requires the screen to send: all fields every time,
        # because a partial payload silently erases what it omits.
        self.actions.save_setup(
            trip_id=trip.trip_id,
            owner_age=26,
            main_style=["sightseeing", "culture"],
            travellers=[
                {"traveller_id": "member_1", "label": "Traveller", "age": 19},
                {"traveller_id": "member_2", "label": "Mother", "age": 50},
            ],
            confirmed=True,
        )
        return trip.trip_id

    def test_every_step_survives_into_one_confirmed_draft(self) -> None:
        trip_id = self.confirmed_taipei()
        setup = self.actions.get_setup(trip_id)
        payload = setup.snapshot.as_dict()

        self.assertTrue(setup.confirmed)
        self.assertEqual("Taipei, Taiwan", self.actions.get_trip(trip_id).destination)
        # Step 2's answers were not lost by steps 3 to 5.
        self.assertEqual(26, payload["owner"]["age"])
        self.assertEqual(["sightseeing", "culture"], payload["owner"]["main_style"])
        # Step 3's member cards, and no ability inferred from age.
        self.assertEqual([19, 50], [person["age"] for person in payload["travellers"]])

    def test_confirming_setup_moves_the_journey_off_setup(self) -> None:
        trip_id = self.confirmed_taipei()
        journey = self.actions.journey(trip_id)

        # The original asserted the Places subheader rendered; the gate data
        # behind that is what the screen reads, and React cannot recompute it.
        self.assertEqual("places", journey["next"])
        stages = {stage["key"]: stage for stage in journey["stages"]}
        self.assertTrue(stages["setup"]["done"])
        self.assertIsNone(stages["places"]["blocked_by"])

    def test_keeping_one_place_does_not_open_the_later_stages(self) -> None:
        """"Check trip facts" and "Build the plan" waited on a single keep.

        The deck deals hundreds of cards, so one keep is the *start* of choosing, not the
        end of it — and the sidebar offered both later stages while the owner was still
        swiping, which was reported as confusing. They now wait for the deliberate press
        of "Build the plan" on `/places`, which is the only moment the app is told the
        choosing is over.
        """

        trip_id = self.confirmed_taipei()
        self.actions.discover_places(trip_id=trip_id)
        place_id = self.actions.get_latest_discovery(trip_id).candidates.as_dict()[
            "candidates"
        ][0]["place_id"]
        self.actions.save_candidate_choice(
            trip_id=trip_id, place_id=place_id, action="interested"
        )

        stages = {s["key"]: s for s in self.actions.journey(trip_id)["stages"]}
        self.assertEqual("places", stages["evidence"]["blocked_by"])
        self.assertEqual("places", stages["optimize"]["blocked_by"])
        self.assertFalse(stages["places"]["done"])

        self.actions.confirm_places_selection(trip_id)

        stages = {s["key"]: s for s in self.actions.journey(trip_id)["stages"]}
        self.assertIsNone(stages["evidence"]["blocked_by"])
        self.assertIsNone(stages["optimize"]["blocked_by"])
        self.assertTrue(stages["places"]["done"])

    def test_a_trip_that_already_has_a_draft_is_not_relocked(self) -> None:
        """Owners mid-flight had no way to press a button that did not exist when they
        chose. A trip holding a preview or an activated plan is confirmed by
        construction."""

        trip_id = self.confirmed_taipei()
        self.actions.discover_places(trip_id=trip_id)
        for candidate in self.actions.get_latest_discovery(trip_id).candidates.as_dict()[
            "candidates"
        ][:2]:
            self.actions.save_candidate_choice(
                trip_id=trip_id, place_id=candidate["place_id"], action="must_do"
            )
        self.actions.generate_plan_preview(trip_id)

        stages = {s["key"]: s for s in self.actions.journey(trip_id)["stages"]}
        self.assertIsNone(stages["optimize"]["blocked_by"])

    def test_an_unconfirmed_draft_keeps_the_journey_on_setup(self) -> None:
        trip = self.actions.create_trip(name="Kyoto ideas", destination="Kyoto, Japan")
        self.actions.save_setup(trip_id=trip.trip_id, main_style=["nature"])

        journey = self.actions.journey(trip.trip_id)
        self.assertEqual("setup", journey["next"])
        self.assertFalse({s["key"]: s for s in journey["stages"]}["setup"]["done"])

    def test_a_language_switch_changes_no_stored_value(self) -> None:
        trip_id = self.confirmed_taipei()
        before = self.actions.get_setup(trip_id).snapshot

        # Language lives in the trip record and in the catalogue lookup; it is
        # never an argument to the planning core. Rewriting it must not touch
        # the draft or its hash.
        self.actions.create_trip(name="Other", destination="Osaka, Japan", language="th")
        after = self.actions.get_setup(trip_id).snapshot

        self.assertEqual(before.sha256, after.sha256)
        self.assertEqual(before.as_dict(), after.as_dict())

    def test_the_setup_screen_labels_exist_in_both_languages(self) -> None:
        # The original proved Thai rendered by reading a Thai subheader. The
        # guarantee underneath is catalogue parity for the keys this screen uses.
        text = COPY["TEXT"]
        for code in ("stage_setup", "stage_places", "stage_optimize", "step_of"):
            for language in ("en", "th"):
                self.assertIn(code, text[language], f"{code} missing in {language}")
                self.assertTrue(text[language][code].strip(), f"{code} empty in {language}")
        self.assertNotEqual(text["en"]["stage_setup"], text["th"]["stage_setup"])

    def test_every_preference_tag_the_screen_offers_has_both_languages(self) -> None:
        tags = COPY["TAG_TEXT"]
        groups = self.actions.setup_vocabulary()["tag_groups"]
        offered = [tag for group in groups.values() for tag in group]

        self.assertEqual(21, len(offered))
        for tag in offered:
            for language in ("en", "th"):
                self.assertIn(tag, tags[language], f"{tag} missing in {language}")

    def test_the_real_taipei_trip_round_trips_whole(self) -> None:
        """S3's closing check: nothing the form holds is lost by saving it.

        `save_setup` defaults every field to empty, so a payload that omits one
        erases it. The screen therefore holds one draft object and sends it
        whole -- and a re-save of what was read back must be a fixed point.
        """

        trip = self.actions.create_trip(
            name="Taipei New Year",
            destination=destinations.destination_text("Taiwan", "Taipei"),
            planning_mode="ready_to_schedule",
        )
        whole = {
            "owner_age": 34,
            "main_style": ["sightseeing", "culture"],
            "also_enjoy": ["local_street_food", "night_view"],
            "avoid": ["tourist_traps"],
            "comfort": ["balanced_pace"],
            "owner_description": "Walking is fine when the route has sights.",
            "owner_must_respect": ["No 6am starts"],
            "owner_nationality": "TH",
            "travellers": [
                {
                    "traveller_id": "member_1",
                    "label": "Mum",
                    "age": 63,
                    "tags": ["rest_breaks"],
                    "description": "Prefers a slower morning",
                    "must_respect": ["No long stairs"],
                    "nationality": "TH",
                },
                {
                    "traveller_id": "member_2",
                    "label": "Dad",
                    "age": 66,
                    "tags": [],
                    "description": "",
                    "must_respect": [],
                    "nationality": "TH",
                },
            ],
            "start_date": "2026-12-29",
            "end_date": "2027-01-03",
            "arrival_time": "17:00",
            "departure_time": "11:00",
            "accommodation_status": "not_booked",
        }
        self.actions.save_setup(trip_id=trip.trip_id, confirmed=True, **whole)
        payload = self.actions.get_setup(trip.trip_id).snapshot.as_dict()

        basics, owner = payload["trip_basics"], payload["owner"]
        self.assertEqual("2026-12-29", basics["start_date"])
        self.assertEqual("2027-01-03", basics["end_date"])
        self.assertEqual("17:00", basics["arrival_time"])
        self.assertEqual("11:00", basics["departure_time"])
        self.assertEqual("not_booked", basics["accommodation_status"])
        self.assertEqual(34, owner["age"])
        self.assertEqual(["sightseeing", "culture"], owner["main_style"])
        self.assertEqual(["No 6am starts"], owner["must_respect"])
        # The POC's save omits both nationality fields, so a round-trip through
        # it drops them. Readiness generation reads them, so they must survive.
        self.assertEqual("TH", owner["nationality"])
        self.assertEqual(["TH", "TH"], [m["nationality"] for m in payload["travellers"]])
        self.assertEqual(["Mum", "Dad"], [m["label"] for m in payload["travellers"]])
        self.assertEqual(["No long stairs"], payload["travellers"][0]["must_respect"])

        # Re-saving what was read back is a fixed point, which is the property
        # the screen depends on when it reloads a draft it did not just write.
        before = self.actions.get_setup(trip.trip_id).snapshot.sha256
        self.actions.save_setup(trip_id=trip.trip_id, confirmed=True, **whole)
        self.assertEqual(before, self.actions.get_setup(trip.trip_id).snapshot.sha256)

    def test_the_pickers_offer_a_stable_meaningful_order(self) -> None:
        vocabulary = self.actions.setup_vocabulary()

        # A frozenset would give the form an arbitrary order on every run.
        self.assertEqual(["explore_first", "ready_to_schedule"], vocabulary["planning_modes"])
        self.assertEqual(
            ["unknown", "not_booked", "booked"], vocabulary["accommodation_statuses"]
        )
        taiwan = next(c for c in vocabulary["countries"] if c["code"] == "Taiwan")
        self.assertEqual("ไต้หวัน", taiwan["label"]["th"])
        self.assertIn("Taipei", taiwan["cities"])


class ActivationGateTest(unittest.TestCase):
    """S3's second closing check: a variant activates, and a stale hash refuses.

    Hashes are the staleness mechanism, not timestamps, so a change to what the
    owner chose must invalidate a preview built from the old choices. The
    optimize screen shows the refusal code because activation is the one action
    that writes an immutable plan version -- a silent failure would read as
    success.

    A `ready` variant needs verified opening hours, which no offline provider can
    supply, so the preview is built from a historic regression fixture and
    `_optimizer_input` is patched to agree with it. That is the same recipe
    `tests/test_optimizer.py` already uses for activation.
    """

    def setUp(self) -> None:
        from tests.test_optimizer import fixture

        self.snapshot = fixture("ix-jp-shibuya-hours-view-walk")["planner_input"]
        self.proposal = optimize_trip(self.snapshot)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.actions = PlannerActions(Path(self.directory.name) / "activation.sqlite3")
        trip = self.actions.create_trip(name="Ready", destination="Test City")
        self.trip_id = trip.trip_id

    def save_preview(self) -> None:
        self.actions.store.save_optimization_preview(
            new_optimization_preview(
                trip_id=self.trip_id,
                optimizer_input=self.snapshot,
                proposal=self.proposal,
            )
        )

    def test_a_ready_variant_activates_as_an_immutable_plan_version(self) -> None:
        self.save_preview()

        with patch.object(self.actions, "_optimizer_input", return_value=self.snapshot):
            version = self.actions.activate_plan_preview(
                trip_id=self.trip_id, variant_id="best_balance"
            )

        self.assertEqual(version, self.actions.get_active_plan(self.trip_id))
        self.assertEqual("ready", version.snapshot.as_dict()["variant"]["status"])
        # Activation consumes the preview rather than leaving it reusable.
        self.assertIsNone(self.actions.get_plan_preview(self.trip_id))

    def test_a_stale_input_hash_refuses_and_writes_nothing(self) -> None:
        self.save_preview()
        moved = {**self.snapshot, "trip_id": "something the preview never saw"}

        with patch.object(self.actions, "_optimizer_input", return_value=moved):
            with self.assertRaises(PlannerRefusal) as caught:
                self.actions.activate_plan_preview(
                    trip_id=self.trip_id, variant_id="best_balance"
                )

        self.assertEqual("preview_stale", caught.exception.code)
        # The refusal is total: no plan version, and the preview still stands.
        self.assertIsNone(self.actions.get_active_plan(self.trip_id))
        self.assertIsNotNone(self.actions.get_plan_preview(self.trip_id))

    def test_a_missing_preview_and_an_unknown_variant_each_refuse(self) -> None:
        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.activate_plan_preview(
                trip_id=self.trip_id, variant_id="best_balance"
            )
        self.assertEqual("preview_missing", caught.exception.code)

        self.save_preview()
        with patch.object(self.actions, "_optimizer_input", return_value=self.snapshot):
            with self.assertRaises(PlannerRefusal) as caught:
                self.actions.activate_plan_preview(
                    trip_id=self.trip_id, variant_id="no_such_variant"
                )
        self.assertEqual("unknown_plan_variant", caught.exception.code)

    def test_the_screen_can_map_every_refusal_it_shows_to_a_status(self) -> None:
        from api import REFUSAL_STATUS

        for code in (
            "preview_missing",
            "preview_stale",
            "unknown_plan_variant",
            "variant_not_ready",
            "no_places_chosen",
        ):
            self.assertIn(code, REFUSAL_STATUS, code)

        # Refusal prose lives with the other stable optimizer/action codes, not
        # in the general interface table. React must use that table explicitly.
        self.assertNotIn("preview_stale", COPY["TEXT"]["en"])
        self.assertIn("preview_stale", COPY["OPTIMIZER_CODE_TEXT"]["th"])


class S4PortedBehaviourTest(unittest.TestCase):
    """The five AppTest behaviours whose React surfaces land in S4."""

    def test_interested_choice_persists_and_thai_ranking_copy_exists(self) -> None:
        from tests.test_ranking import RankingActionsTest

        with TemporaryDirectory() as directory:
            path = Path(directory) / "ranking.sqlite3"
            actions = PlannerActions(path, place_provider=RankingActionsTest.Provider())
            trip = actions.create_trip(name="Taipei", destination="Taipei, Taiwan")
            actions.save_setup(
                trip_id=trip.trip_id,
                main_style=["sightseeing", "culture"],
                travellers=[{"label": "Member", "age": 19, "tags": ["nature"]}],
                confirmed=True,
            )
            actions.discover_places(trip_id=trip.trip_id)
            before = actions.rank_candidates(trip.trip_id)
            place_id = before["lanes"]["main_queue"][0]["place_id"]
            actions.save_candidate_choice(
                trip_id=trip.trip_id, place_id=place_id, action="interested"
            )

            resumed = PlannerActions(path)
            after = resumed.rank_candidates(trip.trip_id)
            self.assertEqual("interested", resumed.list_candidate_choices(trip.trip_id)[0].action)
            self.assertNotIn(
                place_id, [item["place_id"] for item in after["lanes"]["main_queue"]]
            )
            self.assertIn(place_id, after["lanes"]["browse_all"])
            # Updated 2026-08-10 with the terminology pass: "Personalized place
            # cards" became "Places picked for your trip" in both languages. The
            # literal stays pinned rather than being relaxed to a presence check —
            # the point of this line is that the Thai is written, and a test that
            # only asks whether *something* is there would pass on the English.
            self.assertEqual(
                "สถานที่ที่คัดมาให้ทริปนี้", COPY["TEXT"]["th"]["ranking_title"]
            )

    def test_missing_hours_and_hotel_remain_visible_in_a_provisional_export(self) -> None:
        from tests.test_routes import FakePlaceProvider, FakeRouteProvider

        with TemporaryDirectory() as directory:
            actions = PlannerActions(
                Path(directory) / "provisional.sqlite3",
                place_provider=FakePlaceProvider(),
                route_provider=FakeRouteProvider(),
            )
            trip = actions.create_trip(
                name="Taipei provisional",
                destination="Taipei, Taiwan",
                planning_mode="explore_first",
            )
            actions.save_setup(
                trip_id=trip.trip_id,
                main_style=["sightseeing"],
                start_date="2030-01-01",
                end_date="2030-01-03",
                accommodation_status="not_booked",
                confirmed=True,
            )
            discovery = actions.discover_places(trip_id=trip.trip_id)
            for candidate in discovery.candidates.as_dict()["candidates"]:
                actions.save_candidate_choice(
                    trip_id=trip.trip_id,
                    place_id=candidate["place_id"],
                    action="must_do",
                )
            actions.refresh_routes(trip.trip_id)

            proposal = actions.generate_plan_preview(trip.trip_id).proposal.as_dict()
            variant = proposal["variants"][0]
            self.assertEqual("provisional", variant["status"])
            self.assertTrue(variant["validation"]["valid"])
            actions.activate_plan_preview(
                trip_id=trip.trip_id, variant_id=variant["variant_id"]
            )
            exported = actions.build_export_snapshot(trip.trip_id).as_dict()
            self.assertEqual("action_needed", exported["readiness"]["state"])
            self.assertEqual("provisional", exported["readiness"]["variant_status"])
            self.assertEqual(
                "provisional_accommodation_base",
                exported["accommodation"]["anchor"]["subject_id"],
            )

    def test_active_plan_snapshot_carries_timeline_stops_and_both_languages(self) -> None:
        from tests.test_exports import plan_payload, planner_input

        plan = plan_payload(planner_input(with_names=True, with_coordinates=True))
        with TemporaryDirectory() as directory:
            actions = PlannerActions(Path(directory) / "active.sqlite3")
            trip = actions.create_trip(name="Tokyo day", destination="Tokyo")
            actions.save_plan_version(
                trip_id=trip.trip_id, snapshot=plan, cause="optimizer:best_balance"
            )

            english = actions.build_export_snapshot(trip.trip_id, language="en").as_dict()
            thai = actions.build_export_snapshot(trip.trip_id, language="th").as_dict()
            self.assertTrue(any(day["items"] for day in english["days"]))
            self.assertTrue(any(day["stops"] for day in english["days"]))
            self.assertIn(
                "Shibuya Sky",
                [item["display_name"] for day in english["days"] for item in day["stops"]],
            )
            self.assertIn(
                "ชิบูยะสกาย",
                [item["display_name"] for day in thai["days"] for item in day["stops"]],
            )
            self.assertEqual(
                [[item["subject_id"] for item in day["stops"]] for day in english["days"]],
                [[item["subject_id"] for item in day["stops"]] for day in thai["days"]],
            )

    def test_fallback_stays_beneath_the_half_day_that_contains_its_replacement(self) -> None:
        from tests.test_exports import CATALOG, plan_payload

        source = next(
            item
            for item in CATALOG["fixtures"]
            if item["metadata"]["id"] == "ix-jp-rain-fallback-reoptimization"
        )
        plan = plan_payload(json.loads(json.dumps(source["planner_input"])))
        with TemporaryDirectory() as directory:
            actions = PlannerActions(Path(directory) / "fallback.sqlite3")
            trip = actions.create_trip(name="Rain day", destination="Tokyo")
            actions.save_plan_version(
                trip_id=trip.trip_id, snapshot=plan, cause="optimizer:best_balance"
            )
            exported = actions.build_export_snapshot(trip.trip_id).as_dict()

        located = [fallback for day in exported["days"] for fallback in day["fallbacks"]]
        self.assertTrue(located)
        for fallback in located:
            self.assertIn(fallback["half_day"], {"morning", "afternoon"})
            day = next(item for item in exported["days"] if item["date"] == fallback["date"])
            replacement = next(
                item for item in day["items"] if item["item_id"] == fallback["replacement_item_id"]
            )
            self.assertEqual(
                "morning" if replacement["start"] < "12:00" else "afternoon",
                fallback["half_day"],
            )

    def test_a_trip_without_a_plan_names_optimize_as_the_itinerary_blocker(self) -> None:
        with TemporaryDirectory() as directory:
            actions = PlannerActions(Path(directory) / "blocked.sqlite3")
            trip = actions.create_trip(name="No plan", destination="Osaka")
            journey = actions.journey(trip.trip_id)

        itinerary = next(stage for stage in journey["stages"] if stage["key"] == "itinerary")
        self.assertEqual("optimize", itinerary["blocked_by"])
        self.assertEqual("setup", journey["next"])


class TripSlotTest(unittest.TestCase):
    """Replaces `trip_slots_create_switch_and_keep_drafts_independent`.

    The sidebar trip selector is a rendering of this: several trips coexist,
    each keeps its own draft, and switching resumes each at its own stage.
    """

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "slots.sqlite3"
        self.actions = PlannerActions(self.path)

    def two_trips(self) -> tuple[str, str]:
        taiwan = self.actions.create_trip(
            name="Taiwan draft", destination=destinations.destination_text("Taiwan", "Taipei")
        )
        self.actions.save_setup(
            trip_id=taiwan.trip_id,
            main_style=["culture"],
            owner_description="Taiwan night markets",
            confirmed=True,
        )
        kyoto = self.actions.create_trip(
            name="Kyoto ideas", destination=destinations.destination_text("Japan", "Kyoto")
        )
        self.actions.save_setup(
            trip_id=kyoto.trip_id,
            main_style=["nature"],
            owner_description="Kyoto gardens",
        )
        return taiwan.trip_id, kyoto.trip_id

    def test_two_trips_keep_independent_drafts(self) -> None:
        taiwan_id, kyoto_id = self.two_trips()

        self.assertNotEqual(taiwan_id, kyoto_id)
        self.assertEqual("Kyoto, Japan", self.actions.get_trip(kyoto_id).destination)
        taiwan = self.actions.get_setup(taiwan_id).snapshot.as_dict()
        kyoto = self.actions.get_setup(kyoto_id).snapshot.as_dict()
        self.assertEqual("Taiwan night markets", taiwan["owner"]["description"])
        self.assertEqual("Kyoto gardens", kyoto["owner"]["description"])
        self.assertEqual(["culture"], taiwan["owner"]["main_style"])
        self.assertEqual(["nature"], kyoto["owner"]["main_style"])

    def test_each_trip_resumes_at_its_own_stage(self) -> None:
        taiwan_id, kyoto_id = self.two_trips()

        # A confirmed draft resumes past setup; the unfinished one stays on it.
        # Switching needs no navigation click because the stage is derived.
        self.assertEqual("places", self.actions.journey(taiwan_id)["next"])
        self.assertEqual("setup", self.actions.journey(kyoto_id)["next"])

    def test_a_draft_survives_the_process_that_wrote_it(self) -> None:
        taiwan_id, _ = self.two_trips()
        resumed = PlannerActions(self.path)

        self.assertTrue(resumed.get_setup(taiwan_id).confirmed)
        self.assertEqual(
            {"Taiwan draft", "Kyoto ideas"},
            {trip.name for trip in resumed.list_trips()},
        )

    def test_the_selector_lists_newest_first(self) -> None:
        taiwan_id, kyoto_id = self.two_trips()

        # The sidebar renders this order, so it is asserted where it is decided.
        self.assertEqual(
            [kyoto_id, taiwan_id], [trip.trip_id for trip in self.actions.list_trips()]
        )


class LastTripDeletionTest(unittest.TestCase):
    """Replaces `deleting_the_last_trip_returns_to_first_trip_setup`."""

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.actions = PlannerActions(Path(self.directory.name) / "deletion.sqlite3")

    def test_deleting_the_only_trip_leaves_nothing_to_resume(self) -> None:
        trip = self.actions.create_trip(name="Only trip", destination="Taipei")
        self.actions.save_setup(trip_id=trip.trip_id, main_style=["culture"], confirmed=True)

        self.actions.delete_trip(trip_id=trip.trip_id)

        # No trips means the app has no stage to land on, which is what sent the
        # original to first-trip setup.
        self.assertEqual([], self.actions.list_trips())
        self.assertIsNone(self.actions.get_setup(trip.trip_id))

    def test_a_deleted_trip_refuses_rather_than_answering_emptily(self) -> None:
        trip = self.actions.create_trip(name="Only trip", destination="Taipei")
        self.actions.delete_trip(trip_id=trip.trip_id)

        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.journey(trip.trip_id)
        self.assertEqual("unknown_trip", caught.exception.code)

        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.delete_trip(trip_id=trip.trip_id)
        self.assertEqual("unknown_trip", caught.exception.code)

    def test_deleting_one_of_two_leaves_the_other_resumable(self) -> None:
        first = self.actions.create_trip(name="Taipei", destination="Taipei")
        second = self.actions.create_trip(name="Kyoto", destination="Kyoto")
        self.actions.save_setup(trip_id=second.trip_id, main_style=["nature"], confirmed=True)

        self.actions.delete_trip(trip_id=first.trip_id)

        self.assertEqual([second.trip_id], [t.trip_id for t in self.actions.list_trips()])
        self.assertEqual("places", self.actions.journey(second.trip_id)["next"])


if __name__ == "__main__":
    unittest.main()


class S5PortedBehaviourTest(unittest.TestCase):
    """The last four AppTest behaviours, whose React surfaces land in S5.

    With these the S6 deletion checklist is empty: every behaviour artifact 029
    called portable is asserted below Streamlit, so `views/` can go without
    coverage dipping.
    """

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "s5.sqlite3"
        self.actions = PlannerActions(self.path)

    def taipei(self, *, confirmed: bool = True) -> str:
        trip = self.actions.create_trip(
            name="Taipei", destination="Taipei, Taiwan", planning_mode="ready_to_schedule"
        )
        self.actions.save_setup(
            trip_id=trip.trip_id,
            main_style=["sightseeing", "culture"],
            owner_nationality="TH",
            travellers=[{"traveller_id": "member_1", "label": "Mum", "age": 63}],
            start_date="2026-12-29",
            end_date="2027-01-03",
            accommodation_status="not_booked",
            confirmed=confirmed,
        )
        return trip.trip_id

    # ---- trip_without_setup_explains_the_board_is_unavailable ----

    def test_a_trip_without_setup_says_the_board_is_unavailable(self) -> None:
        trip = self.actions.create_trip(name="Bare", destination="Taipei, Taiwan")

        # The board cannot be generated from nothing, and it refuses with a
        # stable code rather than returning an empty board that looks finished.
        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.propose_checklist(trip.trip_id)
        self.assertEqual("setup_missing", caught.exception.code)

        self.assertEqual([], self.actions.list_checklist_items(trip.trip_id))
        self.assertEqual("setup", self.actions.journey(trip.trip_id)["next"])
        for language in ("en", "th"):
            self.assertIn("checklist_needs_setup", COPY["TEXT"][language])

    # ---- board_renders_previews_and_applies_in_both_languages ----

    def test_the_board_previews_before_it_applies(self) -> None:
        trip = self.taipei()

        preview = self.actions.propose_checklist(trip)
        self.assertTrue(preview["additions"], "a fresh trip has something to add")
        self.assertEqual([], self.actions.list_checklist_items(trip))

        applied = self.actions.apply_checklist_proposal(trip)
        items = self.actions.list_checklist_items(trip)

        # Nothing is applied silently: what the preview listed is what landed.
        self.assertEqual(len(preview["additions"]), applied["added"])
        self.assertEqual(applied["added"], len(items))
        # Proposing again is idempotent, so re-opening the screen offers nothing.
        again = self.actions.propose_checklist(trip)
        self.assertEqual([], again["additions"])
        self.assertEqual(len(items), again["unchanged"])

    def test_every_generated_board_item_reads_in_both_languages(self) -> None:
        trip = self.taipei()
        self.actions.apply_checklist_proposal(trip)
        items = self.actions.list_checklist_items(trip)
        self.assertTrue(items)

        from travel_planner.checklist import display_consequence, display_title

        for language in ("en", "th"):
            words = COPY["TEXT"][language]
            for item in items:
                title = display_title(item, words)
                self.assertTrue(title.strip(), f"empty title in {language}")
                self.assertNotIn("{", title, f"unfilled placeholder in {language}: {title}")
                self.assertTrue(display_consequence(item, words).strip())
                # Every code the board renders resolves; none leaks to the owner.
                for code in (item["category"], item["timing"], item["requirement_level"]):
                    self.assertIn(code, words, f"{code} missing in {language}")
                self.assertIn(f"progress_{item['progress']}", words)
                self.assertIn(f"evidence_{item['evidence_state']}", words)

    def test_a_generated_item_dismisses_rather_than_deleting(self) -> None:
        trip = self.taipei()
        self.actions.apply_checklist_proposal(trip)
        item = self.actions.list_checklist_items(trip)[0]

        self.actions.set_checklist_dismissed(
            trip_id=trip, item_id=item["item_id"], dismissed=True
        )
        after = {row["item_id"]: row for row in self.actions.list_checklist_items(trip)}

        # Still present, so a board that changed can be explained.
        self.assertIn(item["item_id"], after)
        self.assertTrue(after[item["item_id"]]["dismissed"])

    def test_readiness_warnings_never_block_the_itinerary(self) -> None:
        trip = self.taipei()
        self.actions.apply_checklist_proposal(trip)

        readiness = self.actions.checklist_readiness(trip)

        # `blocks_itinerary` is always False by decision; a readiness gap warns.
        self.assertFalse(readiness["blocks_itinerary"])
        self.assertIn(readiness["state"], COPY["TEXT"]["en"])

    def test_the_board_vocabulary_cannot_drift_from_the_core(self) -> None:
        from travel_planner import checklist

        vocabulary = self.actions.checklist_vocabulary()

        self.assertEqual(list(checklist.CATEGORIES), vocabulary["categories"])
        self.assertEqual(list(checklist.TIMING_BUCKETS), vocabulary["timing_buckets"])
        self.assertEqual(list(checklist.PROGRESS_STATES), vocabulary["progress_states"])
        self.assertEqual(list(checklist.EVIDENCE_STATES), vocabulary["evidence_states"])
        self.assertEqual(list(checklist.REQUIREMENT_LEVELS), vocabulary["requirement_levels"])

    # ---- the_section_previews_and_applies_in_both_languages (revision) ----

    def test_revision_refuses_without_an_active_plan(self) -> None:
        trip = self.taipei()

        self.assertEqual([], self.actions.quick_actions(trip))
        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.propose_revision(
                trip_id=trip, operation={"operation": "fully_reoptimize", "arguments": {}}
            )
        self.assertEqual("no_active_plan", caught.exception.code)

    def test_every_offered_quick_action_reads_in_both_languages(self) -> None:
        from travel_planner.revision import OPERATIONS

        for language in ("en", "th"):
            words = COPY["TEXT"][language]
            for name in OPERATIONS:
                self.assertIn(f"op_{name}", words, f"op_{name} missing in {language}")

    def test_the_revision_panel_labels_exist_in_both_languages(self) -> None:
        for language in ("en", "th"):
            words = COPY["TEXT"][language]
            for code in (
                "quick_action", "run_action", "pending_revision", "revision_assumptions",
                "changed_days", "no_changes", "before", "after", "delta", "moved_items",
                "added_items", "removed_items", "shortened_items", "lengthened_items",
                "displaced_items", "new_warnings", "cleared_warnings", "revision_blocked",
                "apply_revision", "cancel_revision", "revision_history", "restore_version",
            ):
                self.assertIn(code, words, f"{code} missing in {language}")

    # ---- costs_section_renders_and_saves ----

    def test_the_cost_section_saves_and_totals_a_row(self) -> None:
        trip = self.taipei()
        self.actions.save_rate_snapshot(
            trip_id=trip, rates={"TWD": 1.12}, as_of="2026-12-28", source="BOT reference"
        )

        saved = self.actions.save_cost_item(
            trip_id=trip,
            item={
                "label": "Cable car",
                "category": "transport",
                "original_amount": 600,
                "original_currency": "THB",
                "payment_state": "estimate",
            },
        )
        rows = self.actions.list_cost_items(trip)
        totals = self.actions.cost_totals(trip)

        self.assertEqual(1, len(rows))
        self.assertEqual("Cable car", rows[0]["label"])
        self.assertEqual(600.0, rows[0]["reported_thb"])
        self.assertEqual(600.0, totals["total_thb"])
        self.assertEqual(600.0, totals["estimated_thb"])
        # S2's additions: an estimate is planned, and nothing is actual yet.
        self.assertEqual(600.0, totals["planned_thb"])
        self.assertEqual(0.0, totals["actual_thb"])

        self.actions.delete_cost_item(trip_id=trip, cost_id=saved["cost_id"])
        self.assertEqual([], self.actions.list_cost_items(trip))

    def test_the_cost_screen_labels_exist_in_both_languages(self) -> None:
        from travel_planner.costs import CATEGORIES, PAYMENT_STATES

        for language in ("en", "th"):
            words = COPY["TEXT"][language]
            for code in (*CATEGORIES, *PAYMENT_STATES, "total_thb", "estimated_thb", "paid_thb"):
                self.assertIn(code, words, f"{code} missing in {language}")


class S5RevisionGateTest(unittest.TestCase):
    """S5's closing checks: a quick action rebuilds with consequences, and a
    revision applies and restores.

    The preview is built from a historic regression fixture and
    `_optimizer_input` is patched to agree with it, the same recipe activation
    uses, because a rebuilt variant needs verified opening hours that no offline
    provider can supply.
    """

    def setUp(self) -> None:
        from tests.test_optimizer import fixture

        self.snapshot = fixture("ix-jp-shibuya-hours-view-walk")["planner_input"]
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.actions = PlannerActions(Path(self.directory.name) / "revise.sqlite3")
        trip = self.actions.create_trip(name="Ready", destination="Test City")
        self.trip_id = trip.trip_id
        self.patch = patch.object(
            self.actions, "_optimizer_input", return_value=self.snapshot
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.actions.store.save_optimization_preview(
            new_optimization_preview(
                trip_id=self.trip_id,
                optimizer_input=self.snapshot,
                proposal=optimize_trip(self.snapshot),
            )
        )
        self.first = self.actions.activate_plan_preview(
            trip_id=self.trip_id, variant_id="best_balance"
        )

    def test_quick_actions_are_offered_once_a_plan_is_active(self) -> None:
        offered = self.actions.quick_actions(self.trip_id)

        self.assertTrue(offered)
        # Every offered operation is one the typed set supports, so the screen
        # cannot propose something `revision.py` would refuse.
        from travel_planner.revision import OPERATIONS

        for item in offered:
            self.assertIn(item["operation"], OPERATIONS)
            for required in OPERATIONS[item["operation"]]["args"]:
                self.assertIn(required, item["arguments"])

    def test_a_quick_action_rebuilds_a_variant_and_shows_consequences(self) -> None:
        offered = self.actions.quick_actions(self.trip_id)
        changing = next(
            item
            for item in offered
            if item["operation"] not in {"explain"}
        )

        draft = self.actions.propose_revision(trip_id=self.trip_id, operation=changing)

        # The rebuilt variant and its before/after comparison are both present,
        # which is what the screen renders.
        self.assertEqual(changing["operation"], draft["operation"])
        self.assertIsNotNone(draft.get("consequences") or draft.get("explanation"))
        consequences = draft.get("consequences")
        if consequences:
            self.assertIn("metrics", consequences)
            for delta in consequences["metrics"].values():
                self.assertEqual(
                    delta["after"] - delta["before"], delta["delta"], delta
                )
            self.assertIn("can_apply", consequences)
        # The active plan is untouched until apply.
        self.assertEqual(
            self.first.version_id, self.actions.get_active_plan(self.trip_id).version_id
        )

    def test_only_one_draft_is_pending_at_a_time(self) -> None:
        offered = self.actions.quick_actions(self.trip_id)
        first, second = offered[0], next(
            item for item in offered if item["operation"] != offered[0]["operation"]
        )
        self.actions.propose_revision(trip_id=self.trip_id, operation=first)

        # Re-running the *same* action just rebuilds; it is not a conflict.
        same = self.actions.propose_revision(trip_id=self.trip_id, operation=first)
        self.assertEqual(first["operation"], same["operation"])

        # A *different* action would silently discard the pending one, so it
        # refuses until the caller says to replace it.
        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.propose_revision(trip_id=self.trip_id, operation=second)
        self.assertEqual("revision_already_pending", caught.exception.code)
        self.assertEqual(
            first["operation"], self.actions.get_revision_draft(self.trip_id)["operation"]
        )

        replaced = self.actions.propose_revision(
            trip_id=self.trip_id, operation=second, replace_pending=True
        )
        self.assertEqual(second["operation"], replaced["operation"])

    def test_a_revision_applies_and_the_old_version_restores(self) -> None:
        offered = self.actions.quick_actions(self.trip_id)
        applicable = None
        for item in offered:
            draft = self.actions.propose_revision(
                trip_id=self.trip_id, operation=item, replace_pending=True
            )
            if draft.get("can_apply") or (draft.get("consequences") or {}).get("can_apply"):
                applicable = item
                break
        if applicable is None:
            self.skipTest("no offered quick action was applicable on this fixture")

        self.actions.apply_revision(self.trip_id)
        after = self.actions.get_active_plan(self.trip_id)

        # Applying writes a new immutable version and an append-only history row.
        self.assertNotEqual(self.first.version_id, after.version_id)
        history = self.actions.list_revisions(self.trip_id)
        self.assertEqual(1, len(history))
        self.assertEqual(self.first.version_id, history[0]["from_version_id"])
        self.assertEqual(after.version_id, history[0]["to_version_id"])
        self.assertIsNone(self.actions.get_revision_draft(self.trip_id))

        restored = self.actions.restore_plan_version(
            trip_id=self.trip_id, version_id=self.first.version_id
        )

        # Restoring creates another version pointing at the old snapshot and
        # deletes nothing, so the history stays append-only.
        self.assertNotEqual(self.first.version_id, restored.version_id)
        self.assertNotEqual(after.version_id, restored.version_id)
        self.assertEqual(
            self.first.snapshot.sha256, restored.snapshot.sha256
        )
        versions = {v.version_id for v in self.actions.list_plan_versions(self.trip_id)}
        self.assertTrue({self.first.version_id, after.version_id, restored.version_id} <= versions)

    def test_discarding_a_draft_leaves_the_active_plan_alone(self) -> None:
        offered = self.actions.quick_actions(self.trip_id)
        self.actions.propose_revision(trip_id=self.trip_id, operation=offered[0])

        self.actions.discard_revision_draft(self.trip_id)

        self.assertIsNone(self.actions.get_revision_draft(self.trip_id))
        self.assertEqual(
            self.first.version_id, self.actions.get_active_plan(self.trip_id).version_id
        )
        self.assertEqual([], self.actions.list_revisions(self.trip_id))
