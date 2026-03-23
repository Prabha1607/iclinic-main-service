from typing import Any
from src.control.voice_assistance.prompts.confirmation_node_prompt import (
    CONVERSATION_PROMPT,
    VERIFIER_PROMPT,
)
from src.control.voice_assistance.utils import invokeLargeLLM, invokeLargeLLM_json

def apply_corrections(
    state: dict[str, Any],
    corrected_name: str | None,
    corrected_phone: str | None 
) -> dict[str, Any]:
    if corrected_name:
        state["identity_user_name"] = corrected_name
    if corrected_phone:
        state["identity_user_phone"] = corrected_phone
    return state

async def identity_confirmation_node(state: dict[str, Any]) -> dict[str, Any]:

    print("[identity_confirmation_node] -----------------------------")

    patient_name: str = (state.get("identity_user_name") or "").strip()
    phone_number: str = (state.get("identity_user_phone") or "").strip()
    user_text: str = (state.get("speech_user_text") or "").strip()
    conversation_history = list(state.get("identity_conversation_history") or [])

    if not patient_name:
        return {
            **state,
            "active_node": "identity_confirmation",
            "speech_ai_text": "Could you please tell me your name and phone number so I can look up your account?",
        }

    if user_text:
        conversation_history.append({"role": "user", "content": user_text})

    try:
        history = (
            conversation_history
            if conversation_history
            else [{"role": "user", "content": "start"}]
        )
        messages = [
            {
                "role": "system",
                "content": CONVERSATION_PROMPT.format(
                    name=patient_name, phone=phone_number
                ),
            },
            *history,
        ]

        response = await invokeLargeLLM(messages)

    except Exception as e:
        print("[LLM ERROR]", e)
        return state

    confirmed = False
    corrected_name = None
    corrected_phone = None

    if user_text:
        try:
            verify_result = None
            if user_text:
                verify_messages = [
                    {"role": "system", "content": VERIFIER_PROMPT},
                    {"role": "user", "content": f"Latest user reply: {user_text}"},
                ]
                verify_result = await invokeLargeLLM_json(verify_messages)

            confirmed = (
                bool(verify_result.get("confirmed", False)) if verify_result else False
            )
            corrected_name = (
                verify_result.get("corrected_name") if verify_result else None
            )
            corrected_phone = (
                verify_result.get("corrected_phone") if verify_result else None
            )

        except Exception as e:
            print("[VERIFIER ERROR]", e)

    state = apply_corrections(state, corrected_name, corrected_phone)

    conversation_history.append({"role": "assistant", "content": response})

    return {
        **state,
        "active_node": "identity_confirmation",
        "identity_conversation_history": conversation_history,
        "identity_confirmed_user": confirmed,
        "identity_confirmation_completed": confirmed,
        "speech_ai_text": response,
    }


