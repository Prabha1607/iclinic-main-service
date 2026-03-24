EXTRACT_CONTEXT_PROMPT = """
You are a medical appointment assistant. Analyse the conversation below and extract:

1. reason_for_visit  — Why the patient is seeing the doctor (symptoms, concern, condition).
                        Be concise, 1–2 sentences. null if not mentioned.

2. notes             — Any additional clinical details the patient shared:
                        duration of symptoms, severity, medications, allergies, etc.
                        null if nothing relevant was said.

3. instructions      — Any specific instructions or requests made by the patient or
                        implied from context (e.g. "needs wheelchair access",
                        "prefers female doctor", "follow-up visit").
                        null if none.

Reply ONLY with valid JSON — no markdown, no extra text:
{
  "reason_for_visit": "<string or null>",
  "notes":            "<string or null>",
  "instructions":     "<string or null>"
}
""".strip()

DEFAULT_CONTEXT = {"reason_for_visit": None, "notes": None, "instructions": None}

def build_history_text(conversation_history: list | str) -> str:
    if not isinstance(conversation_history, list):
        return str(conversation_history)

    lines = []

    for turn in conversation_history:
        if isinstance(turn, dict):
            role = turn.get("role", "unknown").capitalize()
            text = turn.get("content", "")

        elif isinstance(turn, (list, tuple)) and len(turn) == 2:
            role, text = turn[0].capitalize(), turn[1]

        else:
            continue

        lines.append(f"{role}: {text}")

    return "\n".join(lines)

