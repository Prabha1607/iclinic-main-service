from typing_extensions import TypedDict


class VoiceState(TypedDict):
    call_to_number: str | None
    call_sid: str | None
    call_user_token: str | None

    speech_user_text: str | None
    speech_ai_text: str | None
    speech_error: str | None

    service_type: str | None

    identity_user_name: str | None
    identity_user_email: str | None
    identity_user_phone: str | None
    identity_patient_id: int | None

    identity_confirmation_completed: bool | None
    identity_conversation_history: list[dict[str, str]] | None
    identity_confirmed_user: bool | None
    identity_confirm_stage: str | None
    identity_speak_final: bool | None
    identity_phone_verified: bool | None

    clarify_step: int | None
    clarify_conversation_history: list[dict[str, str]] | None
    clarify_covered_topics: list[str] | None
    clarify_completed: bool | None
    clarify_symptoms_text: str | None

    mapping_intent: str | None
    mapping_emergency: bool | None
    mapping_appointment_type_completed: bool | None
    mapping_appointment_type_id: int | None

    appointment_types: dict[int, list[str]] | None
    appointments_list: list[dict] | None

    doctor_list: list[dict] | None
    doctor_selection_pending: bool | None
    doctor_selection_completed: bool | None
    doctor_confirmed_id: int | None
    doctor_confirmed_name: str | None

    slot_selection_history: list[dict[str, str]] | None
    slot_stage: str | None
    slot_selection_completed: bool | None
    slot_chosen_date: str | None
    slot_chosen_period: str | None
    slot_available_list: list[dict] | None
    slot_selected: dict | None
    slot_selected_start_time: str | None
    slot_selected_end_time: str | None
    slot_selected_display: str | None
    slot_booked_id: int | None
    slot_booked_display: str | None

    pre_confirmation_completed: bool | None

    booking_appointment_completed: bool | None
    booking_reason_for_visit: str | None
    booking_notes: str | None
    booking_instructions: str | None
    booking_awaiting_confirmation: bool | None
    booking_context_snapshot: dict | None

    cancellation_stage: str | None
    cancellation_appointment: dict | None
    cancellation_complete: bool | None
    cancellation_awaiting_fresh_input: bool | None
    cancellation_confirmed: bool | None
    user_change_request: str | None
