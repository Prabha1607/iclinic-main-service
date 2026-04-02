"""Routing functions for the voice assistance LangGraph.

Each function reads the current graph state and returns the name of the
next node to execute, enabling conditional branching in the appointment
booking and cancellation flows.
"""


def route_after_query_intent(state: dict) -> str:
    """Determine the next node after the query intent classification step.

    Evaluates the current state to decide whether to route to TTS, stay
    in the active node, handle an out-of-context query, collect the service
    type, or continue through the booking or cancellation flow.

    Args:
        state: Graph state containing intent flags, active node, service type,
               and completion flags for each booking step.

    Returns:
        Name of the next graph node to execute.
    """
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
    """Determine the next node after the pre-confirmation step.

    Routes back to slot or doctor selection when the patient declines, or
    forwards to booking when the patient confirms the appointment details.

    Args:
        state: Graph state containing pre-confirmation flags and active node.

    Returns:
        Name of the next graph node to execute.
    """
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
    """Determine the next node after identity confirmation.

    Routes to TTS when confirmation is still pending or the patient has not
    yet confirmed, and forwards to the clarification node once confirmed.

    Args:
        state: Graph state containing identity confirmation flags.

    Returns:
        Name of the next graph node to execute.
    """
    if not state.get("identity_confirmation_completed"):
        return "tts"
    if not state.get("identity_confirmed_user"):
        return "tts"
    if state.get("identity_speak_final"):
        return "tts"
    return "clarify"


def route_after_service_intent(state: dict) -> str:
    """Determine the next node after the service intent step.

    Routes to identity confirmation for booking, cancellation slot selection
    for cancellations, or TTS when no service type has been resolved.

    Args:
        state: Graph state containing the resolved ``service_type``.

    Returns:
        Name of the next graph node to execute.
    """
    service = state.get("service_type")
    if service == "booking":
        return "identity_confirmation"
    if service == "cancellation":
        return "cancellation_slot_selection"
    return "tts"


def route_after_clarify(state: dict) -> str:
    """Determine the next node after the clarification step.

    Routes to TTS on emergency detection or when clarification is still
    ongoing, and forwards to doctor selection once clarification completes.

    Args:
        state: Graph state containing clarify completion and emergency flags.

    Returns:
        Name of the next graph node to execute.
    """
    if state.get("mapping_emergency"):
        return "tts"
    if not state.get("clarify_completed"):
        return "tts"
    return "doctor_selection"


def route_after_doctor_selection(state: dict) -> str:
    """Determine the next node after the doctor selection step.

    Routes to booking slot selection once a doctor has been confirmed,
    or to TTS while waiting for the patient's doctor choice.

    Args:
        state: Graph state containing doctor selection and confirmation flags.

    Returns:
        Name of the next graph node to execute.
    """
    if state.get("doctor_selection_completed") and state.get("doctor_confirmed_id"):
        return "booking_slot_selection"
    return "tts"


def route_after_booking_slot_selection(state: dict) -> str:
    """Determine the next node after the booking slot selection step.

    Routes to the pre-confirmation node when a slot has been chosen and is
    ready to book, or to TTS while waiting for the patient's slot choice.

    Args:
        state: Graph state containing slot selection and stage flags.

    Returns:
        Name of the next graph node to execute.
    """
    if (
        state.get("booking_slot_selection_completed")
        and state.get("slot_stage") == "ready_to_book"
    ):
        return "pre_confirmation"
    return "tts"


def route_after_cancellation_slot_selection(state: dict) -> str:
    """Determine the next node after the cancellation slot selection step.

    Routes to TTS on completion or when awaiting a slot decision, and
    forwards to the cancel_appointment node when confirmation is needed.

    Args:
        state: Graph state containing cancellation stage and completion flags.

    Returns:
        Name of the next graph node to execute.
    """
    if state.get("cancellation_complete"):
        return "tts"
    if state.get("cancellation_stage") == "ask_confirm":
        return "cancel_appointment"
    return "tts"