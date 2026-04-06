"""Identity confirmation node for the voice assistance graph.

Verifies or corrects a patient's identity (name and phone number) through
a conversational LLM interaction before proceeding with the booking flow.
"""
import logging
from typing import Any
from src.control.voice_assistance.prompts.confirmation_node_prompt import (
    CONVERSATION_PROMPT,
    VERIFIER_PROMPT,
)
from src.control.voice_assistance.utils.llm_utils import invokeLargeLLM, invokeLargeLLM_json

logger = logging.getLogger(__name__)


def apply_corrections(
    state: dict[str, Any],
    corrected_name: str | None,
    corrected_phone: str | None,
) -> dict[str, Any]:
    """Apply name and phone corrections to the graph state.

    Updates ``identity_user_name`` and ``identity_user_phone`` in the state
    when the patient provides corrections to their identity details.

    Args:
        state: Mutable graph state dict.
        corrected_name: Corrected patient name, or None if unchanged.
        corrected_phone: Corrected phone number, or None if unchanged.

    Returns:
        The updated state dict with corrections applied.
    """
    if corrected_name:
        state["identity_user_name"] = corrected_name
    if corrected_phone:
        state["identity_user_phone"] = corrected_phone
    return state


async def identity_confirmation_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Confirms or corrects a patient's identity via conversational LLM interaction.

    Builds a conversation from history and the latest user utterance, invokes
    the LLM to generate a response, then runs a verifier to check whether the
    user confirmed their identity and whether any corrections were provided.

    Args:
        state: Graph state containing:
            - identity_user_name: Patient name on record.
            - identity_user_phone: Phone number on record.
            - speech_user_text: Latest user utterance.
            - identity_conversation_history: Prior conversation turns.

    Returns:
        Updated state with:
            - active_node: Set to "identity_confirmation".
            - identity_conversation_history: Appended conversation history.
            - identity_confirmed_user: True if the user confirmed their identity.
            - identity_confirmation_completed: Mirrors identity_confirmed_user.
            - speech_ai_text: AI response text.
            - speech_error: Present if the LLM invocation failed.
    """
    patient_name: str = (state.get("identity_user_name") or "").strip()
    phone_number: str = (state.get("identity_user_phone") or "").strip()
    user_text: str = (state.get("speech_user_text") or "").strip()
    history: list[dict] = list(state.get("identity_conversation_history") or [])

    if not patient_name:
        logger.warning("identity_confirmation_node: patient name missing, prompting user")
        return {
            **state,
            "active_node": "identity_confirmation",
            "speech_ai_text": "Could you please tell me your name and phone number so I can look up your account?",
        }

    if user_text:
        history.append({"role": "user", "content": user_text})

    _history = history or [{"role": "user", "content": "start"}]
    messages = [
        {
            "role": "system",
            "content": CONVERSATION_PROMPT.format(name=patient_name, phone=phone_number),
        },
        *_history,
    ]

    response = await invokeLargeLLM(messages)
    if not response:
        logger.error("identity_confirmation_node: LLM invocation returned no response")
        return {
            **state,
            "active_node": "identity_confirmation",
            "speech_ai_text": "Something went wrong. Please try again.",
            "speech_error": "LLM invocation failed",
        }

    logger.info("identity_confirmation_node: LLM response received")

    confirmed = False
    corrected_name = None
    corrected_phone = None

    if user_text:
        verify_messages = [
            {"role": "system", "content": VERIFIER_PROMPT},
            {"role": "user", "content": f"Latest user reply: {user_text}"},
        ]
        verify_result = await invokeLargeLLM_json(verify_messages)

        if verify_result:
            confirmed = bool(verify_result.get("confirmed", False))
            corrected_name = verify_result.get("corrected_name")
            corrected_phone = verify_result.get("corrected_phone")
            logger.info(
                "identity_confirmation_node: verifier result",
                extra={"confirmed": confirmed, "corrected_name": corrected_name, "corrected_phone": corrected_phone},
            )
        else:
            logger.warning("identity_confirmation_node: verifier returned no data")

    state = apply_corrections(state, corrected_name, corrected_phone)
    history.append({"role": "assistant", "content": response})

    return {
        **state,
        "active_node": "identity_confirmation",
        "identity_conversation_history": history,
        "identity_confirmed_user": confirmed,
        "identity_confirmation_completed": confirmed,
        "speech_ai_text": response,
    }