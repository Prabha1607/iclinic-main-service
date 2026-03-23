from src.control.voice_assistance.utils import invokeLargeLLM


async def general_assistance_node(state: dict) -> dict:
    print("[general_assistance_node] -----------------------------")

    user_text = state.get("speech_user_text", "")

    # Collect any available history for context
    history_parts = []

    service_intent_history = state.get("service_intent_history") or []
    if service_intent_history:
        history_parts.append(("Service Intent", service_intent_history))

    identity_history = state.get("identity_conversation_history") or []
    if identity_history:
        history_parts.append(("Identity Confirmation", identity_history))

    clarify_history = state.get("clarify_conversation_history") or []
    if clarify_history:
        history_parts.append(("Symptom Clarification", clarify_history))

    doctor_history = state.get("doctor_selection_history") or []
    if doctor_history:
        history_parts.append(("Doctor Selection", doctor_history))

    slot_history = state.get("slot_selection_history") or []
    if slot_history:
        history_parts.append(("Slot Selection", slot_history))

    # Build context block
    context_lines = []
    for label, history in history_parts:
        recent = history[-4:] if len(history) > 4 else history
        context_lines.append(f"[{label}]")
        for msg in recent:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "").strip()
            if content:
                context_lines.append(f"  {role}: {content}")

    context_block = "\n".join(context_lines) if context_lines else "No prior conversation."

    # Known confirmed facts
    facts = []
    service_type = state.get("service_type")
    if service_type:
        facts.append(f"Service type: {service_type}")
    name = state.get("patient_name")
    if name:
        facts.append(f"Patient name: {name}")
    doctor = state.get("doctor_confirmed_name")
    if doctor:
        facts.append(f"Doctor: {doctor}")
    slot = state.get("slot_selected_display") or (state.get("slot_selected") or {}).get("full_display")
    if slot:
        facts.append(f"Slot: {slot}")

    facts_block = "\n".join(f"  • {f}" for f in facts) if facts else "None yet."

    system_prompt = """
You are a warm, helpful voice assistant at a healthcare clinic.

The patient has asked something that is not directly part of the current booking or cancellation flow.
Your job is to answer their question helpfully and naturally, then gently guide them back to the ongoing process.

Rules:
- Answer the question clearly and concisely.
- If the question is completely unrelated to healthcare or their appointment, politely let them know
  you are focused on clinic services and redirect them.
- Never make up appointment details, doctor names, or dates.
- After answering, always bring them back to the next pending step in their appointment process.
- Keep it conversational — 2 to 3 sentences max.
- Output only the spoken response. No labels, no markdown.
"""

    user_prompt = f"""
Confirmed facts so far:
{facts_block}

Recent conversation history:
{context_block}

The patient just said:
"{user_text}"

Answer their question helpfully, then redirect them back to the appointment process.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = await invokeLargeLLM(messages=messages)
        ai_text = response.strip() if response else "I'm here to help with your appointment. Could we continue from where we left off?"
    except Exception as e:
        print("[general_assistance_node] LLM error:", e)
        ai_text = "I'm here to help with your appointment. Let's continue from where we left off."

    print("[general_assistance_node] Response:", ai_text)

    return {**state, "speech_ai_text": ai_text, "active_node": "general_assistance"}
