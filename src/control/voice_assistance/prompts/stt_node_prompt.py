def build_stt_intent_system(
    confirmed_doctor: str | None = None,
    confirmed_date: str | None = None,
    confirmed_period: str | None = None,
    confirmed_slot: str | None = None,
) -> str:
    """
    Builds a context-aware intent classifier prompt by injecting what has
    already been selected into the system prompt.

    This is the core fix: without knowing the currently selected slot/date/period,
    the LLM cannot tell whether "I'd like 11:30" is a NEW selection or a CHANGE
    request. With the context injected it can compare directly.

    Args:
        confirmed_doctor : display name of the doctor already chosen, or None
        confirmed_date   : human-readable date already chosen (e.g. "Tuesday, Mar 24 2026"), or None
        confirmed_period : period already chosen ("morning" / "afternoon" / etc.), or None
        confirmed_slot   : slot display already chosen (e.g. "10:30 AM → 11:00 AM"), or None
    """
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