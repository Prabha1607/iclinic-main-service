import logging
from src.control.voice_assistance.prompts.general_assistance_node_prompt import (
    build_general_assistance_prompt,
    system_prompt,
    FALLBACK_RESPONSE
)
from src.control.voice_assistance.utils.llm_utils import invokeLargeLLM

logger = logging.getLogger(__name__)



async def general_assistance_node(state: dict) -> dict:
    """
    Handles off-topic or general user questions during the appointment flow.

    Builds a context-aware prompt from the current state, invokes the LLM to
    generate a helpful response, then redirects the user back to the
    appointment process. Falls back to a static response if the LLM returns
    nothing.

    Args:
        state: Graph state containing conversation histories, confirmed facts,
               and the latest user utterance.

    Returns:
        Updated state with:
            - speech_ai_text: AI response or fallback message.
            - active_node: Set to "general_assistance".
            - speech_error: Present if the LLM invocation failed.
    """
    user_prompt = build_general_assistance_prompt(state)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    response = await invokeLargeLLM(messages=messages)

    if not response:
        logger.warning("general_assistance_node: LLM returned no response, using fallback")
        return {
            **state,
            "speech_ai_text": FALLBACK_RESPONSE,
            "active_node": "general_assistance",
            "speech_error": "LLM invocation returned no response",
        }

    logger.info("general_assistance_node: response generated successfully")
    return {
        **state,
        "speech_ai_text": response.strip(),
        "active_node": "general_assistance",
    }


