# Local Markdown Wayfinder tracker

This repository has no configured issue tracker, so Wayfinder issues live here.

## Wayfinding operations

- There are two maps. [`map.md`](map.md) is the closed Phase 1 planning map (`WF-MAP-001`).
  [`map-002-splitter-merge-and-webapp.md`](map-002-splitter-merge-and-webapp.md) is the open Phase 2 map
  (`WF-MAP-002`) for merging the bill splitter and replacing Streamlit with a webapp.
- Each child issue is one file in [`tickets/`](tickets/), numbered continuously across maps. A ticket's
  `parent:` field says which map it belongs to.
- `status: open|closed` records issue state.
- `assignee:` is the claim. An open ticket with a blank assignee is unclaimed.
- `blocked_by:` records dependency ticket IDs because this tracker has no native dependency feature.
- The frontier is every open, unclaimed ticket whose `blocked_by` tickets are closed.
- Resolve a ticket by adding a dated `## Resolution comments` entry, setting `status: closed`, then adding one linked gist to the map's **Decisions so far** section.
- Human-facing references use ticket titles as links; IDs are metadata only.

Research agents edit only their assigned ticket. The ticket itself is the local context pointer; no research branch is required for this local-only tracker.
