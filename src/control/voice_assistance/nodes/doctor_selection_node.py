from src.control.voice_assistance.prompts.doctor_selection_node_prompt import (
    DOCTOR_CONVERSATION_PROMPT,
    DOCTOR_INTENT_VERIFIER_PROMPT,
    DOCTOR_VERIFIER_PROMPT,
    NO_DOCTORS_RESPONSE,
)
from src.control.voice_assistance.utils import invokeLargeLLM, invokeLargeLLM_json
from src.data.clients.auth_client import get_full_providers


async def run_doctor_llm(
    mode: str,
    doctors: list[dict],
    history: list[dict],
    intent: str,
    previous_doctor_name: str | None = None,
    user_change_request: str | None = None,
) -> str:

    seed = history if history else [{"role": "user", "content": "start"}]
    messages = [
        {
            "role": "system",
            "content": DOCTOR_CONVERSATION_PROMPT.format(
                doctors_context=_doctors_context(doctors),
                intent=intent,
                mode=mode,
                previous_doctor=previous_doctor_name or "none",
                change_request=user_change_request or "none",
            ),
        },
        *seed,
    ]
    ai_text = await invokeLargeLLM(messages)
    history.append({"role": "assistant", "content": ai_text})
    return ai_text


async def fetch_doctors(
    token: str, appointment_type_id: int | None = None
) -> list[dict]:

    providers = await get_full_providers(
        token=token, appointment_type_id=appointment_type_id
    )

    doctors = []

    for p in providers:
        profile = p.get("provider_profile")

        doctors.append(
            {
                "id": p["id"],
                "name": f"Dr. {p['first_name']} {p['last_name']}",
                "specialization": profile["specialization"] if profile else "N/A",
                "qualification": profile["qualification"] if profile else "N/A",
                "experience": profile["experience"] if profile else 0,
                "bio": profile["bio"] if profile else "",
            }
        )

    return doctors


def _doctors_context(doctors: list[dict]) -> str:
    return "\n".join(
        f"{i + 1}. id={d['id']} name={d['name']} specialization={d['specialization']} "
        f"experience={d['experience']}yrs qualification={d['qualification']} bio={d['bio']}"
        for i, d in enumerate(doctors)
    )


async def _verify_selection(
    user_text: str, doctors: list[dict]
) -> tuple[int | None, str | None]:
    try:
        message = [
            {"role": "system", "content": DOCTOR_VERIFIER_PROMPT},
            {
                "role": "user",
                "content": f"Doctors:\n{_doctors_context(doctors)}\n\nPatient said: {user_text}",
            },
        ]
        response = await invokeLargeLLM_json(messages=message)
        doctor_id = response.get("doctor_id")
        doctor_name = response.get("doctor_name")

        return (int(doctor_id), str(doctor_name)) if doctor_id else (None, None)
    except Exception as e:
        print("[doctor verifier error]:", e)
        return None, None


def _resolve_doctor_from_history(
    history: list[dict], doctors: list[dict]
) -> tuple[int | None, str | None]:
    """
    When the user gives a vague confirmation (e.g. 'ok', 'fine', 'get it'),
    try to find the last doctor name mentioned in assistant messages and
    match it to the available doctors list.
    """
    # Walk history in reverse to find the most recently mentioned doctor
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "").lower()
        for d in doctors:
            if d["name"].lower() in content:
                return d["id"], d["name"]
    return None, None


async def doctor_selection_node(state: dict) -> dict:
    print("[doctor_selection_node] -----------------------------")

    user_change_request: str | None = state.get("user_change_request")
    previous_doctor_name: str | None = state.get("doctor_confirmed_name")
    user_text: str = (state.get("speech_user_text") or "").strip()
    history: list[dict] = list(state.get("doctor_selection_history") or [])
    intent: str = state.get("mapping_intent") or "general checkup"

    if user_text:
        history.append({"role": "user", "content": user_text})

    try:
        appointment_type_id = state.get("mapping_appointment_type_id") or -1
        print("appointment_type_id---------------", appointment_type_id)
        token = state.get("call_user_token")
        doctors = await fetch_doctors(
            token=token, appointment_type_id=appointment_type_id
        )

    except Exception as e:
        print("[doctor_selection_node] fetch failed:", e)
        history.append({"role": "assistant", "content": NO_DOCTORS_RESPONSE})
        return {
            **state,
            "active_node": "doctor_selection",
            "doctor_selection_history": history,
            "doctor_selection_completed": True,
            "speech_ai_text": NO_DOCTORS_RESPONSE,
        }

    if not doctors:
        history.append({"role": "assistant", "content": NO_DOCTORS_RESPONSE})
        return {
            **state,
            "active_node": "doctor_selection",
            "doctor_selection_history": history,
            "doctor_selection_completed": True,
            "speech_ai_text": NO_DOCTORS_RESPONSE,
        }

    if user_change_request and previous_doctor_name:
        available_doctors = (
            [d for d in doctors if d["name"] != previous_doctor_name] or doctors
        )
    else:
        available_doctors = doctors

    # ── Already confirmed a doctor, no change requested ─────────────────────
    if state.get("doctor_confirmed_id") and not user_change_request:
        print("[doctor_selection_node] doctor already confirmed — skipping to completed")
        return {
            **state,
            "active_node": "doctor_selection",
            "doctor_selection_history": history,
            "doctor_selection_completed": True,
            "doctor_selection_pending": False,
        }

    # ── Only one doctor available ────────────────────────────────────────────
    if len(available_doctors) == 1:
        doctor = available_doctors[0]

        if user_change_request:
            ai_text = f"Currently, we have only {doctor['name']} available."
            history.append({"role": "assistant", "content": ai_text})
            return {
                **state,
                "active_node": "doctor_selection",
                "user_change_request": None,
                "doctor_confirmed_id": doctor["id"],
                "doctor_confirmed_name": doctor["name"],
                "doctor_selection_pending": False,
                "doctor_selection_completed": True,
                "doctor_selection_history": history,
                "speech_ai_text": ai_text,
            }

        ai_text = await run_doctor_llm(
            mode="auto_select",
            doctors=doctors,
            history=history,
            intent=intent,
        )
        return {
            **state,
            "active_node": "doctor_selection",
            "user_change_request": None,
            "doctor_confirmed_id": doctor["id"],
            "doctor_confirmed_name": doctor["name"],
            "doctor_selection_pending": False,
            "doctor_selection_completed": True,
            "doctor_selection_history": history,
            "speech_ai_text": ai_text,
        }

    # ── Multiple doctors — handle user input ─────────────────────────────────
    if user_text and state.get("doctor_selection_pending"):
        response = await invokeLargeLLM_json(
            messages=[
                {"role": "system", "content": DOCTOR_INTENT_VERIFIER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Doctors:\n{_doctors_context(available_doctors)}\n\n"
                        f"Patient said: {user_text}"
                    ),
                },
            ]
        )

        user_intent = response.get("intent", "unknown")
        print("[user_intent]:", user_intent)

        # ── User is asking a question about a doctor ─────────────────────────
        if user_intent == "asking_info":
            ai_text = await run_doctor_llm(
                mode="handle_question",
                doctors=doctors,
                history=history,
                intent=intent,
            )
            return {
                **state,
                "active_node": "doctor_selection",
                "doctor_selection_history": history,
                "doctor_selection_pending": True,
                "doctor_selection_completed": False,
                "speech_ai_text": ai_text,
            }

        if user_intent in ("selecting", "confirming"):
            doctor_id, doctor_name = await _verify_selection(
                user_text, available_doctors
            )

            if not doctor_id:
                doctor_id, doctor_name = _resolve_doctor_from_history(
                    history, available_doctors
                )
                if doctor_id:
                    print(
                        f"[doctor_selection_node] fallback resolved doctor "
                        f"from history: {doctor_name}"
                    )

            if doctor_id:
                ai_text = await run_doctor_llm(
                    mode="confirm_selection",
                    doctors=doctors,
                    history=history,
                    intent=intent,
                )
                return {
                    **state,
                    "active_node": "doctor_selection",
                    "user_change_request": None,
                    "doctor_confirmed_id": doctor_id,
                    "doctor_confirmed_name": doctor_name,
                    "doctor_selection_completed": True,
                    "doctor_selection_pending": False,
                    "doctor_selection_history": history,
                    "speech_ai_text": ai_text,
                }

            
            ai_text = await run_doctor_llm(
                mode="handle_question",
                doctors=doctors,
                history=history,
                intent=intent,
            )
            return {
                **state,
                "active_node": "doctor_selection",
                "doctor_selection_history": history,
                "doctor_selection_pending": True,
                "doctor_selection_completed": False,   
                "speech_ai_text": ai_text,
            }

    ai_text = await run_doctor_llm(
        mode="present_options",
        doctors=available_doctors,
        history=history,
        intent=intent,
    )

    return {
        **state,
        "active_node": "doctor_selection",
        "doctor_selection_pending": True,
        "doctor_selection_completed": False,
        "doctor_list": available_doctors,
        "doctor_selection_history": history,
        "speech_ai_text": ai_text,
    }
