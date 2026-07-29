"""Snapshot-in, bytes-out artifact writers for the active plan.

Outer adapters: they read one export snapshot from ``exports.build_export_snapshot``
and never call providers, SQLite, the optimizer, Streamlit, or a model.  They
invent no missing value; a missing required field raises a precise error.
"""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import re
from typing import Any
import unicodedata

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont
import xlsxwriter


POSTER_SIZE = (1080, 1920)  # 9:16
PICTOGRAPHS = re.compile(r"[\U0001F000-\U0001FAFF←-⯿️]")
POSTER_HIGHLIGHTS = 5
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
)

# Latin + Thai + local-script coverage is required; a personal machine may have
# any of these.  ponytail: env override first, so a missing system font is a
# configuration fix rather than a code change.
FONT_CANDIDATES = (
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Ayuthaya.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def fit_lines(
    text: str, font: Any, max_width: float, *, max_lines: int = 1
) -> list[str]:
    """Break text to fit max_width, ellipsizing once max_lines is reached.

    Pillow draws whatever it is given, so an unwrapped place name runs off the
    poster and is clipped.  Thai and Chinese names carry no word spaces, so this
    measures character by character and prefers a space break when one exists.
    """

    words = str(text or "")
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    index = 0
    while index < len(words):
        candidate = current + words[index]
        if font.getlength(candidate) <= max_width:
            current = candidate
            index += 1
            continue
        if not current:  # A single glyph wider than the box; take it anyway.
            current, index = words[index], index + 1
        elif len(lines) + 1 >= max_lines:
            remaining = words[index:].strip()
            if remaining:
                current = _ellipsize(current, font, max_width)
            lines.append(current)
            return lines
        else:
            cut = current.rfind(" ")
            if cut > 0:
                index -= len(current) - cut - 1
                current = current[:cut]
            else:
                # ponytail: character break. Thai needs a dictionary to break on
                # word boundaries; this only refuses to strand a combining mark
                # at the start of a line, which is the visibly broken case.
                while len(current) > 1 and unicodedata.combining(words[index]) != 0:
                    index -= 1
                    current = current[:-1]
        lines.append(current.strip() or current)
        current = ""
    if current.strip():
        lines.append(current.strip())
    return lines or [""]


def _ellipsize(text: str, font: Any, max_width: float) -> str:
    trimmed = text.rstrip()
    while trimmed and font.getlength(trimmed + "…") > max_width:
        trimmed = trimmed[:-1].rstrip()
    return (trimmed + "…") if trimmed else text


def resolve_font() -> Path:
    """Return a Unicode TTF able to draw the selected language and local names."""

    override = os.environ.get("TOURIST_EXPORT_FONT", "").strip()
    for candidate in (override, *FONT_CANDIDATES):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise ValueError(
        "No Unicode export font found; set TOURIST_EXPORT_FONT to a .ttf path"
    )


def day_poster_png(
    snapshot: dict[str, Any], date: str, labels: dict[str, str] | None = None
) -> bytes:
    """One 9:16 share poster for a single day: identity, highlights, load, risk."""

    words = _labels(labels)
    day = _day(snapshot, date)
    stamp = snapshot["stamp"]
    font_path = str(resolve_font())
    title_font = ImageFont.truetype(font_path, 64)
    heading_font = ImageFont.truetype(font_path, 44)
    body_font = ImageFont.truetype(font_path, 34)
    small_font = ImageFont.truetype(font_path, 28)

    image = Image.new("RGB", POSTER_SIZE, "#101820")
    draw = ImageDraw.Draw(image)
    margin = 72
    full_width = POSTER_SIZE[0] - margin * 2
    _draw_block(
        draw, (margin, 96), stamp["destination"], title_font, "#F2F5F7", full_width
    )
    _draw_block(
        draw,
        (margin, 184),
        f"{date} · {stamp['trip_name']}",
        heading_font,
        "#8FB8D8",
        full_width,
    )
    draw.line((margin, 268, POSTER_SIZE[0] - margin, 268), fill="#2A3B49", width=3)

    highlights = [item for item in day["items"] if item["type"] == "visit"][
        :POSTER_HIGHLIGHTS
    ]
    text_left = 150
    text_width = POSTER_SIZE[0] - text_left - margin
    top = 340
    for item in highlights:
        centre = top + 28
        draw.ellipse((78, centre - 18, 114, centre + 18), fill="#8FB8D8")
        draw.text(
            (88, centre - 16), str(item["stop_number"]), font=small_font, fill="#101820"
        )
        name_bottom = _draw_block(
            draw,
            (text_left, top),
            item["display_name"],
            heading_font,
            "#F2F5F7",
            text_width,
            max_lines=2,
            line_height=52,
        )
        detail = f"{item['start']}–{item['end']} · {item['duration_minutes']} {words['minutes']}"
        if item.get("local_name"):
            detail = f"{detail} · {item['local_name']}"
        bottom = _draw_block(
            draw, (text_left, name_bottom), detail, body_font, "#A9BECD", text_width
        )
        if item is not highlights[-1]:
            draw.line((96, centre + 24, 96, bottom + 20), fill="#2A3B49", width=4)
        top = bottom + 56

    totals = day["totals"]
    footer = POSTER_SIZE[1] - 400
    draw.line((margin, footer, POSTER_SIZE[0] - margin, footer), fill="#2A3B49", width=3)
    _draw_block(
        draw,
        (margin, footer + 36),
        f"{day['start']}–{day['end']} · {words['scheduled_visits']} "
        f"{totals['scheduled_visits']}",
        heading_font,
        "#F2F5F7",
        full_width,
    )
    _draw_block(
        draw,
        (margin, footer + 104),
        f"{words['walking_minutes']} {totals['walking_minutes']} {words['minutes']} · "
        f"{words['travel_minutes']} {totals['travel_minutes']} {words['minutes']}",
        body_font,
        "#A9BECD",
        full_width,
        max_lines=2,
        line_height=44,
    )
    if day["highest_risk"]:
        risk = words.get(
            f"state_{day['highest_risk']['status']}", day["highest_risk"]["status"]
        )
        _draw_block(
            draw,
            (margin, footer + 204),
            f"{words['highest_risk']}: {risk}",
            body_font,
            "#F2C14E",
            full_width,
        )
    _draw_block(
        draw,
        (margin, POSTER_SIZE[1] - 108),
        _stamp_line(snapshot),
        small_font,
        "#6C8598",
        full_width,
    )

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def plan_pdf(snapshot: dict[str, Any], labels: dict[str, str] | None = None) -> bytes:
    """Offline trip snapshot: cover, one section per day, choices, sources."""

    words = _labels(labels)
    stamp = snapshot["stamp"]
    pdf = FPDF(unit="mm", format="A4")
    font_path = str(resolve_font())
    pdf.add_font("body", "", font_path)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_font("body", size=10)
    pdf.set_title(f"{stamp['destination']} {stamp['plan_version_id']}")

    pdf.add_page()
    _pdf_heading(pdf, stamp["destination"], size=22)
    _pdf_line(pdf, f"{stamp['trip_name']} · {words.get(stamp['variant_id'], stamp['variant_id'])}")
    _pdf_line(
        pdf,
        f"{words['readiness']}: "
        f"{words.get(snapshot['readiness']['state'], snapshot['readiness']['state'])}",
    )
    _pdf_line(pdf, _stamp_line(snapshot))
    totals = snapshot["totals"]
    _pdf_line(
        pdf,
        f"{words['scheduled_visits']} {totals['scheduled_visits']} · "
        f"{words['visit_minutes']} {totals['visit_minutes']} · "
        f"{words['travel_minutes']} {totals['travel_minutes']} · "
        f"{words['walking_minutes']} {totals['walking_minutes']} "
        f"({words['rewarding_walking_minutes']} {totals['rewarding_walking_minutes']} / "
        f"{words['plain_walking_minutes']} {totals['plain_walking_minutes']})",
    )
    if snapshot["readiness"]["capability_gaps"]:
        _pdf_heading(pdf, words["capability_gaps"], size=13)
        for gap in snapshot["readiness"]["capability_gaps"]:
            _pdf_line(pdf, f"- {_code(words, gap)}")
    if snapshot["warnings"]:
        _pdf_heading(pdf, words["optimizer_warning"], size=13)
        for warning in snapshot["warnings"]:
            _pdf_line(pdf, f"- {_code(words, warning)}")

    for day in snapshot["days"]:
        pdf.add_page()
        _pdf_heading(pdf, day["date"], size=18)
        poster = BytesIO(day_poster_png(snapshot, day["date"], labels))
        pdf.image(poster, x=pdf.l_margin, w=58)
        pdf.ln(2)
        _pdf_heading(pdf, words["timeline"], size=13)
        for item in day["items"]:
            _pdf_line(pdf, _item_line(item, words))
        if day["fallbacks"]:
            _pdf_heading(pdf, words["fallback"], size=13)
            for fallback in day["fallbacks"]:
                _pdf_line(pdf, _fallback_line(fallback, words))
        if day["stops"]:
            _pdf_heading(pdf, words["tab_map"], size=13)
            anchor = snapshot["accommodation"]["anchor"]
            if anchor:
                _pdf_line(
                    pdf,
                    f"{words['hotel_anchor']} · {anchor['display_name']}"
                    f"{_coordinates(anchor)}",
                )
            for stop in day["stops"]:
                marker = (
                    f" · {words['state_locked']}"
                    if stop["status"] == "locked"
                    else ""
                )
                _pdf_line(
                    pdf,
                    f"{words['stop']} {stop['stop_number']} · {stop['display_name']}"
                    f"{_coordinates(stop)}{marker}",
                )

    if snapshot["unscheduled"]:
        pdf.add_page()
        _pdf_heading(pdf, words["unscheduled_choices"], size=18)
        for item in snapshot["unscheduled"]:
            _pdf_line(
                pdf,
                f"- {item['display_name']} · {_code(words, item['reason'])} · "
                f"{_code(words, item['consequence'])}",
            )

    pdf.add_page()
    _pdf_heading(pdf, words["checklist"], size=18)
    _pdf_line(pdf, words["checklist_pending"])
    _pdf_heading(pdf, words["sources"], size=18)
    if snapshot["sources"]:
        for source in snapshot["sources"]:
            _pdf_line(
                pdf,
                f"- {source['display_name']} · {source['fact_type']} · "
                f"{source['status']} · {source['source']}",
            )
    else:
        _pdf_line(pdf, words["no_sources"])
    return bytes(pdf.output())


def plan_workbook_xlsx(
    snapshot: dict[str, Any], labels: dict[str, str] | None = None
) -> bytes:
    """The six agreed sheets for the active plan only, with working formulas."""

    words = _labels(labels)
    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    header = workbook.add_format({"bold": True, "bg_color": "#E8EEF3", "border": 1})
    title = workbook.add_format({"bold": True, "font_size": 13})
    wrap = workbook.add_format({"text_wrap": True, "valign": "top"})

    sheets = {name: workbook.add_worksheet(name) for name in SHEETS}
    timeline_rows = _write_timeline(sheets["Timeline"], snapshot, header, wrap)
    _write_summary(sheets["Summary"], snapshot, workbook, header, title, timeline_rows)
    _write_choices(sheets["Choices & Backups"], snapshot, header, wrap)
    _write_checklist(sheets["Checklist"], words, header)
    _write_costs(sheets["Costs"], snapshot, words, header)
    _write_sources(sheets["Sources"], snapshot, header)
    workbook.close()
    return buffer.getvalue()


def _timeline_letter(name: str) -> str:
    """Column letter for a Timeline header, so Summary formulas follow the layout."""

    # ponytail: single-letter columns are enough for 26; extend if Timeline grows.
    return chr(ord("A") + [item[0] for item in TIMELINE_COLUMNS].index(name))


def _write_timeline(
    sheet: Any, snapshot: dict[str, Any], header: Any, wrap: Any
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
                    item.get("reason") or "",
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
        ("Exchange-rate snapshot", snapshot["costs"]["exchange_rate_snapshot"] or "none"),
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
        ("Date", "Visits", "At places (min)", "Travel (min)", "Walking (min)", "Buffers (min)")
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
            (3, "travel", totals["travel_minutes"]),
            (5, "buffer", totals["buffer_minutes"]),
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
            4,
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
        (3, "travel_minutes"),
        (4, "walking_minutes"),
        (5, "buffer_minutes"),
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
        for column, name in ((4, "Walking (min)"), (3, "Travel (min)")):
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


def _write_choices(sheet: Any, snapshot: dict[str, Any], header: Any, wrap: Any) -> None:
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
                item["reason"],
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
                fallback.get("trigger") or "",
                fallback.get("status") or "",
                fallback.get("primary_name") or "",
                fallback.get("replacement_name") or "",
                "yes" if fallback.get("day_reoptimized") else "",
                fallback.get("displaced_reason") or "",
                fallback.get("displaced_consequence") or "",
            ],
            wrap,
        )


def _write_checklist(sheet: Any, words: dict[str, str], header: Any) -> None:
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
    # ponytail: the readiness board is a separate slice; the agreed sheet and its
    # columns exist so the workbook contract stays stable when it lands.
    sheet.write(1, 0, words["checklist_pending"])


def _write_costs(
    sheet: Any, snapshot: dict[str, Any], words: dict[str, str], header: Any
) -> None:
    columns = (
        ("Original amount", 16),
        ("Original currency", 17),
        ("Estimate or actual", 18),
        ("Applied rate", 13),
        ("Rate date", 13),
        ("Converted THB", 15),
        ("Actual THB", 13),
        ("Category", 16),
        ("Payer / share", 16),
        ("Payment state", 15),
        ("Related plan item", 24),
    )
    for index, (name, width) in enumerate(columns):
        sheet.write(0, index, name, header)
        sheet.set_column(index, index, width)
    sheet.freeze_panes(1, 0)
    for row, item in enumerate(snapshot["costs"]["items"], start=1):
        sheet.write_row(row, 0, [item.get(key) or "" for key in (
            "original_amount",
            "original_currency",
            "estimate_or_actual",
            "applied_rate",
            "rate_date",
            "converted_thb",
            "actual_thb",
            "category",
            "payer_share",
            "payment_state",
            "related_item_id",
        )])
    if not snapshot["costs"]["items"]:
        sheet.write(1, 0, words["no_costs"])


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


def _day(snapshot: dict[str, Any], date: str) -> dict[str, Any]:
    day = next((item for item in snapshot["days"] if item["date"] == date), None)
    if day is None:
        raise ValueError(f"Plan has no day {date}")
    return day


def _item_line(item: dict[str, Any], words: dict[str, str]) -> str:
    clock = f"{item['start']}-{item['end']}"
    state = words.get(f"state_{item['status']}", item["status"])
    if item["type"] == "visit":
        line = (
            f"{clock}  [{words['stop']} {item['stop_number']}] {item['display_name']}"
            f"  ({item['duration_minutes']} {words['minutes']}) · {state}"
        )
        if item.get("local_name"):
            line = f"{line} · {item['local_name']}"
        if item.get("address"):
            line = f"{line} · {item['address']}"
        return line
    if item["type"] == "travel":
        return (
            f"{clock}  [{item.get('mode') or '?'}] {item['origin_name']} > "
            f"{item['destination_name']}  ({item['duration_minutes']} {words['minutes']}, "
            f"{words['walk_portion']} {item['walking_minutes']}) · {state}"
        )
    return f"{clock}  [{item.get('reason') or 'buffer'}] ({item['duration_minutes']} {words['minutes']})"


def _draw_block(
    draw: Any,
    xy: tuple[int, int],
    text: str,
    font: Any,
    fill: str,
    max_width: float,
    *,
    max_lines: int = 1,
    line_height: int | None = None,
) -> int:
    """Draw text inside max_width and return the y below the last line."""

    x, y = xy
    step = line_height or int(font.size * 1.2)
    lines = fit_lines(text, font, max_width, max_lines=max_lines)
    for offset, line in enumerate(lines):
        draw.text((x, y + offset * step), line, font=font, fill=fill)
    return y + len(lines) * step


def _code(words: dict[str, str], code: Any) -> str:
    """Localize an optimizer code the way the app does, or prettify it."""

    text = str(code or "")
    if not text:
        return ""
    return words.get(text) or text.replace("_", " ").capitalize()


def _coordinates(point: dict[str, Any]) -> str:
    if point.get("latitude") is None or point.get("longitude") is None:
        return ""
    return f" · {point['latitude']:.5f}, {point['longitude']:.5f}"


def _fallback_line(fallback: dict[str, Any], words: dict[str, str]) -> str:
    parts = [
        f"{words['fallback_trigger']}: {_code(words, fallback.get('trigger')) or '?'}",
        f"{fallback.get('primary_name')} > {fallback.get('replacement_name')}",
    ]
    if fallback.get("half_day"):
        parts.insert(0, words.get(fallback["half_day"], fallback["half_day"]))
    if fallback.get("day_reoptimized"):
        parts.append(words["day_reoptimized"])
    if fallback.get("displaced_consequence"):
        parts.append(_code(words, fallback["displaced_consequence"]))
    return "- " + " · ".join(parts)


def _stamp_line(snapshot: dict[str, Any]) -> str:
    stamp = snapshot["stamp"]
    return (
        f"{stamp['plan_version_id']} · {stamp['variant_id']} · {stamp['language']} · "
        f"{stamp['base_currency']} · {stamp['exported_at']}"
    )


def _pdf_heading(pdf: FPDF, text: str, *, size: int) -> None:
    pdf.set_font_size(size)
    pdf.multi_cell(0, size * 0.5, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font_size(10)
    pdf.ln(1)


def _pdf_line(pdf: FPDF, text: str) -> None:
    pdf.multi_cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")


def _labels(labels: dict[str, str] | None) -> dict[str, str]:
    """Merge caller labels over the defaults, minus glyphs no export font has.

    The app's status labels carry emoji for on-screen scanning; a PDF or poster
    font has no pictographs, so they would silently drop.  The wording alone
    still carries the state, which is what "colour is never the only signal"
    needs.
    """

    words = dict(DEFAULT_LABELS)
    words.update(labels or {})
    return {key: PICTOGRAPHS.sub("", value).strip() for key, value in words.items()}


# Export-only strings; the app passes its own TEXT[language] over these.
DEFAULT_LABELS = {
    "minutes": "min",
    "scheduled_visits": "Visits",
    "visit_minutes": "At places",
    "travel_minutes": "Travel",
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
}
