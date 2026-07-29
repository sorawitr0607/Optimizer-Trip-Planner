---
id: WF-013
title: Make reference workbook inspection available
status: closed
labels:
  - "wayfinder:task"
parent: WF-MAP-001
assignee: user-and-root
blocked_by: []
---

# Make reference workbook inspection available

## Question

Provide an approved way to inspect and render the four reference workbooks—through the required Codex spreadsheet runtime, a connected Excel session, or user-provided PDF/PNG exports—without modifying the source files, so their real structure and visual design can inform later decisions.

## Progress comments

### 2026-07-28 — Approved runtime paths checked

- The required Codex workspace spreadsheet dependency loader and `@oai/artifact-tool` runtime are not exposed in this session. Spreadsheet instructions prohibit guessing a package path, installing a substitute, or using an unrelated system spreadsheet library.
- The connected-document service reports no active Excel session.
- The four source workbooks remain untouched. Inspection can continue as soon as the user either connects an Excel workbook session or places PDF/PNG exports of every relevant sheet in the `Data` folder.
- The claim is released while awaiting one of those approved inputs.

### 2026-07-28 — PDF inspection path verified

- The user added timetable PDFs for Japan, Fukuoka, Kunming, and Shanghai. The originals and `.xlsx` sources were not modified.
- A read-only native macOS PDF path rendered all pages at inspection resolution: Japan two pages, Fukuoka one, Kunming two, and Shanghai one. All six rendered pages received a visual pass.
- The usable pages expose the actual day/date headers, row color coding, time/activity/transport/from/to/note fields, hyperlinks, image panels, and Fukuoka map reference needed by the workbook-inspection ticket.
- The visual pass also exposes print defects that later output must avoid: all-trip pages shrink text heavily, Japan's second page contains only stray video links, and Kunming's second page contains only two overflow rows.
- The approved PDF path now supports downstream structure and design analysis even though the managed workbook runtime and connected Excel session remain unavailable.

## Resolution summary

Reference workbook inspection is available through user-exported PDFs plus native read-only page rendering. Downstream work can inspect the real visual structure and compare it with the user's reported failures while keeping all four source workbooks unchanged.
