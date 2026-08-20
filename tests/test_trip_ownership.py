"""Ten people on one deployment must not see each other's trips.

There is no authentication here and this does not add any: the token is a random
value the browser keeps, and whoever copies it gets the trips, exactly as whoever
copies a share link gets what it points at. What it fixes is the accidental case,
which was the whole of the problem -- `list_trips` returned every visitor's trips
and `/` opened inside whichever was newest, showing a stranger someone's travellers,
their ages and their accommodation address.

Checked through `dispatch`, because that is where the rule lives. 108 methods take a
`trip_id` and asking each of them the same question is how the 109th comes to be
missing it.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from localserver import dispatch
from travel_planner.actions import PlannerActions, PlannerRefusal
from travel_planner.owners import claim_unowned


class TripOwnershipTest(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.actions = PlannerActions(str(Path(self._directory.name) / "t.sqlite3"))

    def make(self, name: str, owner: str | None) -> str:
        trip = dispatch(
            self.actions,
            "create_trip",
            {"name": name, "destination": "Kyoto, Japan"},
            owner=owner,
        )
        return trip["trip_id"]

    def test_each_owner_sees_only_their_own(self):
        self.make("Mine", "tok_me")
        self.make("Theirs", "tok_you")
        self.assertEqual(["Mine"], [t["name"] for t in dispatch(self.actions, "list_trips", {}, owner="tok_me")])
        self.assertEqual(["Theirs"], [t["name"] for t in dispatch(self.actions, "list_trips", {}, owner="tok_you")])

    def test_reading_another_owners_trip_is_refused(self):
        theirs = self.make("Theirs", "tok_you")
        with self.assertRaises(PlannerRefusal) as caught:
            dispatch(self.actions, "journey", {"trip_id": theirs}, owner="tok_me")
        self.assertEqual("not_your_trip", caught.exception.code)

    def test_deleting_another_owners_trip_is_refused(self):
        # The damaging one. `delete_trip` only ever checked that the trip existed.
        theirs = self.make("Theirs", "tok_you")
        with self.assertRaises(PlannerRefusal) as caught:
            dispatch(self.actions, "delete_trip", {"trip_id": theirs}, owner="tok_me")
        self.assertEqual("not_your_trip", caught.exception.code)
        self.assertEqual(1, len(dispatch(self.actions, "list_trips", {}, owner="tok_you")))

    def test_an_owner_reaches_their_own_trip(self):
        mine = self.make("Mine", "tok_me")
        self.assertIn("stages", dispatch(self.actions, "journey", {"trip_id": mine}, owner="tok_me"))

    def test_trips_from_before_owners_are_claimed_by_the_first_lister(self):
        # These are the rows that existed before the column did. Whoever opens the
        # site first adopts them, which for a deployment is the person who deployed it.
        orphan = self.make("Older", None)
        self.assertIsNone(self.actions.store.trip_owner(orphan))
        listed = dispatch(self.actions, "list_trips", {}, owner="tok_me")
        self.assertEqual(["Older"], [t["name"] for t in listed])
        self.assertEqual("tok_me", self.actions.store.trip_owner(orphan))
        # And a second person does not inherit them.
        self.assertEqual([], dispatch(self.actions, "list_trips", {}, owner="tok_you"))
        self.assertEqual(0, claim_unowned(self.actions.store, "tok_you"))

    def test_no_owner_scopes_nothing(self):
        # The exporters, the gates and a local single-user run all call without one.
        self.make("Mine", "tok_me")
        self.make("Theirs", "tok_you")
        self.assertEqual(2, len(dispatch(self.actions, "list_trips", {})))


if __name__ == "__main__":
    unittest.main()
