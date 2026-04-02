from __future__ import annotations
import logging
import re
from datetime import timezone, timedelta
from src.control.voice_assistance.utils.llm_utils import invokeLargeLLM_json
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import SlotStatus
from src.control.voice_assistance.utils.date_utils import (
    today_ist, now_time_ist, format_date, format_time,
)
from src.control.voice_assistance.utils.state_utils import update_state

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

_FALLBACK = "I'm sorry, something went wrong. Could you please repeat that?"
_NO_SLOTS = "I'm sorry, {doctor} has no available slots right now. Please try again later."


# ═══════════════════════════════════════════════════════════════════════════════
# DB HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def _fetch_available_dates(doctor_id: int) -> list[str]:
    async with AsyncSessionLocal() as db:
        today    = today_ist()
        now_time = now_time_ist()
        from src.data.repositories.generic_crud import bulk_get_instance
        slots = await bulk_get_instance(AvailableSlot, db, provider_id=doctor_id, is_active=True)
        dates = sorted({
            s.availability_date.isoformat()
            for s in slots
            if s.status == SlotStatus.AVAILABLE and (
                s.availability_date > today or
                (s.availability_date == today and s.start_time > now_time)
            )
        })
        return dates


async def _fetch_periods_for_date(doctor_id: int, date_iso: str) -> list[str]:
    async with AsyncSessionLocal() as db:
        today    = today_ist()
        now_time = now_time_ist()
        from src.data.repositories.generic_crud import bulk_get_instance
        from datetime import date as dt_date
        target = dt_date.fromisoformat(date_iso)
        slots = await bulk_get_instance(
            AvailableSlot, db, provider_id=doctor_id,
            is_active=True, availability_date=target,
        )
        periods: set[str] = set()
        for s in slots:
            if s.status != SlotStatus.AVAILABLE:
                continue
            if target == today and s.start_time <= now_time:
                continue
            h = s.start_time.hour
            periods.add("morning" if h < 12 else "afternoon" if h < 17 else "evening")
        order = ["morning", "afternoon", "evening"]
        return [p for p in order if p in periods]


async def _fetch_all_times_for_date(doctor_id: int, date_iso: str) -> list[dict]:
    """Return every available slot for the date — NO period filter."""
    async with AsyncSessionLocal() as db:
        today    = today_ist()
        now_time = now_time_ist()
        from src.data.repositories.generic_crud import bulk_get_instance
        from datetime import date as dt_date
        target = dt_date.fromisoformat(date_iso)
        slots = await bulk_get_instance(
            AvailableSlot, db, provider_id=doctor_id,
            is_active=True, availability_date=target,
        )
        result = []
        for s in slots:
            if s.status != SlotStatus.AVAILABLE:
                continue
            if target == today and s.start_time <= now_time:
                continue
            result.append({
                "id":           s.id,
                "date":         date_iso,
                "start_time":   s.start_time.strftime("%H:%M"),
                "end_time":     s.end_time.strftime("%H:%M"),
                "date_display": format_date(s.availability_date),
                "time_display": f"{format_time(s.start_time)} to {format_time(s.end_time)}",
                "full_display": (
                    f"{format_date(s.availability_date)}, "
                    f"{format_time(s.start_time)} to {format_time(s.end_time)}"
                ),
            })
        return sorted(result, key=lambda x: x["start_time"])


# ═══════════════════════════════════════════════════════════════════════════════
# TIME UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def _period_from_time(time_str: str) -> str:
    try:
        h = int(time_str.split(":")[0])
        return "morning" if h < 12 else "afternoon" if h < 17 else "evening"
    except Exception:
        return "afternoon"


def _normalise_time(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = str(raw).strip().lower()

    # Range → take START
    raw = re.split(r"\bto\b|\s*[-–]\s*", raw)[0].strip()
    # Strip seconds
    raw = re.sub(r"(\d{1,2}:\d{2}):\d{2}", r"\1", raw)

    # H[:MM] am/pm
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", raw)
    if m:
        h, mins, mer = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if mer == "pm" and h != 12:
            h += 12
        if mer == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mins:02d}"

    # HH:MM
    m = re.match(r"^(\d{1,2}):(\d{2})$", raw)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"

    # Plain hour
    m = re.match(r"^(\d{1,2})$", raw)
    if m:
        return f"{int(m.group(1)):02d}:00"

    return None


async def _parse_time_with_llm(raw_text: str) -> str | None:
    system = """CRITICAL: Respond with ONLY a valid JSON object.
Your response must start with { and end with }.

Extract a clock time from garbled speech-to-text input.

Examples:
  "1302"             → "13:02"
  "1.30 to 2"        → "13:30"   (range → take START)
  "half past one"    → "13:30"
  "2 clock"          → "14:00"
  "9 baje"           → "09:00"
  "ek baj ke tees"   → "13:30"
  "quarter to 2"     → "13:45"
  "2 in afternoon"   → "14:00"
  "do baj ke pachees"→ "14:25"

Rules:
- For a range ("X to Y"), extract the START time only.
- Output in HH:MM 24h format.
- If no time can be extracted, output null.

OUTPUT FORMAT:
{"time": "<HH:MM 24h or null>"}""".strip()

    try:
        parsed = await invokeLargeLLM_json([
            {"role": "system", "content": system},
            {"role": "user",   "content": f'Speech input: "{raw_text}"'},
        ])
        if isinstance(parsed, dict):
            return _normalise_time(parsed.get("time"))
    except Exception as e:
        logger.warning(f"_parse_time_with_llm failed | error={e}")
    return None


async def _extract_time_hint(raw_text: str) -> str | None:
    """Regex first (fast), LLM fallback for garbled STT."""
    result = _normalise_time(raw_text)
    if result:
        return result
    logger.info(f"_extract_time_hint: regex failed → LLM | raw={raw_text!r}")
    return await _parse_time_with_llm(raw_text)


def _find_slot_by_time(slots: list[dict], time_str: str) -> dict | None:
    if not time_str or not slots:
        return None
    normalised = _normalise_time(time_str)
    if not normalised:
        return None

    for s in slots:
        if s["start_time"] == normalised:
            return s

    def _mins(t: str) -> int:
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    target = _mins(normalised)
    best, best_diff = None, 999
    for s in slots:
        diff = abs(_mins(s["start_time"]) - target)
        if diff < best_diff:
            best_diff, best = diff, s

    if best and best_diff <= 15:
        logger.info(
            f"_find_slot_by_time: fuzzy | requested={normalised} "
            f"→ matched={best['start_time']} (diff={best_diff}min)"
        )
        return best
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _format_dates(date_isos: list[str]) -> str:
    from datetime import date as dt_date
    out = []
    for d in date_isos:
        try:
            out.append(format_date(dt_date.fromisoformat(d)))
        except Exception:
            out.append(d)
    return ", ".join(out)


def _date_display(date_iso: str) -> str:
    from datetime import date as dt_date
    try:
        return format_date(dt_date.fromisoformat(date_iso))
    except Exception:
        return date_iso


# ═══════════════════════════════════════════════════════════════════════════════
# LLM CALLS
# ═══════════════════════════════════════════════════════════════════════════════

async def _call_ask_date(
    doctor_name: str,
    available_dates_str: str,
    history: list[dict],
) -> dict | None:
    today_str = today_ist().isoformat()

    system = f"""CRITICAL: Respond with ONLY a valid JSON object. No prose before or after.
Your response must start with {{ and end with }}.

You are a clinic receptionist on a phone call helping a patient choose an appointment date with {doctor_name}.

Today's date    : {today_str}
Available dates : {available_dates_str}

YOUR JOB:
1. Read the patient's latest message.
2. If they mentioned a date:
   a. First check — is that date in the PAST (before today {today_str})?
      → If YES: tell them that date has already passed. Do NOT silently pick a future date.
        Suggest the closest 2–3 dates from the available list and ask which they prefer.
        Output "date" as null.
   b. If the date is today or future but NOT in the available list →
      say it's not available, suggest the closest 2–3 options from the available list.
      Output "date" as null.
   c. If the date IS in the available list → confirm it. Output as "date".
3. If no date mentioned yet → list the available dates and ask which they prefer.
4. Also check: did the patient mention a specific TIME (e.g. "2 pm", "1:30")?
   If yes → output it verbatim as "time_hint".

RULES:
- NEVER assume the patient meant a future month if they said a past date. Always tell them it has passed.
- NEVER silently pick a different date without telling the patient.
- Never ask without listing the available dates.
- You are mid-conversation. Never say Hello, Hi, or Welcome.
- Keep response to 1–3 sentences. Natural phone speech. No bullet points.
- Output "date" as YYYY-MM-DD only if confirmed from the available list. Otherwise null.
- Output "time_hint" as the raw time string only if the patient gave a specific time. Otherwise null.

OUTPUT FORMAT:
{{
  "speak":     "<what you say to the patient>",
  "date":      "<YYYY-MM-DD or null>",
  "time_hint": "<raw time string or null>"
}}""".strip()

    messages = [{"role": "system", "content": system}, *history]
    return await invokeLargeLLM_json(messages)


async def _call_ask_period(
    doctor_name: str,
    confirmed_date_display: str,
    confirmed_date_iso: str,
    available_periods: list[str],
    history: list[dict],
) -> dict | None:
    today    = today_ist()
    now_time = now_time_ist()
    is_today = (confirmed_date_iso == today.isoformat())

    past_period_note = ""
    if is_today:
        h = now_time.hour
        past = []
        if h >= 12:
            past.append("morning")
        if h >= 17:
            past.append("afternoon")
        if past:
            past_period_note = (
                f"\nCurrent time is {now_time.strftime('%H:%M')} IST. "
                f"These periods have already passed today: {', '.join(past)}. "
                f"If the patient asks for a past period, tell them it has passed "
                f"and suggest only from the available list."
            )

    periods_str = ", ".join(available_periods) if available_periods else "none"

    system = f"""CRITICAL: Respond with ONLY a valid JSON object. No prose before or after.
Your response must start with {{ and end with }}.

You are a clinic receptionist on a phone call. The patient has chosen {confirmed_date_display} with {doctor_name}.

Available periods on that date : {periods_str}{past_period_note}

YOUR JOB:
1. Read the patient's latest message.
2. If they mentioned a period:
   a. If it's a past period (only possible if the date is today) →
      tell them that period has already passed. Suggest only from the available list.
      Output "period" as null.
   b. If it's NOT in the available list →
      say it's not available, suggest from the available list.
      Output "period" as null.
   c. If it IS in the available list → confirm it. Output as "period".
3. If they gave a specific time directly → infer the period:
   00:00–11:59 → morning | 12:00–16:59 → afternoon | 17:00–23:59 → evening.
   If that inferred period is NOT in the available list →
   tell them it's unavailable or has passed, suggest from the available list.
   Output "period" as null and "time_hint" as null.
4. If no period mentioned yet → list the available periods and ask.

RULES:
- NEVER silently skip a past or unavailable period and pick another. Always tell the patient first.
- Never ask without listing the options.
- You are mid-conversation. Never say Hello, Hi, or Welcome.
- Keep response to 1–3 sentences. Natural phone speech.

OUTPUT FORMAT:
{{
  "speak":     "<what you say to the patient>",
  "period":    "<morning|afternoon|evening or null>",
  "time_hint": "<raw time string if patient gave a specific time, else null>"
}}""".strip()

    messages = [{"role": "system", "content": system}, *history]
    return await invokeLargeLLM_json(messages)


async def _call_ask_time(
    doctor_name: str,
    confirmed_date_display: str,
    confirmed_date_iso: str,
    confirmed_period: str,
    available_slots: list[dict],
    history: list[dict],
) -> dict | None:
    today    = today_ist()
    now_time = now_time_ist()
    is_today = (confirmed_date_iso == today.isoformat())

    current_time_note = ""
    if is_today:
        current_time_note = (
            f"\nCurrent time is {now_time.strftime('%H:%M')} IST. "
            f"If the patient asks for a time earlier than {now_time.strftime('%H:%M')} today, "
            f"tell them that time has already passed. NEVER silently pick a later time."
        )

    slot_lines = [
        f"  • {s['time_display']}  "
        f"[period={_period_from_time(s['start_time'])} "
        f"start={s['start_time']} end={s['end_time']}]"
        for s in available_slots
    ]
    slots_str = "\n".join(slot_lines) if slot_lines else "none"

    system = f"""CRITICAL: Respond with ONLY a valid JSON object. No prose before or after.
Your response must start with {{ and end with }}.

You are a clinic receptionist on a phone call.
Patient has chosen {confirmed_date_display} with {doctor_name}.
Currently selected period: {confirmed_period}{current_time_note}

ALL available slots for this date (every period is listed):
{slots_str}

YOUR JOB:
1. Read the patient's message.
2. If the patient mentions a specific time:
   a. If that time is in the PAST (only if date is today and time < current time) →
      tell them that time has already passed. Suggest the nearest available slots.
      Output "time" as null, "completed" as false.
   b. If that time is NOT in the available list →
      say it's not available. Suggest the nearest slots from the list.
      Output "time" as null, "completed" as false.
   c. If that time IS in the available list → confirm it.
      Output exact start= value as "time", "completed" as true.
3. If the patient asks for a DIFFERENT period or mentions a time in a different period →
   switch to that period, show its slots, ask which time they prefer.
   Output new period as "period".
4. Match their time to a slot:
   - "2 pm", "2 o'clock", "14:00"   → match on start=
   - "1:30 to 2", "half one to two" → match on START time
   - "yes / ok / that one / haan"   → if ONE slot in current period confirm it,
                                       otherwise ask which one
5. If no time chosen yet → list slots for the current period and ask.

RULES:
- NEVER silently pick a different time if the patient's requested time is past or unavailable.
  Always tell them explicitly first, then offer alternatives from the list.
- "time" MUST be an exact start= value from the list above. NEVER invent a time.
- completed = true ONLY when you are certain the start= value is in the list.
- When in doubt → completed = false.
- Output "time_hint" as the raw string the patient said (any time expression),
  even if you couldn't match it — our code will try to parse it separately.
- Never ask without listing options.
- Mid-conversation — never say Hello / Hi / Welcome.
- 1–3 sentences, natural phone speech.

OUTPUT FORMAT:
{{
  "speak":     "<what you say to the patient>",
  "period":    "<morning|afternoon|evening — patient's current choice>",
  "time":      "<exact start= value from list above, or null>",
  "time_hint": "<raw time expression patient said, or null>",
  "completed": <true|false>
}}""".strip()

    messages = [{"role": "system", "content": system}, *history]
    return await invokeLargeLLM_json(messages)


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def _handle_ask_date(
    state: dict,
    doctor_id: int,
    doctor_name: str,
    history: list[dict],
) -> dict:
    try:
        dates = await _fetch_available_dates(doctor_id)
    except Exception as e:
        logger.error(f"ask_date: fetch failed | {e}")
        return _fallback_state(state, history)

    if not dates:
        return _no_slots_state(state, doctor_name, history)

    parsed = await _call_ask_date(doctor_name, _format_dates(dates), history)
    if not isinstance(parsed, dict) or not parsed:
        logger.warning("ask_date: LLM unparseable")
        return _fallback_state(state, history)

    ai_text   = _clean_speak(parsed.get("speak"))
    new_date  = parsed.get("date")
    raw_hint  = parsed.get("time_hint")
    time_hint = await _extract_time_hint(raw_hint) if raw_hint else None

    history.append({"role": "assistant", "content": ai_text})

    if new_date and time_hint:
        inferred_period = _period_from_time(time_hint)
        logger.info(f"ask_date: date+time shortcut | date={new_date} hint={time_hint} period={inferred_period}")
        return update_state(
            state,
            active_node                      = "booking_slot_selection",
            slot_stage                       = "ask_time",
            slot_chosen_date                 = new_date,
            slot_chosen_period               = inferred_period,
            slot_time_hint                   = time_hint,
            slot_selected                    = None,
            slot_selected_display            = None,
            slot_selected_start_time         = None,
            slot_selected_end_time           = None,
            booking_slot_selection_completed = False,
            booking_slot_selection_history   = history,
            speech_ai_text                   = ai_text,
        )

    return update_state(
        state,
        active_node                      = "booking_slot_selection",
        slot_stage                       = "ask_period" if new_date else "ask_date",
        slot_chosen_date                 = new_date,
        slot_chosen_period               = None,
        slot_time_hint                   = None,
        slot_selected                    = None,
        slot_selected_display            = None,
        slot_selected_start_time         = None,
        slot_selected_end_time           = None,
        booking_slot_selection_completed = False,
        booking_slot_selection_history   = history,
        speech_ai_text                   = ai_text,
    )


async def _handle_ask_period(
    state: dict,
    doctor_id: int,
    doctor_name: str,
    confirmed_date: str,
    history: list[dict],
) -> dict:
    try:
        periods = await _fetch_periods_for_date(doctor_id, confirmed_date)
    except Exception as e:
        logger.error(f"ask_period: fetch failed | {e}")
        return _fallback_state(state, history)

    if not periods:
        return _no_slots_state(state, doctor_name, history)

    parsed = await _call_ask_period(
        doctor_name,
        _date_display(confirmed_date),
        confirmed_date,                  # ← pass iso date
        periods,
        history,
    )
    if not isinstance(parsed, dict) or not parsed:
        logger.warning("ask_period: LLM unparseable")
        return _fallback_state(state, history)

    ai_text    = _clean_speak(parsed.get("speak"))
    new_period = parsed.get("period")
    raw_hint   = parsed.get("time_hint")
    time_hint  = await _extract_time_hint(raw_hint) if raw_hint else None

    if not new_period and time_hint:
        new_period = _period_from_time(time_hint)
        logger.info(f"ask_period: period inferred from hint | hint={time_hint} → {new_period}")

    history.append({"role": "assistant", "content": ai_text})

    return update_state(
        state,
        active_node                      = "booking_slot_selection",
        slot_stage                       = "ask_time" if new_period else "ask_period",
        slot_chosen_date                 = confirmed_date,
        slot_chosen_period               = new_period,
        slot_time_hint                   = time_hint if new_period else None,
        slot_selected                    = None,
        slot_selected_display            = None,
        slot_selected_start_time         = None,
        slot_selected_end_time           = None,
        booking_slot_selection_completed = False,
        booking_slot_selection_history   = history,
        speech_ai_text                   = ai_text,
    )


async def _handle_ask_time(
    state: dict,
    doctor_id: int,
    doctor_name: str,
    confirmed_date: str,
    confirmed_period: str,
    history: list[dict],
) -> dict:
    try:
        slots = await _fetch_all_times_for_date(doctor_id, confirmed_date)
    except Exception as e:
        logger.error(f"ask_time: fetch failed | {e}")
        return _fallback_state(state, history)

    if not slots:
        return _no_slots_state(state, doctor_name, history)

    def _unavailable_msg(requested: str) -> str:
        times_str = ", ".join(s["time_display"] for s in slots)
        return (
            f"I'm sorry, {requested} isn't available. "
            f"The available slots are: {times_str}. Which one would you prefer?"
        )

    # ── Pre-match time_hint carried from an earlier stage ─────────────────────
    time_hint = state.get("slot_time_hint")
    if time_hint:
        pre_matched = _find_slot_by_time(slots, time_hint)
        if pre_matched:
            logger.info(f"ask_time: pre-matched hint | hint={time_hint} → {pre_matched['start_time']}")
            confirm_msg = (
                f"Great, I've got you down for {pre_matched['full_display']} "
                f"with {state.get('doctor_confirmed_name', 'the doctor')}. "
                "Does that sound right?"
            )
            history.append({"role": "assistant", "content": confirm_msg})
            return update_state(
                state,
                active_node                      = "booking_slot_selection",
                slot_stage                       = "ready_to_book",
                slot_chosen_date                 = confirmed_date,
                slot_chosen_period               = _period_from_time(pre_matched["start_time"]),
                slot_time_hint                   = None,
                booking_slot_selection_completed = True,
                booking_slot_selection_history   = history,
                speech_ai_text                   = confirm_msg,
                slot_selected                    = pre_matched,
                slot_selected_display            = pre_matched["time_display"],
                slot_selected_start_time         = pre_matched["start_time"],
                slot_selected_end_time           = pre_matched["end_time"],
                slot_booked_id                   = None,
            )
        else:
            msg = _unavailable_msg(time_hint)
            logger.info(f"ask_time: hint not available | hint={time_hint} available={[s['start_time'] for s in slots]}")
            history.append({"role": "assistant", "content": msg})
            return update_state(
                state,
                active_node                      = "booking_slot_selection",
                slot_stage                       = "ask_time",
                slot_chosen_date                 = confirmed_date,
                slot_chosen_period               = confirmed_period,
                slot_time_hint                   = None,
                booking_slot_selection_completed = False,
                booking_slot_selection_history   = history,
                speech_ai_text                   = msg,
            )

    # ── Normal LLM call ───────────────────────────────────────────────────────
    parsed = await _call_ask_time(
        doctor_name,
        _date_display(confirmed_date),
        confirmed_date,                  # ← pass iso date
        confirmed_period,
        slots,
        history,
    )
    if not isinstance(parsed, dict) or not parsed:
        logger.warning("ask_time: LLM unparseable")
        return _fallback_state(state, history)

    ai_text    = _clean_speak(parsed.get("speak"))
    raw_time   = parsed.get("time")
    completed  = bool(parsed.get("completed", False))
    new_period = parsed.get("period") or confirmed_period
    raw_hint   = parsed.get("time_hint")

    # ── Verify LLM's slot claim against the REAL slot list ───────────────────
    selected_slot = None

    if completed and raw_time:
        selected_slot = _find_slot_by_time(slots, raw_time)

        if not selected_slot:
            if raw_hint:
                parsed_hint = await _extract_time_hint(raw_hint)
                if parsed_hint:
                    selected_slot = _find_slot_by_time(slots, parsed_hint)
                    if selected_slot:
                        logger.info(
                            f"ask_time: hint fallback rescued | "
                            f"raw_hint={raw_hint!r} → {parsed_hint} → {selected_slot['start_time']}"
                        )
                        new_period = _period_from_time(selected_slot["start_time"])

            if not selected_slot:
                norm = _normalise_time(raw_time) or raw_time
                ai_text = _unavailable_msg(norm)
                logger.warning(
                    f"ask_time: hallucinated slot overridden | "
                    f"raw={raw_time!r} available={[s['start_time'] for s in slots]}"
                )
                completed  = False
                new_period = confirmed_period

    elif completed and not raw_time:
        period_slots = [s for s in slots if _period_from_time(s["start_time"]) == new_period]
        if len(period_slots) == 1:
            selected_slot = period_slots[0]
            logger.info("ask_time: single slot in period auto-confirmed")
        else:
            completed = False

    else:
        if raw_hint and not completed:
            parsed_hint = await _extract_time_hint(raw_hint)
            if parsed_hint:
                candidate = _find_slot_by_time(slots, parsed_hint)
                if candidate:
                    logger.info(
                        f"ask_time: silent hint match | "
                        f"raw_hint={raw_hint!r} → {parsed_hint} → {candidate['start_time']}"
                    )
                    selected_slot = candidate
                    new_period    = _period_from_time(candidate["start_time"])
                    completed     = True
                    ai_text = (
                        f"I've got you down for {candidate['full_display']} "
                        f"with {state.get('doctor_confirmed_name', 'the doctor')}. "
                        "Does that sound right?"
                    )

    history.append({"role": "assistant", "content": ai_text})

    slot_confirmed = completed and selected_slot is not None

    updates: dict = dict(
        active_node                      = "booking_slot_selection",
        slot_stage                       = "ready_to_book" if slot_confirmed else "ask_time",
        slot_chosen_date                 = confirmed_date,
        slot_chosen_period               = new_period,
        slot_time_hint                   = None,
        booking_slot_selection_completed = slot_confirmed,
        booking_slot_selection_history   = history,
        speech_ai_text                   = ai_text,
    )
    if selected_slot:
        updates.update(
            slot_selected            = selected_slot,
            slot_selected_display    = selected_slot["time_display"],
            slot_selected_start_time = selected_slot["start_time"],
            slot_selected_end_time   = selected_slot["end_time"],
            slot_booked_id           = None,
        )

    return update_state(state, **updates)


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _clean_speak(raw: str | None) -> str:
    if not raw:
        return _FALLBACK
    return str(raw).strip().strip('"').strip("'")


def _fallback_state(state: dict, history: list[dict]) -> dict:
    history.append({"role": "assistant", "content": _FALLBACK})
    return update_state(
        state,
        active_node                    = "booking_slot_selection",
        speech_ai_text                 = _FALLBACK,
        booking_slot_selection_history = history,
    )


def _no_slots_state(state: dict, doctor_name: str, history: list[dict]) -> dict:
    msg = _NO_SLOTS.format(doctor=doctor_name)
    history.append({"role": "assistant", "content": msg})
    return update_state(
        state,
        active_node                    = "booking_slot_selection",
        speech_ai_text                 = msg,
        booking_slot_selection_history = history,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN NODE
# ═══════════════════════════════════════════════════════════════════════════════

async def booking_slot_selection_node(state: dict) -> dict:

    # Short-circuit: already done and no change requested
    if state.get("booking_slot_selection_completed") and not state.get("user_change_request"):
        return {**state, "active_node": "booking_slot_selection"}

    doctor_id   = state.get("doctor_confirmed_id")
    doctor_name = state.get("doctor_confirmed_name", "the doctor")
    user_text   = (state.get("speech_user_text") or "").strip()
    stage       = state.get("slot_stage") or "ask_date"
    history     = list(state.get("booking_slot_selection_history") or [])

    if user_text:
        history.append({"role": "user", "content": user_text})

    confirmed_date   = state.get("slot_chosen_date")
    confirmed_period = state.get("slot_chosen_period")

    # ── If already in ask_time and patient mentions a time in a different
    #    period, update confirmed_period before dispatching ──────────────────
    if stage == "ask_time" and user_text and confirmed_date:
        extracted = await _extract_time_hint(user_text)
        if extracted:
            inferred = _period_from_time(extracted)
            if inferred != confirmed_period:
                logger.info(
                    f"main_node: period switch from user text | "
                    f"{confirmed_period} → {inferred} (time={extracted})"
                )
                confirmed_period = inferred
                state = {**state, "slot_chosen_period": inferred}

    if stage == "ask_date" or not confirmed_date:
        return await _handle_ask_date(state, doctor_id, doctor_name, history)

    if stage == "ask_period" or not confirmed_period:
        return await _handle_ask_period(
            state, doctor_id, doctor_name, confirmed_date, history
        )

    return await _handle_ask_time(
        state, doctor_id, doctor_name, confirmed_date, confirmed_period, history
    )