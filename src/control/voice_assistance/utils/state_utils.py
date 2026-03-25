from typing import Any

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



def reset_from_doctor(state: dict, user_text: str) -> dict:
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
    return {
        **state,
        "user_change_request":              user_text,
        "slot_stage":                       "ask_date",
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
    return {
        **state,
        "user_change_request":              user_text,
        "active_node": "doctor_selection",
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
