"""Service intent node for the voice assistance graph.

Determines whether the patient wants to book or cancel an appointment
through conversational LLM interaction, then exposes the resolved
service_type for downstream routing.
"""
import logging
from src.control.voice_assistance.prompts.service_intent_node_prompt import (
    SERVICE_INTENT_PROMPT,
    SERVICE_INTENT_VERIFIER_PROMPT,
)
from src.control.voice_assistance.utils.llm_utils import invokeLargeLLM, invokeLargeLLM_json

logger = logging.getLogger(__name__)


async def service_intent_node(state: dict) -> dict:
    """
    Processes user speech input to determine service intent.

    Invokes the LLM with conversation history to generate a response,
    then optionally runs a verifier to extract a structured service_type
    from the user's message.

    Args:
        state: Graph state containing:
            - speech_user_text: Latest user utterance.
            - service_intent_history: Prior conversation turns.

    Returns:
        Updated state with:
            - active_node: Set to "service_intent".
            - service_intent_history: Appended conversation history.
            - speech_ai_text: AI response, or None if service_type was resolved.
            - service_type: Extracted service type if verifier succeeded, else None.
            - speech_error: Error message string if the LLM invocation failed.
    """
    user_text: str | None = state.get("speech_user_text")
    history: list[dict] = list(state.get("service_intent_history") or [])

    if user_text:
        history.append({"role": "user", "content": user_text.strip()})

    seed = history if history else [{"role": "user", "content": "start"}]
    messages = [{"role": "system", "content": SERVICE_INTENT_PROMPT}, *seed]

    try:
        ai_text = await invokeLargeLLM(messages)
        logger.info("service_intent_node: LLM response received", extra={"ai_text": ai_text})

        service_type = None

        if user_text:
            verify_messages = [
                {"role": "system", "content": SERVICE_INTENT_VERIFIER_PROMPT},
                {"role": "user", "content": user_text.strip()},
            ]
            data = await invokeLargeLLM_json(verify_messages)
            if data:
                service_type = data.get("service_type")
                logger.info("service_intent_node: service type resolved", extra={"service_type": service_type})
            else:
                logger.warning("service_intent_node: verifier returned no data")

        history.append({"role": "assistant", "content": ai_text})

        return {
            **state,
            "active_node": "service_intent",
            "service_intent_history": history,
            "speech_ai_text": ai_text if not service_type else None,
            "service_type": service_type,
        }

    except RuntimeError as e:
        logger.exception("service_intent_node: failed to process intent", extra={"error": str(e)})
        return {
            **state,
            "active_node": "service_intent",
            "speech_ai_text": "Something went wrong. Please try again.",
            "speech_error": str(e),
        }