"""Local Streamlit entry point for the personal travel planner."""

from __future__ import annotations

from datetime import date, time
import os
from urllib.parse import quote

import streamlit as st

from travel_planner import PlannerActions
from travel_planner.costs import (
    CATEGORIES as COST_CATEGORIES,
    PAYMENT_STATES as COST_STATES,
)
from travel_planner.checklist import (
    display_consequence,
    display_title,
    AUTHORITY_TYPES as CHECKLIST_AUTHORITIES,
    CATEGORIES as CHECKLIST_CATEGORIES,
    PROGRESS_STATES as CHECKLIST_PROGRESS,
    REQUIREMENT_LEVELS as CHECKLIST_LEVELS,
    TIMING_BUCKETS as CHECKLIST_TIMING,
)
from travel_planner.exporters import (
    checklist_ics,
    day_poster_png,
    plan_pdf,
    plan_workbook_xlsx,
)
from travel_planner.exports import half_day
from travel_planner.setup import (
    ALSO_ENJOY_TAGS,
    AVOID_TAGS,
    COMFORT_TAGS,
    MAIN_STYLE_TAGS,
)


TEXT = {
    "en": {
        "title": "Personal Travel Planner",
        "caption": "Local POC · your structured trip data stays on this computer",
        "new_trip": "Start a trip",
        "trip_name": "Trip name (optional)",
        "destination": "Destination",
        "mode": "Planning mode",
        "explore_first": "Explore first",
        "ready_to_schedule": "Ready to schedule",
        "create": "Create trip",
        "created": "Trip saved.",
        "destination_required": "Destination is required.",
        "saved_trips": "Saved trips",
        "resume": "Resume trip",
        "status": "Status",
        "draft": "Draft",
        "mode_label": "Mode",
        "active_plan": "Active plan version",
        "no_plan": "No itinerary has been generated. This screen only prepares and discovers places.",
        "empty": "Create your first trip to begin.",
        "setup": "Trip setup",
        "setup_help": "Save a draft anytime. Confirm before the app makes a discovery request.",
        "trip_basics": "1 · Trip basics",
        "dates_known": "Travel dates known",
        "start_date": "Start date",
        "end_date": "End date",
        "arrival_known": "Approximate arrival time known",
        "arrival_time": "Arrival time",
        "departure_known": "Approximate departure time known",
        "departure_time": "Departure time",
        "accommodation": "Accommodation",
        "owner_style": "2 · Owner trip style",
        "owner_age": "Owner age (0 = not set)",
        "main_style": "Main style · choose at least one",
        "also_enjoy": "Also enjoy",
        "avoid": "Avoid",
        "comfort": "Comfort preferences",
        "description": "Extra detail or nuance (optional)",
        "travellers": "3 · Travellers",
        "member_count": "Additional travellers",
        "member": "Traveller",
        "member_name": "Nickname / label",
        "member_age": "Age (0 = not set)",
        "member_tags": "Optional preference tags",
        "member_notes": "Optional notes",
        "member_must": "Must respect · one confirmed need per line",
        "requirements": "4 · Must respect",
        "owner_must": "Only genuine non-negotiables · one per line (optional)",
        "save_draft": "Save draft",
        "confirm": "Confirm setup",
        "draft_saved": "Draft setup saved locally. No provider was called.",
        "confirmed": "Setup confirmed. Discovery is now available.",
        "main_required": "Choose at least one Main style before confirmation.",
        "review": "5 · Review",
        "setup_state": "Setup state",
        "draft_setup": "Draft setup",
        "confirmed_setup": "Confirmed for discovery",
        "people": "People",
        "preferences": "Owner tags",
        "no_dates": "Dates are still optional; results cannot be treated as a dated timetable.",
        "discover_title": "Broad attraction discovery",
        "discover_help": "Runs only when you click. It uses a bounded worldwide OpenStreetMap baseline, cached for 7 days. Results are broad, not exhaustive.",
        "discover": "Discover attractions",
        "refresh": "Refresh provider data",
        "discovering": "Collecting the broad baseline…",
        "discovery_saved": "Discovery result saved.",
        "coverage": "Coverage report",
        "provider_status": "Provider status",
        "candidates": "Candidates",
        "duplicates": "Merged duplicates",
        "cells": "Geographic cells",
        "unranked": "Baseline only: preferences have not ranked or filtered these candidates.",
        "stale_setup": "This result belongs to an older setup. It remains visible, but confirm and discover again before ranking.",
        "provider_gap": "The provider could not return a current catalog. Your setup is safe; the evidence gap is shown below.",
        "no_candidates": "No usable candidates were returned. Check the coverage gaps and retry later.",
        "name": "Name",
        "local_name": "Local name",
        "category": "Category",
        "opening": "Opening evidence",
        "source": "Source",
        "details": "Full normalized coverage details",
        "osm_notice": "OpenStreetMap public services are for low-volume, user-triggered personal use; this app identifies itself, caches identical requests, and does not run autocomplete.",
        "ranking_title": "Personalized place cards",
        "ranking_help": "The score orders cards; it is not a guarantee. Missing route, crowd, rating, holiday-hour, and best-time evidence stays visible and neutral.",
        "ranking_wait": "Confirm the current setup and complete discovery before ranking.",
        "lane": "Card lane",
        "main_queue": "For your trip",
        "city_icons": "City Icons",
        "worth_it_if": "Worth It If…",
        "local_alternatives": "Local Alternatives",
        "browse_all": "Browse All",
        "select_card": "Choose a card",
        "no_lane_cards": "No cards currently qualify for this lane.",
        "score": "Score",
        "duration": "Visit estimate",
        "minutes": "min",
        "planner_estimate": "Planner category estimate; not venue-confirmed",
        "feasibility": "Feasibility",
        "not_evaluated": "Not evaluated until optimizer",
        "why": "Why shown",
        "pros": "Pros",
        "cons": "Cons / evidence gaps",
        "breakdown": "30/20/20/10/15/5 score breakdown",
        "dimension": "Dimension",
        "points": "Points",
        "maximum": "Maximum",
        "deductions": "Named deductions",
        "no_deductions": "No evidence-backed deduction",
        "matched_tags": "Matched tags",
        "group_weights": "Group weights and learned signals",
        "choice": "Your choice",
        "must_do": "Must do",
        "interested": "Interested",
        "maybe": "Maybe",
        "not_for_trip": "Not for trip",
        "rejection_reason": "Optional reason for Not for trip",
        "no_reason": "No reason",
        "choice_saved": "Choice saved. Unseen cards were reordered; Browse All still retains everything.",
        "current_choice": "Current choice",
        "clear_choice": "Clear choice",
        "choice_cleared": "Choice cleared.",
        "exploration_card": "Protected exploration card",
        "icon_card": "Prominent landmark evidence",
        "source_rating": "Source rating",
        "not_enriched": "Not enriched yet",
        "route_effort": "Route / walking effort",
        "not_routed": "Not routed yet",
        "browse_notice": "Every current canonical candidate is retained here, including rated and low-scoring places.",
        "reconciliation": "Selected-place reconciliation",
        "reconciliation_help": "Nothing selected disappears. These card choices remain pending until you run the whole-trip optimizer below.",
        "no_selected": "No Must do or Interested places yet.",
        "pending_optimizer": "Pending optimizer",
        "present_latest": "In latest discovery",
        "next_step": "Next step",
        "run_optimizer": "Run whole-trip optimizer below",
        "all_choices": "All saved choices",
        "formula_note": "Neutral partial points mean evidence is missing—not that the place is average in reality.",
        "photo_source": "Open-data photo reference",
        "photo_unavailable": "No permitted photo reference is available yet.",
        "optimizer_title": "Whole-trip optimizer",
        "optimizer_help": "Uses all selected places across all dates. It may swap days or order, but it cannot invent routes, opening hours, access, or locks.",
        "generate_plan": "Generate / refresh three variants",
        "optimizing": "Optimizing the complete trip…",
        "preview_saved": "Plan preview saved locally.",
        "choose_before_plan": "Choose at least one Must do, Interested, or Maybe place first.",
        "stay_recommendation": "Dates are not fixed yet — compare suggested stay lengths",
        "stay_option": "Stay style",
        "days": "Days",
        "daily_capacity": "Planned daily capacity",
        "variant": "Plan variant",
        "best_balance": "Best balance",
        "relaxed": "Relaxed",
        "more_highlights": "More highlights",
        "ready": "Ready",
        "provisional": "Provisional / needs acceptance",
        "unavailable": "Unavailable",
        "scheduled_visits": "Visits",
        "travel_minutes": "Travel",
        "walking_minutes": "Walking",
        "plain_walking_minutes": "Plain walking",
        "buffer_minutes": "Buffers",
        "optimizer_warning": "Warnings and evidence gaps",
        "optimizer_reconciliation": "Final selected-place reconciliation",
        "fits": "Fits",
        "fits_with_tradeoff": "Fits with tradeoff",
        "cannot_currently_fit": "Cannot currently fit",
        "reason": "Reason",
        "consequence": "Consequence / smallest next step",
        "timeline": "Validated timeline",
        "item_type": "Type",
        "start": "Start",
        "end": "End",
        "place_or_leg": "Place / leg",
        "activate_plan": "Use this as active plan",
        "plan_activated": "Validated plan activated.",
        "activation_disabled": "Only a fully validated Ready variant can become active.",
        "no_schedule": "No selected visit can be scheduled safely with the current evidence.",
        "greedy_check": "Whole-trip result equals or improves the day-greedy baseline",
        "optimizer_limit": "Optimization stopped at its safe limit; only the validated incumbent is shown.",
        "use_title": "Active plan",
        "use_help": "One export snapshot feeds this view; posters, PDF, and Excel will read the same numbers.",
        "no_active_plan": "No plan is active yet. Activate a validated variant above.",
        "superseded_plan": "This is an older plan version. The active plan has moved on.",
        "exported_at": "Snapshot built",
        "readiness": "Readiness",
        "action_needed": "Action needed",
        "verification_needed": "Verification needed",
        "state_confirmed": "✅ Confirmed",
        "state_recheck": "🕒 Recheck",
        "state_tradeoff_accepted": "⚖️ Tradeoff accepted",
        "state_unverified_conflict": "⚠️ Unverified / conflict",
        "state_locked": "🔒 Locked",
        "highest_risk": "Highest risk today",
        "tab_map": "Map",
        "visit_minutes": "At places",
        "rewarding_walking_minutes": "Rewarding walking",
        "stop": "Stop",
        "travel_mode": "Mode",
        "walk_portion": "Walking portion",
        "distance": "Distance",
        "transfers": "Transfers",
        "boarding_buffer": "Boarding buffer",
        "sightseeing_walk": "Evidenced sightseeing walk",
        "plain_transfer": "Plain transfer",
        "opening_unverified": "Opening hours not officially verified",
        "map_no_coordinates": "This day has no stop coordinates yet.",
        "unscheduled_choices": "Selected but not scheduled",
        "capability_gaps": "Evidence still missing",
        "downloads": "Offline snapshots",
        "poster": "Day poster (PNG)",
        "pdf": "Trip PDF",
        "excel": "Excel workbook",
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
        "checklist_help": "Generated from your trip, fully editable. Warnings never block the itinerary or its exports.",
        "checklist_needs_setup": "Save the trip setup first; the board is generated from it.",
        "calendar": "Readiness calendar (.ics)",
        "today_tasks": "Needed today",
        "checklist_preview": "Proposed checklist changes",
        "checklist_applied": "Checklist updated:",
        "checklist_current": "The board matches the current trip.",
        "apply_checklist": "Apply these changes",
        "will_be_dismissed": "will move to history",
        "open_tasks": "open tasks",
        "overdue": "Overdue",
        "due_soon": "Due soon",
        "due": "due",
        "timing": "Timing",
        "requirement_level": "Requirement",
        "required": "Required",
        "recommended": "Recommended",
        "optional": "Optional",
        "do_now": "Do now / before booking",
        "30_days_before": "30 days before",
        "7_days_before": "7 days before",
        "24_hours_before": "24 hours before",
        "departure_arrival_day": "Departure / arrival day",
        "progress": "Progress",
        "progress_to_do": "To do",
        "progress_waiting": "Waiting",
        "progress_done": "Done",
        "progress_not_applicable": "Not applicable",
        "not_applicable_reason": "Why is it not applicable?",
        "evidence": "Official evidence",
        "evidence_verified": "Verified",
        "evidence_verification_needed": "Verification needed",
        "evidence_verification_needed_help": "No official source recorded yet. This app never guesses an entry rule.",
        "expected_authority": "Confirm with",
        "source_url": "Official source URL",
        "authority_type": "Authority",
        "record_evidence": "Record this source",
        "evidence_recorded": "Official source recorded.",
        "last_checked": "Last checked",
        "save_task": "Save",
        "task_saved": "Task updated.",
        "dismiss_task": "Dismiss",
        "task_dismissed": "Moved to history.",
        "dismissed_history": "Dismissed history",
        "restore_task": "Restore",
        "task_restored": "Task restored.",
        "add_task": "Add a task",
        "task_title": "Task",
        "task_added": "Task added.",
        "entry_requirements": "Entry requirements",
        "immigration_customs": "Immigration and customs",
        "money": "Money",
        "connectivity": "Connectivity",
        "insurance_health": "Insurance and health",
        "transport_setup": "Transport setup",
        "reservations": "Reservations",
        "registrations": "Registrations",
        "packing": "Packing",
        "local_rules": "Local rules",
        "emergency": "Emergency",
        "government": "Government",
        "embassy": "Embassy",
        "immigration": "Immigration",
        "customs": "Customs",
        "health_authority": "Health authority",
        "transport_operator": "Transport operator",
        "attraction_operator": "Attraction operator",
        "task_entry_requirements": "Verify entry requirements for {destination}",
        "why_entry_requirements": "Denied boarding or refused entry",
        "task_passport_validity": "Confirm every passport stays valid for the whole trip",
        "why_passport_validity": "Denied boarding",
        "task_immigration_forms": "Check whether {destination} requires an arrival or customs declaration",
        "why_immigration_forms": "Held at the border or fined",
        "task_insurance_health": "Decide travel insurance and check health requirements",
        "why_insurance_health": "Unfunded medical cost, or a refused entry where cover is mandatory",
        "task_money": "Prepare payment methods and local cash",
        "why_money": "Unable to pay where cards are not accepted",
        "task_connectivity": "Arrange data connectivity",
        "why_connectivity": "No maps, tickets, or translation on arrival",
        "task_transport_setup": "Set up local transport payment or passes",
        "why_transport_setup": "Queues and higher fares on the first day",
        "task_local_rules": "Read local rules and etiquette that carry penalties",
        "why_local_rules": "Fines or refused access",
        "task_packing": "Pack against the planned weather and walking load",
        "why_packing": "Avoidable discomfort or an unusable item",
        "task_emergency": "Save emergency contacts and embassy details offline",
        "why_emergency": "No usable contact during an incident",
        "task_departure_recheck": "Recheck departure time, terminal, and any closures",
        "why_departure_recheck": "Missed departure",
        "task_accommodation_base": "Confirm accommodation and record its address offline",
        "why_accommodation_base": "No usable base for routing or for an arrival form",
        "task_place_booking": "Check opening hours and advance booking for {place}",
        "why_place_booking_timed": "A timed or limited entry sells out or closes the visit",
        "why_place_booking_open": "Queueing, or arriving when the place cannot be entered",
        "costs": "Costs",
        "costs_help": "Thai baht is the reporting currency; every expense keeps its original amount and currency. Rates are yours to set and buffer.",
        "rate_snapshot": "Exchange-rate snapshot",
        "rate_as_of": "Rate date",
        "rate_source": "Rate source",
        "rate_currency": "Currency",
        "rate_value": "THB per unit",
        "rate_buffer": "Buffer %",
        "save_rates": "Save rate snapshot",
        "rates_saved": "Rate snapshot saved.",
        "no_rates": "No rate snapshot yet; costs in other currencies stay unconverted.",
        "add_cost": "Add a cost",
        "cost_label": "What is it",
        "cost_amount": "Original amount",
        "cost_currency": "Original currency",
        "cost_state": "Payment state",
        "cost_actual": "Actual THB charged",
        "cost_payer": "Payer",
        "cost_share": "Share",
        "cost_added": "Cost saved.",
        "cost_removed": "Cost removed.",
        "remove_cost": "Remove",
        "estimate": "Estimate",
        "committed": "Committed",
        "paid": "Paid",
        "estimated_thb": "Estimated THB",
        "paid_thb": "Paid THB",
        "total_thb": "Total THB",
        "rate_missing": "No rate for this currency",
        "locked_charge": "Locked actual charge",
        "transport": "Transport",
        "accommodation_cost": "Accommodation",
        "activity": "Activity",
        "food": "Food",
        "fees": "Fees",
        "shopping_cost": "Shopping",
        "other": "Other",
    },
    "th": {
        "title": "ตัวช่วยวางแผนท่องเที่ยวส่วนตัว",
        "caption": "POC บนเครื่อง · ข้อมูลทริปแบบมีโครงสร้างอยู่ในคอมพิวเตอร์นี้",
        "new_trip": "เริ่มสร้างทริป",
        "trip_name": "ชื่อทริป (ไม่บังคับ)",
        "destination": "จุดหมายปลายทาง",
        "mode": "รูปแบบการวางแผน",
        "explore_first": "เลือกสถานที่ก่อน",
        "ready_to_schedule": "พร้อมจัดตาราง",
        "create": "สร้างทริป",
        "created": "บันทึกทริปแล้ว",
        "destination_required": "กรุณาระบุจุดหมายปลายทาง",
        "saved_trips": "ทริปที่บันทึกไว้",
        "resume": "เปิดทริปต่อ",
        "status": "สถานะ",
        "draft": "แบบร่าง",
        "mode_label": "โหมด",
        "active_plan": "เวอร์ชันแผนที่ใช้งาน",
        "no_plan": "ยังไม่ได้สร้างตาราง หน้านี้ใช้ตั้งค่าและค้นหาสถานที่เท่านั้น",
        "empty": "สร้างทริปแรกเพื่อเริ่มต้น",
        "setup": "ตั้งค่าทริป",
        "setup_help": "บันทึกร่างได้ทุกเมื่อ และยืนยันก่อนให้แอปเรียกค้นหาสถานที่",
        "trip_basics": "1 · ข้อมูลทริป",
        "dates_known": "ทราบวันเดินทางแล้ว",
        "start_date": "วันเริ่มต้น",
        "end_date": "วันสิ้นสุด",
        "arrival_known": "ทราบเวลาถึงโดยประมาณ",
        "arrival_time": "เวลาถึง",
        "departure_known": "ทราบเวลาออกโดยประมาณ",
        "departure_time": "เวลาออก",
        "accommodation": "ที่พัก",
        "owner_style": "2 · สไตล์หลักของเจ้าของทริป",
        "owner_age": "อายุเจ้าของทริป (0 = ยังไม่ระบุ)",
        "main_style": "สไตล์หลัก · เลือกอย่างน้อยหนึ่งข้อ",
        "also_enjoy": "ชอบเพิ่มเติม",
        "avoid": "อยากหลีกเลี่ยง",
        "comfort": "ความสบายที่ต้องการ",
        "description": "รายละเอียดหรือบริบทเพิ่มเติม (ไม่บังคับ)",
        "travellers": "3 · ผู้ร่วมทริป",
        "member_count": "จำนวนผู้ร่วมทริปเพิ่มเติม",
        "member": "ผู้ร่วมทริป",
        "member_name": "ชื่อเล่น / ป้ายชื่อ",
        "member_age": "อายุ (0 = ยังไม่ระบุ)",
        "member_tags": "แท็กความชอบ (ไม่บังคับ)",
        "member_notes": "หมายเหตุ (ไม่บังคับ)",
        "member_must": "ข้อจำเป็นที่ต้องทำตาม · หนึ่งข้อต่อบรรทัด",
        "requirements": "4 · ข้อจำเป็นที่ต้องทำตาม",
        "owner_must": "ใส่เฉพาะสิ่งที่ต่อรองไม่ได้ · หนึ่งข้อต่อบรรทัด (ไม่บังคับ)",
        "save_draft": "บันทึกร่าง",
        "confirm": "ยืนยันการตั้งค่า",
        "draft_saved": "บันทึกร่างไว้ในเครื่องแล้ว โดยไม่ได้เรียกผู้ให้บริการ",
        "confirmed": "ยืนยันการตั้งค่าแล้ว พร้อมค้นหาสถานที่",
        "main_required": "เลือกสไตล์หลักอย่างน้อยหนึ่งข้อก่อนยืนยัน",
        "review": "5 · ตรวจสอบ",
        "setup_state": "สถานะการตั้งค่า",
        "draft_setup": "ร่างการตั้งค่า",
        "confirmed_setup": "ยืนยันเพื่อค้นหาแล้ว",
        "people": "จำนวนคน",
        "preferences": "แท็กเจ้าของทริป",
        "no_dates": "วันเดินทางยังไม่บังคับ ผลลัพธ์จึงยังไม่ใช่ตารางตามวันที่",
        "discover_title": "ค้นหาสถานที่แบบกว้าง",
        "discover_help": "ทำงานเมื่อกดเท่านั้น ใช้ฐาน OpenStreetMap ทั่วโลกแบบจำกัดพื้นที่และแคช 7 วัน ผลลัพธ์ครอบคลุมกว้างแต่ไม่ครบทุกแห่ง",
        "discover": "ค้นหาสถานที่",
        "refresh": "รีเฟรชข้อมูลผู้ให้บริการ",
        "discovering": "กำลังรวบรวมสถานที่พื้นฐาน…",
        "discovery_saved": "บันทึกผลการค้นหาแล้ว",
        "coverage": "รายงานความครอบคลุม",
        "provider_status": "สถานะผู้ให้บริการ",
        "candidates": "สถานที่",
        "duplicates": "รายการซ้ำที่รวมแล้ว",
        "cells": "พื้นที่ที่พบสถานที่",
        "unranked": "เป็นรายการพื้นฐานเท่านั้น ยังไม่ได้จัดอันดับหรือกรองด้วยความชอบ",
        "stale_setup": "ผลนี้มาจากการตั้งค่าเก่า ยังดูได้ แต่ควรยืนยันและค้นหาใหม่ก่อนจัดอันดับ",
        "provider_gap": "ผู้ให้บริการยังส่งรายการปัจจุบันไม่ได้ การตั้งค่าของคุณยังปลอดภัย และช่องว่างของข้อมูลแสดงด้านล่าง",
        "no_candidates": "ไม่พบสถานที่ที่ใช้ได้ โปรดดูช่องว่างของข้อมูลและลองใหม่ภายหลัง",
        "name": "ชื่อ",
        "local_name": "ชื่อท้องถิ่น",
        "category": "ประเภท",
        "opening": "หลักฐานเวลาเปิด",
        "source": "แหล่งข้อมูล",
        "details": "รายละเอียดความครอบคลุมแบบมาตรฐาน",
        "osm_notice": "บริการสาธารณะ OpenStreetMap ใช้แบบส่วนตัว ปริมาณต่ำ และผู้ใช้กดเอง แอประบุตัวตน แคชคำขอซ้ำ และไม่ทำ autocomplete",
        "ranking_title": "การ์ดสถานที่ที่เหมาะกับทริป",
        "ranking_help": "คะแนนใช้เรียงการ์ด ไม่ใช่การรับประกัน ข้อมูลเส้นทาง คนแน่น เรตติ้ง เวลาเปิดวันหยุด และช่วงเวลาที่ดีที่สุดที่ยังขาดจะแสดงอย่างชัดเจนและให้คะแนนแบบกลาง",
        "ranking_wait": "ยืนยันการตั้งค่าปัจจุบันและค้นหาสถานที่ก่อนจัดอันดับ",
        "lane": "กลุ่มการ์ด",
        "main_queue": "เหมาะกับทริปของคุณ",
        "city_icons": "แลนด์มาร์กสำคัญ",
        "worth_it_if": "คุ้มถ้า…",
        "local_alternatives": "ตัวเลือกท้องถิ่น",
        "browse_all": "ดูทั้งหมด",
        "select_card": "เลือกการ์ด",
        "no_lane_cards": "ยังไม่มีการ์ดที่เข้าเงื่อนไขกลุ่มนี้",
        "score": "คะแนน",
        "duration": "เวลาชมโดยประมาณ",
        "minutes": "นาที",
        "planner_estimate": "ค่าประมาณตามประเภทจากตัววางแผน ยังไม่ยืนยันโดยสถานที่",
        "feasibility": "ความเป็นไปได้",
        "not_evaluated": "ยังไม่ประเมินจนกว่าจะจัดแผน",
        "why": "เหตุผลที่แสดง",
        "pros": "ข้อดี",
        "cons": "ข้อเสีย / ข้อมูลที่ยังขาด",
        "breakdown": "รายละเอียดคะแนน 30/20/20/10/15/5",
        "dimension": "องค์ประกอบ",
        "points": "คะแนน",
        "maximum": "คะแนนเต็ม",
        "deductions": "คะแนนหักพร้อมเหตุผล",
        "no_deductions": "ไม่มีคะแนนหักที่มีหลักฐานรองรับ",
        "matched_tags": "แท็กที่ตรงกัน",
        "group_weights": "น้ำหนักสมาชิกและสัญญาณที่เรียนรู้",
        "choice": "ตัวเลือกของคุณ",
        "must_do": "ต้องไป",
        "interested": "สนใจ",
        "maybe": "อาจจะ",
        "not_for_trip": "ไม่เหมาะกับทริปนี้",
        "rejection_reason": "เหตุผลเพิ่มเติมสำหรับไม่เหมาะกับทริปนี้",
        "no_reason": "ไม่ระบุเหตุผล",
        "choice_saved": "บันทึกแล้ว การ์ดที่ยังไม่เลือกถูกเรียงใหม่ และรายการดูทั้งหมดยังเก็บทุกสถานที่",
        "current_choice": "ตัวเลือกปัจจุบัน",
        "clear_choice": "ล้างตัวเลือก",
        "choice_cleared": "ล้างตัวเลือกแล้ว",
        "exploration_card": "การ์ดสำรวจที่ระบบกันไว้",
        "icon_card": "มีหลักฐานว่าเป็นแลนด์มาร์กเด่น",
        "source_rating": "เรตติ้งจากแหล่งข้อมูล",
        "not_enriched": "ยังไม่ได้เพิ่มข้อมูล",
        "route_effort": "เส้นทาง / การเดิน",
        "not_routed": "ยังไม่ได้คำนวณเส้นทาง",
        "browse_notice": "สถานที่มาตรฐานปัจจุบันทุกแห่งอยู่ที่นี่ รวมทั้งที่เลือกแล้วและคะแนนต่ำ",
        "reconciliation": "ตรวจสอบสถานที่ที่เลือกทั้งหมด",
        "reconciliation_help": "ไม่มีสถานที่ที่เลือกหายไป ตัวเลือกจากการ์ดยังคงรอจนกว่าจะรันระบบจัดแผนทั้งทริปด้านล่าง",
        "no_selected": "ยังไม่มีสถานที่ที่เลือกเป็น ต้องไป หรือ สนใจ",
        "pending_optimizer": "รอจัดแผน",
        "present_latest": "อยู่ในการค้นหาล่าสุด",
        "next_step": "ขั้นต่อไป",
        "run_optimizer": "รันระบบจัดแผนทั้งทริปด้านล่าง",
        "all_choices": "ตัวเลือกที่บันทึกทั้งหมด",
        "formula_note": "คะแนนกลางหมายถึงข้อมูลยังขาด ไม่ได้แปลว่าสถานที่นั้นอยู่ระดับกลางจริง",
        "photo_source": "รูปจากแหล่งข้อมูลเปิด",
        "photo_unavailable": "ยังไม่มีแหล่งรูปที่อนุญาตให้ใช้",
        "optimizer_title": "ระบบจัดแผนทั้งทริป",
        "optimizer_help": "ใช้สถานที่ที่เลือกทั้งหมดข้ามทุกวันและสลับวันหรือลำดับได้ แต่จะไม่เดาเส้นทาง เวลาเปิด ทางเข้า หรือรายการล็อก",
        "generate_plan": "สร้าง / รีเฟรชแผน 3 แบบ",
        "optimizing": "กำลังจัดแผนทั้งทริป…",
        "preview_saved": "บันทึกตัวอย่างแผนไว้ในเครื่องแล้ว",
        "choose_before_plan": "เลือกอย่างน้อยหนึ่งสถานที่เป็น ต้องไป สนใจ หรือ อาจจะ ก่อน",
        "stay_recommendation": "ยังไม่กำหนดวันแน่นอน — เปรียบเทียบจำนวนวันที่แนะนำ",
        "stay_option": "รูปแบบระยะเวลา",
        "days": "วัน",
        "daily_capacity": "เวลาวางแผนต่อวัน",
        "variant": "รูปแบบแผน",
        "best_balance": "สมดุลที่สุด",
        "relaxed": "สบายขึ้น",
        "more_highlights": "เก็บไฮไลต์มากขึ้น",
        "ready": "พร้อมใช้",
        "provisional": "ชั่วคราว / ต้องยอมรับผลกระทบ",
        "unavailable": "ยังสร้างไม่ได้",
        "scheduled_visits": "สถานที่",
        "travel_minutes": "เวลาเดินทาง",
        "walking_minutes": "เวลาเดิน",
        "plain_walking_minutes": "การเดินทางธรรมดา",
        "buffer_minutes": "เวลาสำรอง",
        "optimizer_warning": "คำเตือนและข้อมูลที่ยังขาด",
        "optimizer_reconciliation": "ผลตรวจสถานที่ที่เลือกทั้งหมด",
        "fits": "ใส่ในแผนได้",
        "fits_with_tradeoff": "ใส่ได้เมื่อยอมรับข้อแลกเปลี่ยน",
        "cannot_currently_fit": "ตอนนี้ใส่ในแผนไม่ได้",
        "reason": "เหตุผล",
        "consequence": "ผลกระทบ / ขั้นต่อไปที่เล็กที่สุด",
        "timeline": "ตารางเวลาที่ตรวจแล้ว",
        "item_type": "ประเภท",
        "start": "เริ่ม",
        "end": "จบ",
        "place_or_leg": "สถานที่ / ช่วงเดินทาง",
        "activate_plan": "ใช้เป็นแผนปัจจุบัน",
        "plan_activated": "เปิดใช้แผนที่ผ่านการตรวจแล้ว",
        "activation_disabled": "เปิดใช้ได้เฉพาะแผนสถานะ พร้อมใช้ และผ่านการตรวจครบ",
        "no_schedule": "ยังจัดสถานที่ที่เลือกอย่างปลอดภัยไม่ได้ด้วยข้อมูลปัจจุบัน",
        "greedy_check": "ผลทั้งทริปเท่ากับหรือดีกว่าแผนแบบจัดทีละวัน",
        "optimizer_limit": "ระบบหยุดเมื่อถึงขีดจำกัดและแสดงเฉพาะผลที่ตรวจแล้ว",
        "use_title": "แผนที่ใช้งาน",
        "use_help": "หน้านี้อ่านสแนปช็อตส่งออกชุดเดียว โพสเตอร์ PDF และ Excel จะอ่านตัวเลขชุดเดียวกัน",
        "no_active_plan": "ยังไม่มีแผนที่ใช้งาน กรุณาเปิดใช้แผนที่ผ่านการตรวจด้านบน",
        "superseded_plan": "นี่คือแผนเวอร์ชันเก่า แผนที่ใช้งานเปลี่ยนไปแล้ว",
        "exported_at": "สร้างสแนปช็อตเมื่อ",
        "readiness": "ความพร้อม",
        "action_needed": "ต้องดำเนินการ",
        "verification_needed": "ต้องตรวจสอบหลักฐาน",
        "state_confirmed": "✅ ยืนยันแล้ว",
        "state_recheck": "🕒 ต้องตรวจซ้ำ",
        "state_tradeoff_accepted": "⚖️ ยอมรับผลกระทบแล้ว",
        "state_unverified_conflict": "⚠️ ยังไม่ยืนยัน / ข้อมูลขัดแย้ง",
        "state_locked": "🔒 ล็อกไว้",
        "highest_risk": "ความเสี่ยงสูงสุดของวันนี้",
        "tab_map": "แผนที่",
        "visit_minutes": "เวลาอยู่ในสถานที่",
        "rewarding_walking_minutes": "การเดินที่คุ้มค่า",
        "stop": "จุดที่",
        "travel_mode": "รูปแบบเดินทาง",
        "walk_portion": "ช่วงที่ต้องเดิน",
        "distance": "ระยะทาง",
        "transfers": "จำนวนต่อรถ",
        "boarding_buffer": "เวลาสำรองก่อนขึ้นรถ",
        "sightseeing_walk": "เส้นทางเดินชมเมืองที่มีหลักฐาน",
        "plain_transfer": "การเดินทางธรรมดา",
        "opening_unverified": "เวลาเปิดยังไม่ได้ยืนยันจากแหล่งทางการ",
        "map_no_coordinates": "วันนี้ยังไม่มีพิกัดของจุดหมาย",
        "unscheduled_choices": "เลือกไว้แต่ยังจัดลงตารางไม่ได้",
        "capability_gaps": "หลักฐานที่ยังขาด",
        "downloads": "ไฟล์สำหรับใช้ออฟไลน์",
        "poster": "โพสเตอร์รายวัน (PNG)",
        "pdf": "PDF ทั้งทริป",
        "excel": "ไฟล์ Excel",
        "checklist": "รายการเตรียมตัวก่อนเดินทาง",
        "checklist_pending": "ยังไม่ได้สร้างรายการเตรียมตัว",
        "sources": "หลักฐานและแหล่งข้อมูล",
        "no_sources": "ยังไม่มีข้อมูลที่ตรวจสอบแล้วเข้าสู่แผนนี้",
        "no_costs": "ยังไม่มีข้อมูลค่าใช้จ่าย",
        "fallback": "แผนสำรองของช่วงนี้",
        "fallback_trigger": "เงื่อนไขที่ทำให้ใช้แผนสำรอง",
        "day_reoptimized": "จัดตารางวันนี้ใหม่แล้ว",
        "hotel_anchor": "ย่านที่พัก",
        "morning": "ช่วงเช้า",
        "afternoon": "ช่วงบ่าย",
        "checklist_help": "สร้างจากข้อมูลทริปและแก้ไขได้ทั้งหมด คำเตือนไม่ปิดกั้นตารางเดินทางหรือไฟล์ส่งออก",
        "checklist_needs_setup": "บันทึกการตั้งค่าทริปก่อน ระบบจะสร้างรายการจากข้อมูลนั้น",
        "calendar": "ปฏิทินเตรียมตัว (.ics)",
        "today_tasks": "ต้องทำวันนี้",
        "checklist_preview": "การเปลี่ยนแปลงที่เสนอ",
        "checklist_applied": "อัปเดตรายการแล้ว:",
        "checklist_current": "รายการตรงกับข้อมูลทริปปัจจุบันแล้ว",
        "apply_checklist": "ใช้การเปลี่ยนแปลงนี้",
        "will_be_dismissed": "จะย้ายไปประวัติ",
        "open_tasks": "รายการที่ยังไม่เสร็จ",
        "overdue": "เกินกำหนด",
        "due_soon": "ใกล้ครบกำหนด",
        "due": "กำหนด",
        "timing": "ช่วงเวลา",
        "requirement_level": "ระดับความจำเป็น",
        "required": "จำเป็น",
        "recommended": "แนะนำ",
        "optional": "ไม่บังคับ",
        "do_now": "ทำทันที / ก่อนจอง",
        "30_days_before": "ก่อนเดินทาง 30 วัน",
        "7_days_before": "ก่อนเดินทาง 7 วัน",
        "24_hours_before": "ก่อนเดินทาง 24 ชั่วโมง",
        "departure_arrival_day": "วันเดินทาง / วันถึง",
        "progress": "สถานะงาน",
        "progress_to_do": "ยังไม่ทำ",
        "progress_waiting": "รอผล",
        "progress_done": "เสร็จแล้ว",
        "progress_not_applicable": "ไม่เกี่ยวข้อง",
        "not_applicable_reason": "เหตุผลที่ไม่เกี่ยวข้อง",
        "evidence": "หลักฐานจากแหล่งทางการ",
        "evidence_verified": "ยืนยันแล้ว",
        "evidence_verification_needed": "ต้องตรวจสอบ",
        "evidence_verification_needed_help": "ยังไม่มีแหล่งทางการบันทึกไว้ แอปนี้ไม่เดากฎการเข้าเมือง",
        "expected_authority": "ตรวจสอบกับ",
        "source_url": "ลิงก์แหล่งทางการ",
        "authority_type": "หน่วยงาน",
        "record_evidence": "บันทึกแหล่งข้อมูลนี้",
        "evidence_recorded": "บันทึกแหล่งทางการแล้ว",
        "last_checked": "ตรวจครั้งล่าสุด",
        "save_task": "บันทึก",
        "task_saved": "อัปเดตรายการแล้ว",
        "dismiss_task": "ซ่อนรายการ",
        "task_dismissed": "ย้ายไปประวัติแล้ว",
        "dismissed_history": "ประวัติรายการที่ซ่อน",
        "restore_task": "นำกลับมา",
        "task_restored": "นำรายการกลับมาแล้ว",
        "add_task": "เพิ่มรายการ",
        "task_title": "ชื่อรายการ",
        "task_added": "เพิ่มรายการแล้ว",
        "entry_requirements": "ข้อกำหนดการเข้าประเทศ",
        "immigration_customs": "ตรวจคนเข้าเมืองและศุลกากร",
        "money": "การเงิน",
        "connectivity": "อินเทอร์เน็ต",
        "insurance_health": "ประกันและสุขภาพ",
        "transport_setup": "การเดินทางในพื้นที่",
        "reservations": "การจอง",
        "registrations": "การลงทะเบียน",
        "packing": "การจัดกระเป๋า",
        "local_rules": "กฎท้องถิ่น",
        "emergency": "เหตุฉุกเฉิน",
        "government": "หน่วยงานรัฐ",
        "embassy": "สถานทูต",
        "immigration": "ตรวจคนเข้าเมือง",
        "customs": "ศุลกากร",
        "health_authority": "หน่วยงานสาธารณสุข",
        "transport_operator": "ผู้ให้บริการขนส่ง",
        "attraction_operator": "ผู้ดูแลสถานที่",
        "task_entry_requirements": "ตรวจสอบข้อกำหนดการเข้า {destination} จากแหล่งทางการ",
        "why_entry_requirements": "ถูกปฏิเสธการขึ้นเครื่องหรือปฏิเสธการเข้าประเทศ",
        "task_passport_validity": "ยืนยันว่าหนังสือเดินทางทุกเล่มมีอายุครอบคลุมทั้งทริป",
        "why_passport_validity": "ถูกปฏิเสธการขึ้นเครื่อง",
        "task_immigration_forms": "ตรวจว่า {destination} ต้องกรอกแบบฟอร์มขาเข้าหรือใบสำแดงศุลกากรหรือไม่",
        "why_immigration_forms": "ถูกกักที่ด่านตรวจหรือถูกปรับ",
        "task_insurance_health": "ตัดสินใจเรื่องประกันการเดินทางและตรวจข้อกำหนดด้านสุขภาพ",
        "why_insurance_health": "ค่ารักษาที่ไม่มีผู้รับผิดชอบ หรือถูกปฏิเสธเข้าประเทศหากบังคับให้มีประกัน",
        "task_money": "เตรียมวิธีชำระเงินและเงินสดสกุลท้องถิ่น",
        "why_money": "จ่ายเงินไม่ได้ในที่ที่ไม่รับบัตร",
        "task_connectivity": "จัดเตรียมอินเทอร์เน็ตสำหรับใช้ระหว่างเดินทาง",
        "why_connectivity": "ใช้แผนที่ ตั๋ว หรือการแปลภาษาไม่ได้เมื่อไปถึง",
        "task_transport_setup": "ตั้งค่าการชำระเงินหรือบัตรโดยสารขนส่งท้องถิ่น",
        "why_transport_setup": "ต้องต่อคิวและจ่ายค่าโดยสารแพงขึ้นในวันแรก",
        "task_local_rules": "อ่านกฎและธรรมเนียมท้องถิ่นที่มีบทลงโทษ",
        "why_local_rules": "ถูกปรับหรือถูกปฏิเสธไม่ให้เข้า",
        "task_packing": "จัดกระเป๋าให้เหมาะกับสภาพอากาศและปริมาณการเดินที่วางแผนไว้",
        "why_packing": "ไม่สบายตัวโดยไม่จำเป็น หรือของที่พกไปใช้ไม่ได้",
        "task_emergency": "บันทึกเบอร์ฉุกเฉินและข้อมูลสถานทูตให้ใช้ได้แบบออฟไลน์",
        "why_emergency": "ติดต่อใครไม่ได้เมื่อเกิดเหตุ",
        "task_departure_recheck": "ตรวจเวลาออกเดินทาง อาคารผู้โดยสาร และการปิดให้บริการอีกครั้ง",
        "why_departure_recheck": "พลาดเที่ยวเดินทาง",
        "task_accommodation_base": "ยืนยันที่พักและบันทึกที่อยู่ให้ใช้ได้แบบออฟไลน์",
        "why_accommodation_base": "ไม่มีฐานที่พักสำหรับคำนวณเส้นทางหรือกรอกแบบฟอร์มขาเข้า",
        "task_place_booking": "ตรวจเวลาเปิดและการจองล่วงหน้าของ {place}",
        "why_place_booking_timed": "รอบเข้าชมแบบกำหนดเวลาหรือจำนวนจำกัดอาจเต็มหรือปิดรับ",
        "why_place_booking_open": "ต้องต่อคิว หรือไปถึงตอนที่เข้าชมไม่ได้",
        "costs": "ค่าใช้จ่าย",
        "costs_help": "รายงานเป็นเงินบาท และเก็บจำนวนเงินสกุลเดิมไว้ทุกรายการ อัตราแลกเปลี่ยนคุณกำหนดและเผื่อได้เอง",
        "rate_snapshot": "ชุดอัตราแลกเปลี่ยน",
        "rate_as_of": "วันที่ของอัตรา",
        "rate_source": "แหล่งอัตรา",
        "rate_currency": "สกุลเงิน",
        "rate_value": "บาทต่อหนึ่งหน่วย",
        "rate_buffer": "เผื่อ %",
        "save_rates": "บันทึกชุดอัตรา",
        "rates_saved": "บันทึกชุดอัตราแล้ว",
        "no_rates": "ยังไม่มีชุดอัตรา รายการสกุลอื่นจะยังไม่ถูกแปลงเป็นบาท",
        "add_cost": "เพิ่มค่าใช้จ่าย",
        "cost_label": "รายการ",
        "cost_amount": "จำนวนเงินสกุลเดิม",
        "cost_currency": "สกุลเงินเดิม",
        "cost_state": "สถานะการจ่าย",
        "cost_actual": "ยอดที่จ่ายจริง (บาท)",
        "cost_payer": "ผู้จ่าย",
        "cost_share": "การแบ่งจ่าย",
        "cost_added": "บันทึกค่าใช้จ่ายแล้ว",
        "cost_removed": "ลบค่าใช้จ่ายแล้ว",
        "remove_cost": "ลบ",
        "estimate": "ประมาณการ",
        "committed": "ผูกพันแล้ว",
        "paid": "จ่ายแล้ว",
        "estimated_thb": "ประมาณการ (บาท)",
        "paid_thb": "จ่ายแล้ว (บาท)",
        "total_thb": "รวม (บาท)",
        "rate_missing": "ไม่มีอัตราสำหรับสกุลนี้",
        "locked_charge": "ยอดจ่ายจริงถูกล็อกไว้",
        "transport": "การเดินทาง",
        "accommodation_cost": "ที่พัก",
        "activity": "กิจกรรม",
        "food": "อาหาร",
        "fees": "ค่าธรรมเนียม",
        "shopping_cost": "ช้อปปิ้ง",
        "other": "อื่นๆ",
    },
}

TAG_TEXT = {
    "en": {
        "sightseeing": "Sightseeing",
        "culture": "Culture",
        "nature": "Nature",
        "activity": "Activity",
        "shopping": "Shopping",
        "chill": "Chill",
        "local_street_food": "Local street food",
        "photography": "Photography",
        "night_view": "Night view",
        "markets": "Markets",
        "architecture": "Architecture",
        "neighborhoods": "Neighbourhoods",
        "tourist_traps": "Tourist traps",
        "plain_long_walks": "Plain long walks",
        "late_meals": "Late meals",
        "heavy_crowds": "Heavy crowds",
        "balanced_pace": "Balanced pace",
        "rewarding_walks": "Rewarding walks",
        "meal_on_time": "Meals on time",
        "rest_breaks": "Rest breaks",
        "low_walking": "Low walking",
    },
    "th": {
        "sightseeing": "เที่ยวชมเมือง",
        "culture": "วัฒนธรรม",
        "nature": "ธรรมชาติ",
        "activity": "กิจกรรม",
        "shopping": "ช้อปปิ้ง",
        "chill": "สบาย ๆ",
        "local_street_food": "อาหารข้างทางท้องถิ่น",
        "photography": "ถ่ายภาพ",
        "night_view": "วิวกลางคืน",
        "markets": "ตลาด",
        "architecture": "สถาปัตยกรรม",
        "neighborhoods": "ย่านน่าเดิน",
        "tourist_traps": "แหล่งดักนักท่องเที่ยว",
        "plain_long_walks": "เดินไกลแบบไม่มีอะไรน่าสนใจ",
        "late_meals": "กินข้าวช้า",
        "heavy_crowds": "คนแน่นมาก",
        "balanced_pace": "จังหวะพอดี",
        "rewarding_walks": "เดินเมื่อมีสิ่งคุ้มค่าให้ชม",
        "meal_on_time": "กินตรงเวลา",
        "rest_breaks": "มีเวลาพัก",
        "low_walking": "เดินน้อย",
    },
}

ACCOMMODATION_TEXT = {
    "en": {"unknown": "Unknown", "not_booked": "Not booked", "booked": "Booked"},
    "th": {"unknown": "ยังไม่ทราบ", "not_booked": "ยังไม่ได้จอง", "booked": "จองแล้ว"},
}

DIMENSION_TEXT = {
    "en": {
        "group_preference_fit": "Group preference fit",
        "experience_value": "Expected experience value",
        "reward_vs_effort": "Reward versus effort",
        "time_fit": "Date / opening / best-time fit",
        "route_compatibility": "Route and cluster compatibility",
        "evidence_quality": "Evidence quality",
    },
    "th": {
        "group_preference_fit": "ความตรงกับความชอบของกลุ่ม",
        "experience_value": "คุณค่าประสบการณ์ที่คาดไว้",
        "reward_vs_effort": "ความคุ้มค่าเทียบกับแรงที่ใช้",
        "time_fit": "ความเหมาะกับวัน เวลาเปิด และช่วงชม",
        "route_compatibility": "ความเข้ากันของเส้นทางและกลุ่มสถานที่",
        "evidence_quality": "คุณภาพหลักฐาน",
    },
}

EXPLANATION_TEXT = {
    "en": {
        "group_preference_match": "Matches confirmed group preferences",
        "member_preferences_considered": "Uses supplied member preferences; missing profiles are not guessed",
        "city_icon_evidence": "Open data links this place to prominent landmark references",
        "learned_from_choices": "Similar to places you marked Must do / Interested / Maybe",
        "high_experience_potential": "Its city-independent category has strong experience potential",
        "broad_baseline_candidate": "Retained from the broad baseline even without a strong preference match",
        "protected_exploration": "Protected diversity slot from an under-seen experience family",
        "open_export_source": "Open, attributable catalog source",
        "preference_match": "Matches one or more explicit tags",
        "city_icon": "Kept visible as a City Icon; never forced into the plan",
        "regular_hours_present": "A regular schedule is present, but the trip date is not confirmed",
        "near_selected_cluster": "Geographically near a selected place; actual route is still unverified",
        "route_not_verified": "Walking, transit, transfers and effort are not routed yet",
        "ratings_not_enriched": "No licensed source rating or review sample has been enriched yet",
        "best_time_unconfirmed": "Best viewing time is unconfirmed",
        "opening_unconfirmed": "Opening hours are unconfirmed",
        "possible_duplicate": "Possible duplicate needs owner review",
        "access_unconfirmed": "Entrance and access instructions are unconfirmed",
        "near_selected_similar_experience": "Similar experience very near a selected place",
        "owner_rejected_without_reason": "Owner marked Not for trip without a reason",
        "too_crowded": "Owner marked it too crowded",
        "too_expensive": "Owner marked it too expensive",
        "too_tiring": "Owner marked it too tiring",
        "wrong_vibe": "Owner marked it the wrong vibe",
        "weak_value": "Owner marked its value too weak",
        "already_seen": "Owner has already seen it",
    },
    "th": {
        "group_preference_match": "ตรงกับความชอบของกลุ่มที่ยืนยันแล้ว",
        "member_preferences_considered": "ใช้เฉพาะความชอบสมาชิกที่กรอกไว้ และไม่เดาข้อมูลที่ขาด",
        "city_icon_evidence": "ข้อมูลเปิดเชื่อมสถานที่นี้กับแหล่งอ้างอิงแลนด์มาร์กเด่น",
        "learned_from_choices": "คล้ายสถานที่ที่คุณเลือก ต้องไป / สนใจ / อาจจะ",
        "high_experience_potential": "ประเภทสถานที่มีโอกาสให้ประสบการณ์ที่โดดเด่น",
        "broad_baseline_candidate": "เก็บไว้จากการค้นหาแบบกว้าง แม้ยังไม่ตรงความชอบชัดเจน",
        "protected_exploration": "ช่องสำรวจเพื่อรักษาความหลากหลายจากรูปแบบที่ยังเห็นน้อย",
        "open_export_source": "แหล่งข้อมูลเปิดที่ระบุที่มาได้",
        "preference_match": "ตรงกับแท็กที่ระบุอย่างน้อยหนึ่งข้อ",
        "city_icon": "แสดงไว้ในกลุ่มแลนด์มาร์ก แต่ไม่บังคับใส่แผน",
        "regular_hours_present": "มีเวลาปกติ แต่ยังไม่ยืนยันสำหรับวันเดินทาง",
        "near_selected_cluster": "อยู่ใกล้สถานที่ที่เลือกในเชิงพิกัด แต่ยังไม่ยืนยันเส้นทางจริง",
        "route_not_verified": "ยังไม่คำนวณการเดิน รถสาธารณะ การต่อรถ และแรงที่ใช้",
        "ratings_not_enriched": "ยังไม่มีเรตติ้งหรือตัวอย่างรีวิวจากแหล่งที่ได้รับอนุญาต",
        "best_time_unconfirmed": "ยังไม่ยืนยันช่วงเวลาที่ดีที่สุด",
        "opening_unconfirmed": "ยังไม่ยืนยันเวลาเปิด",
        "possible_duplicate": "อาจเป็นรายการซ้ำ ต้องให้เจ้าของตรวจสอบ",
        "access_unconfirmed": "ยังไม่ยืนยันทางเข้าและวิธีเข้าถึง",
        "near_selected_similar_experience": "ประสบการณ์คล้ายกันและอยู่ใกล้สถานที่ที่เลือกมาก",
        "owner_rejected_without_reason": "เจ้าของเลือกไม่เหมาะกับทริปโดยไม่ระบุเหตุผล",
        "too_crowded": "เจ้าของระบุว่าคนแน่นเกินไป",
        "too_expensive": "เจ้าของระบุว่าแพงเกินไป",
        "too_tiring": "เจ้าของระบุว่าเหนื่อยเกินไป",
        "wrong_vibe": "เจ้าของระบุว่าบรรยากาศไม่ตรง",
        "weak_value": "เจ้าของระบุว่าไม่คุ้ม",
        "already_seen": "เจ้าของเคยไปแล้ว",
    },
}

REJECTION_TEXT = {
    "en": {
        None: "No reason",
        "too_crowded": "Too crowded",
        "too_expensive": "Too expensive",
        "too_tiring": "Too tiring",
        "wrong_vibe": "Wrong vibe",
        "weak_value": "Weak value",
        "already_seen": "Already seen",
    },
    "th": {
        None: "ไม่ระบุเหตุผล",
        "too_crowded": "คนแน่นเกินไป",
        "too_expensive": "แพงเกินไป",
        "too_tiring": "เหนื่อยเกินไป",
        "wrong_vibe": "บรรยากาศไม่ตรง",
        "weak_value": "ไม่คุ้ม",
        "already_seen": "เคยไปแล้ว",
    },
}

CATEGORY_TEXT = {
    "en": {},
    "th": {
        "attraction": "สถานที่ท่องเที่ยว",
        "museum": "พิพิธภัณฑ์",
        "gallery": "แกลเลอรี",
        "viewpoint": "จุดชมวิว",
        "artwork": "งานศิลปะ",
        "theme_park": "สวนสนุก",
        "zoo": "สวนสัตว์",
        "aquarium": "พิพิธภัณฑ์สัตว์น้ำ",
        "historic": "สถานที่ประวัติศาสตร์",
        "place_of_worship": "ศาสนสถาน",
        "marketplace": "ตลาด",
        "theatre": "โรงละคร",
        "arts_centre": "ศูนย์ศิลปะ",
        "park": "สวนสาธารณะ",
        "garden": "สวน",
        "nature_reserve": "เขตอนุรักษ์ธรรมชาติ",
        "water_park": "สวนน้ำ",
        "sports_centre": "ศูนย์กีฬา",
        "spa": "สปา",
        "beach": "ชายหาด",
        "peak": "ยอดเขา",
        "mall": "ศูนย์การค้า",
        "department_store": "ห้างสรรพสินค้า",
        "tower": "หอคอย",
        "landmark": "แลนด์มาร์ก",
    },
}

OPTIMIZER_CODE_TEXT = {
    "th": {
        "OPENING_UNVERIFIED": "ยังไม่ยืนยันเวลาเปิดสำหรับวันเดินทาง",
        "ROUTE_UNVERIFIED": "ยังไม่มีเส้นทางและเวลาการเดินทางที่ยืนยันแล้ว",
        "ACCESS_UNVERIFIED": "ยังไม่ยืนยันทางเข้าและกฎการเข้าถึง",
        "ENTRANCE_UNVERIFIED": "ยังไม่ยืนยันจุดเข้าและวิธีเดินเข้า",
        "CLOSED_AT_AVAILABLE_TIME": "สถานที่ปิดในช่วงเวลาที่ใช้ได้",
        "SHOW_TYPE_UNAVAILABLE_AT_TIME": "ไม่มีรอบการแสดงที่ต้องการในเวลาที่ใช้ได้",
        "PLAIN_WALK_THRESHOLD": "การเดินทางธรรมดาเกินค่าที่ตั้งไว้",
        "LONG_TRANSFER_WALK": "ช่วงเดินทางด้วยการเดินไกลเกินค่าที่ตั้งไว้",
        "FATIGUE_THRESHOLD": "ภาระรวมของวันเกินค่าความสบาย",
        "TOURIST_TRAP_RISK": "มีความเสี่ยงเป็นกับดักนักท่องเที่ยว",
        "QUEUE_CAUSES_LATE_MEAL": "เวลารอทำให้มื้ออาหารช้าเกินช่วงที่ตั้งไว้",
        "WEAK_VALUE_FOR_EFFORT": "คุณค่าที่คาดหวังไม่คุ้มแรงเดินทาง",
        "TRANSPORT_MODE_PROHIBITED": "วิธีเดินทางนี้ไม่อนุญาต",
        "HEAT_AND_CYCLING_LOAD": "ความร้อนและภาระการปั่นเกินค่าที่ตั้งไว้",
        "EFFORT_OR_TIME_CONFLICT": "แรงที่ใช้หรือเวลาการเดินทางขัดกับตาราง",
        "RAIN_FALLBACK_ACTIVATED": "เปิดใช้แผนสำรองฝนและจัดวันใหม่แล้ว",
        "NO_VERIFIED_WEATHER_FALLBACK": "ยังไม่มีแผนสำรองอากาศที่ยืนยันแล้ว",
        "NO_TIME_CAPACITY": "ไม่มีเวลาว่างพอในทริป",
        "SCHEDULED": "จัดลงตารางได้หนึ่งครั้ง",
        "ROUTE_SNAPSHOT_MISSING": "ยังไม่มีชุดข้อมูลเส้นทางสำหรับสถานที่ที่เลือก",
        "DESTINATION_TIMEZONE_UNVERIFIED": "ยังไม่ยืนยันเขตเวลาของปลายทาง",
        "ACCOMMODATION_BASE_UNCONFIRMED": "ยังไม่มีฐานที่พักที่ยืนยันแล้ว",
        "FREE_TEXT_HARD_CONSTRAINT_NEEDS_STRUCTURED_CONFIRMATION": "ข้อจำเป็นแบบข้อความต้องยืนยันเป็นข้อมูลโครงสร้างก่อน",
        "NO_SELECTED_PLACE_COULD_BE_SCHEDULED": "ยังไม่มีสถานที่ที่เลือกใส่ตารางได้อย่างปลอดภัย",
    }
}


def _category_text(category: str, language: str) -> str:
    return CATEGORY_TEXT[language].get(category, category.replace("_", " ").title())


def _explain(code: str, language: str) -> str:
    return EXPLANATION_TEXT[language].get(code, code.replace("_", " ").title())


def _optimizer_code(code: str, language: str) -> str:
    return OPTIMIZER_CODE_TEXT.get(language, {}).get(
        code, code.replace("_", " ").capitalize()
    )


def _plan_item_name(item: dict, language: str) -> str:
    if item["type"] == "travel":
        return f"{item.get('origin_id') or 'start'} → {item['destination_id']} · {item.get('mode') or '?'}"
    if item["type"] == "buffer":
        return _optimizer_code(item.get("reason", "buffer"), language)
    names = item.get("names", {})
    return names.get(language) or names.get("en") or names.get("local") or item["name"]


def _candidate_name(candidate: dict, language: str) -> str:
    names = candidate.get("names", {})
    return names.get(language) or names.get("en") or names.get("local") or candidate["name"]


def _photo_url(reference: str | None) -> str | None:
    if not reference:
        return None
    if reference.startswith(("https://", "http://")):
        return reference
    if reference.startswith("File:"):
        return "https://commons.wikimedia.org/wiki/Special:Redirect/file/" + quote(
            reference.removeprefix("File:")
        )
    return None


def _empty_setup(mode: str) -> dict:
    return {
        "planning_mode": mode,
        "trip_basics": {
            "start_date": None,
            "end_date": None,
            "arrival_time": None,
            "departure_time": None,
            "accommodation_status": "unknown",
        },
        "owner": {
            "age": None,
            "main_style": [],
            "also_enjoy": [],
            "avoid": [],
            "comfort": [],
            "description": "",
            "must_respect": [],
        },
        "travellers": [],
    }


def _date_value(value: str | None) -> date:
    return date.fromisoformat(value) if value else date.today()


def _time_value(value: str | None, fallback: time) -> time:
    return time.fromisoformat(value) if value else fallback


def _export_labels(language: str) -> dict:
    """Interface copy plus optimizer-code wording, so documents match the app."""

    return TEXT[language] | OPTIMIZER_CODE_TEXT.get(language, {})


@st.cache_data(show_spinner=False)
def _plan_documents(_snapshot: dict, sha256: str, language: str) -> dict[str, bytes]:
    """Cached per plan-version snapshot and language; exporters are pure."""

    labels = _export_labels(language)
    return {
        "pdf": plan_pdf(_snapshot, labels),
        "xlsx": plan_workbook_xlsx(_snapshot, labels),
        "ics": checklist_ics(_snapshot, labels),
    }


@st.cache_data(show_spinner=False)
def _day_poster(_snapshot: dict, sha256: str, language: str, date: str) -> bytes:
    return day_poster_png(_snapshot, date, _export_labels(language))


def _render_checklist_item(
    actions, trip, item: dict, language: str, flash_key: str
) -> None:
    """One board row: state, deadline, consequence, and its evidence controls."""

    words = TEXT[language]
    with st.container(border=True):
        badge = words[f"progress_{item['progress']}"]
        evidence = words[f"evidence_{item['evidence_state']}"]
        st.markdown(f"**{display_title(item, words)}**")
        line = f"{words[item['requirement_level']]} · {badge} · {evidence}"
        if item.get("due_date"):
            line = f"{line} · {words['due']} {item['due_date']}"
        st.caption(line)
        consequence = display_consequence(item, words)
        if consequence:
            st.caption(f"{words['consequence']}: {consequence}")

        progress = st.selectbox(
            words["progress"],
            options=CHECKLIST_PROGRESS,
            index=CHECKLIST_PROGRESS.index(item["progress"]),
            format_func=lambda value: words[f"progress_{value}"],
            key=f"progress_{item['item_id']}",
        )
        note = ""
        if progress == "not_applicable":
            note = st.text_input(
                words["not_applicable_reason"],
                value=item.get("note") or "",
                key=f"note_{item['item_id']}",
            )
        if progress != item["progress"] or (note and note != (item.get("note") or "")):
            if st.button(words["save_task"], key=f"save_{item['item_id']}"):
                try:
                    actions.set_checklist_progress(
                        trip_id=trip.trip_id,
                        item_id=item["item_id"],
                        progress=progress,
                        note=note or None,
                    )
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.session_state[flash_key] = words["task_saved"]
                    st.rerun()

        with st.expander(words["evidence"]):
            if item.get("expected_authority"):
                st.caption(
                    f"{words['expected_authority']}: "
                    f"{words.get(item['expected_authority'], item['expected_authority'])}"
                )
            if item["evidence_state"] == "verified":
                st.markdown(f"{item.get('source_url')}")
                st.caption(f"{words['last_checked']}: {item.get('last_checked_at')}")
            else:
                st.caption(words["evidence_verification_needed_help"])
            url = st.text_input(
                words["source_url"],
                value=item.get("source_url") or "",
                key=f"url_{item['item_id']}",
            )
            authority = st.selectbox(
                words["authority_type"],
                options=CHECKLIST_AUTHORITIES,
                index=(
                    CHECKLIST_AUTHORITIES.index(item["authority_type"])
                    if item.get("authority_type") in CHECKLIST_AUTHORITIES
                    else 0
                ),
                format_func=lambda value: words.get(value, value),
                key=f"authority_{item['item_id']}",
            )
            if st.button(words["record_evidence"], key=f"verify_{item['item_id']}"):
                try:
                    actions.record_checklist_evidence(
                        trip_id=trip.trip_id,
                        item_id=item["item_id"],
                        source_url=url,
                        authority_type=authority,
                    )
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.session_state[flash_key] = words["evidence_recorded"]
                    st.rerun()

        if st.button(words["dismiss_task"], key=f"dismiss_{item['item_id']}"):
            actions.set_checklist_dismissed(
                trip_id=trip.trip_id, item_id=item["item_id"], dismissed=True
            )
            st.session_state[flash_key] = words["task_dismissed"]
            st.rerun()


def _render_fallback(fallback: dict, language: str) -> None:
    """The half-day's fallback, with its trigger, swap, and displaced selection."""

    words = TEXT[language]
    with st.container(border=True):
        st.markdown(
            f"**{words['fallback']}** · {words['fallback_trigger']}: "
            f"{_optimizer_code(fallback.get('trigger') or 'unknown', language)}"
        )
        st.caption(
            f"{fallback['primary_name']} → {fallback['replacement_name']}"
            + (f" · {fallback['replacement_start']}" if fallback.get("replacement_start") else "")
            + (f" · {words['day_reoptimized']}" if fallback.get("day_reoptimized") else "")
        )
        if fallback.get("displaced_consequence"):
            st.caption(
                f"{words['consequence']}: "
                f"{_optimizer_code(fallback['displaced_consequence'], language)}"
            )


def _render_plan_item(item: dict, language: str) -> None:
    """One compact export-snapshot row; details stay behind progressive disclosure."""

    words = TEXT[language]
    clock = f"{item['start']}–{item['end']}"
    length = f"{item['duration_minutes']} {words['minutes']}"
    state = words[f"state_{item['status']}"]
    if item["type"] == "visit":
        st.markdown(
            f"**{clock}** · {words['stop']} {item['stop_number']} · {item['display_name']}"
        )
        local = f" · {item['local_name']}" if item.get("local_name") else ""
        st.caption(f"{state} · {length}{local}")
        with st.expander(words["details"]):
            st.markdown(
                f"- {words['choice']}: {words.get(item['priority'], item['priority'])}"
            )
            if item.get("address"):
                st.markdown(f"- {item['address']}")
            if not item["opening_verified"]:
                st.markdown(f"- {words['opening_unverified']}")
    elif item["type"] == "travel":
        st.markdown(f"{clock} · {item['origin_name']} → {item['destination_name']}")
        st.caption(
            f"{state} · {words['travel_mode']} {item.get('mode') or '?'} · {length} · "
            f"{words['walk_portion']} {item['walking_minutes']} {words['minutes']}"
        )
        with st.expander(words["details"]):
            st.markdown(
                "- "
                + (
                    words["sightseeing_walk"]
                    if item["sightseeing_walk"]
                    else words["plain_transfer"]
                )
            )
            if item.get("distance_m"):
                st.markdown(f"- {words['distance']}: {item['distance_m']} m")
            if item.get("transfers") is not None:
                st.markdown(f"- {words['transfers']}: {item['transfers']}")
            if item["boarding_buffer_minutes"]:
                st.markdown(
                    f"- {words['boarding_buffer']}: "
                    f"{item['boarding_buffer_minutes']} {words['minutes']}"
                )
    else:
        reason = _optimizer_code(item.get("reason") or "buffer", language)
        st.caption(f"{clock} · {reason} · {length}")


st.set_page_config(page_title="Personal Travel Planner", page_icon="🧭", layout="centered")
language = st.sidebar.radio(
    "Language / ภาษา",
    options=("en", "th"),
    format_func=lambda value: "English" if value == "en" else "ไทย",
    horizontal=True,
)
copy = TEXT[language]
actions = PlannerActions(os.environ.get("TOURIST_DB_PATH", "data/tourist.sqlite3"))

st.title(copy["title"])
st.caption(copy["caption"])

with st.form("create_trip"):
    st.subheader(copy["new_trip"])
    name = st.text_input(copy["trip_name"], key="trip_name")
    destination = st.text_input(copy["destination"], key="destination")
    planning_mode = st.selectbox(
        copy["mode"],
        options=("explore_first", "ready_to_schedule"),
        format_func=lambda value: copy[value],
        key="planning_mode",
    )
    submitted = st.form_submit_button(copy["create"])

if submitted:
    if not destination.strip():
        st.error(copy["destination_required"])
    else:
        try:
            created = actions.create_trip(
                name=name,
                destination=destination,
                planning_mode=planning_mode,
                language=language,
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state["selected_trip_id"] = created.trip_id
            st.success(copy["created"])

trips = actions.list_trips()
st.divider()
st.subheader(copy["saved_trips"])
if not trips:
    st.info(copy["empty"])
    st.stop()

trip_ids = [trip.trip_id for trip in trips]
selected_id = st.session_state.get("selected_trip_id")
selected_index = trip_ids.index(selected_id) if selected_id in trip_ids else 0
selected_id = st.selectbox(
    copy["resume"],
    options=trip_ids,
    index=selected_index,
    format_func=lambda trip_id: next(
        f"{trip.name} — {trip.destination}" for trip in trips if trip.trip_id == trip_id
    ),
    key="resume_trip",
)
st.session_state["selected_trip_id"] = selected_id
trip = next(trip for trip in trips if trip.trip_id == selected_id)
active_plan = actions.get_active_plan(trip.trip_id)
status_column, mode_column = st.columns(2)
status_column.metric(copy["status"], copy["ready"] if active_plan else copy["draft"])
mode_column.metric(copy["mode_label"], copy[trip.planning_mode])
if active_plan:
    st.caption(f"{copy['active_plan']}: {active_plan.version_id}")
else:
    st.info(copy["no_plan"])

# Readiness summary on the home surface; overdue work shows whenever the app opens.
readiness = (
    actions.checklist_readiness(trip.trip_id)
    if actions.get_setup(trip.trip_id)
    else None
)
if readiness and readiness["counts"]["total"]:
    st.markdown(
        f"**{copy['readiness']}: {copy[readiness['state']]}** · "
        f"{copy['open_tasks']} {readiness['counts']['open']}"
    )
    for item in readiness["overdue"][:3]:
        st.warning(
            f"{copy['overdue']}: {display_title(item, copy)} · {item['due_date']}"
        )
    for item in readiness["due_soon"][:3]:
        st.info(
            f"{copy['due_soon']}: {display_title(item, copy)} · {item['due_date']}"
        )

setup = actions.get_setup(trip.trip_id)
setup_payload = setup.snapshot.as_dict() if setup else _empty_setup(trip.planning_mode)
basics = setup_payload["trip_basics"]
owner = setup_payload["owner"]
saved_members = setup_payload.get("travellers", [])

st.divider()
st.subheader(copy["setup"])
st.caption(copy["setup_help"])
member_count = int(
    st.number_input(
        copy["member_count"],
        min_value=0,
        max_value=8,
        value=len(saved_members),
        step=1,
        key=f"member_count_{trip.trip_id}",
    )
)

all_member_tags = tuple(dict.fromkeys(MAIN_STYLE_TAGS + ALSO_ENJOY_TAGS + AVOID_TAGS + COMFORT_TAGS))
with st.form(f"setup_form_{trip.trip_id}"):
    st.markdown(f"#### {copy['trip_basics']}")
    has_dates = st.checkbox(
        copy["dates_known"],
        value=bool(basics.get("start_date") and basics.get("end_date")),
        key=f"has_dates_{trip.trip_id}",
    )
    start_column, end_column = st.columns(2)
    start_value = start_column.date_input(
        copy["start_date"],
        value=_date_value(basics.get("start_date")),
        disabled=not has_dates,
        key=f"start_date_{trip.trip_id}",
    )
    end_value = end_column.date_input(
        copy["end_date"],
        value=_date_value(basics.get("end_date")),
        disabled=not has_dates,
        key=f"end_date_{trip.trip_id}",
    )
    arrival_column, departure_column = st.columns(2)
    with arrival_column:
        has_arrival = st.checkbox(
            copy["arrival_known"],
            value=bool(basics.get("arrival_time")),
            key=f"has_arrival_{trip.trip_id}",
        )
        arrival_value = st.time_input(
            copy["arrival_time"],
            value=_time_value(basics.get("arrival_time"), time(17, 0)),
            disabled=not has_arrival,
            key=f"arrival_time_{trip.trip_id}",
        )
    with departure_column:
        has_departure = st.checkbox(
            copy["departure_known"],
            value=bool(basics.get("departure_time")),
            key=f"has_departure_{trip.trip_id}",
        )
        departure_value = st.time_input(
            copy["departure_time"],
            value=_time_value(basics.get("departure_time"), time(11, 0)),
            disabled=not has_departure,
            key=f"departure_time_{trip.trip_id}",
        )
    accommodation_options = ("unknown", "not_booked", "booked")
    accommodation_status = st.selectbox(
        copy["accommodation"],
        accommodation_options,
        index=accommodation_options.index(basics.get("accommodation_status", "unknown")),
        format_func=lambda value: ACCOMMODATION_TEXT[language][value],
        key=f"accommodation_{trip.trip_id}",
    )

    st.markdown(f"#### {copy['owner_style']}")
    owner_age = int(
        st.number_input(
            copy["owner_age"],
            min_value=0,
            max_value=120,
            value=int(owner.get("age") or 0),
            step=1,
            key=f"owner_age_{trip.trip_id}",
        )
    )
    main_style = st.multiselect(
        copy["main_style"],
        MAIN_STYLE_TAGS,
        default=owner.get("main_style", []),
        format_func=lambda value: TAG_TEXT[language][value],
        key=f"main_style_{trip.trip_id}",
    )
    also_enjoy = st.multiselect(
        copy["also_enjoy"],
        ALSO_ENJOY_TAGS,
        default=owner.get("also_enjoy", []),
        format_func=lambda value: TAG_TEXT[language][value],
        key=f"also_enjoy_{trip.trip_id}",
    )
    avoid = st.multiselect(
        copy["avoid"],
        AVOID_TAGS,
        default=owner.get("avoid", []),
        format_func=lambda value: TAG_TEXT[language][value],
        key=f"avoid_{trip.trip_id}",
    )
    comfort = st.multiselect(
        copy["comfort"],
        COMFORT_TAGS,
        default=owner.get("comfort", []),
        format_func=lambda value: TAG_TEXT[language][value],
        key=f"comfort_{trip.trip_id}",
    )
    owner_description = st.text_area(
        copy["description"],
        value=owner.get("description", ""),
        key=f"owner_description_{trip.trip_id}",
    )

    st.markdown(f"#### {copy['travellers']}")
    member_inputs = []
    for index in range(member_count):
        saved = saved_members[index] if index < len(saved_members) else {}
        with st.expander(f"{copy['member']} {index + 1}", expanded=index < 2):
            member_inputs.append(
                {
                    "traveller_id": saved.get("traveller_id", f"member_{index + 1}"),
                    "label": st.text_input(
                        copy["member_name"],
                        value=saved.get("label", f"Traveller {index + 1}"),
                        key=f"member_label_{trip.trip_id}_{index}",
                    ),
                    "age": int(
                        st.number_input(
                            copy["member_age"],
                            min_value=0,
                            max_value=120,
                            value=int(saved.get("age") or 0),
                            step=1,
                            key=f"member_age_{trip.trip_id}_{index}",
                        )
                    ),
                    "tags": st.multiselect(
                        copy["member_tags"],
                        all_member_tags,
                        default=saved.get("tags", []),
                        format_func=lambda value: TAG_TEXT[language][value],
                        key=f"member_tags_{trip.trip_id}_{index}",
                    ),
                    "description": st.text_area(
                        copy["member_notes"],
                        value=saved.get("description", ""),
                        key=f"member_notes_{trip.trip_id}_{index}",
                    ),
                    "must_respect": st.text_area(
                        copy["member_must"],
                        value="\n".join(saved.get("must_respect", [])),
                        key=f"member_must_{trip.trip_id}_{index}",
                    ).splitlines(),
                }
            )

    st.markdown(f"#### {copy['requirements']}")
    owner_must_respect = st.text_area(
        copy["owner_must"],
        value="\n".join(owner.get("must_respect", [])),
        key=f"owner_must_{trip.trip_id}",
    )
    save_draft, confirm_setup = st.columns(2)
    draft_submitted = save_draft.form_submit_button(copy["save_draft"])
    confirm_submitted = confirm_setup.form_submit_button(copy["confirm"])

if draft_submitted or confirm_submitted:
    if confirm_submitted and not main_style:
        st.error(copy["main_required"])
    else:
        try:
            setup = actions.save_setup(
                trip_id=trip.trip_id,
                owner_age=owner_age or None,
                main_style=main_style,
                also_enjoy=also_enjoy,
                avoid=avoid,
                comfort=comfort,
                owner_description=owner_description,
                owner_must_respect=owner_must_respect,
                travellers=member_inputs,
                start_date=start_value.isoformat() if has_dates else None,
                end_date=end_value.isoformat() if has_dates else None,
                arrival_time=arrival_value.strftime("%H:%M") if has_arrival else None,
                departure_time=departure_value.strftime("%H:%M") if has_departure else None,
                accommodation_status=accommodation_status,
                confirmed=confirm_submitted,
            )
        except ValueError as error:
            st.error(str(error))
        else:
            setup_payload = setup.snapshot.as_dict()
            st.success(copy["confirmed"] if setup.confirmed else copy["draft_saved"])

if setup:
    st.markdown(f"#### {copy['review']}")
    review_owner = setup_payload["owner"]
    review_basics = setup_payload["trip_basics"]
    setup_state, people, preference_count = st.columns(3)
    setup_state.metric(
        copy["setup_state"], copy["confirmed_setup"] if setup.confirmed else copy["draft_setup"]
    )
    people.metric(copy["people"], 1 + len(setup_payload.get("travellers", [])))
    preference_count.metric(
        copy["preferences"],
        len(review_owner["main_style"])
        + len(review_owner["also_enjoy"])
        + len(review_owner["avoid"])
        + len(review_owner["comfort"]),
    )
    st.write(" · ".join(TAG_TEXT[language][tag] for tag in review_owner["main_style"]))
    if not review_basics.get("start_date"):
        st.warning(copy["no_dates"])

latest = actions.get_latest_discovery(trip.trip_id)
catalog = []
st.divider()
st.subheader(copy["discover_title"])
st.caption(copy["discover_help"])
st.caption(copy["osm_notice"])

if setup and setup.confirmed:
    discover_column, refresh_column = st.columns(2)
    discover_clicked = discover_column.button(
        copy["discover"], key=f"discover_{trip.trip_id}", width="stretch"
    )
    refresh_clicked = refresh_column.button(
        copy["refresh"],
        key=f"refresh_{trip.trip_id}",
        width="stretch",
        disabled=latest is None,
    )
    if discover_clicked or refresh_clicked:
        with st.spinner(copy["discovering"]):
            latest = actions.discover_places(
                trip_id=trip.trip_id, force_refresh=refresh_clicked
            )
        st.success(copy["discovery_saved"])

if latest:
    report = latest.report.as_dict()
    catalog = latest.candidates.as_dict()["candidates"]
    if not setup or latest.setup_sha256 != setup.snapshot.sha256:
        st.warning(copy["stale_setup"])
    if latest.status in {"unavailable", "error", "stale"}:
        st.warning(copy["provider_gap"])
    st.markdown(f"#### {copy['coverage']}")
    provider_status, candidate_count, duplicate_count, cell_count = st.columns(4)
    provider_status.metric(copy["provider_status"], latest.status)
    candidate_count.metric(copy["candidates"], report["canonical_candidates"])
    duplicate_count.metric(copy["duplicates"], report["duplicates_merged"])
    cell_count.metric(copy["cells"], report["geographic_cells_with_candidates"])
    st.caption(copy["unranked"])
    if catalog:
        with st.expander(copy["browse_all"], expanded=False):
            rows = []
            for candidate in catalog:
                names = candidate.get("names", {})
                alias = candidate["provider_aliases"][0]
                rows.append(
                    {
                        copy["name"]: _candidate_name(candidate, language),
                        copy["local_name"]: names.get("local") or candidate["name"],
                        copy["category"]: _category_text(candidate["category"], language),
                        copy["opening"]: candidate["operational_evidence"]["opening_hours"][
                            "state"
                        ],
                        copy["source"]: alias.get("source_url"),
                    }
                )
            st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.info(copy["no_candidates"])
    if report.get("attribution"):
        st.markdown(
            f"[{report['attribution']}]({report['license_url']}) · {report['license']}"
        )
    with st.expander(copy["details"]):
        st.json(report)

st.divider()
st.subheader(copy["ranking_title"])
st.caption(copy["ranking_help"])
st.caption(copy["formula_note"])
flash_key = f"choice_flash_{trip.trip_id}"
if flash := st.session_state.pop(flash_key, None):
    st.success(copy[flash])

ranking = None
if catalog:
    try:
        ranking = actions.rank_candidates(trip.trip_id)
    except ValueError as error:
        st.info(f"{copy['ranking_wait']} ({error})")
else:
    st.info(copy["ranking_wait"])

if ranking:
    candidate_by_id = {candidate["place_id"]: candidate for candidate in catalog}
    saved_choices = {
        choice.place_id: choice for choice in actions.list_candidate_choices(trip.trip_id)
    }
    lane_entries = {
        "main_queue": ranking["lanes"]["main_queue"],
        "city_icons": [
            {"place_id": place_id, "role": "city_icon"}
            for place_id in ranking["lanes"]["city_icons"]
        ],
        "worth_it_if": [
            {"place_id": place_id, "role": "worth_it_if"}
            for place_id in ranking["lanes"]["worth_it_if"]
        ],
        "local_alternatives": [
            {**entry, "role": "local_alternative"}
            for entry in ranking["lanes"]["local_alternatives"]
        ],
        "browse_all": [
            {"place_id": place_id, "role": "browse_all"}
            for place_id in ranking["lanes"]["browse_all"]
        ],
    }
    lane = st.selectbox(
        copy["lane"],
        options=tuple(lane_entries),
        format_func=lambda value: f"{copy[value]} ({len(lane_entries[value])})",
        key=f"ranking_lane_{trip.trip_id}",
    )
    entries = lane_entries[lane]
    if not entries:
        st.info(copy["no_lane_cards"])
    else:
        entry_by_id = {entry["place_id"]: entry for entry in entries}
        card_id = st.selectbox(
            copy["select_card"],
            options=[entry["place_id"] for entry in entries],
            format_func=lambda place_id: (
                f"{_candidate_name(candidate_by_id[place_id], language)} · "
                f"{ranking['cards'][place_id]['total_score']:.1f}/100"
            ),
            key=f"ranking_card_{trip.trip_id}_{lane}",
        )
        candidate = candidate_by_id[card_id]
        card = ranking["cards"][card_id]
        entry = entry_by_id[card_id]
        local_name = candidate.get("names", {}).get("local")
        st.markdown(f"### {_candidate_name(candidate, language)}")
        if local_name and local_name != _candidate_name(candidate, language):
            st.caption(local_name)
        st.caption(_category_text(candidate["category"], language))
        if photo_url := _photo_url(candidate.get("photo_reference")):
            st.image(photo_url, caption=copy["photo_source"], width="stretch")
        else:
            st.caption(copy["photo_unavailable"])
        if entry["role"] == "protected_exploration":
            st.info(copy["exploration_card"])
        if card["is_city_icon"]:
            st.info(copy["icon_card"])
        if entry.get("alternative_to"):
            compared = candidate_by_id.get(entry["alternative_to"])
            if compared:
                st.caption(
                    f"{copy['local_alternatives']}: "
                    f"{_candidate_name(compared, language)}"
                )

        score_column, duration_column, feasibility_column = st.columns(3)
        score_column.metric(copy["score"], f"{card['total_score']:.1f}/100")
        duration = card["duration_estimate"]
        duration_column.metric(
            copy["duration"],
            f"{duration['minimum_minutes']}–{duration['maximum_minutes']} {copy['minutes']}",
        )
        feasibility_column.metric(copy["feasibility"], copy["not_evaluated"])
        st.caption(copy["planner_estimate"])

        if card["matched_tags"]:
            st.write(
                f"**{copy['matched_tags']}:** "
                + " · ".join(
                    TAG_TEXT[language].get(tag, tag) for tag in card["matched_tags"]
                )
            )
        explanation_columns = st.columns(3)
        with explanation_columns[0]:
            st.markdown(f"**{copy['why']}**")
            for code in card["why_shown"]:
                st.markdown(f"- {_explain(code, language)}")
        with explanation_columns[1]:
            st.markdown(f"**{copy['pros']}**")
            for code in card["pros"]:
                st.markdown(f"- {_explain(code, language)}")
        with explanation_columns[2]:
            st.markdown(f"**{copy['cons']}**")
            for code in card["cons"]:
                st.markdown(f"- {_explain(code, language)}")

        with st.expander(copy["breakdown"]):
            st.dataframe(
                [
                    {
                        copy["dimension"]: DIMENSION_TEXT[language][dimension],
                        copy["points"]: values["score"],
                        copy["maximum"]: values["max"],
                    }
                    for dimension, values in card["dimensions"].items()
                ],
                hide_index=True,
                width="stretch",
            )
            st.markdown(f"**{copy['deductions']}**")
            if card["deductions"]:
                for deduction in card["deductions"]:
                    st.markdown(
                        f"- −{deduction['points']:.1f}: "
                        f"{_explain(deduction['code'], language)}"
                    )
            else:
                st.caption(copy["no_deductions"])

        evidence_column, rating_column = st.columns(2)
        opening_state = candidate["operational_evidence"]["opening_hours"]["state"]
        evidence_column.write(f"**{copy['opening']}:** {opening_state}")
        evidence_column.write(f"**{copy['route_effort']}:** {copy['not_routed']}")
        rating_column.write(f"**{copy['source_rating']}:** {copy['not_enriched']}")
        alias = candidate["provider_aliases"][0]
        if alias.get("source_url"):
            st.markdown(f"[{copy['source']}]({alias['source_url']})")

        existing_choice = saved_choices.get(card_id)
        if existing_choice:
            st.caption(
                f"{copy['current_choice']}: {copy[existing_choice.action]}"
                + (
                    f" · {REJECTION_TEXT[language][existing_choice.reason]}"
                    if existing_choice.reason
                    else ""
                )
            )
        reason_options = (None, "too_crowded", "too_expensive", "too_tiring", "wrong_vibe", "weak_value", "already_seen")
        rejection_reason = st.selectbox(
            copy["rejection_reason"],
            options=reason_options,
            format_func=lambda value: REJECTION_TEXT[language][value],
            key=f"rejection_reason_{trip.trip_id}_{card_id}",
        )
        action_columns = st.columns(4)
        clicked_action = None
        for column, action in zip(
            action_columns,
            ("must_do", "interested", "maybe", "not_for_trip"),
            strict=True,
        ):
            if column.button(
                copy[action],
                key=f"choice_{action}_{trip.trip_id}_{card_id}",
                width="stretch",
            ):
                clicked_action = action
        if clicked_action:
            try:
                actions.save_candidate_choice(
                    trip_id=trip.trip_id,
                    place_id=card_id,
                    action=clicked_action,
                    reason=rejection_reason if clicked_action == "not_for_trip" else None,
                )
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state[flash_key] = "choice_saved"
                st.rerun()
        if existing_choice and st.button(
            copy["clear_choice"], key=f"clear_choice_{trip.trip_id}_{card_id}"
        ):
            actions.clear_candidate_choice(trip_id=trip.trip_id, place_id=card_id)
            st.session_state[flash_key] = "choice_cleared"
            st.rerun()

    with st.expander(copy["browse_all"], expanded=False):
        st.caption(copy["browse_notice"])
        st.dataframe(
            [
                {
                    copy["name"]: _candidate_name(candidate_by_id[place_id], language),
                    copy["local_name"]: candidate_by_id[place_id]
                    .get("names", {})
                    .get("local"),
                    copy["category"]: _category_text(
                        candidate_by_id[place_id]["category"], language
                    ),
                    copy["score"]: ranking["cards"][place_id]["total_score"],
                    copy["choice"]: copy[saved_choices[place_id].action]
                    if place_id in saved_choices
                    else "",
                    copy["feasibility"]: copy["not_evaluated"],
                }
                for place_id in ranking["lanes"]["browse_all"]
            ],
            hide_index=True,
            width="stretch",
        )

    with st.expander(copy["group_weights"], expanded=False):
        member_labels = {"owner": "Owner" if language == "en" else "เจ้าของทริป"}
        member_labels.update(
            {
                member["traveller_id"]: member["label"]
                for member in setup_payload.get("travellers", [])
            }
        )
        st.dataframe(
            [
                {
                    copy["member"]: member_labels.get(person, person),
                    "Base": weight,
                    "Effective": ranking["effective_group_weights"].get(person, 0),
                }
                for person, weight in ranking["base_group_weights"].items()
            ],
            hide_index=True,
            width="stretch",
        )
        st.json(
            {
                "formula_weights": ranking["formula_weights"],
                "learned_category_weights": ranking["learned_category_weights"],
            }
        )

    st.markdown(f"#### {copy['all_choices']}")
    if saved_choices:
        st.dataframe(
            [
                {
                    copy["name"]: _candidate_name(choice.candidate.as_dict(), language),
                    copy["choice"]: copy[choice.action],
                    copy["rejection_reason"]: REJECTION_TEXT[language][choice.reason]
                    if choice.reason
                    else "",
                }
                for choice in saved_choices.values()
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption(copy["no_selected"])

    st.markdown(f"#### {copy['reconciliation']}")
    st.caption(copy["reconciliation_help"])
    if ranking["reconciliation"]:
        st.dataframe(
            [
                {
                    copy["name"]: _candidate_name(
                        saved_choices[item["place_id"]].candidate.as_dict(), language
                    ),
                    copy["choice"]: copy[item["choice"]],
                    copy["feasibility"]: copy["pending_optimizer"],
                    copy["present_latest"]: "✓"
                    if item["present_in_latest_discovery"]
                    else "—",
                    copy["next_step"]: copy["run_optimizer"],
                }
                for item in ranking["reconciliation"]
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.info(copy["no_selected"])

st.divider()
st.subheader(copy["optimizer_title"])
st.caption(copy["optimizer_help"])
optimizer_flash_key = f"optimizer_flash_{trip.trip_id}"
if optimizer_flash := st.session_state.pop(optimizer_flash_key, None):
    st.success(copy[optimizer_flash])

selected_for_optimizer = [
    choice
    for choice in actions.list_candidate_choices(trip.trip_id)
    if choice.action in {"must_do", "interested", "maybe"}
]
generate_plan = st.button(
    copy["generate_plan"],
    key=f"generate_plan_{trip.trip_id}",
    width="stretch",
    disabled=not selected_for_optimizer,
)
if not selected_for_optimizer:
    st.info(copy["choose_before_plan"])
if generate_plan:
    try:
        with st.spinner(copy["optimizing"]):
            actions.generate_plan_preview(trip.trip_id)
    except ValueError as error:
        st.error(str(error))
    else:
        st.session_state[optimizer_flash_key] = "preview_saved"
        st.rerun()

preview = actions.get_plan_preview(trip.trip_id)
if preview:
    proposal = preview.proposal.as_dict()
    if proposal["mode"] == "stay_recommendation":
        st.markdown(f"#### {copy['stay_recommendation']}")
        st.dataframe(
            [
                {
                    copy["stay_option"]: copy.get(item["id"], item["id"]),
                    copy["days"]: item["days"],
                    copy["daily_capacity"]: f"{item['daily_capacity_minutes']} {copy['minutes']}",
                }
                for item in proposal["stay_recommendations"]
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        variants = proposal["variants"]
        variant_id = st.selectbox(
            copy["variant"],
            options=[item["variant_id"] for item in variants],
            format_func=lambda value: copy[value],
            key=f"plan_variant_{trip.trip_id}",
        )
        variant = next(item for item in variants if item["variant_id"] == variant_id)
        st.markdown(f"#### {copy[variant_id]} · {copy[variant['status']]}")
        metric_columns = st.columns(5)
        for column, label, value in zip(
            metric_columns,
            (
                "scheduled_visits",
                "travel_minutes",
                "walking_minutes",
                "plain_walking_minutes",
                "buffer_minutes",
            ),
            (
                variant["metrics"]["scheduled_visits"],
                variant["metrics"]["travel_minutes"],
                variant["metrics"]["walking_minutes"],
                variant["metrics"]["plain_walking_minutes"],
                variant["metrics"]["buffer_minutes"],
            ),
            strict=True,
        ):
            column.metric(copy[label], value)
        if (
            variant["metrics"]["scheduled_visits"]
            and variant["objective_improved_or_equal_to_greedy"]
        ):
            st.success(copy["greedy_check"])
        if variant["stopped_at_limit"]:
            st.warning(copy["optimizer_limit"])

        if variant["warnings"]:
            with st.expander(copy["optimizer_warning"], expanded=True):
                for warning in variant["warnings"]:
                    st.markdown(f"- {_optimizer_code(warning, language)}")

        st.markdown(f"#### {copy['optimizer_reconciliation']}")
        st.dataframe(
            [
                {
                    copy["name"]: item.get("names", {}).get(language)
                    or item.get("names", {}).get("en")
                    or item.get("names", {}).get("local")
                    or item["name"],
                    copy["choice"]: copy.get(item["priority"], item["priority"]),
                    copy["feasibility"]: copy[item["status"]],
                    copy["reason"]: _optimizer_code(item["reason"], language),
                    copy["consequence"]: _optimizer_code(
                        item["consequence"], language
                    ),
                }
                for item in variant["reconciliation"]
            ],
            hide_index=True,
            width="stretch",
        )

        timeline_rows = [
            {
                copy["days"]: day["date"],
                copy["start"]: item["start"],
                copy["end"]: item["end"],
                copy["item_type"]: item["type"],
                copy["place_or_leg"]: _plan_item_name(item, language),
                copy["duration"]: f"{item['duration_minutes']} {copy['minutes']}",
            }
            for day in variant["days"]
            for item in day["items"]
        ]
        if timeline_rows:
            st.markdown(f"#### {copy['timeline']}")
            st.dataframe(timeline_rows, hide_index=True, width="stretch")
        else:
            st.warning(copy["no_schedule"])

        if variant["status"] != "ready":
            st.caption(copy["activation_disabled"])
        activate = st.button(
            copy["activate_plan"],
            key=f"activate_plan_{trip.trip_id}_{variant_id}",
            width="stretch",
            disabled=variant["status"] != "ready",
        )
        if activate:
            try:
                actions.activate_plan_preview(
                    trip_id=trip.trip_id, variant_id=variant_id
                )
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state[optimizer_flash_key] = "plan_activated"
                st.rerun()

st.subheader(copy["use_title"])
st.caption(copy["use_help"])

if actions.get_active_plan(trip.trip_id) is None:
    st.info(copy["no_active_plan"])
else:
    export_snapshot = actions.build_export_snapshot(trip.trip_id, language=language)
    export = export_snapshot.as_dict()
    stamp = export["stamp"]
    readiness = export["readiness"]

    st.markdown(
        f"**{copy[stamp['variant_id']]}** · {copy['readiness']}: "
        f"{copy[readiness['state']]}"
    )
    st.caption(
        f"{copy['active_plan']} `{stamp['plan_version_id'][5:17]}` · "
        f"{copy['exported_at']} {stamp['exported_at'][:16]} · "
        f"{stamp['base_currency']} · {stamp['language'].upper()}"
    )
    if not stamp["is_active_plan"]:
        st.warning(copy["superseded_plan"])
    if readiness["capability_gaps"]:
        with st.expander(copy["capability_gaps"]):
            for gap in readiness["capability_gaps"]:
                st.markdown(f"- {_optimizer_code(gap, language)}")

    chosen_date = st.selectbox(
        copy["days"],
        options=[value["date"] for value in export["days"]],
        key=f"plan_day_{trip.trip_id}",
    )
    day = next(item for item in export["days"] if item["date"] == chosen_date)
    totals = day["totals"]
    st.markdown(
        f"**{day['start']}–{day['end']}** · {copy['scheduled_visits']} "
        f"{totals['scheduled_visits']} · {copy['visit_minutes']} "
        f"{totals['visit_minutes']} {copy['minutes']} · {copy['travel_minutes']} "
        f"{totals['travel_minutes']} {copy['minutes']}"
    )
    st.caption(
        f"{copy['walking_minutes']} {totals['walking_minutes']} {copy['minutes']} "
        f"({copy['rewarding_walking_minutes']} {totals['rewarding_walking_minutes']} · "
        f"{copy['plain_walking_minutes']} {totals['plain_walking_minutes']}) · "
        f"{copy['buffer_minutes']} {totals['buffer_minutes']} {copy['minutes']}"
    )
    if day["highest_risk"]:
        st.warning(
            f"{copy['highest_risk']}: "
            f"{copy['state_' + day['highest_risk']['status']]}"
        )

    timeline_tab, map_tab = st.tabs([copy["timeline"], copy["tab_map"]])
    with timeline_tab:
        if not day["items"]:
            st.warning(copy["no_schedule"])
        for part in ("morning", "afternoon"):
            part_items = [
                item for item in day["items"] if half_day(item["start"]) == part
            ]
            if not part_items:
                continue
            for plan_item in part_items:
                _render_plan_item(plan_item, language)
            for fallback in day["fallbacks"]:
                if fallback["half_day"] == part:
                    _render_fallback(fallback, language)
        for fallback in day["fallbacks"]:
            if fallback["half_day"] not in ("morning", "afternoon"):
                _render_fallback(fallback, language)
    with map_tab:
        anchor = export["accommodation"]["anchor"]
        points = [
            {
                "latitude": stop["latitude"],
                "longitude": stop["longitude"],
                "colour": "#B4532A" if stop["status"] == "locked" else "#2A6FB4",
                "radius": 90 if stop["status"] == "locked" else 60,
            }
            for stop in day["stops"]
            if stop["latitude"] is not None and stop["longitude"] is not None
        ]
        if anchor and anchor["latitude"] is not None and anchor["longitude"] is not None:
            points.append(
                {
                    "latitude": anchor["latitude"],
                    "longitude": anchor["longitude"],
                    "colour": "#E0A32E",
                    "radius": 120,
                }
            )
        if points:
            st.map(
                {key: [point[key] for point in points] for key in points[0]},
                latitude="latitude",
                longitude="longitude",
                color="colour",
                size="radius",
            )
        else:
            st.info(copy["map_no_coordinates"])
        # Text labels carry the same distinctions as the marker colours.
        if anchor:
            st.markdown(f"**{copy['hotel_anchor']}** · {anchor['display_name']}")
        for stop in day["stops"]:
            st.markdown(
                f"{copy['stop']} {stop['stop_number']} · {stop['display_name']} · "
                f"{copy['state_' + stop['status']]}"
            )

    st.markdown(f"#### {copy['downloads']}")
    version_tag = stamp["plan_version_id"][5:17]
    try:
        documents = _plan_documents(export, export_snapshot.sha256, language)
        poster = _day_poster(export, export_snapshot.sha256, language, day["date"])
    except ValueError as error:
        st.error(str(error))
    else:
        st.download_button(
            copy["poster"],
            data=poster,
            file_name=f"plan-{version_tag}-{day['date']}-poster.png",
            mime="image/png",
            key=f"poster_{trip.trip_id}",
            width="stretch",
        )
        st.download_button(
            copy["pdf"],
            data=documents["pdf"],
            file_name=f"plan-{version_tag}.pdf",
            mime="application/pdf",
            key=f"pdf_{trip.trip_id}",
            width="stretch",
        )
        st.download_button(
            copy["excel"],
            data=documents["xlsx"],
            file_name=f"plan-{version_tag}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"excel_{trip.trip_id}",
            width="stretch",
        )
        if export["checklist"]["items"]:
            st.download_button(
                copy["calendar"],
                data=documents["ics"],
                file_name=f"plan-{version_tag}-readiness.ics",
                mime="text/calendar",
                key=f"ics_{trip.trip_id}",
                width="stretch",
            )
        else:
            st.caption(copy["checklist_pending"])

    if export["unscheduled"]:
        with st.expander(f"{copy['unscheduled_choices']} ({len(export['unscheduled'])})"):
            st.dataframe(
                [
                    {
                        copy["name"]: item["display_name"],
                        copy["choice"]: copy.get(item["priority"], item["priority"]),
                        copy["reason"]: _optimizer_code(item["reason"], language),
                        copy["consequence"]: _optimizer_code(
                            item["consequence"], language
                        ),
                    }
                    for item in export["unscheduled"]
                ],
                hide_index=True,
                width="stretch",
            )

st.subheader(copy["checklist"])
st.caption(copy["checklist_help"])
checklist_flash_key = f"checklist_flash_{trip.trip_id}"
if checklist_flash := st.session_state.pop(checklist_flash_key, None):
    st.success(checklist_flash)

if not actions.get_setup(trip.trip_id):
    st.info(copy["checklist_needs_setup"])
else:
    preview = actions.propose_checklist(trip.trip_id)
    pending = (
        len(preview["additions"])
        + len(preview["removals"])
        + len(preview["deadline_changes"])
    )
    if pending:
        # Nothing is applied silently: additions, removals, and deadline moves
        # are previewed first.
        with st.expander(f"{copy['checklist_preview']} ({pending})", expanded=True):
            for item in preview["additions"]:
                st.markdown(
                    f"➕ {display_title(item, copy)} · {copy[item['timing']]}"
                )
            for item in preview["removals"]:
                st.markdown(
                    f"➖ {display_title(item, copy)} · {copy['will_be_dismissed']}"
                )
            for change in preview["deadline_changes"]:
                st.markdown(
                    f"📅 {change['title']} · {change['from']['due_date'] or '—'} → "
                    f"{change['to']['due_date'] or '—'}"
                )
            if st.button(
                copy["apply_checklist"],
                key=f"apply_checklist_{trip.trip_id}",
                width="stretch",
            ):
                result = actions.apply_checklist_proposal(trip.trip_id)
                st.session_state[checklist_flash_key] = (
                    f"{copy['checklist_applied']} "
                    f"+{result['added']} / ~{result['deadlines_changed']} / "
                    f"-{result['dismissed']}"
                )
                st.rerun()
    else:
        st.caption(copy["checklist_current"])

    items = actions.list_checklist_items(trip.trip_id)
    active_items = [item for item in items if not item["dismissed"]]
    category_filter = st.multiselect(
        copy["category"],
        options=sorted({item["category"] for item in active_items}),
        format_func=lambda value: copy.get(value, value),
        key=f"checklist_categories_{trip.trip_id}",
    )
    shown = [
        item
        for item in active_items
        if not category_filter or item["category"] in category_filter
    ]

    for bucket in CHECKLIST_TIMING:
        bucket_items = [item for item in shown if item["timing"] == bucket]
        if not bucket_items:
            continue
        st.markdown(f"#### {copy[bucket]}")
        for item in sorted(bucket_items, key=lambda value: display_title(value, copy)):
            _render_checklist_item(actions, trip, item, language, checklist_flash_key)

    with st.expander(copy["add_task"]):
        new_title = st.text_input(copy["task_title"], key=f"task_title_{trip.trip_id}")
        new_category = st.selectbox(
            copy["category"],
            options=CHECKLIST_CATEGORIES,
            format_func=lambda value: copy.get(value, value),
            key=f"task_category_{trip.trip_id}",
        )
        new_timing = st.selectbox(
            copy["timing"],
            options=CHECKLIST_TIMING,
            format_func=lambda value: copy[value],
            key=f"task_timing_{trip.trip_id}",
        )
        new_level = st.selectbox(
            copy["requirement_level"],
            options=CHECKLIST_LEVELS,
            format_func=lambda value: copy[value],
            key=f"task_level_{trip.trip_id}",
        )
        new_consequence = st.text_input(
            copy["consequence"], key=f"task_consequence_{trip.trip_id}"
        )
        if st.button(copy["add_task"], key=f"add_task_{trip.trip_id}", width="stretch"):
            try:
                actions.save_checklist_item(
                    trip_id=trip.trip_id,
                    item={
                        "title": new_title,
                        "category": new_category,
                        "timing": new_timing,
                        "requirement_level": new_level,
                        "consequence": new_consequence,
                    },
                )
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state[checklist_flash_key] = copy["task_added"]
                st.rerun()

    dismissed = [item for item in items if item["dismissed"]]
    if dismissed:
        with st.expander(f"{copy['dismissed_history']} ({len(dismissed)})"):
            for item in dismissed:
                st.markdown(
                    f"- {display_title(item, copy)} · {copy[item['timing']]}"
                )
                if st.button(
                    copy["restore_task"],
                    key=f"restore_{item['item_id']}",
                ):
                    actions.set_checklist_dismissed(
                        trip_id=trip.trip_id, item_id=item["item_id"], dismissed=False
                    )
                    st.session_state[checklist_flash_key] = copy["task_restored"]
                    st.rerun()

st.subheader(copy["costs"])
st.caption(copy["costs_help"])
cost_flash_key = f"cost_flash_{trip.trip_id}"
if cost_flash := st.session_state.pop(cost_flash_key, None):
    st.success(cost_flash)

rate_snapshot = actions.get_rate_snapshot(trip.trip_id)
with st.expander(copy["rate_snapshot"], expanded=not rate_snapshot):
    if not rate_snapshot:
        st.info(copy["no_rates"])
    else:
        st.caption(
            f"{rate_snapshot['as_of']} · {rate_snapshot['source']}"
            + (f" · +{rate_snapshot['buffer_percent']}%" if rate_snapshot["buffer_percent"] else "")
        )
        st.dataframe(
            [
                {copy["rate_currency"]: code, copy["rate_value"]: value}
                for code, value in rate_snapshot["rates"].items()
            ],
            hide_index=True,
            width="stretch",
        )
    rate_currency = st.text_input(
        copy["rate_currency"], value="CNY", key=f"rate_cur_{trip.trip_id}"
    )
    rate_value = st.number_input(
        copy["rate_value"], min_value=0.0, value=5.0, step=0.01, key=f"rate_val_{trip.trip_id}"
    )
    rate_as_of = st.text_input(
        copy["rate_as_of"], value=date.today().isoformat(), key=f"rate_as_of_{trip.trip_id}"
    )
    rate_source = st.text_input(
        copy["rate_source"], value="", key=f"rate_src_{trip.trip_id}"
    )
    rate_buffer = st.number_input(
        copy["rate_buffer"], min_value=0.0, max_value=50.0, value=0.0, step=0.5,
        key=f"rate_buf_{trip.trip_id}",
    )
    if st.button(copy["save_rates"], key=f"save_rates_{trip.trip_id}", width="stretch"):
        merged = dict((rate_snapshot or {}).get("rates", {}))
        merged[rate_currency.strip().upper()] = rate_value
        try:
            actions.save_rate_snapshot(
                trip_id=trip.trip_id,
                rates=merged,
                as_of=rate_as_of,
                source=rate_source,
                buffer_percent=rate_buffer,
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state[cost_flash_key] = copy["rates_saved"]
            st.rerun()

cost_items = actions.list_cost_items(trip.trip_id)
if cost_items:
    totals = actions.cost_totals(trip.trip_id)
    st.markdown(
        f"**{copy['total_thb']} {totals['total_thb']:,.2f}** · "
        f"{copy['estimated_thb']} {totals['estimated_thb']:,.2f} · "
        f"{copy['paid_thb']} {totals['paid_thb']:,.2f}"
    )
    if totals["missing_rates"]:
        st.warning(f"{copy['rate_missing']}: {', '.join(totals['missing_rates'])}")
    for item in cost_items:
        with st.container(border=True):
            reported = item.get("reported_thb")
            headline = f"**{item['label']}** · {item['original_amount']:,.2f} {item['original_currency']}"
            if reported is not None:
                headline = f"{headline} → {reported:,.2f} THB"
            st.markdown(headline)
            marks = [copy.get(item["payment_state"], item["payment_state"]), copy.get(item["category"], item["category"])]
            if item["payment_state"] == "paid":
                marks.append(copy["locked_charge"])
            if item["rate_missing"]:
                marks.append(copy["rate_missing"])
            st.caption(" · ".join(marks))
            if st.button(copy["remove_cost"], key=f"rm_cost_{item['cost_id']}"):
                actions.delete_cost_item(trip_id=trip.trip_id, cost_id=item["cost_id"])
                st.session_state[cost_flash_key] = copy["cost_removed"]
                st.rerun()

with st.expander(copy["add_cost"]):
    cost_label = st.text_input(copy["cost_label"], key=f"cost_label_{trip.trip_id}")
    cost_amount = st.number_input(
        copy["cost_amount"], min_value=0.0, value=0.0, step=1.0, key=f"cost_amt_{trip.trip_id}"
    )
    cost_currency = st.text_input(
        copy["cost_currency"], value="THB", key=f"cost_cur_{trip.trip_id}"
    )
    cost_category = st.selectbox(
        copy["category"],
        options=COST_CATEGORIES,
        format_func=lambda value: copy.get(
            "accommodation_cost" if value == "accommodation" else
            "shopping_cost" if value == "shopping" else value, value
        ),
        key=f"cost_cat_{trip.trip_id}",
    )
    cost_state = st.selectbox(
        copy["cost_state"],
        options=COST_STATES,
        format_func=lambda value: copy.get(value, value),
        key=f"cost_state_{trip.trip_id}",
    )
    cost_actual = st.number_input(
        copy["cost_actual"], min_value=0.0, value=0.0, step=1.0, key=f"cost_act_{trip.trip_id}"
    )
    if st.button(copy["add_cost"], key=f"add_cost_{trip.trip_id}", width="stretch"):
        try:
            actions.save_cost_item(
                trip_id=trip.trip_id,
                item={
                    "label": cost_label,
                    "original_amount": cost_amount,
                    "original_currency": cost_currency,
                    "category": cost_category,
                    "payment_state": cost_state,
                    "actual_thb": cost_actual if cost_state == "paid" else None,
                },
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state[cost_flash_key] = copy["cost_added"]
            st.rerun()
