from src.control.voice_assistance.prompts.stt_node_prompt import STT_INTENT_SYSTEM
from src.control.voice_assistance.utils import invokeLLM_json


def _reset_from_doctor(state: dict, user_text: str) -> dict:
    return {
        **state,
        "user_change_request": user_text,
        "doctor_selection_pending": False,
        "doctor_selection_completed": False,
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
        "booking_appointment_completed": False,
        "booking_reason_for_visit": None,
        "booking_notes": None,
        "booking_instructions": None,
        "booking_awaiting_confirmation": False,
        "booking_context_snapshot": None,
        "pre_confirmation_completed": False,
        "cancellation_stage": None,
        "cancellation_appointment": None,
        "cancellation_complete": False,
    }


def _reset_from_date(state: dict, user_text: str) -> dict:
    return {
        **state,
        "user_change_request": user_text,
        "slot_stage": None,
        "slot_selection_completed": False,
        "slot_chosen_period": None,
        "slot_available_list": None,
        "slot_selected": None,
        "slot_selected_start_time": None,
        "slot_selected_end_time": None,
        "slot_selected_display": None,
        "slot_booked_id": None,
        "slot_booked_display": None,
        "booking_appointment_completed": False,
        "booking_reason_for_visit": None,
        "booking_notes": None,
        "booking_instructions": None,
        "booking_awaiting_confirmation": False,
        "booking_context_snapshot": None,
        "pre_confirmation_completed": False,
        "cancellation_stage": None,
        "cancellation_appointment": None,
        "cancellation_complete": False,
    }


def _reset_from_slot(state: dict, user_text: str) -> dict:
    return {
        **state,
        "user_change_request": user_text,
        "slot_stage": "ask_slot",
        "slot_selection_completed": False,
        "slot_selected": None,
        "slot_selected_display": None,
        "slot_booked_id": None,
        "slot_booked_display": None,
        "booking_appointment_completed": False,
        "booking_reason_for_visit": None,
        "booking_notes": None,
        "booking_instructions": None,
        "booking_awaiting_confirmation": False,
        "booking_context_snapshot": None,
        "pre_confirmation_completed": False,
        "cancellation_stage": None,
        "cancellation_appointment": None,
        "cancellation_complete": False,
    }


async def stt_node(state: dict) -> dict:

    user_text: str | None = state.get("speech_user_text")

    if not user_text:
        return {**state, "speech_user_text": None}
    cleaned = " ".join(user_text.split()).strip()

    print(f"[stt_node] user text: {user_text}")

    base_state = {
        **state,
        "speech_user_text": cleaned,
        "user_change_request": None,
    }

    parsed = await invokeLLM_json(system_prompt=STT_INTENT_SYSTEM, user_prompt=cleaned)
    intent = parsed.get("intent", "none")

    if intent == "change_doctor" and state.get("doctor_confirmed_id") is not None:
        return _reset_from_doctor(base_state, cleaned)

    if intent == "change_date" and state.get("slot_chosen_date") is not None:
        return _reset_from_date(base_state, cleaned)

    if intent == "change_slot" and state.get("slot_selected") is not None:
        return _reset_from_slot(base_state, cleaned)

    return base_state
