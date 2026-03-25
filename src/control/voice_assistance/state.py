from typing_extensions import TypedDict


class VoiceState(TypedDict):
    # ── Call metadata ─────────────────────────────────────────────────────────
    call_to_number: str | None
    call_sid: str | None
    call_user_token: str | None

    # ── Speech I/O ────────────────────────────────────────────────────────────
    speech_user_text: str | None
    speech_ai_text: str | None
    speech_error: str | None

    # ── Top-level routing ─────────────────────────────────────────────────────
    service_type: str | None
    service_intent_history: list[dict[str, str]] | None
    active_node: str | None
    is_out_of_context: bool | None              

    # ── Identity confirmation ─────────────────────────────────────────────────
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

    # ── Symptom clarification ─────────────────────────────────────────────────
    clarify_step: int | None
    clarify_conversation_history: list[dict[str, str]] | None
    clarify_covered_topics: list[str] | None
    clarify_completed: bool | None
    clarify_symptoms_text: str | None

    # ── Appointment type mapping ──────────────────────────────────────────────
    mapping_intent: str | None
    mapping_emergency: bool | None
    mapping_appointment_type_completed: bool | None
    mapping_appointment_type_id: int | None
    mapping_history: list[dict[str, str]] | None

    appointment_types: dict[int, list[str]] | None
    appointments_list: list[dict] | None

    # ── Doctor selection ──────────────────────────────────────────────────────
    doctor_selection_history: list[dict[str, str]] | None   # recent raw turns (trimmed)
    doctor_conversation_summary: str | None                  # LLM-compressed earlier turns
    doctor_change_log: list[dict] | None                     # [{from, to, reason}] per switch
    doctor_list: list[dict] | None                           # available doctors shown to patient
    doctor_selection_pending: bool | None
    doctor_selection_completed: bool | None
    doctor_confirmed_id: int | None
    doctor_confirmed_name: str | None
    doctors_cache: dict[str, list[dict]] | None              # keyed by str(appointment_type_id)

    # ── Booking slot selection ────────────────────────────────────────────────
    booking_slot_selection_history: list[dict[str, str]] | None
    slot_stage: str | None
    booking_slot_selection_completed: bool | None
    slot_chosen_date: str | None
    slot_chosen_period: str | None
    slot_available_list: list[dict] | None
    slot_time_hint: str | None
    slot_selected: dict | None
    slot_selected_start_time: str | None
    slot_selected_end_time: str | None
    slot_selected_display: str | None
    slot_booked_id: int | None
    slot_booked_display: str | None

    # ── Pre-confirmation ──────────────────────────────────────────────────────
    pre_confirmation_completed: bool | None

    # ── Booking ───────────────────────────────────────────────────────────────
    booking_appointment_completed: bool | None
    booking_reason_for_visit: str | None
    booking_notes: str | None
    booking_instructions: str | None
    booking_awaiting_confirmation: bool | None
    booking_context_snapshot: dict | None

    # ── Cancellation ─────────────────────────────────────────────────────────
    cancellation_slot_selection_history: list[dict[str, str]] | None  # full turn log
    cancellation_stage: str | None          # None | "ask_date" | "ask_slot" | "ask_confirm"
    cancellation_appointments_list: list[dict] | None   # all fetched upcoming appointments
    cancellation_slot_date: str | None      # date the patient picked for cancellation
    cancellation_slot_start_time: str | None            # start time of chosen slot
    cancellation_slot_end_time: str | None              # end time of chosen slot
    cancellation_slot_type_name: str | None             # appointment type name of chosen slot
    cancellation_slot_reason: str | None                # reason_for_visit of chosen slot
    cancellation_appointment_id: int | None             # DB id of the appointment to cancel
    cancellation_appointment: dict | None               # full chosen appointment dict
    cancellation_complete: bool | None
    cancellation_awaiting_fresh_input: bool | None
    cancellation_confirmed: bool | None

    # ── Shared / misc ─────────────────────────────────────────────────────────
    user_change_request: str | None
    explained_topics: set | None


    