import logging
from src.control.voice_assistance.prompts.doctor_selection_node_prompt import (
    DOCTOR_CONVERSATION_PROMPT,
    DOCTOR_INTENT_VERIFIER_PROMPT,
    DOCTOR_VERIFIER_PROMPT,
    NO_DOCTORS_RESPONSE,
    DOCTOR_SUMMARY_PROMPT,
    doctor_summary,
    doctors_context,
)
from src.control.voice_assistance.utils.llm_utils import invokeLargeLLM, invokeLargeLLM_json
from src.data.clients.auth_client import get_full_providers
from src.control.voice_assistance.utils.state_utils import confirm_doctor_return

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _format_change_log(change_log: list[dict]) -> str:
    if not change_log:
        return "No doctor changes so far."
    lines = []
    for i, entry in enumerate(change_log, 1):
        from_doc = doctor_summary(entry.get("from")) if entry.get("from") else "initial selection"
        to_doc   = doctor_summary(entry.get("to"))   if entry.get("to")   else "undecided"
        reason   = entry.get("reason") or "not specified"
        lines.append(f"  Change {i}: {from_doc} → {to_doc} (reason: {reason})")
    return "\n".join(lines)


def _find_doctor_by_id(doctors: list[dict], doctor_id: int | None) -> dict | None:
    if not doctor_id:
        return None
    return next((d for d in doctors if d["id"] == doctor_id), None)


def _no_doctors_return(state: dict, history: list[dict]) -> dict:
    history.append({"role": "assistant", "content": NO_DOCTORS_RESPONSE})
    return {
        **state,
        "active_node":                "doctor_selection",
        "doctor_selection_history":   history,
        "doctor_selection_completed": True,
        "speech_ai_text":             NO_DOCTORS_RESPONSE,
    }


# ── Doctor fetch with caching ──────────────────────────────────────────────────

async def fetch_doctors(
    token: str,
    appointment_type_id: int | None,
    state: dict,
) -> tuple[list[dict], dict]:

    cache: dict = dict(state.get("doctors_cache") or {})
    cache_key = str(appointment_type_id or "default")

    if cache_key in cache:
        logger.info(f"fetch_doctors: cache hit | appointment_type_id={appointment_type_id}")
        return cache[cache_key], cache

    providers = await get_full_providers(
        token=token,
        appointment_type_id=appointment_type_id,
    )

    doctors = []
    for p in providers:
        profile = p.get("provider_profile")
        doctors.append({
            "id":             p["id"],
            "name":           f"Dr. {p['first_name']} {p['last_name']}",
            "specialization": profile["specialization"] if profile else "N/A",
            "qualification":  profile["qualification"]  if profile else "N/A",
            "experience":     profile["experience"]     if profile else 0,
            "bio":            profile["bio"]             if profile else "",
        })

    cache[cache_key] = doctors
    logger.info(f"fetch_doctors: fetched providers | count={len(doctors)} | cache_key={cache_key}")
    return doctors, cache


# ── Summary compression ────────────────────────────────────────────────────────

async def build_summary(
    previous_summary: str | None,
    new_turns: list[dict],
    change_log: list[dict],
    confirmed_doctor: dict | None,
) -> str:
    turns_text = "\n".join(
        f"  {m['role'].capitalize()}: {m['content']}"
        for m in new_turns
        if m.get("role") in ("user", "assistant")
    )
    user_prompt = (
        f"Previous summary (may be empty):\n{previous_summary or 'None'}\n\n"
        f"New conversation turns:\n{turns_text}\n\n"
        f"Doctor change log:\n{_format_change_log(change_log)}\n\n"
        f"Currently confirmed doctor:\n{doctor_summary(confirmed_doctor)}"
    )
    messages = [
        {"role": "system", "content": DOCTOR_SUMMARY_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]
    summary = await invokeLargeLLM(messages=messages)
    if not summary:
        logger.warning("build_summary: LLM returned no summary, retaining previous")
        return previous_summary or ""
    return summary.strip()


SUMMARY_TURN_THRESHOLD = 8
RECENCY_WINDOW = 6


async def _maybe_compress(
    history:          list[dict],
    previous_summary: str,
    change_log:       list[dict],
    confirmed_doctor: dict | None,
) -> tuple[list[dict], str]:
    if len(history) <= SUMMARY_TURN_THRESHOLD:
        return history, previous_summary

    older_turns  = history[:-RECENCY_WINDOW]
    recent_turns = history[-RECENCY_WINDOW:]

    new_summary = await build_summary(
        previous_summary=previous_summary,
        new_turns=older_turns,
        change_log=change_log,
        confirmed_doctor=confirmed_doctor,
    )
    logger.info(f"doctor_selection_node: history compressed | turns={len(older_turns)}")
    return recent_turns, new_summary


# ── Change log ─────────────────────────────────────────────────────────────────

def _append_change_log_entry(
    doctor_change_log: list[dict],
    history:           list[dict],
    previous_doctor:   dict | None,
    confirmed_doctor:  dict,
    reason:            str,
) -> None:
    if previous_doctor and previous_doctor["id"] != confirmed_doctor["id"]:
        doctor_change_log.append({"from": previous_doctor, "to": confirmed_doctor, "reason": reason})
        history.append({
            "role": "system",
            "content": (
                f"[Doctor changed: from {doctor_summary(previous_doctor)} "
                f"→ to {doctor_summary(confirmed_doctor)} | reason: {reason}]"
            ),
        })
    elif previous_doctor and previous_doctor["id"] == confirmed_doctor["id"]:
        doctor_change_log.append({
            "from": previous_doctor,
            "to":   confirmed_doctor,
            "reason": "patient re-confirmed same doctor after change request",
        })
        history.append({
            "role": "system",
            "content": (
                f"[Doctor re-confirmed: {doctor_summary(confirmed_doctor)} "
                f"| patient chose to keep the same doctor]"
            ),
        })
    else:
        doctor_change_log.append({"from": None, "to": confirmed_doctor, "reason": "initial selection"})
        history.append({
            "role": "system",
            "content": f"[Doctor selected: {doctor_summary(confirmed_doctor)} | initial selection]",
        })


# ── LLM conversation runner ────────────────────────────────────────────────────

async def run_doctor_llm(
    mode:                 str,
    doctors:              list[dict],
    recent_turns:         list[dict],
    conversation_summary: str,
    intent:               str,
    previous_doctor:      dict | None = None,
    confirmed_doctor:     dict | None = None,
    user_change_request:  str | None  = None,
    doctor_change_log:    list[dict] | None = None,
    all_doctors:          list[dict] | None = None,
) -> str:
    seed = recent_turns[-RECENCY_WINDOW:] if recent_turns else [{"role": "user", "content": "start"}]
    summary_block = (
        f"[Earlier conversation summary]\n{conversation_summary}"
        if conversation_summary
        else "No prior summary yet."
    )
    display_doctors = all_doctors if (mode == "present_options" and all_doctors) else doctors

    messages = [
        {
            "role": "system",
            "content": DOCTOR_CONVERSATION_PROMPT.format(
                doctors_context      = doctors_context(display_doctors),
                intent               = intent,
                mode                 = mode,
                previous_doctor      = doctor_summary(previous_doctor),
                confirmed_doctor     = doctor_summary(confirmed_doctor),
                change_request       = user_change_request or "none",
                change_log           = _format_change_log(doctor_change_log or []),
                conversation_summary = summary_block,
            ),
        },
        *seed,
    ]

    ai_text = await invokeLargeLLM(messages)
    if not ai_text:
        logger.warning(f"run_doctor_llm: LLM returned empty response | mode={mode}")
    return ai_text or ""


# ── Doctor verifier ────────────────────────────────────────────────────────────

async def _verify_selection(
    user_text: str,
    doctors:   list[dict],
) -> tuple[int | None, str | None]:
    messages = [
        {"role": "system", "content": DOCTOR_VERIFIER_PROMPT},
        {
            "role": "user",
            "content": (
                f"Doctors:\n{doctors_context(doctors)}\n\n"
                f"Patient said: {user_text}"
            ),
        },
    ]
    response = await invokeLargeLLM_json(messages=messages)
    if not response:
        logger.warning(f"_verify_selection: verifier returned None | user_text={user_text!r}")
        return None, None

    doctor_id   = response.get("doctor_id")
    doctor_name = response.get("doctor_name")
    return (int(doctor_id), str(doctor_name)) if doctor_id else (None, None)


# ── Main node ──────────────────────────────────────────────────────────────────

async def doctor_selection_node(state: dict) -> dict:
    user_change_request:  str | None = state.get("user_change_request")
    previous_doctor_id:   int | None = state.get("doctor_confirmed_id")
    previous_doctor_name: str | None = state.get("doctor_confirmed_name")
    user_text:            str        = (state.get("speech_user_text") or "").strip()
    history:              list[dict] = list(state.get("doctor_selection_history") or [])
    intent:               str        = state.get("mapping_intent") or "general checkup"
    doctor_change_log:    list[dict] = list(state.get("doctor_change_log") or [])
    conversation_summary: str        = state.get("doctor_conversation_summary") or ""

    if user_text:
        history.append({"role": "user", "content": user_text})

    appointment_type_id = state.get("mapping_appointment_type_id") or -1
    token = state.get("call_user_token")

    # ── Fetch doctors ──────────────────────────────────────────────────────────
    try:
        doctors, updated_cache = await fetch_doctors(
            token=token,
            appointment_type_id=appointment_type_id,
            state=state,
        )
    except Exception as e:
        logger.error(f"doctor_selection_node: failed to fetch doctors | error={e}")
        return _no_doctors_return(state, history)

    if not doctors:
        logger.warning(f"doctor_selection_node: no doctors available | appointment_type_id={appointment_type_id}")
        return _no_doctors_return(state, history)

    # ── Resolve previous doctor object ─────────────────────────────────────────
    previous_doctor: dict | None = _find_doctor_by_id(doctors, previous_doctor_id)

    # ── Doctors to present (exclude previous if change requested) ──────────────
    doctors_for_presentation = (
        [d for d in doctors if d["name"] != previous_doctor_name] or doctors
        if user_change_request and previous_doctor_name
        else doctors
    )

    # ── Compress history if needed ─────────────────────────────────────────────
    confirmed_doctor_so_far = _find_doctor_by_id(doctors, state.get("doctor_confirmed_id"))
    history, conversation_summary = await _maybe_compress(
        history          = history,
        previous_summary = conversation_summary,
        change_log       = doctor_change_log,
        confirmed_doctor = confirmed_doctor_so_far,
    )

    # ── Handle change request: check if patient already picked a new doctor ────
    if user_change_request and user_text:
        doctor_id, doctor_name = await _verify_selection(user_text, doctors)

        if doctor_id:
            confirmed_doctor = _find_doctor_by_id(doctors, doctor_id)
            logger.info(f"doctor_selection_node: change request resolved | doctor_id={doctor_id}")
            
            _append_change_log_entry(
                doctor_change_log, history, previous_doctor,
                confirmed_doctor, user_change_request or user_text,
            )
            
            ai_text = await run_doctor_llm(
                mode                 = "confirm_selection",
                doctors              = doctors,
                recent_turns         = history,
                conversation_summary = conversation_summary,
                intent               = intent,
                previous_doctor      = previous_doctor,
                confirmed_doctor     = confirmed_doctor,
                user_change_request  = user_change_request,
                doctor_change_log    = doctor_change_log,
            )
            history.append({"role": "assistant", "content": ai_text})
            return confirm_doctor_return(
                state, doctor_id, doctor_name, confirmed_doctor,
                history, conversation_summary, doctor_change_log,
                updated_cache, ai_text, reset_slots=True,
            )

        # Patient hasn't picked yet — present remaining options
        ai_text = await run_doctor_llm(
            mode                 = "present_options",
            doctors              = doctors_for_presentation,
            recent_turns         = history,
            conversation_summary = conversation_summary,
            intent               = intent,
            previous_doctor      = previous_doctor,
            user_change_request  = user_change_request,
            doctor_change_log    = doctor_change_log,
            all_doctors          = doctors,
        )
        history.append({"role": "assistant", "content": ai_text})
        return {
            **state,
            "active_node":                 "doctor_selection",
            "doctor_selection_pending":    True,
            "doctor_selection_completed":  False,
            "doctor_list":                 doctors_for_presentation,
            "doctor_selection_history":    history,
            "doctor_conversation_summary": conversation_summary,
            "doctor_change_log":           doctor_change_log,
            "doctors_cache":               updated_cache,
            "speech_ai_text":              ai_text,
        }

    # ── Already confirmed, no change request — pass through silently ───────────
    if state.get("doctor_confirmed_id") and not user_change_request:
        logger.info("doctor_selection_node: doctor already confirmed, skipping selection")
        confirmed_doc = _find_doctor_by_id(doctors, state.get("doctor_confirmed_id"))
        return {
            **state,
            "active_node":                 "doctor_selection",
            "doctor_selection_history":    history,
            "doctor_conversation_summary": conversation_summary,
            "doctor_selection_completed":  True,
            "doctor_selection_pending":    False,
            "doctor_change_log":           doctor_change_log,
            "doctors_cache":               updated_cache,
            "doctor_confirmed_id":         state.get("doctor_confirmed_id"),
            "doctor_confirmed_name":       confirmed_doc["name"] if confirmed_doc else state.get("doctor_confirmed_name"),
            "speech_ai_text":              state.get("speech_ai_text") or "",
        }

    # ── Auto-select if only one doctor available ───────────────────────────────
    if len(doctors_for_presentation) == 1 and not user_change_request:
        doctor = doctors_for_presentation[0]
        logger.info(f"doctor_selection_node: single doctor, auto-selecting | doctor_id={doctor['id']}")
        ai_text = await run_doctor_llm(
            mode                 = "auto_select",
            doctors              = doctors,
            recent_turns         = history,
            conversation_summary = conversation_summary,
            intent               = intent,
            confirmed_doctor     = doctor,
            doctor_change_log    = doctor_change_log,
        )
        history.append({"role": "assistant", "content": ai_text})
        return confirm_doctor_return(
            state, doctor["id"], doctor["name"], doctor,
            history, conversation_summary, doctor_change_log,
            updated_cache, ai_text, reset_slots=False,
        )

    # ── Selection pending: classify intent ─────────────────────────────────────
    if user_text and state.get("doctor_selection_pending"):
        response = await invokeLargeLLM_json(
            messages=[
                {"role": "system", "content": DOCTOR_INTENT_VERIFIER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Doctors:\n{doctors_context(doctors)}\n\n"
                        f"Patient said: {user_text}"
                    ),
                },
            ]
        )

        if not response:
            logger.warning(
                f"doctor_selection_node: intent classification failed, defaulting to present_options"
                f" | user_text={user_text!r}"
            )
            user_intent = "unknown"
        else:
            user_intent = response.get("intent", "unknown")

        logger.info(f"doctor_selection_node: intent classified | intent={user_intent}")

        # ── Asking about a doctor ──────────────────────────────────────────────
        if user_intent == "asking_info":
            ai_text = await run_doctor_llm(
                mode                 = "handle_question",
                doctors              = doctors,
                recent_turns         = history,
                conversation_summary = conversation_summary,
                intent               = intent,
                previous_doctor      = previous_doctor,
                doctor_change_log    = doctor_change_log,
                all_doctors          = doctors,
            )
            history.append({"role": "assistant", "content": ai_text})
            return {
                **state,
                "active_node":                 "doctor_selection",
                "doctor_selection_history":    history,
                "doctor_conversation_summary": conversation_summary,
                "doctor_selection_pending":    True,
                "doctor_selection_completed":  False,
                "doctor_change_log":           doctor_change_log,
                "doctors_cache":               updated_cache,
                "speech_ai_text":              ai_text,
            }

        # ── Selecting or confirming a doctor ───────────────────────────────────
        if user_intent in ("selecting", "confirming"):
            doctor_id, doctor_name = await _verify_selection(user_text, doctors)

            # Confirming with no explicit name — infer from last assistant message
            if not doctor_id and user_intent == "confirming":
                assistant_text = " ".join(
                    m["content"] for m in history if m.get("role") == "assistant"
                )
                for d in doctors:
                    if d["name"].lower() in assistant_text.lower():
                        doctor_id   = d["id"]
                        doctor_name = d["name"]
                        break

            if doctor_id:
                confirmed_doctor = _find_doctor_by_id(doctors, doctor_id)
                logger.info(f"doctor_selection_node: doctor confirmed | doctor_id={doctor_id} | name={doctor_name}")
                _append_change_log_entry(
                    doctor_change_log, history, previous_doctor,
                    confirmed_doctor, user_change_request or user_text,
                )
                ai_text = await run_doctor_llm(
                    mode                 = "confirm_selection",
                    doctors              = doctors,
                    recent_turns         = history,
                    conversation_summary = conversation_summary,
                    intent               = intent,
                    previous_doctor      = previous_doctor,
                    confirmed_doctor     = confirmed_doctor,
                    user_change_request  = user_change_request,
                    doctor_change_log    = doctor_change_log,
                )
                history.append({"role": "assistant", "content": ai_text})
                return confirm_doctor_return(
                    state, doctor_id, doctor_name, confirmed_doctor,
                    history, conversation_summary, doctor_change_log,
                    updated_cache, ai_text, reset_slots=False,
                )

        # ── Unrecognised intent — re-present options ───────────────────────────
        logger.info(f"doctor_selection_node: unrecognised intent, re-presenting options | intent={user_intent}")

    # ── First turn or fallback — present options ───────────────────────────────
    ai_text = await run_doctor_llm(
        mode                 = "present_options",
        doctors              = doctors_for_presentation,
        recent_turns         = history,
        conversation_summary = conversation_summary,
        intent               = intent,
        previous_doctor      = previous_doctor,
        user_change_request  = user_change_request,
        doctor_change_log    = doctor_change_log,
        all_doctors          = doctors,
    )
    history.append({"role": "assistant", "content": ai_text})
    return {
        **state,
        "active_node":                 "doctor_selection",
        "doctor_selection_pending":    True,
        "doctor_selection_completed":  False,
        "doctor_list":                 doctors_for_presentation,
        "doctor_selection_history":    history,
        "doctor_conversation_summary": conversation_summary,
        "doctor_change_log":           doctor_change_log,
        "doctors_cache":               updated_cache,
        "speech_ai_text":              ai_text,
    }