from __future__ import annotations
import logging
import re
from datetime import date, time, timedelta, timezone
from datetime import time as time_type
from src.control.voice_assistance.models import ainvoke_llm
from src.control.voice_assistance.prompts.booking_slot_selection_node_prompt import (
    LLM_ALTERNATE_DATE_SYSTEM,
    LLM_CONFIRM_SYSTEM,
    LLM_DATE_SYSTEM,
    LLM_PERIOD_SYSTEM,
    LLM_TIME_EXTRACT_SYSTEM,
    LLM_SLOT_SYSTEM,
    NO_SLOTS_RESPONSE,
    SLOT_CONVERSATION_PROMPT,
    SLOT_CONFIRM_CHECK_SYSTEM,
    build_slot_context_text,
)
from src.control.voice_assistance.utils.state_utils import resolve_slot_state
from src.control.voice_assistance.utils.date_utils import (
    format_time, format_date, format_date_iso,
    today_ist, now_time_ist, coerce_time, parse_date,
    format_dates_only,
)
from src.control.voice_assistance.utils.llm_utils import (
    invokeLLM_json, invokeLargeLLM_json, llm_extract,
)
from src.control.voice_assistance.utils.state_utils import update_state
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import SlotStatus
from src.data.repositories.generic_crud import bulk_get_instance

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

MORNING_START = time(6, 0)
MORNING_END = time(12, 0)
AFTERNOON_START = time(12, 0)
AFTERNOON_END = time(17, 0)
EVENING_START = time(17, 0)
EVENING_END = time(21, 0)

_FALLBACK_SPEAK = "I'm sorry, I ran into a technical issue. Could you please repeat that?"
_FALLBACK_SLOT_ERROR = "Sorry, something went wrong. Could you please repeat that?"
_FALLBACK_FETCH_ERROR = "Sorry, I ran into an issue fetching available slots. Please try again."


def classify_period(t: time) -> str:
    if MORNING_START <= t < MORNING_END:
        return "morning"
    if AFTERNOON_START <= t < AFTERNOON_END:
        return "afternoon"
    if EVENING_START <= t < EVENING_END:
        return "evening"
    return "night"


def slots_for_date(all_slots: list[dict], target: date) -> list[dict]:
    return [s for s in all_slots if s["date"] == target]


def group_slots_by_period(slots: list[dict]) -> dict[str, list[dict]]:
    periods: dict[str, list[dict]] = {}
    for s in slots:
        periods.setdefault(s["period"], []).append(s)
    return periods


def get_available_dates(all_slots: list[dict]) -> list[date]:
    return sorted({s["date"] for s in all_slots})


def _user_said_time(text: str) -> bool:
    return bool(re.search(
        r'\b(\d{1,2})(:\d{2})?\s*(am|pm|o\.?clock)\b'
        r'|\b(half|quarter)\s+(past|to)\b'
        r'|\b\d{1,2}:\d{2}\b',
        text, re.IGNORECASE,
    ))


def build_date_options_text(available_dates: list[date]) -> str:
    return "\n".join(format_date_iso(d) for d in available_dates)


def _infer_period_from_slot(slot: dict) -> str:
    return slot.get("period") or classify_period(slot["start_time"])


async def _check_slot_confirmation(
    user_text: str,
    chosen_date: date,
    chosen_period: str,
    chosen_slot: str,
    doctor_name: str,
) -> bool:
    system_prompt = SLOT_CONFIRM_CHECK_SYSTEM.format(
        chosen_date=format_date(chosen_date),
        chosen_period=chosen_period,
        chosen_slot=chosen_slot,
        doctor_name=doctor_name,
    )
    result = await invokeLLM_json(system_prompt=system_prompt, user_prompt=user_text)
    if not isinstance(result, dict):
        return False
    return bool(result.get("is_confirming", False))


def _build_state_snapshot(
    state: dict,
    all_slots: list[dict] | None = None,
    available_dates: list[date] | None = None,
) -> str:
    lines: list[str] = []

    if name := state.get("patient_name"):
        lines.append(f"Patient name       : {name}")

    symptoms = state.get("clarify_symptoms_text") or state.get("booking_reason_for_visit")
    if symptoms:
        lines.append(f"Reason for visit   : {symptoms}")

    if doctor := state.get("doctor_confirmed_name"):
        lines.append(f"Doctor             : {doctor}")

    if slot_stage := state.get("slot_stage"):
        lines.append(f"Slot stage         : {slot_stage}")

    if chosen_date := state.get("slot_chosen_date"):
        lines.append(f"Date patient chose : {format_date(chosen_date)}")
    else:
        lines.append("Date               : not yet chosen")

    if chosen_period := state.get("slot_chosen_period"):
        lines.append(f"Period chosen      : {chosen_period}")

    if available_dates:
        lines.append(f"All available dates: {', '.join(format_date(d) for d in available_dates[:7])}")

    if all_slots and chosen_date:
        date_slots = slots_for_date(all_slots, chosen_date)
        if date_slots:
            for period_name, pslots in group_slots_by_period(date_slots).items():
                lines.append(
                    f"  [{period_name.capitalize()}] slots on {format_date(chosen_date)}: "
                    f"{', '.join(s['display'] for s in pslots)} ({len(pslots)} total)"
                )
        else:
            lines.append(f"Slots on {format_date(chosen_date)}: none available")

    if prev_slot := state.get("slot_selected_display"):
        label = "Previous slot" if state.get("user_change_request") else "Selected slot"
        suffix = " (patient wants to change)" if state.get("user_change_request") else ""
        lines.append(f"{label:<19}: {prev_slot}{suffix}")

    slot_available_list: list[dict] = state.get("slot_available_list") or []
    if slot_available_list and not (all_slots and chosen_date):
        shown = [s.get("full_display") or s.get("display", "") for s in slot_available_list]
        lines.append(f"Slots shown        : {', '.join(shown)}")

    return "\n".join(f"  {l}" for l in lines) if lines else "  (no confirmed details yet)"


async def _fetch_all_slots(doctor_id: int) -> list[dict]:
    async with AsyncSessionLocal() as db:
        today = today_ist()
        now_time = now_time_ist()

        all_slots = await bulk_get_instance(AvailableSlot, db, provider_id=doctor_id, is_active=True)
        future_available = [
            s for s in all_slots
            if s.status == SlotStatus.AVAILABLE
            and (
                s.availability_date > today
                or (s.availability_date == today and s.start_time > now_time)
            )
        ]
        all_appointments = await bulk_get_instance(Appointment, db, provider_id=doctor_id, is_active=True)
        booked_slot_ids = {
            a.availability_slot_id
            for a in all_appointments
            if str(a.status.value).upper() in ("SCHEDULED", "CONFIRMED")
        }
        return [
            {
                "id": s.id,
                "date": s.availability_date,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "period": classify_period(s.start_time),
                "display": f"{format_time(s.start_time)} → {format_time(s.end_time)}",
                "full_display": (
                    f"{format_time(s.start_time)} → {format_time(s.end_time)}"
                    f" on {format_date(s.availability_date)}"
                ),
            }
            for s in future_available
            if s.id not in booked_slot_ids
        ]


def _build_period_summary(date_slots: list[dict]) -> str:
    parts = []
    for period_name, pslots in group_slots_by_period(date_slots).items():
        times = ", ".join(s["display"] for s in pslots)
        parts.append(f"{period_name} ({len(pslots)} slot{'s' if len(pslots) > 1 else ''}: {times})")
    return " | ".join(parts)


def _build_date_period_summary(all_slots: list[dict], dates: list[date]) -> str:
    parts = []
    for d in dates[:5]:
        date_slots = slots_for_date(all_slots, d)
        if date_slots:
            parts.append(f"{format_date(d)}: {_build_period_summary(date_slots)}")
    return " | ".join(parts) if parts else "no dates available"


async def _speak(
    history: list[dict],
    doctor_name: str,
    situation: str,
    context: str,
    state_snapshot: str = "",
) -> str:
    seed = history if history else [{"role": "user", "content": "start"}]
    messages = [
        {
            "role": "system",
            "content": SLOT_CONVERSATION_PROMPT.format(
                doctor_name=doctor_name,
                state_snapshot=state_snapshot or "  (no snapshot available)",
                situation=situation,
                context=context,
            ),
        },
        *seed,
    ]
    response = await ainvoke_llm(messages)
    if not response:
        logger.warning("_speak: LLM returned no response, using fallback")
        return _FALLBACK_SPEAK
    return response.content.strip().strip('"').strip("'")


def exclude_previously_selected_slot(
    slots: list[dict],
    user_change_request: str | None,
    prev_start: str | None,
    prev_end: str | None,
) -> list[dict]:
    if not user_change_request or not prev_start or not prev_end:
        return slots

    prev_start_t = coerce_time(prev_start)
    prev_end_t = coerce_time(prev_end)

    if prev_start_t is None or prev_end_t is None:
        return slots

    filtered = [
        s for s in slots
        if not (
            coerce_time(s["start_time"]) == prev_start_t
            and coerce_time(s["end_time"]) == prev_end_t
        )
    ]
    return filtered or slots


def get_nearest_alternate_dates(chosen_date: date, available_dates: list[date]) -> list[date]:
    before = sorted([d for d in available_dates if d < chosen_date], reverse=True)
    after = sorted([d for d in available_dates if d > chosen_date])

    alts: list[date] = []
    if before:
        alts.append(before[0])
    alts.extend(after[:2])

    if len(alts) < 3:
        if not before and len(after) >= 3:
            alts = after[:3]
        elif not after and len(before) >= 3:
            alts = sorted(before[:3])

    return sorted(set(alts))[:3]


async def _resolve_with_speech(
    state: dict,
    matched_slot: dict,
    history: list[dict],
    doctor_name: str,
    situation: str,
    context: str,
    snapshot: str,
) -> dict:
    slot_detail = (
        f"IMPORTANT — tell the patient ONLY which slot has been selected: "
        f"Date: {format_date(matched_slot['date'])}, "
        f"Time: {matched_slot['display']} ({format_time(matched_slot['start_time'])} to {format_time(matched_slot['end_time'])}), "
        f"Doctor: {doctor_name}. "
        f"Do NOT use the words 'confirmed', 'booked', 'all set', 'locked in', "
        f"or any phrase that implies the appointment is already finalised. "
        f"Do NOT invent or guess any time — use ONLY the exact time stated above. "
        f"Say only that this slot has been selected and you will confirm it in the next step."
    )
    ai_text = await _speak(
        history, doctor_name,
        situation=situation,
        context=f"{context}\n\n{slot_detail}",
        state_snapshot=snapshot,
    )
    history.append({"role": "assistant", "content": ai_text})

    logger.info(
        "booking_slot_selection: slot resolved → ready_to_book",
        extra={"slot": matched_slot.get("display"), "date": str(matched_slot.get("date"))},
    )
    return resolve_slot_state(
        {**state, "booking_slot_selection_history": history},
        matched_slot,
        ai_text,
        slot_chosen_period=_infer_period_from_slot(matched_slot),
    )


async def _match_slot_from_text(
    user_text: str,
    filtered: list[dict],
    all_slots: list[dict],
    chosen_date: date | None,
) -> dict | None:
    if _user_said_time(user_text):
        time_parsed = await llm_extract(system=LLM_TIME_EXTRACT_SYSTEM, human=user_text)
        requested_time_str = time_parsed.get("time")

        if requested_time_str and requested_time_str not in ("any", None):
            try:
                req_hour, req_min = map(int, requested_time_str.split(":"))
                requested_time_obj = time_type(req_hour, req_min)
                matching = [
                    s for s in filtered
                    if s["start_time"].hour == requested_time_obj.hour
                    and s["start_time"].minute == requested_time_obj.minute
                ]
                if matching:
                    return matching[0]
            except (ValueError, AttributeError):
                pass

    slots_context = build_slot_context_text(filtered)
    parsed = await invokeLargeLLM_json(
        messages=[
            {"role": "system", "content": LLM_SLOT_SYSTEM.format(slots_context=slots_context)},
            {"role": "user", "content": user_text},
        ]
    )
    if not parsed:
        return None

    slot_id = parsed.get("slot_id")
    if slot_id:
        return next((s for s in filtered if s["id"] == int(slot_id)), None)

    return None


async def _handle_ask_date(
    state: dict,
    user_text: str,
    doctor_name: str,
    all_slots: list[dict],
    available_dates: list[date],
) -> dict:
    history: list[dict] = list(state.get("booking_slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    previous_date: date | None = state.get("slot_chosen_date")
    snapshot = _build_state_snapshot(state, all_slots, available_dates)

    if user_change_request and previous_date:
        filtered_slots = [s for s in all_slots if s["date"] != previous_date]
        filtered_dates = get_available_dates(filtered_slots) or available_dates
    else:
        filtered_slots = all_slots
        filtered_dates = available_dates

    parsed = await llm_extract(
        system=LLM_DATE_SYSTEM.format(today=today_ist().isoformat()),
        human=user_text,
    )
    chosen_date = parse_date(parsed.get("date"))

    if chosen_date is None:
        ai_text = await _speak(
            history, doctor_name,
            situation=(
                "couldn't understand the date the patient mentioned — "
                "list only the available dates (day name + date) and ask them to pick one. "
                "Do NOT mention periods or time slots yet."
            ),
            context=f"Available dates: {format_dates_only(filtered_dates)}",
            state_snapshot=snapshot,
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state, active_node="booking_slot_selection", slot_stage="ask_date",
            speech_ai_text=ai_text, booking_slot_selection_history=history,
        )

    if user_change_request and previous_date and chosen_date == previous_date:
        alt_dates = [d for d in filtered_dates[:5] if d != previous_date]
        ai_text = await _speak(
            history, doctor_name,
            situation=(
                "patient picked the same date they already had — "
                "gently point that out and offer only the alternate dates (no periods or times yet)"
            ),
            context=(
                f"Same date chosen: {format_date(chosen_date)}, "
                f"Alternate dates: {format_dates_only(alt_dates)}"
            ),
            state_snapshot=snapshot,
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state, active_node="booking_slot_selection", slot_stage="ask_alternate_date",
            speech_ai_text=ai_text, booking_slot_selection_history=history,
        )

    date_slots = slots_for_date(filtered_slots, chosen_date)

    if not date_slots:
        alts = get_nearest_alternate_dates(chosen_date, filtered_dates)
        if not alts:
            ai_text = await _speak(
                history, doctor_name,
                situation="the doctor has absolutely no upcoming availability — apologise and inform the patient",
                context=f"Doctor: {doctor_name}",
                state_snapshot=snapshot,
            )
            history.append({"role": "assistant", "content": ai_text})
            return update_state(
                state, active_node="booking_slot_selection", slot_stage="ask_date",
                speech_ai_text=ai_text, booking_slot_selection_history=history,
            )

        ai_text = await _speak(
            history, doctor_name,
            situation=(
                "requested date has no slots — tell the patient that date is not available, "
                "then offer only the nearest alternate dates (no periods or times yet)"
            ),
            context=(
                f"Requested date: {format_date(chosen_date)} — NOT available, "
                f"Nearest alternate dates: {format_dates_only(alts)}"
            ),
            state_snapshot=snapshot,
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state, active_node="booking_slot_selection", slot_stage="ask_alternate_date",
            speech_ai_text=ai_text, booking_slot_selection_history=history,
        )

    if _user_said_time(user_text):
        time_parsed = await llm_extract(system=LLM_TIME_EXTRACT_SYSTEM, human=user_text)
        requested_time_str = time_parsed.get("time")

        if requested_time_str and requested_time_str not in ("any", None):
            try:
                req_hour, req_min = map(int, requested_time_str.split(":"))
                requested_time_obj = time_type(req_hour, req_min)
                matching = [
                    s for s in date_slots
                    if s["start_time"].hour == requested_time_obj.hour
                    and s["start_time"].minute == requested_time_obj.minute
                ]
                if matching:
                    return await _resolve_with_speech(
                        state={**state, "slot_chosen_date": chosen_date},
                        matched_slot=matching[0],
                        history=history,
                        doctor_name=doctor_name,
                        situation="patient specified date and time — inform them of selected slot",
                        context=f"Selected slot: {matching[0]['display']} on {format_date(chosen_date)} with {doctor_name}.",
                        snapshot=snapshot,
                    )
            except (ValueError, AttributeError):
                pass

    return await _proceed_to_period(
        {**state, "slot_chosen_date": chosen_date, "booking_slot_selection_history": history},
        doctor_name, chosen_date, date_slots, snapshot,
    )


async def _handle_confirm_date(
    state: dict,
    user_text: str,
    doctor_name: str,
    all_slots: list[dict],
    available_dates: list[date],
) -> dict:
    history: list[dict] = list(state.get("booking_slot_selection_history") or [])
    chosen_date: date = state.get("slot_chosen_date")
    user_change_request: str | None = state.get("user_change_request")
    snapshot = _build_state_snapshot(state, all_slots, available_dates)

    parsed = await llm_extract(system=LLM_CONFIRM_SYSTEM, human=user_text)

    if parsed.get("confirmed") is True:
        date_slots = slots_for_date(all_slots, chosen_date)
        return await _proceed_to_period(
            {**state, "user_change_request": None, "booking_slot_selection_history": history},
            doctor_name, chosen_date, date_slots, snapshot,
        )

    if user_change_request and chosen_date:
        filtered_slots = [s for s in all_slots if s["date"] != chosen_date]
        filtered_dates = get_available_dates(filtered_slots) or available_dates
    else:
        filtered_slots = all_slots
        filtered_dates = available_dates

    parsed2 = await llm_extract(
        system=LLM_DATE_SYSTEM.format(today=today_ist().isoformat()),
        human=user_text,
    )
    new_date = parse_date(parsed2.get("date"))

    if new_date and new_date != chosen_date:
        date_slots = slots_for_date(filtered_slots, new_date)
        if date_slots:
            return await _proceed_to_period(
                {**state, "slot_chosen_date": new_date, "booking_slot_selection_history": history},
                doctor_name, new_date, date_slots, snapshot,
            )

        alts = get_nearest_alternate_dates(new_date, filtered_dates)
        ai_text = await _speak(
            history, doctor_name,
            situation=(
                "the new date the patient suggested also has no slots — "
                "tell them it's not available, then offer only the nearest alternate dates (no periods or times yet)"
            ),
            context=(
                f"Requested date: {format_date(new_date)} — NOT available, "
                f"Nearest alternate dates: {format_dates_only(alts)}"
            ),
            state_snapshot=snapshot,
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state, active_node="booking_slot_selection", slot_stage="ask_alternate_date",
            speech_ai_text=ai_text, booking_slot_selection_history=history,
        )

    ai_text = await _speak(
        history, doctor_name,
        situation=(
            "patient declined or rejected the date — acknowledge it politely, "
            "list only the available dates (no periods or times yet) and ask what date they would prefer"
        ),
        context=f"Available dates: {format_dates_only(filtered_dates)}",
        state_snapshot=snapshot,
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(
        state, active_node="booking_slot_selection", slot_stage="ask_date",
        slot_chosen_date=None, slot_chosen_period=None, slot_available_list=None,
        speech_ai_text=ai_text, booking_slot_selection_history=history,
    )


async def _handle_ask_alternate_date(
    state: dict,
    user_text: str,
    doctor_name: str,
    all_slots: list[dict],
    available_dates: list[date],
) -> dict:
    history: list[dict] = list(state.get("booking_slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    previous_date: date | None = state.get("slot_chosen_date")
    snapshot = _build_state_snapshot(state, all_slots, available_dates)

    if user_change_request and previous_date:
        filtered_slots = [s for s in all_slots if s["date"] != previous_date]
        filtered_dates = get_available_dates(filtered_slots) or available_dates
    else:
        filtered_slots = all_slots
        filtered_dates = available_dates

    parsed = await llm_extract(
        system=LLM_ALTERNATE_DATE_SYSTEM.format(
            today=today_ist().isoformat(),
            date_options=build_date_options_text(filtered_dates),
        ),
        human=user_text,
    )
    chosen_date = parse_date(parsed.get("date"))
    date_slots = slots_for_date(filtered_slots, chosen_date) if chosen_date else []

    if not date_slots:
        ai_text = await _speak(
            history, doctor_name,
            situation=(
                "patient didn't pick a valid alternate date — "
                "list only the available dates (day name + date) and ask them to choose one. "
                "Do NOT mention periods or time slots yet."
            ),
            context=f"Available dates: {format_dates_only(filtered_dates)}",
            state_snapshot=snapshot,
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state, active_node="booking_slot_selection", slot_stage="ask_alternate_date",
            speech_ai_text=ai_text, booking_slot_selection_history=history,
        )

    return await _proceed_to_period(
        {**state, "slot_chosen_date": chosen_date, "booking_slot_selection_history": history},
        doctor_name, chosen_date, date_slots, snapshot,
    )


async def _proceed_to_period(
    state: dict,
    doctor_name: str,
    chosen_date: date,
    date_slots: list[dict],
    snapshot: str = "",
) -> dict:
    history: list[dict] = list(state.get("booking_slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None = state.get("slot_selected_start_time")
    prev_end: str | None = state.get("slot_selected_end_time")

    filtered = exclude_previously_selected_slot(
        date_slots, user_change_request, prev_start, prev_end
    ) or date_slots

    periods = group_slots_by_period(filtered)
    all_filtered_slots = [s for slots in periods.values() for s in slots]
    period_names = list(periods.keys())

    if len(all_filtered_slots) == 1:
        single_slot = all_filtered_slots[0]
        return await _resolve_with_speech(
            state=state,
            matched_slot=single_slot,
            history=history,
            doctor_name=doctor_name,
            situation=(
                f"Only ONE slot on {format_date(chosen_date)}: "
                f"{single_slot['display']} in {_infer_period_from_slot(single_slot)}. "
                f"Inform patient of selected slot."
            ),
            context=(
                f"Date: {format_date(chosen_date)}, "
                f"Only slot: {single_slot['display']} "
                f"({format_time(single_slot['start_time'])} to {format_time(single_slot['end_time'])}) "
                f"with {doctor_name}."
            ),
            snapshot=snapshot,
        )

    if len(period_names) == 1:
        chosen_period = period_names[0]
        period_slots = periods[chosen_period]
        ai_text = await _speak(
            history, doctor_name,
            situation=(
                f"Date confirmed as {format_date(chosen_date)}. "
                f"Only {chosen_period} slots are available on this date. "
                f"List ALL times in {chosen_period} and ask patient to pick one."
            ),
            context=(
                f"Date: {format_date(chosen_date)}, "
                f"Only available period: {chosen_period}, "
                f"All slots in {chosen_period} ({len(period_slots)} total): "
                f"{', '.join(s['display'] for s in period_slots)}"
            ),
            state_snapshot=snapshot,
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state, active_node="booking_slot_selection", slot_stage="ask_slot",
            slot_chosen_date=chosen_date, slot_chosen_period=chosen_period,
            slot_available_list=period_slots, speech_ai_text=ai_text,
            booking_slot_selection_history=history,
        )

    ai_text = await _speak(
        history, doctor_name,
        situation=(
            f"Date confirmed as {format_date(chosen_date)}. "
            f"Multiple periods are available — ask which part of the day the patient prefers. "
            f"Do NOT list individual time slots yet."
        ),
        context=(
            f"Date: {format_date(chosen_date)}, "
            f"Available periods: {', '.join(period_names)}"
        ),
        state_snapshot=snapshot,
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(
        state, active_node="booking_slot_selection", slot_stage="ask_period",
        slot_chosen_date=chosen_date, speech_ai_text=ai_text,
        booking_slot_selection_history=history,
    )


async def _handle_ask_period(
    state: dict,
    user_text: str,
    doctor_name: str,
    all_slots: list[dict],
) -> dict:
    history: list[dict] = list(state.get("booking_slot_selection_history") or [])
    chosen_date: date = state.get("slot_chosen_date")
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None = state.get("slot_selected_start_time")
    prev_end: str | None = state.get("slot_selected_end_time")
    snapshot = _build_state_snapshot(state, all_slots)

    date_slots = slots_for_date(all_slots, chosen_date)
    filtered = exclude_previously_selected_slot(
        date_slots, user_change_request, prev_start, prev_end
    ) or date_slots
    periods = group_slots_by_period(filtered)
    period_names = list(periods.keys())

    if _user_said_time(user_text):
        time_parsed = await llm_extract(system=LLM_TIME_EXTRACT_SYSTEM, human=user_text)
        requested_time_str = time_parsed.get("time")

        if requested_time_str and requested_time_str not in ("any", None):
            try:
                req_hour, req_min = map(int, requested_time_str.split(":"))
                requested_time_obj = time_type(req_hour, req_min)
                matching = [
                    s for s in filtered
                    if s["start_time"].hour == requested_time_obj.hour
                    and s["start_time"].minute == requested_time_obj.minute
                ]
                if matching:
                    return await _resolve_with_speech(
                        state=state,
                        matched_slot=matching[0],
                        history=history,
                        doctor_name=doctor_name,
                        situation=f"Patient said exact time — selected slot is {matching[0]['display']} on {format_date(chosen_date)}. Inform patient.",
                        context=(
                            f"Selected: {matching[0]['display']} "
                            f"({format_time(matching[0]['start_time'])} to {format_time(matching[0]['end_time'])}) "
                            f"on {format_date(chosen_date)} with {doctor_name}."
                        ),
                        snapshot=snapshot,
                    )
            except (ValueError, AttributeError):
                pass

    parsed = await llm_extract(
        system=LLM_PERIOD_SYSTEM.format(available_periods=period_names),
        human=user_text,
    )
    chosen_period = (parsed.get("period") or "").lower()

    if chosen_period not in periods:
        ai_text = await _speak(
            history, doctor_name,
            situation=(
                f"The period the patient asked for is not available on {format_date(chosen_date)}. "
                f"Tell them what periods ARE available and ask them to pick one. "
                f"Do NOT list individual time slots yet."
            ),
            context=f"Requested period: NOT available, Available periods: {', '.join(period_names)}",
            state_snapshot=snapshot,
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state, active_node="booking_slot_selection", slot_stage="ask_period",
            speech_ai_text=ai_text, booking_slot_selection_history=history,
        )

    period_slots = periods[chosen_period]

    if len(period_slots) == 1:
        single_slot = period_slots[0]
        return await _resolve_with_speech(
            state=state,
            matched_slot=single_slot,
            history=history,
            doctor_name=doctor_name,
            situation=f"Only one slot in {chosen_period} on {format_date(chosen_date)}: {single_slot['display']}. Inform patient.",
            context=(
                f"Date: {format_date(chosen_date)}, Period: {chosen_period}, "
                f"Only slot: {single_slot['display']} "
                f"({format_time(single_slot['start_time'])} to {format_time(single_slot['end_time'])}) "
                f"with {doctor_name}."
            ),
            snapshot=snapshot,
        )

    ai_text = await _speak(
        history, doctor_name,
        situation=f"Patient chose {chosen_period} on {format_date(chosen_date)}. List ALL slots in that period and ask to pick one.",
        context=(
            f"Date: {format_date(chosen_date)}, Period: {chosen_period}, "
            f"All slots ({len(period_slots)} total): {', '.join(s['display'] for s in period_slots)}"
        ),
        state_snapshot=snapshot,
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(
        state, active_node="booking_slot_selection", slot_stage="ask_slot",
        slot_chosen_period=chosen_period, slot_available_list=period_slots,
        speech_ai_text=ai_text, booking_slot_selection_history=history,
    )


async def _handle_ask_slot(
    state: dict,
    user_text: str,
    doctor_name: str,
    all_slots: list[dict],
) -> dict:
    history: list[dict] = list(state.get("booking_slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None = state.get("slot_selected_start_time")
    prev_end: str | None = state.get("slot_selected_end_time")
    chosen_date: date = state.get("slot_chosen_date")
    chosen_period: str | None = state.get("slot_chosen_period")
    snapshot = _build_state_snapshot(state, all_slots)

    date_slots = slots_for_date(all_slots, chosen_date)
    period_slots = (
        [s for s in date_slots if s["period"] == chosen_period]
        if chosen_period else date_slots
    ) or state.get("slot_available_list") or []

    filtered = (
        exclude_previously_selected_slot(period_slots, user_change_request, prev_start, prev_end)
        or period_slots
    )

    if user_change_request:
        ai_text = await _speak(
            history, doctor_name,
            situation=(
                f"Patient wants to change slot on {format_date(chosen_date)}. "
                f"List ALL available slots by period. Do NOT auto-select."
            ),
            context=(
                f"Date: {format_date(chosen_date)}, "
                f"All available slots: {_build_period_summary(filtered)}, "
                f"Previous slot excluded: {prev_start} – {prev_end}"
            ),
            state_snapshot=snapshot,
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state, active_node="booking_slot_selection", slot_stage="ask_slot",
            slot_available_list=filtered, user_change_request=None,
            speech_ai_text=ai_text, booking_slot_selection_history=history,
        )

    matched = await _match_slot_from_text(user_text, filtered, all_slots, chosen_date)

    if matched:
        return await _resolve_with_speech(
            state=state,
            matched_slot=matched,
            history=history,
            doctor_name=doctor_name,
            situation=(
                f"Patient picked {matched['display']} on {format_date(chosen_date)}. "
                f"Inform them of selected slot. Do NOT say confirmed or booked."
            ),
            context=(
                f"Selected: {matched['display']} "
                f"({format_time(matched['start_time'])} to {format_time(matched['end_time'])}) "
                f"on {format_date(chosen_date)} with {doctor_name}."
            ),
            snapshot=snapshot,
        )

    all_times_on_date = ", ".join(s["display"] for s in slots_for_date(all_slots, chosen_date))
    other_slots = [s for s in all_slots if s["date"] != chosen_date]

    if not other_slots:
        ai_text = await _speak(
            history, doctor_name,
            situation="patient didn't pick a valid slot — present ALL available times on chosen date",
            context=f"Date: {format_date(chosen_date)}, All slots: {all_times_on_date}",
            state_snapshot=snapshot,
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state, active_node="booking_slot_selection", slot_stage="ask_slot",
            slot_available_list=filtered, speech_ai_text=ai_text,
            booking_slot_selection_history=history,
        )

    next_dates = sorted({s["date"] for s in other_slots})[:2]
    alt_slots = (
        exclude_previously_selected_slot(
            [s for s in all_slots if s["date"] in next_dates][:5],
            user_change_request, prev_start, prev_end,
        )
        or [s for s in all_slots if s["date"] in next_dates][:5]
    )
    ai_text = await _speak(
        history, doctor_name,
        situation="patient didn't pick valid slot — show remaining slots and offer nearby alternate dates",
        context=(
            f"Date: {format_date(chosen_date)}, "
            f"Remaining slots: {all_times_on_date}, "
            f"Alternate dates: {_build_date_period_summary(all_slots, next_dates)}"
        ),
        state_snapshot=snapshot,
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(
        state, active_node="booking_slot_selection", slot_stage="ask_alternate_slot",
        slot_available_list=alt_slots, speech_ai_text=ai_text,
        booking_slot_selection_history=history,
    )


async def _handle_ask_alternate_slot(
    state: dict,
    user_text: str,
    doctor_name: str,
    all_slots: list[dict] | None = None,
) -> dict:
    history: list[dict] = list(state.get("booking_slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None = state.get("slot_selected_start_time")
    prev_end: str | None = state.get("slot_selected_end_time")
    snapshot = _build_state_snapshot(state)

    raw_slots = state.get("slot_available_list") or []
    filtered = (
        exclude_previously_selected_slot(raw_slots, user_change_request, prev_start, prev_end)
        or raw_slots
    )

    matched = await _match_slot_from_text(user_text, filtered, all_slots or [], None)

    if matched:
        return await _resolve_with_speech(
            state=state,
            matched_slot=matched,
            history=history,
            doctor_name=state.get("doctor_confirmed_name"),
            situation=(
                f"Patient picked alternate slot: {matched['full_display']}. "
                f"Inform them of selected slot. Do NOT say confirmed or booked."
            ),
            context=(
                f"Selected: {matched['full_display']} "
                f"({format_time(matched['start_time'])} to {format_time(matched['end_time'])})."
            ),
            snapshot=snapshot,
        )

    dates_str = format_dates_only(get_available_dates(all_slots)) if all_slots else "no further availability found"
    ai_text = await _speak(
        history, state.get("doctor_confirmed_name", "the doctor"),
        situation=(
            "patient rejected all alternate slots — apologise and show only the available dates. "
            "Do NOT mention periods or times yet."
        ),
        context=f"Available dates: {dates_str}",
        state_snapshot=snapshot,
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(
        state, active_node="booking_slot_selection", slot_stage="ask_date",
        slot_chosen_date=None, slot_chosen_period=None, slot_available_list=None,
        speech_ai_text=ai_text, booking_slot_selection_history=history,
    )


async def _handle_selecting(
    state: dict,
    user_text: str,
    doctor_name: str,
    all_slots: list[dict],
    available_dates: list[date],
) -> dict:
    logger.warning("booking_slot_selection: legacy stage='selecting' — recovering")
    chosen_date: date | None = state.get("slot_chosen_date")
    chosen_period: str | None = state.get("slot_chosen_period")

    if chosen_date:
        date_slots = slots_for_date(all_slots, chosen_date)
        if date_slots:
            period_slots = (
                [s for s in date_slots if s["period"] == chosen_period]
                if chosen_period else date_slots
            ) or date_slots
            return await _handle_ask_slot(
                {**state, "slot_stage": "ask_slot", "slot_available_list": period_slots},
                user_text, doctor_name, all_slots,
            )

    return await _handle_ask_date(
        {**state, "slot_stage": "ask_date", "slot_chosen_date": None,
         "slot_chosen_period": None, "slot_available_list": None},
        user_text, doctor_name, all_slots, available_dates,
    )


_STAGE_HANDLERS = {
    "ask_date":           lambda s, t, d, a, av: _handle_ask_date(s, t, d, a, av),
    "confirm_date":       lambda s, t, d, a, av: _handle_confirm_date(s, t, d, a, av),
    "ask_alternate_date": lambda s, t, d, a, av: _handle_ask_alternate_date(s, t, d, a, av),
    "ask_period":         lambda s, t, d, a, _:  _handle_ask_period(s, t, d, a),
    "ask_slot":           lambda s, t, d, a, _:  _handle_ask_slot(s, t, d, a),
    "ask_alternate_slot": lambda s, t, d, a, __: _handle_ask_alternate_slot(s, t, d, a),
    "selecting":          lambda s, t, d, a, av: _handle_selecting(s, t, d, a, av),
}


async def booking_slot_selection_node(state: dict) -> dict:
    """
    Manages the multi-turn slot selection phase of the appointment booking flow.

    This node drives a staged conversation to narrow the patient down to a
    single bookable slot. The stages progress as follows:

        ask_date → (confirm_date | ask_alternate_date) → ask_period →
        ask_slot → (ask_alternate_slot) → ready_to_book

    On each invocation the node:
      1. Coerces any ISO string dates/times in state back to Python objects
         (guards against serialisation round-trips in the graph).
      2. Short-circuits immediately if a slot is already booked or if the
         stage is ready_to_book with no pending change request.
      3. Resets completion flags when the patient has requested a change.
      4. Appends the latest user utterance to history.
      5. Runs a lightweight slot-confirmation check for ask_slot / ask_period
         stages to detect early confirmation without a full LLM round-trip.
      6. Fetches all future available slots for the doctor from the database,
         filtering out already-booked and past slots.
      7. Dispatches to the appropriate stage handler via _STAGE_HANDLERS.

    Falls back to a static error message on fetch failure or unhandled
    stage-handler exceptions. Resets to ask_date on unknown stages.

    Args:
        state: Graph state containing:
            - doctor_confirmed_id: ID used to fetch available slots.
            - doctor_confirmed_name: Display name for LLM prompts.
            - speech_user_text: Latest user utterance.
            - slot_stage: Current stage key (None on first entry).
            - slot_chosen_date: Date selected so far (date or ISO str).
            - slot_chosen_period: Period selected so far.
            - slot_available_list: Slot dicts shown in the last turn.
            - slot_selected_display: Previously selected slot display string.
            - slot_selected_start_time / slot_selected_end_time: Used for
              exclusion when the patient requests a change.
            - user_change_request: Truthy if patient wants a different slot.
            - booking_slot_selection_history: Conversation history for this node.
            - slot_booked_id: Set once a booking is confirmed downstream.

    Returns:
        Updated state with:
            - active_node: Set to "booking_slot_selection".
            - slot_stage: Advances through the stage machine.
            - booking_slot_selection_history: Appended conversation.
            - speech_ai_text: AI response or fallback/error message.
            - booking_slot_selection_completed: True when ready_to_book.
            - slot_chosen_date / slot_chosen_period: Updated as stages progress.
            - slot_available_list: Slots offered in the current turn.
            - slot_selected_display / slot_selected_start_time /
              slot_selected_end_time: Populated once a slot is resolved.
            - speech_error: Present on unhandled stage-handler exceptions.
    """
    if isinstance(state.get("slot_chosen_date"), str):
        try:
            state = {**state, "slot_chosen_date": date.fromisoformat(state["slot_chosen_date"])}
        except (ValueError, TypeError):
            state = {**state, "slot_chosen_date": None}

    raw_slots = state.get("slot_available_list") or []
    if raw_slots and isinstance(raw_slots[0].get("date"), str):
        state = {
            **state,
            "slot_available_list": [
                {
                    **s,
                    "date": date.fromisoformat(s["date"]) if isinstance(s.get("date"), str) else s["date"],
                    "start_time": time_type.fromisoformat(s["start_time"]) if isinstance(s.get("start_time"), str) else s["start_time"],
                    "end_time": time_type.fromisoformat(s["end_time"]) if isinstance(s.get("end_time"), str) else s["end_time"],
                }
                for s in raw_slots
            ],
        }

    if state.get("slot_booked_id"):
        return {**state, "active_node": "booking_slot_selection", "booking_slot_selection_completed": True}

    if (
        state.get("slot_stage") == "ready_to_book"
        and state.get("booking_slot_selection_completed")
        and not state.get("user_change_request")
    ):
        logger.info("booking_slot_selection: stage=ready_to_book — returning immediately")
        return {
            **state,
            "active_node": "booking_slot_selection",
            "booking_slot_selection_completed": True,
            "speech_ai_text": state.get("speech_ai_text"),
        }

    if state.get("user_change_request"):
        state = {
            **state,
            "booking_slot_selection_completed": False,
            "slot_stage": state.get("slot_stage") or "ask_date",
        }

    doctor_id: int = state.get("doctor_confirmed_id")
    doctor_name: str = state.get("doctor_confirmed_name", "the doctor")
    user_text: str = (state.get("speech_user_text") or "").strip()
    slot_stage: str | None = state.get("slot_stage")
    history: list[dict] = list(state.get("booking_slot_selection_history") or [])

    if user_text:
        history.append({"role": "user", "content": user_text})
        state = {**state, "booking_slot_selection_history": history}

    if (
        user_text
        and not state.get("user_change_request")
        and slot_stage in ("ask_slot", "ask_period")
        and state.get("slot_chosen_date")
        and state.get("slot_chosen_period")
        and state.get("slot_selected_display")
    ):
        is_confirming = await _check_slot_confirmation(
            user_text=user_text,
            chosen_date=state["slot_chosen_date"],
            chosen_period=state["slot_chosen_period"],
            chosen_slot=state["slot_selected_display"],
            doctor_name=doctor_name,
        )
        if is_confirming:
            logger.info("booking_slot_selection: user confirmed slot → ready_to_book")
            return {
                **state,
                "active_node": "booking_slot_selection",
                "slot_stage": "ready_to_book",
                "booking_slot_selection_completed": True,
                "speech_ai_text": state.get("speech_ai_text"),
            }

    try:
        all_slots = await _fetch_all_slots(doctor_id)
    except Exception as e:
        logger.error("booking_slot_selection: failed to fetch slots", extra={"error": str(e)})
        return update_state(
            state,
            active_node="booking_slot_selection",
            booking_slot_selection_completed=False,
            speech_ai_text=_FALLBACK_FETCH_ERROR,
        )

    if not all_slots:
        return update_state(
            state,
            active_node="booking_slot_selection",
            booking_slot_selection_completed=False,
            speech_ai_text=NO_SLOTS_RESPONSE.format(doctor_name=doctor_name),
        )

    available_dates = get_available_dates(all_slots)

    if slot_stage is None:
        ai_text = (
            f"Now let's find a good time with {doctor_name}. "
            f"Which date works for you? "
            f"We have availability on: {format_dates_only(available_dates)}."
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state, active_node="booking_slot_selection", slot_stage="ask_date",
            booking_slot_selection_completed=False,
            booking_slot_selection_history=history,
            slot_chosen_date=None, slot_chosen_period=None,
            slot_available_list=None, speech_ai_text=ai_text,
        )

    handler = _STAGE_HANDLERS.get(slot_stage)
    if handler is None:
        logger.warning(
            "booking_slot_selection: unhandled stage — resetting",
            extra={"slot_stage": slot_stage},
        )
        return await booking_slot_selection_node({
            **state,
            "slot_stage": None, "slot_chosen_date": None,
            "slot_chosen_period": None, "slot_available_list": None,
            "booking_slot_selection_history": [],
        })

    try:
        return await handler(state, user_text, doctor_name, all_slots, available_dates)
    except Exception as e:
        logger.error(
            "booking_slot_selection: stage handler failed",
            extra={"slot_stage": slot_stage, "error": str(e)},
        )
        return update_state(
            state,
            active_node="booking_slot_selection",
            speech_ai_text=_FALLBACK_SLOT_ERROR,
            speech_error=str(e),
        )