from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from src.control.voice_assistance.models import ainvoke_llm, get_llama1
from src.control.voice_assistance.prompts.slot_selection_node_prompt import (
    LLM_ALTERNATE_DATE_SYSTEM,
    LLM_ALTERNATE_SLOT_SYSTEM,
    LLM_CONFIRM_SYSTEM,
    LLM_DATE_SYSTEM,
    LLM_PERIOD_SYSTEM,
    LLM_SLOT_SYSTEM,
    NO_SLOTS_RESPONSE,
    SLOT_CONVERSATION_PROMPT,
)
from src.control.voice_assistance.utils import (
    build_date_options_text,
    build_slot_context_text,
    classify_period,
    clear_markdown,
    exclude_previously_selected_slot,
    format_date,
    format_time,
    get_available_dates,
    get_nearest_alternate_dates,
    group_slots_by_period,
    looks_like_slot_choice,
    slots_for_date,
    update_state,
)
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import SlotStatus
from src.data.repositories.generic_crud import bulk_get_instance

IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> datetime:
    return datetime.now(tz=IST)


def _today_ist() -> date:
    return _now_ist().date()


def _now_time_ist():
    return _now_ist().time()


async def _fetch_all_slots(doctor_id: int) -> list[dict]:
    try:
        async with AsyncSessionLocal() as db:
            today = _today_ist()
            now_time = _now_time_ist()

            all_slots = await bulk_get_instance(
                AvailableSlot, db, provider_id=doctor_id, is_active=True
            )
            future_available = [
                s
                for s in all_slots
                if s.status == SlotStatus.AVAILABLE
                and (
                    s.availability_date > today
                    or (s.availability_date == today and s.start_time > now_time)
                )
            ]
            all_appointments = await bulk_get_instance(
                Appointment, db, provider_id=doctor_id, is_active=True
            )
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
                    "full_display": f"{format_time(s.start_time)} → {format_time(s.end_time)} on {format_date(s.availability_date)}",
                }
                for s in future_available
                if s.id not in booked_slot_ids
            ]
    except Exception as e:
        print("[_fetch_all_slots] error:", e)
        return []


async def _llm_extract(system: str, human: str) -> dict:
    try:
        llm = get_llama1()
        response = await llm.ainvoke([("system", system), ("human", human)])
        raw = response.content.strip()
        try:
            return json.loads(clear_markdown(raw))
        except Exception as parse_err:
            print("[_llm_extract] parse error:", parse_err, "| raw:", raw)
            return {}
    except Exception as e:
        print("[_llm_extract] error:", e)
        return {}


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except Exception:
        return None


async def _speak(
    history: list[dict], doctor_name: str, situation: str, context: str
) -> str:
    seed = history if history else [{"role": "user", "content": "start"}]
    messages = [
        {
            "role": "system",
            "content": SLOT_CONVERSATION_PROMPT.format(
                doctor_name=doctor_name,
                situation=situation,
                context=context,
            ),
        },
        *seed,
    ]
    try:
        response = await ainvoke_llm(messages)
        return response.content.strip().strip('"').strip("'")
    except Exception as e:
        print("[_speak] error:", e)
        return "I'm sorry, I ran into a technical issue. Could you please repeat that?"


async def _resolve_and_confirm_slot(state: dict, matched_slot: dict) -> dict:
    return update_state(
        state,
        slot_stage="ready_to_book",
        slot_selection_completed=True,
        slot_selected=matched_slot,
        slot_selected_start_time=str(matched_slot["start_time"]),
        slot_selected_end_time=str(matched_slot["end_time"]),
        slot_selected_display=matched_slot["display"],
        user_change_request=None,
    )


async def _handle_ask_date(
    state: dict,
    user_text: str,
    doctor_name: str,
    all_slots: list[dict],
    available_dates: list[date],
) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    previous_date: date | None = state.get("slot_chosen_date")

    if user_change_request and previous_date:
        filtered_slots = [s for s in all_slots if s["date"] != previous_date]
        filtered_dates = get_available_dates(filtered_slots) or available_dates
    else:
        filtered_slots = all_slots
        filtered_dates = available_dates

    parsed = await _llm_extract(
        system=LLM_DATE_SYSTEM.format(today=_today_ist().isoformat()), human=user_text
    )
    chosen_date = _parse_date(parsed.get("date"))

    if chosen_date is None:
        ai_text = await _speak(
            history,
            doctor_name,
            situation="couldn't understand the date the patient mentioned — ask them to clarify with an example like 'March 8' or 'next Monday'",
            context=f"Doctor: {doctor_name}",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state,
            slot_stage="ask_date",
            speech_ai_text=ai_text,
            slot_selection_history=history,
        )

    if user_change_request and previous_date and chosen_date == previous_date:
        alt_dates = [d for d in filtered_dates[:3] if d != previous_date]
        ai_text = await _speak(
            history,
            doctor_name,
            situation="patient picked the same date they already had — gently point that out and offer the alternate dates listed in context",
            context=f"Same date chosen: {format_date(chosen_date)}, Alternate available dates: {', '.join(format_date(d) for d in alt_dates)}",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state,
            slot_stage="ask_alternate_date",
            speech_ai_text=ai_text,
            slot_selection_history=history,
        )

    date_slots = slots_for_date(filtered_slots, chosen_date)

    if date_slots:
        ai_text = await _speak(
            history,
            doctor_name,
            situation="confirm the date the patient just chose before proceeding",
            context=f"Chosen date: {format_date(chosen_date)}, Doctor: {doctor_name}",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state,
            slot_stage="confirm_date",
            slot_chosen_date=chosen_date,
            speech_ai_text=ai_text,
            slot_selection_history=history,
        )

    alts = get_nearest_alternate_dates(chosen_date, filtered_dates)
    if not alts:
        ai_text = await _speak(
            history,
            doctor_name,
            situation="the doctor has absolutely no upcoming availability — apologise and inform the patient",
            context=f"Doctor: {doctor_name}",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state,
            slot_stage="ask_date",
            speech_ai_text=ai_text,
            slot_selection_history=history,
        )

    ai_text = await _speak(
        history,
        doctor_name,
        situation="requested date has no slots — apologise and offer the nearest alternate dates listed in context",
        context=f"Requested date: {format_date(chosen_date)}, Nearest available dates: {', '.join(format_date(d) for d in alts)}",
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(
        state,
        slot_stage="ask_alternate_date",
        speech_ai_text=ai_text,
        slot_selection_history=history,
    )


async def _handle_confirm_date(
    state: dict,
    user_text: str,
    doctor_name: str,
    all_slots: list[dict],
    available_dates: list[date],
) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    chosen_date: date = state.get("slot_chosen_date")
    user_change_request: str | None = state.get("user_change_request")

    parsed = await _llm_extract(system=LLM_CONFIRM_SYSTEM, human=user_text)
    confirmed = parsed.get("confirmed")

    if confirmed is True:
        date_slots = slots_for_date(all_slots, chosen_date)
        return await _proceed_to_period(
            {**state, "user_change_request": None, "slot_selection_history": history},
            doctor_name,
            chosen_date,
            date_slots,
        )

    parsed2 = await _llm_extract(
        system=LLM_DATE_SYSTEM.format(today=_today_ist().isoformat()), human=user_text
    )
    new_date = _parse_date(parsed2.get("date"))

    if user_change_request and chosen_date:
        filtered_slots = [s for s in all_slots if s["date"] != chosen_date]
        filtered_dates = get_available_dates(filtered_slots) or available_dates
    else:
        filtered_slots = all_slots
        filtered_dates = available_dates

    if new_date and new_date != chosen_date:
        date_slots = slots_for_date(filtered_slots, new_date)
        if date_slots:
            ai_text = await _speak(
                history,
                doctor_name,
                situation="patient gave a new date instead of confirming — acknowledge it and ask them to confirm this new date",
                context=f"New date: {format_date(new_date)}, Doctor: {doctor_name}",
            )
            history.append({"role": "assistant", "content": ai_text})
            return update_state(
                state,
                slot_stage="confirm_date",
                slot_chosen_date=new_date,
                speech_ai_text=ai_text,
                slot_selection_history=history,
            )

        alts = get_nearest_alternate_dates(new_date, filtered_dates)
        ai_text = await _speak(
            history,
            doctor_name,
            situation="the new date the patient suggested also has no slots — apologise and offer the alternate dates from context",
            context=f"Requested date: {format_date(new_date)}, Nearest available dates: {', '.join(format_date(d) for d in alts)}",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state,
            slot_stage="ask_alternate_date",
            speech_ai_text=ai_text,
            slot_selection_history=history,
        )

    ai_text = await _speak(
        history,
        doctor_name,
        situation="patient declined or rejected the date — acknowledge it politely and ask what date they would prefer instead",
        context=f"Doctor: {doctor_name}",
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(
        state,
        slot_stage="ask_date",
        slot_chosen_date=None,
        slot_chosen_period=None,
        slot_available_list=None,
        speech_ai_text=ai_text,
        slot_selection_history=history,
    )


async def _handle_ask_alternate_date(
    state: dict,
    user_text: str,
    doctor_name: str,
    all_slots: list[dict],
    available_dates: list[date],
) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    previous_date: date | None = state.get("slot_chosen_date")

    if user_change_request and previous_date:
        filtered_slots = [s for s in all_slots if s["date"] != previous_date]
        filtered_dates = get_available_dates(filtered_slots) or available_dates
    else:
        filtered_slots = all_slots
        filtered_dates = available_dates

    parsed = await _llm_extract(
        system=LLM_ALTERNATE_DATE_SYSTEM.format(
            today=_today_ist().isoformat(),
            date_options=build_date_options_text(filtered_dates),
        ),
        human=user_text,
    )
    chosen_date = _parse_date(parsed.get("date"))
    date_slots = slots_for_date(filtered_slots, chosen_date) if chosen_date else []

    if not date_slots:
        ai_text = await _speak(
            history,
            doctor_name,
            situation="patient didn't pick a valid alternate date — list all available dates from context and ask them to choose",
            context=f"All available dates: {', '.join(format_date(d) for d in filtered_dates)}",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state,
            slot_stage="ask_alternate_date",
            speech_ai_text=ai_text,
            slot_selection_history=history,
        )

    ai_text = await _speak(
        history,
        doctor_name,
        situation="confirm the alternate date the patient just chose",
        context=f"Chosen date: {format_date(chosen_date)}, Doctor: {doctor_name}",
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(
        state,
        slot_stage="confirm_date",
        slot_chosen_date=chosen_date,
        speech_ai_text=ai_text,
        slot_selection_history=history,
    )


async def _proceed_to_period(
    state: dict, doctor_name: str, chosen_date: date, date_slots: list[dict]
) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None = state.get("slot_selected_start_time")
    prev_end: str | None = state.get("slot_selected_end_time")

    filtered = exclude_previously_selected_slot(
        date_slots, user_change_request, prev_start, prev_end
    )
    periods = group_slots_by_period(filtered or date_slots)
    period_names = list(periods.keys())

    if len(period_names) == 1:
        chosen_period = period_names[0]
        period_slots = periods[chosen_period]
        slot_options = ", ".join(s["display"] for s in period_slots)
        ai_text = await _speak(
            history,
            doctor_name,
            situation="only one time period is available — present the available time slots in that period and ask the patient to pick one",
            context=f"Date: {format_date(chosen_date)}, Period: {chosen_period}, Available slots: {slot_options}",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state,
            slot_stage="ask_slot",
            slot_chosen_date=chosen_date,
            slot_chosen_period=chosen_period,
            slot_available_list=period_slots,
            speech_ai_text=ai_text,
            slot_selection_history=history,
        )

    ai_text = await _speak(
        history,
        doctor_name,
        situation="multiple time periods are available for the chosen date — ask the patient which part of the day they prefer",
        context=f"Date: {format_date(chosen_date)}, Available periods: {', '.join(period_names)}",
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(
        state,
        slot_stage="ask_period",
        slot_chosen_date=chosen_date,
        speech_ai_text=ai_text,
        slot_selection_history=history,
    )


async def _handle_ask_period(
    state: dict, user_text: str, doctor_name: str, all_slots: list[dict]
) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    chosen_date: date = state.get("slot_chosen_date")
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None = state.get("slot_selected_start_time")
    prev_end: str | None = state.get("slot_selected_end_time")

    date_slots = slots_for_date(all_slots, chosen_date)
    filtered = exclude_previously_selected_slot(
        date_slots, user_change_request, prev_start, prev_end
    )
    periods = group_slots_by_period(filtered or date_slots)
    period_names = list(periods.keys())

    parsed = await _llm_extract(
        system=LLM_PERIOD_SYSTEM.format(available_periods=period_names), human=user_text
    )
    chosen_period = (parsed.get("period") or "").lower()

    if chosen_period not in periods:
        ai_text = await _speak(
            history,
            doctor_name,
            situation="the period the patient requested is not available — inform them and offer only the available periods listed in context",
            context=f"Available periods: {', '.join(period_names)}, Date: {format_date(chosen_date)}",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state,
            slot_stage="ask_period",
            speech_ai_text=ai_text,
            slot_selection_history=history,
        )

    period_slots = periods[chosen_period]
    slot_options = ", ".join(s["display"] for s in period_slots)
    ai_text = await _speak(
        history,
        doctor_name,
        situation="present the available time slots for the period the patient chose and ask them to pick one",
        context=f"Date: {format_date(chosen_date)}, Period: {chosen_period}, Available slots: {slot_options}",
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(
        state,
        slot_stage="ask_slot",
        slot_chosen_period=chosen_period,
        slot_available_list=period_slots,
        speech_ai_text=ai_text,
        slot_selection_history=history,
    )


async def _handle_ask_slot(
    state: dict, user_text: str, doctor_name: str, all_slots: list[dict]
) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None = state.get("slot_selected_start_time")
    prev_end: str | None = state.get("slot_selected_end_time")
    chosen_date: date = state.get("slot_chosen_date")
    chosen_period: str | None = state.get("slot_chosen_period")

    date_slots = slots_for_date(all_slots, chosen_date)
    period_slots = (
        (
            [s for s in date_slots if s["period"] == chosen_period]
            if chosen_period
            else date_slots
        )
        or state.get("slot_available_list")
        or []
    )
    filtered = (
        exclude_previously_selected_slot(
            period_slots, user_change_request, prev_start, prev_end
        )
        or period_slots
    )

    if user_change_request and not looks_like_slot_choice(user_text):
        slot_options = ", ".join(s["display"] for s in filtered)
        ai_text = await _speak(
            history,
            doctor_name,
            situation="patient wants to change their slot — list all other available times from context and ask them to pick",
            context=f"Date: {format_date(chosen_date)}, Other available slots: {slot_options}",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state,
            slot_stage="ask_slot",
            slot_available_list=filtered,
            user_change_request=user_change_request,
            speech_ai_text=ai_text,
            slot_selection_history=history,
        )

    parsed = await _llm_extract(
        system=LLM_SLOT_SYSTEM.format(slots_context=build_slot_context_text(filtered)),
        human=user_text,
    )
    slot_id = parsed.get("slot_id")

    if not slot_id:
        other_slots = [s for s in all_slots if s["date"] != chosen_date]
        if not other_slots:
            slot_options = ", ".join(s["display"] for s in filtered)
            ai_text = await _speak(
                history,
                doctor_name,
                situation="no other slots exist at all — present what's available on the chosen date and ask if any works",
                context=f"Date: {format_date(chosen_date)}, Available slots: {slot_options}",
            )
            history.append({"role": "assistant", "content": ai_text})
            return update_state(
                state,
                slot_stage="ask_slot",
                slot_available_list=filtered,
                speech_ai_text=ai_text,
                slot_selection_history=history,
            )

        next_dates = sorted({s["date"] for s in other_slots})[:2]
        alt_slots = (
            exclude_previously_selected_slot(
                [s for s in all_slots if s["date"] in next_dates][:5],
                user_change_request,
                prev_start,
                prev_end,
            )
            or [s for s in all_slots if s["date"] in next_dates][:5]
        )
        alt_options = ", ".join(s["full_display"] for s in alt_slots)
        ai_text = await _speak(
            history,
            doctor_name,
            situation="patient didn't pick a slot — offer the alternative slots on nearby dates listed in context",
            context=f"Alternative slots: {alt_options}",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state,
            slot_stage="ask_alternate_slot",
            slot_available_list=alt_slots,
            speech_ai_text=ai_text,
            slot_selection_history=history,
        )

    matched = next((s for s in filtered if s["id"] == int(slot_id)), filtered[0])
    return await _resolve_and_confirm_slot(
        {**state, "slot_selection_history": history}, matched
    )


async def _handle_ask_alternate_slot(
    state: dict, user_text: str, doctor_name: str
) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None = state.get("slot_selected_start_time")
    prev_end: str | None = state.get("slot_selected_end_time")

    raw_slots = state.get("slot_available_list") or []
    filtered = (
        exclude_previously_selected_slot(
            raw_slots, user_change_request, prev_start, prev_end
        )
        or raw_slots
    )

    parsed = await _llm_extract(
        system=LLM_ALTERNATE_SLOT_SYSTEM.format(
            slots_context=build_slot_context_text(filtered, use_full_display=True)
        ),
        human=user_text,
    )
    slot_id = parsed.get("slot_id")

    if not slot_id:
        ai_text = await _speak(
            history,
            doctor_name,
            situation="patient rejected all alternate slots — apologise and ask what date would work best for them instead",
            context=f"Doctor: {doctor_name}",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state,
            slot_stage="ask_date",
            slot_chosen_date=None,
            slot_chosen_period=None,
            slot_available_list=None,
            speech_ai_text=ai_text,
            slot_selection_history=history,
        )

    matched = next((s for s in filtered if s["id"] == int(slot_id)), filtered[0])
    return await _resolve_and_confirm_slot(
        {**state, "slot_selection_history": history}, matched
    )


async def _handle_selecting(
    state: dict,
    user_text: str,
    doctor_name: str,
    all_slots: list[dict],
    available_dates: list[date],
) -> dict:
    print("[slot_selection_node] legacy stage='selecting' — recovering")
    chosen_date: date | None = state.get("slot_chosen_date")
    chosen_period: str | None = state.get("slot_chosen_period")

    if chosen_date:
        date_slots = slots_for_date(all_slots, chosen_date)
        if date_slots:
            period_slots = (
                [s for s in date_slots if s["period"] == chosen_period]
                if chosen_period
                else date_slots
            ) or date_slots
            recovered_state = {
                **state,
                "slot_stage": "ask_slot",
                "slot_available_list": period_slots,
            }
            return await _handle_ask_slot(
                recovered_state, user_text, doctor_name, all_slots
            )

    recovered_state = {
        **state,
        "slot_stage": "ask_date",
        "slot_chosen_date": None,
        "slot_chosen_period": None,
        "slot_available_list": None,
    }
    return await _handle_ask_date(
        recovered_state, user_text, doctor_name, all_slots, available_dates
    )


_STAGE_HANDLERS = {
    "ask_date": lambda state, user_text, doctor_name, all_slots, available_dates: (
        _handle_ask_date(state, user_text, doctor_name, all_slots, available_dates)
    ),
    "confirm_date": lambda state, user_text, doctor_name, all_slots, available_dates: (
        _handle_confirm_date(state, user_text, doctor_name, all_slots, available_dates)
    ),
    "ask_alternate_date": lambda state, user_text, doctor_name, all_slots, available_dates: (
        _handle_ask_alternate_date(
            state, user_text, doctor_name, all_slots, available_dates
        )
    ),
    "ask_period": lambda state, user_text, doctor_name, all_slots, _: (
        _handle_ask_period(state, user_text, doctor_name, all_slots)
    ),
    "ask_slot": lambda state, user_text, doctor_name, all_slots, _: _handle_ask_slot(
        state, user_text, doctor_name, all_slots
    ),
    "ask_alternate_slot": lambda state, user_text, doctor_name, _, __: (
        _handle_ask_alternate_slot(state, user_text, doctor_name)
    ),
    "selecting": lambda state, user_text, doctor_name, all_slots, available_dates: (
        _handle_selecting(state, user_text, doctor_name, all_slots, available_dates)
    ),
}


async def slot_selection_node(state: dict) -> dict:
    print("[slot_selection_node] -----------------------------")

    if state.get("slot_booked_id"):
        return {**state, "slot_selection_completed": True}

    if state.get("slot_stage") == "ready_to_book" and state.get(
        "slot_selection_completed"
    ):
        return state

    doctor_id: int = state.get("doctor_confirmed_id")
    doctor_name: str = state.get("doctor_confirmed_name", "the doctor")
    user_text: str = (state.get("speech_user_text") or "").strip()
    slot_stage: str | None = state.get("slot_stage")
    history: list[dict] = list(state.get("slot_selection_history") or [])

    if user_text:
        history.append({"role": "user", "content": user_text})
        state = {**state, "slot_selection_history": history}

    try:
        all_slots = await _fetch_all_slots(doctor_id)
    except Exception as e:
        print("[slot_selection_node] _fetch_all_slots failed:", e)
        return update_state(
            state,
            slot_selection_completed=False,
            speech_ai_text="Sorry, I ran into an issue fetching available slots. Please try again.",
        )

    if not all_slots:
        return update_state(
            state,
            slot_selection_completed=False,
            speech_ai_text=NO_SLOTS_RESPONSE.format(doctor_name=doctor_name),
        )

    available_dates = get_available_dates(all_slots)

    if slot_stage is None:
        ai_text = f"Now let's find a good time with {doctor_name}. What date were you thinking?"
        history.append({"role": "assistant", "content": ai_text})
        return update_state(
            state,
            slot_stage="ask_date",
            slot_selection_completed=False,
            slot_selection_history=history,
            slot_chosen_date=None,
            slot_chosen_period=None,
            slot_available_list=None,
            speech_ai_text=ai_text,
        )

    handler = _STAGE_HANDLERS.get(slot_stage)
    if handler is None:
        print(
            f"[slot_selection_node] WARNING: truly unhandled stage='{slot_stage}' — resetting"
        )
        recovered = {
            **state,
            "slot_stage": None,
            "slot_chosen_date": None,
            "slot_chosen_period": None,
            "slot_available_list": None,
            "slot_selection_history": [],
        }
        return await slot_selection_node(recovered)

    try:
        return await handler(state, user_text, doctor_name, all_slots, available_dates)
    except Exception as e:
        print(f"[slot_selection_node] stage={slot_stage} error:", e)
        return update_state(
            state,
            speech_ai_text="Sorry, something went wrong. Could you please repeat that?",
        )
