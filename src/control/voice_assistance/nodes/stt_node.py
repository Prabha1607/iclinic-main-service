from datetime import date
from src.control.voice_assistance.prompts.stt_node_prompt import build_stt_intent_system
from src.control.voice_assistance.utils import invokeLLM_json


def _format_date_display(value) -> str | None:
    """Convert a date object or ISO string to human-readable form for the prompt."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.strftime("%A, %b %d %Y")
    try:
        return date.fromisoformat(str(value)).strftime("%A, %b %d %Y")
    except Exception:
        return str(value)


def _build_intent_system(state: dict) -> str:
    """
    Build the context-aware STT_INTENT_SYSTEM prompt by reading the current
    confirmed selections from state.

    This is the core fix: previously the classifier had no idea what was already
    selected, so "I'd like 11:30" looked identical to a first-time selection and
    was classified as 'none'. Now it can compare the patient's words directly
    against the confirmed slot/date/period/doctor.
    """
    confirmed_doctor: str | None = state.get("doctor_confirmed_name")
    confirmed_date: str | None = _format_date_display(state.get("slot_chosen_date"))
    confirmed_period: str | None = state.get("slot_chosen_period")
    confirmed_slot: str | None = state.get("slot_selected_display")

    return build_stt_intent_system(
        confirmed_doctor=confirmed_doctor,
        confirmed_date=confirmed_date,
        confirmed_period=confirmed_period,
        confirmed_slot=confirmed_slot,
    )


def _reset_from_doctor(state: dict, user_text: str) -> dict:
    return {
        **state,
        "user_change_request":              user_text,
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


def _reset_from_date(state: dict, user_text: str) -> dict:
    return {
        **state,
        "user_change_request":              user_text,
        "slot_stage":                       None,
        "booking_slot_selection_completed": False,
        "slot_chosen_date":                 None,
        "slot_chosen_period":               None,
        "slot_available_list":              None,
        "slot_selected":                    None,
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


def _reset_from_slot(state: dict, user_text: str) -> dict:
    # Keep slot_chosen_date only — clear period and available list so the node
    # re-presents ALL slots for that date fresh. This prevents stale morning/afternoon
    # context from causing the wrong slot to be matched.
    return {
        **state,
        "user_change_request":              user_text,
        "slot_stage":                       "ask_slot",
        "booking_slot_selection_completed": False,
        "slot_chosen_period":               None,
        "slot_available_list":              None,
        "slot_selected":                    None,
        "slot_selected_start_time":         None,
        "slot_selected_end_time":           None,
        "slot_selected_display":            None,
        "slot_booked_id":                   None,
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


def _build_context_block(state: dict) -> str:
    active_node: str | None = state.get("active_node")

    if active_node in ("pre_confirmation", "book_appointment", "cancel_appointment"):
        stage_descriptions = {
            "pre_confirmation": (
                "The assistant has just presented the full appointment summary "
                "(doctor, date, time) to the patient and is waiting for a yes/no confirmation."
            ),
            "book_appointment": (
                "The assistant is in the process of finalising and saving the appointment booking. "
                "No further input is expected from the patient at this point."
            ),
            "cancel_appointment": (
                "The assistant has identified the appointment to cancel and is waiting "
                "for the patient to confirm or decline the cancellation."
            ),
        }
        return f"Current stage: {stage_descriptions[active_node]}"

    history_map = {
        "service_intent":              state.get("service_intent_history") or [],
        "identity_confirmation":       state.get("identity_conversation_history") or [],
        "clarify":                     state.get("clarify_conversation_history") or [],
        "booking_slot_selection":      state.get("booking_slot_selection_history") or [],
        "cancellation_slot_selection": state.get("cancellation_slot_selection_history") or [],
    }

    if active_node == "doctor_selection":
        summary = (state.get("doctor_conversation_summary") or "").strip()
        if summary:
            return (
                f"Current stage: The assistant is helping the patient choose a doctor.\n"
                f"Conversation summary so far:\n  {summary}"
            )
        return "Current stage: The assistant is helping the patient choose a doctor. No prior turns yet."

    history: list[dict] = history_map.get(active_node or "", [])

    stage_labels = {
        "service_intent":              "The assistant is identifying whether the patient wants to book or cancel an appointment.",
        "identity_confirmation":       "The assistant is verifying the patient's identity (name and phone number).",
        "clarify":                     "The assistant is collecting the patient's symptoms and health concerns.",
        "booking_slot_selection":      "The assistant is helping the patient choose a date and time slot for their appointment.",
        "cancellation_slot_selection": "The assistant is helping the patient identify which appointment they want to cancel.",
    }

    label = stage_labels.get(active_node or "", "The assistant is handling an appointment-related task.")
    lines = [f"Current stage: {label}"]

    if history:
        recent = history[-4:] if len(history) > 4 else history
        lines.append("Recent conversation (last few turns):")
        for msg in recent:
            role = msg.get("role", "user").capitalize()
            content = (msg.get("content") or "").strip()
            if content and msg.get("role") in ("user", "assistant"):
                lines.append(f"  {role}: {content}")

    return "\n".join(lines)


def _build_out_of_context_prompt(context_block: str) -> str:
    return f"""
You are an intent classifier for a healthcare clinic voice assistant.

The assistant handles ONLY these tasks:
  - Booking a doctor appointment
  - Cancelling a doctor appointment
  - Selecting or changing a doctor
  - Choosing or changing a date / time slot
  - Confirming patient identity (name, phone)
  - Describing health symptoms or medical concerns
  - Answering yes/no confirmation questions during the booking or cancellation flow
  - Asking clarifying questions about the current step (e.g. "what does that mean?", "can you repeat?")

────────────────────────────────────────
CURRENT CONVERSATION CONTEXT
────────────────────────────────────────
{context_block}

────────────────────────────────────────
CLASSIFICATION RULES
────────────────────────────────────────
Mark as OUT OF CONTEXT (true) if the patient says something completely unrelated
to the above tasks — for example:
  - General knowledge questions ("what is the capital of France?")
  - Weather, news, sports, entertainment
  - Jokes, casual chitchat unrelated to the appointment
  - Requests for the assistant to do something outside clinic tasks

Mark as IN CONTEXT (false) if the patient says something that:
  - Directly relates to any of the tasks listed above
  - Is a yes/no or short reply that fits the current stage (e.g. "yes", "no", "tomorrow", "morning")
  - Mentions a doctor, date, time, symptom, health issue, name, or phone number
  - Is a follow-up or clarifying question about the current step
  - Could reasonably be interpreted as part of the ongoing appointment flow

When in doubt, lean towards IN CONTEXT (false).
The patient may use casual or indirect language — do not penalise natural speech.

Respond ONLY with valid JSON, no markdown, no explanation:
{{"is_out_of_context": true}}   — if completely off-topic
{{"is_out_of_context": false}}  — if related to the appointment flow
""".strip()


async def stt_node(state: dict) -> dict:

    user_text: str | None = state.get("speech_user_text")

    if not user_text:
        return {**state, "speech_user_text": None}

    cleaned = " ".join(user_text.split()).strip()
    print(f"[stt_node] user text: {cleaned}")

    base_state = {
        **state,
        "speech_user_text": cleaned,
        "user_change_request": None,
        "is_out_of_context": False,
    }

    # Build context-aware intent prompt using current confirmed selections.
    # This is injected into EVERY intent check so the LLM can compare the
    # patient's words against what is already booked/selected.
    stt_intent_system = _build_intent_system(state)

    active_node = state.get("active_node")

    # ── At pre_confirmation stage, run change-intent detection FIRST ──────────
    # Ensures "I'd like 11:30" is detected as change_slot rather than treated as
    # a confirmation of the currently selected slot (e.g. 10:30 AM).
    if active_node == "pre_confirmation":
        parsed = await invokeLLM_json(system_prompt=stt_intent_system, user_prompt=cleaned)
        intent = parsed.get("intent", "none") if isinstance(parsed, dict) else "none"
        print(f"[stt_node] pre_confirmation intent check: {intent}")
        print(f"[stt_node] context → doctor={state.get('doctor_confirmed_name')} "
              f"date={state.get('slot_chosen_date')} "
              f"period={state.get('slot_chosen_period')} "
              f"slot={state.get('slot_selected_display')}")

        if intent == "change_doctor" and state.get("doctor_confirmed_id") is not None:
            return _reset_from_doctor(base_state, cleaned)

        if intent == "change_date" and state.get("slot_chosen_date") is not None:
            return _reset_from_date(base_state, cleaned)

        if intent == "change_slot":
            return _reset_from_slot(base_state, cleaned)

        return base_state

    # ── Normal flow for all other nodes ──────────────────────────────────────
    context_block = _build_context_block(state)
    out_of_context_system = _build_out_of_context_prompt(context_block)

    context_check = await invokeLLM_json(
        system_prompt=out_of_context_system,
        user_prompt=cleaned,
    )

    if isinstance(context_check, dict) and context_check.get("is_out_of_context"):
        print("[stt_node] Out-of-context utterance detected — routing to general_assistance")
        return {**base_state, "is_out_of_context": True}

    # ── Change-intent detection for non-pre_confirmation nodes ────────────────
    # Also context-aware: if a patient says "give me morning instead" while in
    # booking_slot_selection with afternoon already chosen, it is a change_slot.
    parsed = await invokeLLM_json(system_prompt=stt_intent_system, user_prompt=cleaned)
    intent = parsed.get("intent", "none") if isinstance(parsed, dict) else "none"

    if intent == "change_doctor" and state.get("doctor_confirmed_id") is not None:
        return _reset_from_doctor(base_state, cleaned)

    if intent == "change_date" and state.get("slot_chosen_date") is not None:
        return _reset_from_date(base_state, cleaned)

    if intent == "change_slot" and state.get("slot_selected") is not None:
        return _reset_from_slot(base_state, cleaned)

    return base_state