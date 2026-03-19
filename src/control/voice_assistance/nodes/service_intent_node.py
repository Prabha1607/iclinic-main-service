from src.control.voice_assistance.prompts.service_intent_node_prompt import (
    SERVICE_INTENT_PROMPT,
    SERVICE_INTENT_VERIFIER_PROMPT,
)
from src.control.voice_assistance.utils import invokeLargeLLM, invokeLargeLLM_json


async def service_intent_node(state: dict) -> dict:
    print("[service_intent_node] -----------------------------")

    user_text: str | None = state.get("speech_user_text")
    history: list[dict] = list(state.get("service_intent_history") or [])

    if user_text:
        history.append({"role": "user", "content": user_text.strip()})

    seed = history if history else [{"role": "user", "content": "start"}]
    messages = [{"role": "system", "content": SERVICE_INTENT_PROMPT}, *seed]

    try:
        ai_text = await invokeLargeLLM(messages)

        print("[ai_response]:", ai_text)

        service_type = None

        if user_text:
            try:
                verify_messages = [
                    {"role": "system", "content": SERVICE_INTENT_VERIFIER_PROMPT},
                    {"role": "user", "content": user_text.strip()},
                ]

                data = await invokeLargeLLM_json(verify_messages)

                service_type = data.get("service_type")
                print("[service_type]:", service_type)
            except Exception as e:
                print("[verifier error]:", e)

        history.append({"role": "assistant", "content": ai_text})

        return {
            **state,
            "active_node": "service_intent",
            "service_intent_history": history,
            "speech_ai_text": ai_text if not service_type else None,
            "service_type": service_type,
        }

    except Exception as e:
        return {
            **state,
            "active_node": "service_intent",
            "speech_ai_text": "Something went wrong. Please try again.",
            "speech_error": str(e),
        }