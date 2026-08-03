"""Snapshot-in, bytes-out artifact writers for the active plan.

Outer adapters: they read one export snapshot from ``exports.build_export_snapshot``
and never call providers, SQLite, the optimizer, Streamlit, or a model.  They
invent no missing value; a missing required field raises a precise error.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import cache
from io import BytesIO
from pathlib import Path
import re
from typing import Any
import unicodedata

import xlsxwriter

from .checklist import display_consequence, display_title


PICTOGRAPHS = re.compile(r"[\U0001F000-\U0001FAFF←-⯿️]")
CHECKLIST_TIMING = (
    "do_now",
    "30_days_before",
    "7_days_before",
    "24_hours_before",
    "departure_arrival_day",
)
SHEETS = ("Summary", "Timeline", "Choices & Backups", "Checklist", "Costs", "Sources")
TIMELINE_COLUMNS = (
    ("Date", 12),
    ("Order", 7),
    ("Start", 8),
    ("End", 8),
    ("Type", 9),
    ("Stop", 6),
    ("Name", 30),
    ("Name (EN)", 26),
    ("Name (TH)", 26),
    ("Local name", 24),
    ("Duration (min)", 14),
    ("Status", 20),
    ("Kind / mode", 14),
    ("Walking (min)", 14),
    ("Distance (m)", 13),
    ("Transfers", 10),
    ("Boarding buffer (min)", 20),
    ("Sightseeing walk", 16),
    ("Priority", 12),
    ("Opening verified", 16),
    ("Address", 34),
    ("Reason", 22),
    ("From", 30),
    ("To", 30),
    ("Operational notes", 52),
    ("Confirm / assumption", 24),
)

# Latin + Thai + local-script coverage is required; a personal machine may have
# any of these.  ponytail: env override first, so a missing system font is a
# configuration fix rather than a code change.
TOKEN_FILE = Path(__file__).resolve().parents[1] / "tokens.css"


@cache
def _light_tokens() -> dict[str, str]:
    match = re.search(r":root\s*\{(?P<body>.*?)\}", TOKEN_FILE.read_text(encoding="utf-8"), re.S)
    if match is None:
        raise RuntimeError("tokens.css has no :root token block")
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", match.group("body")))


def _design_token(name: str) -> str:
    tokens = _light_tokens()
    value = tokens[name].strip()
    seen = {name}
    while reference := re.fullmatch(r"var\((--[\w-]+)\)", value):
        name = reference.group(1)
        if name in seen:
            raise RuntimeError(f"Circular design token: {name}")
        seen.add(name)
        value = tokens[name].strip()
    return value


def checklist_ics(
    snapshot: dict[str, Any], labels: dict[str, str] | None = None
) -> bytes:
    """All-day calendar entries for every dated readiness task.

    All-day VEVENTs rather than VTODOs: every calendar app shows them, while
    VTODO support is uneven.
    """

    words = _labels(labels)
    stamp = snapshot["stamp"]
    when = "".join(char for char in str(stamp["exported_at"])[:19] if char.isdigit())
    dtstamp = f"{when[:8]}T{when[8:14]}Z" if len(when) >= 14 else f"{when[:8]}T000000Z"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Optimizer Trip Planner//Readiness//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    dated = [
        item for item in snapshot["checklist"]["items"] if item.get("due_date")
    ]
    for index, item in enumerate(dated):
        due = str(item["due_date"]).replace("-", "")
        end = (
            date.fromisoformat(str(item["due_date"])) + timedelta(days=1)
        ).strftime("%Y%m%d")
        # Real newlines: _ics_text escapes them, and calendars show separate lines.
        description = "\n".join(
            part
            for part in (
                f"{words['requirement_level']}: "
                f"{words.get(item['requirement_level'], item['requirement_level'])}",
                f"{words['progress']}: "
                f"{words.get('progress_' + str(item['progress']), item['progress'])}",
                f"{words['evidence']}: "
                f"{words.get('evidence_' + str(item['evidence_state']), item['evidence_state'])}",
                f"{words['consequence']}: {display_consequence(item, words)}"
                if item.get("consequence")
                else "",
                item.get("source_url") or "",
            )
            if part
        )
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{stamp['trip_id']}-{item.get('item_id') or index}@optimizer-trip-planner",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{due}",
                f"DTEND;VALUE=DATE:{end}",
                f"SUMMARY:{_ics_text(display_title(item, words))}",
                f"DESCRIPTION:{_ics_text(description)}",
                f"CATEGORIES:{_ics_text(str(item.get('category') or ''))}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(line) for line in lines).encode("utf-8") + b"\r\n"


def _ics_text(value: str) -> str:
    """Escape per RFC 5545; an unescaped comma silently truncates a field."""

    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _ics_fold(line: str) -> str:
    """Fold to 75 octets; a long unfolded line makes some importers reject the file."""

    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        limit = 75 if not chunks else 74
        if len(current) + len(encoded) > limit:
            chunks.append(current)
            current = b""
        current += encoded
    chunks.append(current)
    return "\r\n ".join(chunk.decode("utf-8") for chunk in chunks)


def plan_workbook_xlsx(
    snapshot: dict[str, Any], labels: dict[str, str] | None = None
) -> bytes:
    """The six agreed sheets for the active plan only, with working formulas."""

    words = _labels(labels)
    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    header = workbook.add_format(
        {"bold": True, "bg_color": _design_token("--export-header-bg"), "border": 1}
    )
    title = workbook.add_format({"bold": True, "font_size": 13})
    wrap = workbook.add_format({"text_wrap": True, "valign": "top"})

    sheets = {name: workbook.add_worksheet(name) for name in SHEETS}
    timeline_rows = _write_timeline(sheets["Timeline"], snapshot, words, header, wrap)
    _write_summary(sheets["Summary"], snapshot, workbook, header, title, timeline_rows)
    _write_choices(sheets["Choices & Backups"], snapshot, words, header, wrap)
    _write_checklist(sheets["Checklist"], snapshot, words, header, wrap)
    _write_costs(sheets["Costs"], snapshot, words, header)
    _write_sources(sheets["Sources"], snapshot, header)
    workbook.close()
    return buffer.getvalue()


def _timeline_letter(name: str) -> str:
    """Column letter for a Timeline header, so Summary formulas follow the layout."""

    # ponytail: single-letter columns are enough for 26; extend if Timeline grows.
    return chr(ord("A") + [item[0] for item in TIMELINE_COLUMNS].index(name))


def _write_timeline(
    sheet: Any,
    snapshot: dict[str, Any],
    words: dict[str, str],
    header: Any,
    wrap: Any,
) -> int:
    columns = TIMELINE_COLUMNS
    for index, (name, width) in enumerate(columns):
        sheet.write(0, index, name, header)
        sheet.set_column(index, index, width)
    sheet.freeze_panes(1, 0)

    row = 0
    for day in snapshot["days"]:
        for item in day["items"]:
            row += 1
            sheet.write_row(
                row,
                0,
                [
                    item["date"],
                    item["order"],
                    item["start"],
                    item["end"],
                    item["type"],
                    item.get("stop_number", ""),
                    item.get("display_name", ""),
                    item.get("names", {}).get("en", ""),
                    item.get("names", {}).get("th", ""),
                    item.get("local_name") or "",
                    item["duration_minutes"],
                    item["status"],
                    item.get("kind") or item.get("mode") or "",
                    item.get("walking_minutes", 0),
                    item.get("distance_m") if item.get("distance_m") is not None else "",
                    item.get("transfers") if item.get("transfers") is not None else "",
                    item.get("boarding_buffer_minutes", 0),
                    "yes" if item.get("sightseeing_walk") else "",
                    item.get("priority") or "",
                    "yes" if item.get("opening_verified") else "",
                    item.get("address") or "",
                    _code(words, item.get("reason")),
                    item.get("from_name") or item.get("origin_name") or "",
                    item.get("to_name") or item.get("destination_name") or "",
                    item.get("notes") or "",
                    _code(words, item.get("reason")),
                ],
                wrap,
            )
    if row:
        sheet.autofilter(0, 0, row, len(columns) - 1)
    return row


def _write_summary(
    sheet: Any,
    snapshot: dict[str, Any],
    workbook: Any,
    header: Any,
    title: Any,
    timeline_rows: int,
) -> None:
    stamp = snapshot["stamp"]
    sheet.set_column(0, 0, 26)
    sheet.set_column(1, 6, 18)
    sheet.write(0, 0, stamp["destination"], title)
    facts = (
        ("Trip", stamp["trip_name"]),
        ("Plan version", stamp["plan_version_id"]),
        ("Variant", stamp["variant_id"]),
        ("Variant status", stamp["variant_status"]),
        ("Active plan", "yes" if stamp["is_active_plan"] else "no"),
        ("Readiness", snapshot["readiness"]["state"]),
        ("Optimizer", stamp["optimizer_version"]),
        ("Input sha256", stamp["input_sha256"]),
        ("Language", stamp["language"]),
        ("Base currency", stamp["base_currency"]),
        (
            "Exchange-rate snapshot",
            _rate_summary(snapshot["costs"]["exchange_rate_snapshot"]),
        ),
        ("Estimated THB", (snapshot["costs"].get("totals") or {}).get("estimated_thb", 0)),
        ("Paid THB", (snapshot["costs"].get("totals") or {}).get("paid_thb", 0)),
        ("Exported at", stamp["exported_at"]),
        ("Timezone", stamp["timezone"] or "unverified"),
        ("Discovery status", stamp["discovery_status"]),
        ("Evidence gaps", ", ".join(stamp["capability_gaps"]) or "none"),
    )
    for offset, (name, value) in enumerate(facts, start=2):
        sheet.write(offset, 0, name, header)
        sheet.write(offset, 1, value)

    start = len(facts) + 4
    for index, name in enumerate(
        (
            "Date",
            "Visits",
            "At places (min)",
            "Meals (min)",
            "Travel (min)",
            "Walking (min)",
            "Logistics (min)",
            "Preparation (min)",
            "Buffers (min)",
        )
    ):
        sheet.write(start, index, name, header)
    # Formula-driven so a reader can audit the totals against the Timeline sheet.
    last_row = timeline_rows + 1
    dates = f"Timeline!${_timeline_letter('Date')}$2:${_timeline_letter('Date')}${last_row}"
    kinds = f"Timeline!${_timeline_letter('Type')}$2:${_timeline_letter('Type')}${last_row}"
    duration = (
        f"Timeline!${_timeline_letter('Duration (min)')}$2:"
        f"${_timeline_letter('Duration (min)')}${last_row}"
    )
    walking = (
        f"Timeline!${_timeline_letter('Walking (min)')}$2:"
        f"${_timeline_letter('Walking (min)')}${last_row}"
    )
    for offset, day in enumerate(snapshot["days"], start=1):
        row = start + offset
        totals = day["totals"]
        sheet.write(row, 0, day["date"])
        sheet.write_formula(
            row,
            1,
            f'=COUNTIFS({dates},$A{row + 1},{kinds},"visit")',
            None,
            totals["scheduled_visits"],
        )
        for column, kind, value in (
            (2, "visit", totals["visit_minutes"]),
            (3, "meal", totals["meal_minutes"]),
            (4, "travel", totals["travel_minutes"]),
            (6, "logistics", totals["logistics_minutes"]),
            (7, "preparation", totals["preparation_minutes"]),
            (8, "buffer", totals["buffer_minutes"]),
        ):
            sheet.write_formula(
                row,
                column,
                f'=SUMIFS({duration},{dates},$A{row + 1},{kinds},"{kind}")',
                None,
                value,
            )
        sheet.write_formula(
            row,
            5,
            f"=SUMIFS({walking},{dates},$A{row + 1})",
            None,
            totals["walking_minutes"],
        )

    last = start + len(snapshot["days"])
    total_row = last + 1
    sheet.write(total_row, 0, "Trip total", header)
    for column, key in (
        (1, "scheduled_visits"),
        (2, "visit_minutes"),
        (3, "meal_minutes"),
        (4, "travel_minutes"),
        (5, "walking_minutes"),
        (6, "logistics_minutes"),
        (7, "preparation_minutes"),
        (8, "buffer_minutes"),
    ):
        letter = chr(ord("A") + column)
        sheet.write_formula(
            total_row,
            column,
            f"=SUM({letter}{start + 2}:{letter}{last + 1})",
            None,
            snapshot["totals"][key],
        )

    if snapshot["days"]:
        chart = workbook.add_chart({"type": "column"})
        for column, name in ((5, "Walking (min)"), (4, "Travel (min)")):
            chart.add_series(
                {
                    "name": name,
                    "categories": ["Summary", start + 1, 0, last, 0],
                    "values": ["Summary", start + 1, column, last, column],
                }
            )
        chart.set_title({"name": "Daily walking and travel load"})
        chart.set_size({"width": 640, "height": 320})
        sheet.insert_chart(total_row + 2, 0, chart)


def _write_choices(
    sheet: Any,
    snapshot: dict[str, Any],
    words: dict[str, str],
    header: Any,
    wrap: Any,
) -> None:
    columns = (
        ("Place", 30),
        ("Choice", 12),
        ("Feasibility", 20),
        ("Reason", 26),
        ("Consequence", 30),
        ("Smallest alternative", 30),
        ("Owner acceptance required", 24),
    )
    for index, (name, width) in enumerate(columns):
        sheet.write(0, index, name, header)
        sheet.set_column(index, index, width)
    sheet.freeze_panes(1, 0)
    for row, item in enumerate(snapshot["reconciliation"], start=1):
        sheet.write_row(
            row,
            0,
            [
                item["display_name"],
                item["priority"],
                item["status"],
                _code(words, item["reason"]),
                item["consequence"],
                item["smallest_alternative"],
                "yes" if item["owner_acceptance_required"] else "",
            ],
            wrap,
        )
    if snapshot["reconciliation"]:
        sheet.autofilter(0, 0, len(snapshot["reconciliation"]), len(columns) - 1)

    offset = len(snapshot["reconciliation"]) + 3
    sheet.write(offset, 0, "Linked fallbacks", header)
    fallback_columns = (
        "Date",
        "Half-day",
        "Trigger",
        "Status",
        "Replaced place",
        "Replacement",
        "Day re-optimized",
        "Displaced reason",
        "Displaced consequence",
    )
    for index, name in enumerate(fallback_columns):
        sheet.write(offset + 1, index, name, header)
    for row, fallback in enumerate(snapshot["fallbacks"], start=offset + 2):
        sheet.write_row(
            row,
            0,
            [
                fallback.get("date") or "",
                fallback.get("half_day") or "",
                _code(words, fallback.get("trigger")),
                fallback.get("status") or "",
                fallback.get("primary_name") or "",
                fallback.get("replacement_name") or "",
                "yes" if fallback.get("day_reoptimized") else "",
                fallback.get("displaced_reason") or "",
                fallback.get("displaced_consequence") or "",
            ],
            wrap,
        )


def _write_checklist(
    sheet: Any, snapshot: dict[str, Any], words: dict[str, str], header: Any, wrap: Any
) -> None:
    columns = (
        ("Title", 34),
        ("Category", 16),
        ("Requirement level", 18),
        ("Progress", 12),
        ("Owner", 14),
        ("Applies to", 18),
        ("Due date / milestone", 20),
        ("Related plan component", 24),
        ("Consequence if skipped", 30),
        ("Source URL", 30),
        ("Authority type", 18),
        ("Evidence state", 16),
        ("Last checked", 20),
        ("Note", 24),
    )
    for index, (name, width) in enumerate(columns):
        sheet.write(0, index, name, header)
        sheet.set_column(index, index, width)
    sheet.freeze_panes(1, 0)

    board = snapshot["checklist"]
    rows = board["items"] + board["dismissed"]
    if not rows:
        sheet.write(1, 0, words["checklist_pending"])
        return
    for row, item in enumerate(rows, start=1):
        sheet.write_row(
            row,
            0,
            [
                display_title(item, words) or "",
                item["category"] or "",
                item["requirement_level"] or "",
                item["progress"] or "",
                item["owner"] or "",
                ", ".join(item["applies_to"]),
                item["due_date"] or (item["timing"] or ""),
                item["related_component"] or "",
                display_consequence(item, words) or "",
                item["source_url"] or "",
                item["authority_type"] or (item["expected_authority"] or ""),
                item["evidence_state"] or "",
                item["last_checked_at"] or "",
                item["note"] or ("dismissed" if item["dismissed"] else ""),
            ],
            wrap,
        )
    sheet.autofilter(0, 0, len(rows), len(columns) - 1)


def _write_costs(
    sheet: Any, snapshot: dict[str, Any], words: dict[str, str], header: Any
) -> None:
    columns = (
        ("Cost", 30),
        ("Original amount", 16),
        ("Original currency", 17),
        ("Payment state", 15),
        ("Applied rate", 13),
        ("Rate date", 13),
        ("Converted THB", 15),
        ("Actual THB", 13),
        ("Reported THB", 14),
        ("Category", 16),
        ("Payer / share", 16),
        ("Related plan item", 24),
        ("Note", 24),
    )
    for index, (name, width) in enumerate(columns):
        sheet.write(0, index, name, header)
        sheet.set_column(index, index, width)
    sheet.freeze_panes(1, 0)
    board = snapshot["costs"]
    for row, item in enumerate(board["items"], start=1):
        share = " / ".join(
            str(part) for part in (item.get("payer"), item.get("share")) if part
        )
        sheet.write_row(
            row,
            0,
            [
                item.get("label") or "",
                item.get("original_amount") if item.get("original_amount") is not None else "",
                item.get("original_currency") or "",
                item.get("payment_state") or "",
                item.get("applied_rate") if item.get("applied_rate") is not None else "",
                item.get("applied_rate_date") or "",
                item.get("converted_thb") if item.get("converted_thb") is not None else "",
                item.get("actual_thb") if item.get("actual_thb") is not None else "",
                item.get("reported_thb") if item.get("reported_thb") is not None else "",
                item.get("category") or "",
                share,
                item.get("related_item_id") or "",
                item.get("note") or ("rate missing" if item.get("rate_missing") else ""),
            ],
        )
    if not board["items"]:
        sheet.write(1, 0, words["no_costs"])
        return
    totals = board.get("totals") or {}
    offset = len(board["items"]) + 2
    for index, (name, value) in enumerate(
        (
            ("Estimated THB", totals.get("estimated_thb")),
            ("Paid THB", totals.get("paid_thb")),
            ("Total THB", totals.get("total_thb")),
            ("Rows without a rate", totals.get("unconvertible_rows")),
        )
    ):
        sheet.write(offset + index, 0, name, header)
        sheet.write(offset + index, 1, value if value is not None else "")
    sheet.autofilter(0, 0, len(board["items"]), len(columns) - 1)


def _write_sources(sheet: Any, snapshot: dict[str, Any], header: Any) -> None:
    columns = (
        ("Subject", 30),
        ("Governed field", 20),
        ("Status", 14),
        ("Provider / source", 24),
        ("Subject ID", 24),
    )
    for index, (name, width) in enumerate(columns):
        sheet.write(0, index, name, header)
        sheet.set_column(index, index, width)
    sheet.freeze_panes(1, 0)
    for row, source in enumerate(snapshot["sources"], start=1):
        sheet.write_row(
            row,
            0,
            [
                source["display_name"],
                source["fact_type"],
                source["status"],
                source["source"],
                source["subject_id"],
            ],
        )
    if snapshot["sources"]:
        sheet.autofilter(0, 0, len(snapshot["sources"]), len(columns) - 1)


def _code(words: dict[str, str], code: Any) -> str:
    """Localize an optimizer code, visibly marking a missing catalogue entry."""

    text = str(code or "")
    if not text:
        return ""
    return words.get(text) or f"⚠ {text}"


def _rate_summary(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return "none"
    rates = ", ".join(
        f"{code} {rate}" for code, rate in (snapshot.get("rates") or {}).items()
        if code != "THB"
    )
    buffer_percent = snapshot.get("buffer_percent") or 0
    return " · ".join(
        part
        for part in (
            snapshot.get("as_of"),
            snapshot.get("source"),
            rates,
            f"+{buffer_percent}% buffer" if buffer_percent else "",
        )
        if part
    )


def _labels(labels: dict[str, str] | None) -> dict[str, str]:
    """Merge caller labels over the defaults, minus glyphs no export font has.

    The app's status labels may carry emoji for scanning. The wording alone
    still carries the state, which is what "colour is never the only signal"
    needs in the workbook.
    """

    words = dict(DEFAULT_LABELS)
    words.update(labels or {})
    return {key: PICTOGRAPHS.sub("", value).strip() for key, value in words.items()}


# Export-only strings; the app passes its own TEXT[language] over these.
DEFAULT_LABELS = {
    "rain": "Rain",
    "minutes": "min",
    "scheduled_visits": "Visits",
    "visit_minutes": "At places",
    "travel_minutes": "Travel",
    "meal_minutes": "Meals",
    "preparation_minutes": "Preparation",
    "logistics_minutes": "Airport / hotel logistics",
    "walking_minutes": "Walking",
    "plain_walking_minutes": "Plain walking",
    "rewarding_walking_minutes": "Rewarding walking",
    "buffer_minutes": "Buffers",
    "readiness": "Readiness",
    "highest_risk": "Highest risk",
    "timeline": "Timeline",
    "tab_map": "Day overview",
    "stop": "Stop",
    "walk_portion": "walking",
    "capability_gaps": "Evidence still missing",
    "optimizer_warning": "Warnings",
    "unscheduled_choices": "Selected but not scheduled",
    "checklist": "Trip readiness checklist",
    "checklist_pending": "The readiness checklist is not generated yet.",
    "sources": "Evidence and sources",
    "no_sources": "No governed fact reached this plan.",
    "no_costs": "No cost evidence is available yet.",
    "fallback": "Fallback for this half-day",
    "fallback_trigger": "Trigger",
    "day_reoptimized": "day re-optimized",
    "hotel_anchor": "Hotel area",
    "morning": "Morning",
    "afternoon": "Afternoon",
    "state_locked": "Locked",
    "consequence": "If skipped",
    "today_tasks": "Needed today",
    "open_tasks": "open",
    "overdue": "overdue",
    "due": "due",
    "requirement_level": "Requirement",
    "progress": "Progress",
    "evidence": "Evidence",
    "dismissed_history": "Dismissed history",
    "ready": "Ready",
    "action_needed": "Action needed",
    "verification_needed": "Verification needed",
}
