import json
from src.control.voice_assistance.models import get_llama1
from src.control.voice_assistance.prompts.pre_confirmation_noode_prompt import (
    INTENT_DETECTION_SYSTEM_PROMPT,
    PRE_CONFIRMATION_SYSTEM_PROMPT,
)
from src.control.voice_assistance.utils import invokeLLM_json, update_state


def _build_snapshot(state: dict) -> dict:

    slot = state.get("slot_selected") or {}
    return {
        "patient_name": state.get("identity_user_name"),
        "doctor_name": state.get("doctor_confirmed_name"),
        "appointment_slot": slot.get("full_display")
        or state.get("slot_booked_display"),
        "appointment_date": slot.get("date"),
        "appointment_time": (
            f"{slot.get('start_time')} – {slot.get('end_time')}"
            if slot.get("start_time")
            else None
        ),
        "appointment_type_id": state.get("mapping_appointment_type_id"),
        "symptoms_summary": state.get("clarify_symptoms_text"),
        "reason_for_visit": state.get("booking_reason_for_visit"),
    }


async def _generate_confirmation_message(snapshot: dict) -> str:
    llm = get_llama1()
    response = await llm.ainvoke(
        [
            ("system", PRE_CONFIRMATION_SYSTEM_PROMPT),
            (
                "human",
                f"Booking details:\n{json.dumps(snapshot, default=str, indent=2)}",
            ),
        ]
    )
    return response.content.strip()


async def pre_confirmation_node(state: dict) -> dict:
    print("\n[pre_confirmation_node] --------------------------------")

    # FIX: If stt_node detected a change request (doctor / date / slot),
    # do NOT treat this turn as a confirmation reply. Route back to slot
    # selection so the patient can re-select.
    # This fixes the race where "I want to go with 10 o'clock" was
    # interpreted as confirming the previously selected slot.
    if state.get("user_change_request"):
        print(
            f"[pre_confirmation_node] Change request detected "
            f"({state['user_change_request']!r}) — deferring to slot selection"
        )
        return update_state(
            state,
            active_node="booking_slot_selection",
            booking_awaiting_confirmation=False,
            pre_confirmation_completed=False,
        )

    awaiting = state.get("booking_awaiting_confirmation", False)

    if awaiting:
        user_text = (state.get("speech_user_text") or "").strip()
        print(f"[pre_confirmation_node] User reply: {user_text!r}")

        response = await invokeLLM_json(
            INTENT_DETECTION_SYSTEM_PROMPT, f'Patient reply: "{user_text}"'
        )

        confirmed = bool(response.get("confirmed"))
        uncertain = bool(response.get("uncertain"))

        if confirmed:
            return update_state(
                state,
                active_node="pre_confirmation",
                booking_awaiting_confirmation=False,
                pre_confirmation_completed=True,
                pre_confirmation_retry_count=0,
                speech_ai_text=None,
            )

        if uncertain:
            retry_count = state.get("pre_confirmation_retry_count", 0) + 1
            print(f"[pre_confirmation_node] Uncertain reply (attempt {retry_count})")

            if retry_count >= 3:
                print("[pre_confirmation_node] Too many uncertain replies — resetting to slot selection")
                return update_state(
                    state,
                    active_node="pre_confirmation",
                    booking_awaiting_confirmation=False,
                    pre_confirmation_completed=False,
                    pre_confirmation_retry_count=0,
                    slot_selected=None,
                    slot_stage="ask_date",
                    booking_slot_selection_completed=False,
                    speech_ai_text=(
                        "I'm having a little trouble hearing you clearly. "
                        "Let me take you back to the slot selection so we can start fresh."
                    ),
                )

            snapshot = state.get("booking_context_snapshot") or _build_snapshot(state)
            confirmation_msg = await _generate_confirmation_message(snapshot)
            re_ask = f"Sorry, I didn't quite catch that. {confirmation_msg}"
            return update_state(
                state,
                active_node="pre_confirmation",
                booking_awaiting_confirmation=True,
                pre_confirmation_completed=False,
                pre_confirmation_retry_count=retry_count,
                speech_ai_text=re_ask,
            )

        # Patient declined — go back to slot selection
        return update_state(
            state,
            active_node="pre_confirmation",
            booking_awaiting_confirmation=False,
            pre_confirmation_completed=False,
            pre_confirmation_retry_count=0,
            slot_selected=None,
            slot_stage="ask_date",
            booking_slot_selection_completed=False,
            speech_ai_text=(
                "No problem! Let me show you the available slots again "
                "so you can pick a different time."
            ),
        )

    # Not yet awaiting confirmation — generate initial confirmation message
    snapshot = _build_snapshot(state)
    try:
        confirmation_text = await _generate_confirmation_message(snapshot)
    except Exception as e:
        print(f"[pre_confirmation_node] LLM generation failed: {e}")
        slot = state.get("slot_selected") or {}
        confirmation_text = (
            f"I'd like to confirm your appointment with "
            f"{state.get('doctor_confirmed_name', 'the doctor')} "
            f"on {slot.get('full_display', 'the selected slot')}. "
            "Shall I go ahead and book this for you? Please say yes or no."
        )

    return update_state(
        state,
        active_node="pre_confirmation",
        booking_awaiting_confirmation=True,
        pre_confirmation_completed=False,
        pre_confirmation_retry_count=0,
        booking_context_snapshot=snapshot,
        speech_ai_text=confirmation_text,
    )