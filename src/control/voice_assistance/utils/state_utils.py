"""State helper utilities for the voice assistance LangGraph.

Provides factory and mutation helpers for building, updating, and partially
resetting the ``VoiceState`` dict as the graph transitions between nodes.
"""
from typing import Any
from src.control.voice_assistance.state import VoiceState

def update_state(state: dict, **kwargs: Any) -> dict:
    """Return a new state dict with the given key-value pairs applied.

    Args:
        state: Current graph state.
        **kwargs: Fields to override.

    Returns:
        New state dict with overrides merged.
    """
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
    """Build a blank initial state dict for a new voice call session.

    Args:
        call_to_number: Destination phone number for the call.
        token: Bearer JWT token for downstream API calls.
        call_sid: Unique Twilio call SID.
        identity_user_name: Pre-populated patient name (from token claims).
        identity_user_email: Pre-populated patient email.
        identity_user_phone: Pre-populated patient phone number.
        identity_patient_id: Pre-populated patient ID.
        appointment_types: Pre-fetched appointment type dict.

    Returns:
        Fully initialised ``VoiceState``-compatible dict.
    """
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



def reset_from_doctor(state: dict, user_text: str) -> dict:
    """Reset booking progress to the doctor selection step.

    Clears all downstream slot and booking state while preserving earlier
    identity and appointment-type progress.

    Args:
        state: Current graph state.
        user_text: Patient utterance that triggered the change request.

    Returns:
        Updated state with doctor selection and subsequent fields reset.
    """
    return {
        **state,
        "user_change_request":              user_text,
        "active_node": "doctor_selection",
        "doctor_selection_pending":         False,
        "doctor_selection_completed":       False,
        "slot_stage":                       None,
        "booking_slot_selection_completed": False,
        "slot_chosen_date":                 None,
        "slot_chosen_period":               None,
        "slot_available_list":              None,
        "slot_selected":                    None,
        "slot_selected_start_time":         None,
        "slot_selected_end_time":           None,
        "slot_time_hint":                   None,
        "slot_selected_display":            None,
        "slot_booked_id":                   None,
        "slot_booked_display":              None,
        "booking_slot_selection_history":   [],
        "pre_confirmation_completed":       False,
        "booking_appointment_completed":    False,
        "booking_reason_for_visit":         None,
        "booking_notes":                    None,
        "booking_instructions":             None,
        "booking_awaiting_confirmation":    False,
        "booking_context_snapshot":         None,
        "cancellation_stage":               None,
        "cancellation_appointment":         None,
        "cancellation_complete":            False,
    }


def reset_from_date(state: dict, user_text: str) -> dict:
    """Reset booking progress to the date-selection step.

    Preserves doctor selection and clears only slot and booking state.

    Args:
        state: Current graph state.
        user_text: Patient utterance that triggered the change request.

    Returns:
        Updated state with slot-related fields reset.
    """
    return {
        **state,
        "user_change_request":              user_text,
        "slot_stage":                       "ask_date",
        "active_node": "booking_slot_selection",
        "booking_slot_selection_completed": False,
        "slot_chosen_date":                 None,
        "slot_chosen_period":               None,
        "slot_available_list":              None,
        "slot_selected":                    None,
        "slot_time_hint":                   None,
        "slot_selected_start_time":         None,
        "slot_selected_end_time":           None,
        "slot_selected_display":            None,
        "slot_booked_id":                   None,
        "slot_booked_display":              None,
        "booking_slot_selection_history":   [],
        "pre_confirmation_completed":       False,
        "booking_appointment_completed":    False,
        "booking_reason_for_visit":         None,
        "booking_notes":                    None,
        "booking_instructions":             None,
        "booking_awaiting_confirmation":    False,
        "booking_context_snapshot":         None,
        "cancellation_stage":               None,
        "cancellation_appointment":         None,
        "cancellation_complete":            False,
    }


def reset_from_slot(state: dict, user_text: str) -> dict:
    """Reset booking progress to the slot-selection step.

    Preserves the already-chosen date while clearing slot, pre-confirmation,
    and booking fields.

    Args:
        state: Current graph state.
        user_text: Patient utterance that triggered the change request.

    Returns:
        Updated state with time-slot and downstream fields reset.
    """
    return {
        **state,
        "user_change_request":              user_text,
        "active_node": "booking_slot_selection",
        "slot_stage":                       "ask_slot",
        "booking_slot_selection_completed": False,
        "slot_chosen_period":               None,
        "slot_available_list":              None,
        "slot_selected":                    None,
        "slot_selected_start_time":         None,
        "slot_selected_end_time":           None,
        "slot_selected_display":            None,
        "slot_booked_id":                   None,
        "slot_time_hint":                   None,
        "slot_booked_display":              None,
        "pre_confirmation_completed":       False,
        "booking_appointment_completed":    False,
        "booking_reason_for_visit":         None,
        "booking_notes":                    None,
        "booking_instructions":             None,
        "booking_awaiting_confirmation":    False,
        "booking_context_snapshot":         None,
        "cancellation_stage":               None,
        "cancellation_appointment":         None,
        "cancellation_complete":            False,
    }



def reset_slot_state() -> dict:
    """Return a partial state dict that clears all slot-selection fields.

    Returns:
        Dict containing slot-related keys set to their default empty values.
    """
    return {
        "slot_stage":                       None,
        "slot_chosen_date":                 None,
        "slot_chosen_period":               None,
        "slot_available_list":              None,
        "slot_selected":                    None,
        "slot_selected_start_time":         None,
        "slot_selected_end_time":           None,
        "slot_selected_display":            None,
        "booking_slot_selection_completed": False,
        "booking_slot_selection_history":   [],
    }


def resolve_slot_state(state: dict, matched_slot: dict, ai_text: str,slot_chosen_period : str) -> dict:
    """Build a state update that marks a slot as selected and ready to book.

    Args:
        state: Current graph state.
        matched_slot: Slot dict returned from the availability query.
        ai_text: AI response text to speak to the patient.
        slot_chosen_period: Time-of-day period string (e.g. ``'morning'``).

    Returns:
        Updated state with slot fields populated and completion flag set.
    """
    return update_state(
        state,
        active_node="booking_slot_selection",
        slot_stage="ready_to_book",
        booking_slot_selection_completed=True,
        slot_selected=matched_slot,
        slot_selected_start_time=str(matched_slot["start_time"]),
        slot_selected_end_time=str(matched_slot["end_time"]),
        slot_selected_display=matched_slot["display"],
        slot_chosen_date=matched_slot["date"],
        slot_chosen_period= slot_chosen_period,
        user_change_request=None,
        speech_ai_text=ai_text,
    )


def confirm_doctor_return(
    state: dict,
    doctor_id: int,
    doctor_name: str,
    confirmed_doctor: dict,
    history: list[dict],
    conversation_summary: str,
    doctor_change_log: list[dict],
    updated_cache: dict,
    ai_text: str,
    reset_slots: bool = False,
) -> dict:
    """Build and return the state update that confirms a doctor selection.

    Optionally resets slot-selection state when the patient switches doctors
    after already choosing a slot.

    Args:
        state: Current graph state.
        doctor_id: ID of the confirmed doctor.
        doctor_name: Display name of the confirmed doctor.
        confirmed_doctor: Full doctor dict for the selected provider.
        history: Updated conversation history list.
        conversation_summary: Rolling summary of the conversation.
        doctor_change_log: Log of doctor change events this session.
        updated_cache: Refreshed doctors cache dict.
        ai_text: AI response text to speak to the patient.
        reset_slots: If ``True``, clear slot-related state fields.

    Returns:
        Updated state with doctor confirmation fields and optional slot reset.
    """

    result = {
        **state,
        "active_node":                 "doctor_selection",
        "user_change_request":         None,
        "doctor_confirmed_id":          doctor_id,
        "doctor_confirmed_name":        doctor_name,
        "doctor_selection_completed":   True,
        "doctor_selection_pending":     False,
        "doctor_selection_history":     history,
        "doctor_conversation_summary":  conversation_summary,
        "doctor_change_log":            doctor_change_log,
        "doctors_cache":                updated_cache,
        "speech_ai_text":               ai_text,
    }
    if reset_slots:
        result.update(reset_slot_state())
    return result

def update_global_history(state: VoiceState, role: str, message: str, node: str):
    if state.get("global_conversation_history") is None:
        state["global_conversation_history"] = []

    state["global_conversation_history"].append({
        "role": role,
        "message": message,
        "node": node
    })
