from src.control.voice_assistance.prompts.doctor_selection_node_prompt import (
    DOCTOR_CONVERSATION_PROMPT,
    DOCTOR_INTENT_VERIFIER_PROMPT,
    DOCTOR_SUMMARY_PROMPT,
    DOCTOR_VERIFIER_PROMPT,
    NO_DOCTORS_RESPONSE,
)
from src.control.voice_assistance.utils import invokeLargeLLM, invokeLargeLLM_json
from src.data.clients.auth_client import get_full_providers


def _doctors_context(doctors: list[dict]) -> str:
    return "\n".join(
        f"{i+1}. id={d['id']} name={d['name']} "
        f"specialization={d['specialization']} "
        f"experience={d['experience']}yrs "
        f"qualification={d['qualification']} bio={d['bio']}"
        for i, d in enumerate(doctors)
    )


def _doctor_summary(doctor: dict | None) -> str:
    if not doctor:
        return "none"
    return (
        f"{doctor['name']} (id={doctor['id']}, "
        f"specialization={doctor['specialization']}, "
        f"experience={doctor['experience']}yrs, "
        f"qualification={doctor['qualification']})"
    )


def _format_change_log(change_log: list[dict]) -> str:
    if not change_log:
        return "No doctor changes so far."
    lines = []
    for i, entry in enumerate(change_log, 1):
        from_doc = _doctor_summary(entry.get("from")) if entry.get("from") else "initial selection"
        to_doc   = _doctor_summary(entry.get("to"))   if entry.get("to")   else "undecided"
        reason   = entry.get("reason") or "not specified"
        lines.append(f"  Change {i}: {from_doc} → {to_doc} (reason: {reason})")
    return "\n".join(lines)


def _find_doctor_by_id(doctors: list[dict], doctor_id: int) -> dict | None:
    return next((d for d in doctors if d["id"] == doctor_id), None)


def _reset_slot_state() -> dict:
    """Returns state keys that wipe slot selection when doctor changes."""
    return {
        "slot_stage":                       None,
        "slot_chosen_date":                 None,
        "slot_chosen_period":               None,
        "slot_available_list":              None,
        "slot_selected":                    None,
        "slot_selected_start_time":         None,
        "slot_selected_end_time":           None,
        "slot_selected_display":            None,
        "booking_slot_selection_completed": False,
        "booking_slot_selection_history":   [],
    }


async def fetch_doctors(
    token: str,
    appointment_type_id: int | None,
    state: dict,
) -> tuple[list[dict], dict]:
    cache: dict = dict(state.get("doctors_cache") or {})
    cache_key   = str(appointment_type_id or "default")

    if cache_key in cache:
        print(f"[fetch_doctors] cache hit for appointment_type_id={appointment_type_id}")
        return cache[cache_key], cache

    providers = await get_full_providers(
        token=token,
        appointment_type_id=appointment_type_id,
    )

    doctors = []
    for p in providers:
        profile = p.get("provider_profile")
        doctors.append(
            {
                "id":             p["id"],
                "name":           f"Dr. {p['first_name']} {p['last_name']}",
                "specialization": profile["specialization"] if profile else "N/A",
                "qualification":  profile["qualification"]  if profile else "N/A",
                "experience":     profile["experience"]     if profile else 0,
                "bio":            profile["bio"]            if profile else "",
            }
        )

    cache[cache_key] = doctors
    print(f"[fetch_doctors] fetched {len(doctors)} doctors for key={cache_key}")
    return doctors, cache


async def _build_summary(
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

    user_prompt = f"""
Previous summary (may be empty):
{previous_summary or 'None'}

New conversation turns:
{turns_text}

Doctor change log:
{_format_change_log(change_log)}

Currently confirmed doctor:
{_doctor_summary(confirmed_doctor)}
""".strip()

    messages = [
        {"role": "system", "content": DOCTOR_SUMMARY_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    try:
        summary = await invokeLargeLLM(messages=messages)
        return (summary or "").strip()
    except Exception as e:
        print("[_build_summary] error:", e)
        return previous_summary or ""


async def run_doctor_llm(
    mode:                 str,
    doctors:              list[dict],
    recent_turns:         list[dict],
    conversation_summary: str,
    intent:               str,
    previous_doctor:      dict | None = None,
    confirmed_doctor:     dict | None = None,
    user_change_request:  str | None = None,
    doctor_change_log:    list[dict] | None = None,
    all_doctors:          list[dict] | None = None,
) -> str:
    RECENCY_WINDOW = 6

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
                doctors_context      = _doctors_context(display_doctors),
                intent               = intent,
                mode                 = mode,
                previous_doctor      = _doctor_summary(previous_doctor),
                confirmed_doctor     = _doctor_summary(confirmed_doctor),
                change_request       = user_change_request or "none",
                change_log           = _format_change_log(doctor_change_log or []),
                conversation_summary = summary_block,
            ),
        },
        *seed,
    ]

    ai_text = await invokeLargeLLM(messages)
    return ai_text or ""


async def _verify_selection(
    user_text: str, doctors: list[dict]
) -> tuple[int | None, str | None]:
    try:
        message = [
            {"role": "system", "content": DOCTOR_VERIFIER_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Doctors:\n{_doctors_context(doctors)}\n\n"
                    f"Patient said: {user_text}"
                ),
            },
        ]
        response    = await invokeLargeLLM_json(messages=message)
        doctor_id   = response.get("doctor_id")
        doctor_name = response.get("doctor_name")
        return (int(doctor_id), str(doctor_name)) if doctor_id else (None, None)
    except Exception as e:
        print("[doctor verifier error]:", e)
        return None, None


SUMMARY_TURN_THRESHOLD = 8


async def _maybe_compress(
    history:          list[dict],
    previous_summary: str,
    change_log:       list[dict],
    confirmed_doctor: dict | None,
) -> tuple[list[dict], str]:
    RECENCY_WINDOW = 6
    if len(history) <= SUMMARY_TURN_THRESHOLD:
        return history, previous_summary

    older_turns  = history[:-RECENCY_WINDOW]
    recent_turns = history[-RECENCY_WINDOW:]

    new_summary = await _build_summary(
        previous_summary = previous_summary,
        new_turns        = older_turns,
        change_log       = change_log,
        confirmed_doctor = confirmed_doctor,
    )
    print(f"[doctor_selection_node] history compressed: {len(older_turns)} turns → summary")
    return recent_turns, new_summary


def _confirm_doctor_return(
    state: dict,
    doctor_id: int,
    doctor_name: str,
    confirmed_doctor: dict,
    history: list[dict],
    conversation_summary: str,
    doctor_change_log: list[dict],
    updated_cache: dict,
    ai_text: str,
    reset_slots: bool = False,
) -> dict:
    """Shared return dict for any path that confirms a doctor."""
    result = {
        **state,
        "active_node":                 "doctor_selection",
        "user_change_request":         None,
        "doctor_confirmed_id":          doctor_id,
        "doctor_confirmed_name":        doctor_name,
        "doctor_selection_completed":   True,
        "doctor_selection_pending":     False,
        "doctor_selection_history":     history,
        "doctor_conversation_summary":  conversation_summary,
        "doctor_change_log":            doctor_change_log,
        "doctors_cache":                updated_cache,
        "speech_ai_text":               ai_text,
    }
    if reset_slots:
        result.update(_reset_slot_state())
    return result


async def doctor_selection_node(state: dict) -> dict:
    print("[doctor_selection_node] -----------------------------")

    user_change_request:  str | None  = state.get("user_change_request")
    previous_doctor_id:   int | None  = state.get("doctor_confirmed_id")
    previous_doctor_name: str | None  = state.get("doctor_confirmed_name")
    user_text:            str         = (state.get("speech_user_text") or "").strip()
    history:              list[dict]  = list(state.get("doctor_selection_history") or [])
    intent:               str         = state.get("mapping_intent") or "general checkup"
    doctor_change_log:    list[dict]  = list(state.get("doctor_change_log") or [])
    conversation_summary: str         = state.get("doctor_conversation_summary") or ""

    if user_text:
        history.append({"role": "user", "content": user_text})

    try:
        appointment_type_id = state.get("mapping_appointment_type_id") or -1
        print("appointment_type_id:", appointment_type_id)
        token   = state.get("call_user_token")
        doctors, updated_cache = await fetch_doctors(
            token=token,
            appointment_type_id=appointment_type_id,
            state=state,
        )
    except Exception as e:
        print("[doctor_selection_node] fetch failed:", e)
        history.append({"role": "assistant", "content": NO_DOCTORS_RESPONSE})
        return {
            **state,
            "active_node":                "doctor_selection",
            "doctor_selection_history":   history,
            "doctor_selection_completed": True,
            "speech_ai_text":             NO_DOCTORS_RESPONSE,
        }

    if not doctors:
        history.append({"role": "assistant", "content": NO_DOCTORS_RESPONSE})
        return {
            **state,
            "active_node":                "doctor_selection",
            "doctor_selection_history":   history,
            "doctor_selection_completed": True,
            "speech_ai_text":             NO_DOCTORS_RESPONSE,
        }

    previous_doctor: dict | None = (
        _find_doctor_by_id(doctors, previous_doctor_id) if previous_doctor_id else None
    )

    doctors_for_presentation = (
        [d for d in doctors if d["name"] != previous_doctor_name] or doctors
        if user_change_request and previous_doctor_name
        else doctors
    )

    confirmed_doctor_so_far = _find_doctor_by_id(doctors, state.get("doctor_confirmed_id"))
    history, conversation_summary = await _maybe_compress(
        history          = history,
        previous_summary = conversation_summary,
        change_log       = doctor_change_log,
        confirmed_doctor = confirmed_doctor_so_far,
    )

    if user_change_request and user_text:
        print("[doctor_selection_node] change request detected — verifying from user_text")
        doctor_id, doctor_name = await _verify_selection(user_text, doctors)

        if doctor_id:
            confirmed_doctor = _find_doctor_by_id(doctors, doctor_id)
            print(f"[doctor_selection_node] change → confirmed id={doctor_id} name={doctor_name}")

            if previous_doctor and previous_doctor["id"] != doctor_id:
                doctor_change_log.append({
                    "from":   previous_doctor,
                    "to":     confirmed_doctor,
                    "reason": user_change_request or user_text,
                })
                history.append({
                    "role":    "system",
                    "content": (
                        f"[Doctor changed: from {_doctor_summary(previous_doctor)} "
                        f"→ to {_doctor_summary(confirmed_doctor)} "
                        f"| reason: {user_change_request or user_text}]"
                    ),
                })
            elif previous_doctor and previous_doctor["id"] == doctor_id:
                doctor_change_log.append({
                    "from":   previous_doctor,
                    "to":     confirmed_doctor,
                    "reason": "patient re-confirmed same doctor after change request",
                })
                history.append({
                    "role":    "system",
                    "content": (
                        f"[Doctor re-confirmed: {_doctor_summary(confirmed_doctor)} "
                        f"| patient chose to keep the same doctor]"
                    ),
                })
            else:
                doctor_change_log.append({
                    "from":   None,
                    "to":     confirmed_doctor,
                    "reason": "initial selection via change request",
                })
                history.append({
                    "role":    "system",
                    "content": (
                        f"[Doctor selected: {_doctor_summary(confirmed_doctor)} "
                        f"| initial selection]"
                    ),
                })

            ai_text = await run_doctor_llm(
                mode                 = "confirm_selection",
                doctors              = doctors,
                recent_turns         = history,
                conversation_summary = conversation_summary,
                intent               = intent,
                previous_doctor      = previous_doctor,
                confirmed_doctor     = confirmed_doctor,
                user_change_request  = user_change_request,
                doctor_change_log    = doctor_change_log
            )
            history.append({"role": "assistant", "content": ai_text})
            return _confirm_doctor_return(
                state, doctor_id, doctor_name, confirmed_doctor,
                history, conversation_summary, doctor_change_log,
                updated_cache, ai_text, reset_slots=True
            )


    if state.get("doctor_confirmed_id") and not user_change_request:
        print("[doctor_selection_node] doctor already confirmed — skipping")
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
        }


    if len(doctors_for_presentation) == 1 and not user_change_request:
        doctor = doctors_for_presentation[0]
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
        return _confirm_doctor_return(
            state, doctor["id"], doctor["name"], doctor,
            history, conversation_summary, doctor_change_log,
            updated_cache, ai_text, reset_slots=False,
        )


    if user_text and state.get("doctor_selection_pending"):
        response = await invokeLargeLLM_json(
            messages=[
                {"role": "system", "content": DOCTOR_INTENT_VERIFIER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Doctors:\n{_doctors_context(doctors)}\n\n"
                        f"Patient said: {user_text}"
                    ),
                },
            ]
        )

        user_intent = response.get("intent", "unknown") if isinstance(response, dict) else "unknown"
        print("[user_intent]:", user_intent)

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

        if user_intent in ("selecting", "confirming"):
            doctor_id, doctor_name = await _verify_selection(user_text, doctors)

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

                if previous_doctor and previous_doctor["id"] != doctor_id:
                    doctor_change_log.append({
                        "from":   previous_doctor,
                        "to":     confirmed_doctor,
                        "reason": user_change_request or user_text,
                    })
                    history.append({
                        "role":    "system",
                        "content": (
                            f"[Doctor changed: from {_doctor_summary(previous_doctor)} "
                            f"→ to {_doctor_summary(confirmed_doctor)} "
                            f"| reason: {user_change_request or user_text}]"
                        ),
                    })
                elif previous_doctor and previous_doctor["id"] == doctor_id:
                    doctor_change_log.append({
                        "from":   previous_doctor,
                        "to":     confirmed_doctor,
                        "reason": "patient re-confirmed same doctor after change request",
                    })
                    history.append({
                        "role":    "system",
                        "content": (
                            f"[Doctor re-confirmed: {_doctor_summary(confirmed_doctor)} "
                            f"| patient chose to keep the same doctor]"
                        ),
                    })
                elif not previous_doctor:
                    doctor_change_log.append({
                        "from":   None,
                        "to":     confirmed_doctor,
                        "reason": "initial selection",
                    })
                    history.append({
                        "role":    "system",
                        "content": (
                            f"[Doctor selected: {_doctor_summary(confirmed_doctor)} "
                            f"| initial selection]"
                        ),
                    })

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
                return _confirm_doctor_return(
                    state, doctor_id, doctor_name, confirmed_doctor,
                    history, conversation_summary, doctor_change_log,
                    updated_cache, ai_text, reset_slots=False,
                )

      
        print(f"[doctor_selection_node] intent='{user_intent}' is not doctor-related — re-asking")
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

