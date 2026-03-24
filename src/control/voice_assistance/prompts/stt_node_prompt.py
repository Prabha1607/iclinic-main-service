from src.control.voice_assistance.utils.date_utils import format_date_display

def build_out_of_context_prompt(state: dict) -> str:
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

    context_block = "\n".join(lines)

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



def build_intent_system(state: dict) -> str:
    confirmed_doctor: str | None = state.get("doctor_confirmed_name")
    confirmed_date: str | None = format_date_display(state.get("slot_chosen_date"))
    confirmed_period: str | None = state.get("slot_chosen_period")
    confirmed_slot: str | None = state.get("slot_selected_display")

    context_lines = []
    if confirmed_doctor:
        context_lines.append(f"  Doctor selected    : {confirmed_doctor}")
    if confirmed_date:
        context_lines.append(f"  Date selected      : {confirmed_date}")
    if confirmed_period:
        context_lines.append(f"  Period selected    : {confirmed_period}")
    if confirmed_slot:
        context_lines.append(f"  Time slot selected : {confirmed_slot}")

    if context_lines:
        context_block = (
            "WHAT HAS ALREADY BEEN SELECTED IN THIS BOOKING:\n"
            + "\n".join(context_lines)
        )
    else:
        context_block = "WHAT HAS ALREADY BEEN SELECTED IN THIS BOOKING:\n  (nothing selected yet)"

    return f"""
    You are an intent classifier for a medical appointment voice booking system.
    The patient is mid-flow. Use the context below to decide if they want to CHANGE something.

    {context_block}

    ────────────────────────────────────────
    YOUR TASK
    ────────────────────────────────────────
    Classify the patient's message into ONE of:
    - "change_doctor"  → wants a different doctor than the one already selected
    - "change_date"    → wants a different date than the one already selected
    - "change_slot"    → wants a different time slot OR period than what is already selected
    - "none"           → normal reply, confirmation, unrelated

    ────────────────────────────────────────
    RULES
    ────────────────────────────────────────
    Use the selected context above to detect implicit changes. Examples:

    If slot selected = "10:30 AM → 11:00 AM":
    - "I'd like 11:30"           → change_slot  (different time from selected)
    - "can I do 11:30 instead"   → change_slot
    - "actually 12 o'clock"      → change_slot
    - "yes that's fine"          → none         (agreeing with selected)
    - "sounds good"              → none

    If period selected = "morning":
    - "I want afternoon instead" → change_slot
    - "can we do evening"        → change_slot
    - "morning is fine"          → none

    If date selected = "Tuesday, Mar 24 2026":
    - "can I do Wednesday"       → change_date
    - "actually next Friday"     → change_date
    - "Tuesday works"            → none

    If doctor selected = "Dr. Sneha Singh":
    - "I want the male doctor"   → change_doctor
    - "can I switch doctors"     → change_doctor
    - "she's fine"               → none

    General rules:
    - If the patient mentions a DIFFERENT time/date/doctor than what is selected → it is a change.
    - If nothing is selected yet for that field, a mention is a FIRST selection → "none".
    - "no" alone or "incorrect" alone → "none" (let pre_confirmation handle it).
    - A simple yes/confirmation word → "none".
    - When in doubt → "none".

    Respond with ONLY valid JSON, no markdown, no explanation:
    {{"intent": "<change_doctor|change_date|change_slot|none>"}}
    """.strip()


