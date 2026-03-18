from __future__ import annotations

import json
import re
from datetime import date, time
from typing import Any

from twilio.twiml.voice_response import Gather, Say

from src.config.settings import settings
from src.control.voice_assistance.models import ainvoke_llm, get_llama1


def update_state(state: dict, **kwargs: Any) -> dict:
    return {**state, **kwargs}


def fresh_state(
    call_to_number=None,
    token=None,
    call_sid=None,
    identity_user_name=None,
    identity_user_email=None,
    identity_user_phone=None,
    identity_patient_id=None,
    appointment_types=None,
) -> dict:
    return {
        "call_to_number": call_to_number,
        "call_sid": call_sid,
        "call_user_token": token,
        "speech_user_text": None,
        "speech_ai_text": None,
        "speech_error": None,
        "service_type": None,
        "identity_user_name": identity_user_name,
        "identity_user_email": identity_user_email,
        "identity_user_phone": identity_user_phone,
        "identity_patient_id": identity_patient_id,
        "identity_confirmation_completed": False,
        "identity_confirmed_user": False,
        "identity_confirm_stage": None,
        "identity_speak_final": False,
        "identity_phone_verified": False,
        "clarify_step": 0,
        "clarify_conversation_history": [],
        "clarify_covered_topics": [],
        "clarify_completed": False,
        "clarify_symptoms_text": None,
        "mapping_intent": None,
        "mapping_emergency": False,
        "mapping_appointment_type_completed": False,
        "mapping_appointment_type_id": None,
        "appointment_types": appointment_types,
        "appointments_list": None,
        "doctor_list": None,
        "doctor_selection_pending": False,
        "doctor_selection_completed": False,
        "doctor_confirmed_id": None,
        "doctor_confirmed_name": None,
        "slot_stage": None,
        "slot_selection_completed": False,
        "slot_chosen_date": None,
        "slot_chosen_period": None,
        "slot_available_list": None,
        "slot_selected": None,
        "slot_selected_start_time": None,
        "slot_selected_end_time": None,
        "slot_selected_display": None,
        "slot_booked_id": None,
        "slot_booked_display": None,
        "pre_confirmation_completed": False,
        "booking_appointment_completed": False,
        "booking_reason_for_visit": None,
        "booking_notes": None,
        "booking_instructions": None,
        "booking_awaiting_confirmation": False,
        "booking_context_snapshot": None,
        "cancellation_stage": None,
        "cancellation_appointment": None,
        "cancellation_complete": False,
    }


def clear_markdown(raw: str) -> str:
    if raw.startswith("```"):
        return "\n".join(line for line in raw.splitlines() if "```" not in line).strip()
    return raw.strip()


async def is_emergency(text: str, get_llama, system_prompt: str) -> bool:
    try:
        model = get_llama()
        response = await model.ainvoke(
            [
                ("system", system_prompt),
                ("human", text),
            ]
        )
        return response.content.strip().upper() == "EMERGENCY"
    except Exception as exc:
        print("is_emergency error:", str(exc))
        return False


async def generate_next_response(
    conversation: str,
    uncovered_topics: list[str],
    model: Any,
    system_prompt: str,
) -> str:
    topics_str = (
        "\n".join(f"- {t}" for t in uncovered_topics)
        if uncovered_topics
        else "None — all covered."
    )

    prompt = f"""Conversation so far:
{conversation if conversation.strip() else "(No conversation yet — warmly thank the patient for confirming their name and phone number, then ask about their main symptom.)"}

Topics still not covered:
{topics_str}

Generate your next response now."""

    try:
        response = await model(
            [
                ("system", system_prompt),
                ("human", prompt),
            ]
        )
        return response.content.strip().strip('"').strip("'")
    except Exception as exc:
        print("generate_next_response error:", str(exc))
        return "Could you tell me a bit more about what brings you in today?"


def build_conversation_string(history: list[dict]) -> str:
    lines = []
    for turn in history:
        role = "Agent" if turn.get("role") == "agent" else "Patient"
        lines.append(f"{role}: {turn.get('text', '')}")
    return "\n".join(lines)


def build_symptoms_text(history: list[dict], topics: list[str]) -> str:
    patient_turns = [t["text"] for t in history if t.get("role") == "patient"]
    pairs = [
        f"Q: {topic.capitalize()}\nA: {patient_turns[i] if i < len(patient_turns) else 'Not provided'}"
        for i, topic in enumerate(topics)
    ]
    return "\n\n".join(pairs)


def say(parent, text: str) -> None:
    ssml = f'<speak><prosody rate="{settings.SPEAKING_RATE}">{text}</prosody></speak>'
    parent.append(Say(message=ssml, voice=settings.VOICE))


def make_gather() -> Gather:
    return Gather(
        input="speech",
        action="/api/v1/voice/voice-response",
        method="POST",
        speech_timeout=settings.SPEECH_TIMEOUT,
        timeout=settings.GATHER_TIMEOUT,
        action_on_empty_result=settings.ACTION_ON_EMPTY_RESULT,
        speech_model="phone_call",
        language=settings.LANGUAGE,
    )


MORNING_START = time(6, 0)
MORNING_END = time(12, 0)
AFTERNOON_START = time(12, 0)
AFTERNOON_END = time(17, 0)
EVENING_START = time(17, 0)
EVENING_END = time(21, 0)


def format_time(t: time) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def format_date(d: date) -> str:
    return d.strftime("%A, %b %d %Y")


def format_date_iso(d: date) -> str:
    return f"{format_date(d)} -> {d.isoformat()}"


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


def build_date_options_text(available_dates: list[date]) -> str:
    return "\n".join(format_date_iso(d) for d in available_dates)


def build_slot_context_text(
    slots: list[dict], *, use_full_display: bool = False
) -> str:
    display_key = "full_display" if use_full_display else "display"
    return "\n".join(
        f"slot_id={s['id']} start_time={s['start_time']} end_time={s['end_time']} display={s[display_key]}"
        for s in slots
    )

def _coerce_time(val: time | str | None) -> time | None:
    if val is None:
        return None
    if isinstance(val, time):
        return val
    try:
        return time.fromisoformat(str(val))
    except Exception:
        return None


def exclude_previously_selected_slot(
    slots: list[dict],
    user_change_request: str | None,
    prev_start: str | None,
    prev_end: str | None,
) -> list[dict]:

    if not user_change_request or not prev_start or not prev_end:
        return slots

    prev_start_t = _coerce_time(prev_start)
    prev_end_t = _coerce_time(prev_end)

    if prev_start_t is None or prev_end_t is None:
        return slots

    filtered = [
        s
        for s in slots
        if not (
            _coerce_time(s["start_time"]) == prev_start_t
            and _coerce_time(s["end_time"]) == prev_end_t
        )
    ]
    return filtered or slots


def get_nearest_alternate_dates(
    chosen_date: date, available_dates: list[date]
) -> list[date]:
    
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


_SLOT_CHOICE_RE = re.compile(
    r"\b(\d{1,2}(:\d{2})?\s*(am|pm)?"
    r"|morning|afternoon|evening|night"
    r"|first|second|last|other|another)\b",
    re.IGNORECASE,
)


def looks_like_slot_choice(text: str) -> bool:

    return bool(_SLOT_CHOICE_RE.search(text))


async def invokeLLM_json(system_prompt: str, user_prompt: str) -> str:
    try:
        llm = get_llama1()
        response = await llm.ainvoke(
            [
                ("system", system_prompt),
                ("human", user_prompt),
            ]
        )
        raw = response.content.strip()
        cleaned_response = json.loads(clear_markdown(raw))
        return cleaned_response

    except Exception:
        return "none"


async def invokeLLM(system_prompt: str, user_prompt: str) -> str:
    try:
        llm = get_llama1()
        raw = await llm.ainvoke(
            [
                ("system", system_prompt),
                ("human", user_prompt),
            ]
        )
        response = raw.content.strip()
        return response

    except Exception:
        return "none"


async def invokeLargeLLM_json(messages) -> str:
    try:
        response = await ainvoke_llm(messages)
        raw = response.content.strip()
        cleaned_response = json.loads(clear_markdown(raw))

        return cleaned_response

    except Exception:
        return "none"


async def invokeLargeLLM(messages) -> str:
    try:
        raw = await ainvoke_llm(messages)
        response = raw.content.strip()

        return response

    except Exception:
        return "none"
