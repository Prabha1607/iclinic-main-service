from typing import Any

from src.control.voice_assistance.utils import invokeLargeLLM


# ── History keys per active node ─────────────────────────────────────────────
# Maps each active_node value to the ordered list of history keys that should
# be included in the unified conversation context for that node.
# Empty list = no history context needed.
_NODE_HISTORY_KEYS: dict[str, list[tuple[str, str]]] = {
    # No history needed
    "service_intent": [],
    "identity_confirmation": [],
    "cancellation_slot_selection": [],
    "cancel_appointment": [],
    "cancel_confirmation": [],

    # Clarify: only its own history
    "clarify": [
        ("clarify_conversation_history", "Intent Clarification"),
    ],

    # Doctor selection: clarify + mapping + doctor
    "doctor_selection": [
        ("clarify_conversation_history", "Intent Clarification"),
        ("mapping_history", "Symptom Mapping"),
        ("doctor_selection_history", "Doctor Selection"),
    ],

    # Slot selection and all booking nodes: full booking history
    "slot_selection": [
        ("clarify_conversation_history", "Intent Clarification"),
        ("mapping_history", "Symptom Mapping"),
        ("doctor_selection_history", "Doctor Selection"),
        ("slot_selection_history", "Appointment Slot Selection"),
    ],
    "pre_confirmation": [
        ("clarify_conversation_history", "Intent Clarification"),
        ("mapping_history", "Symptom Mapping"),
        ("doctor_selection_history", "Doctor Selection"),
        ("slot_selection_history", "Appointment Slot Selection"),
    ],
    "book_appointment": [
        ("clarify_conversation_history", "Intent Clarification"),
        ("mapping_history", "Symptom Mapping"),
        ("doctor_selection_history", "Doctor Selection"),
        ("slot_selection_history", "Appointment Slot Selection"),
    ],
    "booking_confirmation": [
        ("clarify_conversation_history", "Intent Clarification"),
        ("mapping_history", "Symptom Mapping"),
        ("doctor_selection_history", "Doctor Selection"),
        ("slot_selection_history", "Appointment Slot Selection"),
    ],
}

# Primary (most recent / most relevant) history key per active node
_NODE_PRIMARY_KEY: dict[str, str] = {
    "clarify": "clarify_conversation_history",
    "doctor_selection": "doctor_selection_history",
    "slot_selection": "slot_selection_history",
    "pre_confirmation": "slot_selection_history",
    "book_appointment": "slot_selection_history",
    "booking_confirmation": "slot_selection_history",
    "mapping": "mapping_history",
}
# ─────────────────────────────────────────────────────────────────────────────


def _build_unified_history(state: dict, active_node: str) -> str:
    """
    Builds a chronological conversation transcript using only the history
    keys relevant to the current active node.
    Returns an empty string when no history is needed for that node.
    """
    keys = _NODE_HISTORY_KEYS.get(active_node)

    # Unknown node — fall back to no history rather than dumping everything
    if keys is None:
        return ""

    # Node explicitly configured to use no history
    if not keys:
        return ""

    all_turns = []
    for key, label in keys:
        history = state.get(key) or []
        turns = []
        for msg in history:
            content = msg.get("content", "").strip()
            role = msg.get("role", "user").capitalize()
            if content:
                turns.append(f"  {role}: {content}")
        if turns:
            all_turns.append(f"[{label}]\n" + "\n".join(turns))

    return "\n\n".join(all_turns) if all_turns else ""


def _get_primary_history(state: dict, active_node: str) -> str:
    """
    Returns the single most relevant recent history block for the active node.
    Used to give the LLM a tight recent-context window alongside the full history.
    """
    key = _NODE_PRIMARY_KEY.get(active_node)
    if not key:
        return ""

    history = state.get(key) or []
    lines = []
    for msg in history:
        content = msg.get("content", "").strip()
        role = msg.get("role", "user").capitalize()
        if content:
            lines.append(f"  {role}: {content}")

    return "\n".join(lines) if lines else ""


async def tts_node(state: dict[str, Any]) -> dict[str, Any]:
    print("[tts_node] -----------------------------")

    ai_text: str | None = state.get("speech_ai_text")
    user_text: str | None = state.get("speech_user_text")

    print("User said:", user_text)
    print("AI raw:", ai_text)

    if not ai_text or not ai_text.strip():
        ai_text = "Sorry, something went wrong. Let me help you with that."

    ai_text = ai_text.replace("*", "").replace("#", "").strip()

    # ── Build conversation context ───────────────────────────────────────────
    active_node = state.get("active_node", "unknown")
    unified_history = _build_unified_history(state, active_node)
    primary_history = _get_primary_history(state, active_node)
    is_first_turn = not user_text or not user_text.strip()

    # Topics already explained — prevent the LLM from repeating the same answer
    explained_topics: set = state.get("explained_topics") or set()
    explained_note = (
        f"\nTopics already explained earlier in this call: {', '.join(explained_topics)}. "
        "Do NOT repeat the same explanation. Briefly acknowledge and redirect forward."
        if explained_topics
        else ""
    )

    # ── System prompt ────────────────────────────────────────────────────────
    system_prompt = """
You are a warm, human-like voice assistant working in a healthcare call center.

Your ONLY job is to rewrite the given AI response so it sounds completely natural when spoken aloud over a phone call.

=== STRICT OUTPUT RULES ===
- Output ONLY the final spoken sentence(s). No explanations, no labels, no preamble.
- Strip all markdown, symbols, asterisks, bullet points, and formatting entirely.
- Never start with robotic openers like "Certainly!", "Of course!", "Sure!", or "Absolutely!".
- Never repeat information the user already confirmed in this conversation.
- Never add a greeting (Hello/Hi) unless the user greeted first in this turn.

=== RESPONSE LENGTH RULES ===
- For simple confirmations, questions, or status updates: 1–2 sentences max.
- For presenting choices (doctors, appointment slots, departments): use as many sentences as
  needed to clearly present each option — typically 3–5 sentences. Each option should be on
  its own natural spoken phrase.
- Never compress a list of options into one rushed sentence — the caller needs time to mentally
  register each choice.
- Never pad a simple response with filler just to sound longer.

=== TONE & STYLE ===
- Sound like a calm, friendly human healthcare receptionist — not a chatbot.
- Be direct and specific. Avoid vague filler like "I'll take care of that for you."
- Match the emotional register: if the user seems frustrated, be more reassuring; if casual,
  be warm and light.
- Use natural spoken contractions: "you're", "we've", "I'll", "that's".
- When presenting doctors or slots, introduce them naturally — for example:
  "We have a few options for you." then list each one clearly.
- When listing slots or doctors, say them in a flowing spoken way — avoid sounding like you're
  reading a table.
- When confirming something, mirror the user's own phrasing where natural.

=== HISTORY & REPETITION RULES ===
- Before answering any question from the user, scan the full conversation history.
- If the user is asking a question that was ALREADY answered earlier in this call
  (e.g. "why did you choose general checkup?"), do NOT repeat the same answer again.
  Instead: briefly acknowledge it was already covered, then redirect forward.
  Example: "As I mentioned, it was the best fit given your symptoms — now, what date works for you?"
- If the raw AI response is off-topic or doesn't address what the user actually asked,
  use the conversation history to craft a more relevant response instead.
- Never invent information not present in the raw AI response or conversation history.
- Do NOT hallucinate doctor names, dates, or slot details not present in the raw AI response.
"""

    # ── User prompt ──────────────────────────────────────────────────────────
    if is_first_turn:
        user_prompt = f"""
No user input yet — this is the very first moment of the call.

AI response to rewrite:
{ai_text}

Instructions:
- Rewrite into a single natural opening line that tells the caller they've reached the right
  place and invites them to share what they need.
- Do NOT use any greeting words like Hello, Hi, Hey, Good morning, etc.
- Do NOT ask for their name or details yet.
- Keep it under 15 words if possible.
"""
    elif not unified_history and not primary_history:
        # Nodes that need no history context — just rewrite cleanly
        user_prompt = f"""
What the user just said:
"{user_text}"

Raw AI response to rewrite:
{ai_text}

Instructions:
- Rewrite into 1–2 natural spoken sentences that directly follow what the user said.
- Output ONLY the final spoken line(s). Nothing else.
"""
    else:
        user_prompt = f"""
=== FULL CONVERSATION HISTORY (chronological) ===
{unified_history if unified_history else "No prior history."}

=== CURRENT NODE: {active_node} ===
Most relevant recent exchanges:
{primary_history if primary_history else "None."}
{explained_note}

=== CURRENT TURN ===
What the user just said:
"{user_text}"

Raw AI response to rewrite:
{ai_text}

=== YOUR TASK ===
Rewrite the raw AI response into 1–2 natural spoken sentences that directly follow what the
user just said. Follow these rules strictly:

1. REPETITION CHECK: If the user is asking a question already answered earlier in this call,
   do NOT give the same answer again. Acknowledge briefly and redirect to the next step.

2. RELEVANCE CHECK: If the raw AI response does not directly address what the user just said,
   adjust it using the conversation history to be more relevant. Do not blindly rewrite
   an off-topic response.

3. HALLUCINATION GUARD: Never invent dates, doctor names, slot times, or facts not present
   in the raw AI response or conversation history.

4. FORWARD MOMENTUM: After answering any side question or clarification, always bring the
   user back to the next pending action (choosing a date, confirming a doctor, etc.).

5. Output ONLY the final spoken line(s). Nothing else.
"""

    # ── Call LLM ─────────────────────────────────────────────────────────────
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        refined_response = await invokeLargeLLM(messages=messages)

        if refined_response and refined_response.strip().lower() != "none":
            ai_text = refined_response.strip()

    except Exception as e:
        print("TTS refinement failed:", str(e))

    print("Final TTS:", ai_text)

    return {**state, "speech_ai_text": ai_text}