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

FALLBACK_RESPONSE = "I'm here to help with your appointment. Let's continue from where we left off."

def build_general_assistance_prompt(state: dict) -> str:
    
    user_text = state.get("speech_user_text", "")

    mapping = [
        ("Service Intent", state.get("service_intent_history")),
        ("Identity Confirmation", state.get("identity_conversation_history")),
        ("Symptom Clarification", state.get("clarify_conversation_history")),
        ("Doctor Selection", state.get("doctor_selection_history")),
        ("Slot Selection", state.get("slot_selection_history")),
        ("Mapping History",state.get("mapping_history"))
    ]

    context_lines = []
    for label, history in mapping:
        if not history:
            continue
        recent = history[-4:]
        context_lines.append(f"[{label}]")
        for msg in recent:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "").strip()
            if content:
                context_lines.append(f"  {role}: {content}")

    context_block = "\n".join(context_lines) if context_lines else "No prior conversation."

    facts = []
    if state.get("service_type"):
        facts.append(f"Service type: {state['service_type']}")
    if state.get("patient_name"):
        facts.append(f"Patient name: {state['patient_name']}")
    if state.get("doctor_confirmed_name"):
        facts.append(f"Doctor: {state['doctor_confirmed_name']}")

    slot = state.get("slot_selected_display") or (state.get("slot_selected") or {}).get("full_display")
    if slot:
        facts.append(f"Slot: {slot}")

    facts_block = "\n".join(f"  • {f}" for f in facts) if facts else "None yet."

    return f"""
Confirmed facts so far:
{facts_block}

Recent conversation history:
{context_block}

The patient just said:
"{user_text}"

Answer their question helpfully, then redirect them back to the appointment process.
""".strip()