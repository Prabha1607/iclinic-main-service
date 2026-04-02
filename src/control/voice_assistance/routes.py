def route_after_query_intent(state: dict) -> str:
    service_type = state.get("service_type")

    if state.get("speak_only"):
        return "tts"
    
    forced_node = state.get("active_node")
    if forced_node in {
        "booking_slot_selection",
        "doctor_selection",
        "pre_confirmation",
        "identity_confirmation",
        "clarify",
    }:
        return forced_node

    if state.get("is_out_of_context"):
        return "general_assistance"

    if not service_type:
        return "service_intent"

    if service_type == "booking":
        if state.get("user_change_request"):
            if not state.get("doctor_selection_completed"):
                return "doctor_selection"
            if not state.get("booking_slot_selection_completed"):
                return "booking_slot_selection"
            return "booking_slot_selection"
        return _get_booking_next_step(state)

    if service_type == "cancellation":
        if state.get("cancellation_stage") == "ask_confirm":
            return "cancel_appointment"
        return "cancellation_slot_selection"

    return "service_intent"


def _get_booking_next_step(state: dict) -> str:
    if not state.get("identity_confirmation_completed"):
        return "identity_confirmation"
    if not state.get("clarify_completed"):
        return "clarify"
    if not state.get("mapping_appointment_type_completed"):
        return "clarify"
    if not state.get("doctor_selection_completed"):
        return "doctor_selection"
    if not state.get("booking_slot_selection_completed"):
        return "booking_slot_selection"
    if not state.get("pre_confirmation_completed"):
        return "pre_confirmation"
    if not state.get("booking_appointment_completed"):
        return "book_appointment"
    return "tts"


def route_after_pre_confirmation(state: dict) -> str:
    if state.get("active_node") == "booking_slot_selection":
        return "booking_slot_selection"
    if state.get("active_node") == "doctor_selection":
        return "doctor_selection"

    if state.get("pre_confirmation_completed"):
        return "book_appointment"

    if state.get("booking_awaiting_confirmation"):
        return "tts"

    return "tts"


def route_after_identity_confirmation(state: dict) -> str:
    if not state.get("identity_confirmation_completed"):
        return "tts"
    if not state.get("identity_confirmed_user"):
        return "tts"
    if state.get("identity_speak_final"):
        return "tts"
    return "clarify"


def route_after_service_intent(state: dict) -> str:
    service = state.get("service_type")
    if service == "booking":
        return "identity_confirmation"
    if service == "cancellation":
        return "cancellation_slot_selection"
    return "tts"


def route_after_clarify(state: dict) -> str:
    if state.get("mapping_emergency"):
        return "tts"
    if not state.get("clarify_completed"):
        return "tts"
    return "doctor_selection"


def route_after_doctor_selection(state: dict) -> str:
    if state.get("doctor_selection_completed") and state.get("doctor_confirmed_id"):
        return "booking_slot_selection"
    return "tts"


def route_after_booking_slot_selection(state: dict) -> str:
    if (
        state.get("booking_slot_selection_completed")
        and state.get("slot_stage") == "ready_to_book"
    ):
        return "pre_confirmation"
    return "tts"


def route_after_cancellation_slot_selection(state: dict) -> str:
    if state.get("cancellation_complete"):
        return "tts"
    if state.get("cancellation_stage") == "ask_confirm":
        return "cancel_appointment"
    return "tts"