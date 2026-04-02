"""LLM invocation utilities for the voice assistance nodes.

Wraps the ainvoke calls for both the lightweight (Llama-1) and large LLM
instances, providing JSON-parsing, fallback handling, and emergency detection
helpers used throughout the graph nodes.
"""
import json
import logging
from src.control.voice_assistance.utils.common import clear_markdown
from src.control.voice_assistance.models import ainvoke_llm, get_llama1

logger = logging.getLogger(__name__)


async def invokeLLM_json(system_prompt: str, user_prompt: str) -> dict | None:
    """Invoke the lightweight LLM and parse the JSON response.

    Args:
        system_prompt: System-role prompt string.
        user_prompt: User-role prompt string.

    Returns:
        Parsed response dict, or ``None`` on parse failure or error.
    """
    raw = ""
    try:
        llm = get_llama1()
        response = await llm.ainvoke([("system", system_prompt), ("human", user_prompt)])
        raw = response.content.strip()
        cleaned = clear_markdown(raw)
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"invokeLLM_json: failed to parse JSON | error={e} | raw={raw[:300]!r}", exc_info=True)
    except RuntimeError as e:
        logger.exception(f"invokeLLM_json: unexpected error | error={e}")
    return None


async def invokeLLM(system_prompt: str, user_prompt: str) -> str | None:
    """Invoke the lightweight LLM and return the raw text response.

    Args:
        system_prompt: System-role prompt string.
        user_prompt: User-role prompt string.

    Returns:
        Stripped response string, or ``None`` on error.
    """
    try:
        llm = get_llama1()
        response = await llm.ainvoke([("system", system_prompt), ("human", user_prompt)])
        return response.content.strip()
    except RuntimeError as e:
        logger.exception(f"invokeLLM: unexpected error | error={e}")
    return None


async def invokeLargeLLM_json(messages) -> dict | None:
    """Invoke the large LLM with a messages list and parse the JSON response.

    Args:
        messages: List of message dicts in LangChain format.

    Returns:
        Parsed response dict, or ``None`` on parse failure or error.
    """
    raw = ""
    try:
        response = await ainvoke_llm(messages)
        raw = response.content.strip()
        cleaned = clear_markdown(raw)
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"invokeLargeLLM_json: failed to parse JSON | error={e} | raw={raw[:500]!r}", exc_info=True)
    except RuntimeError as e:
        logger.exception(f"invokeLargeLLM_json: unexpected error | error={e}")
    return None


async def invokeLargeLLM(messages) -> str | None:
    """Invoke the large LLM with a messages list and return the raw text response.

    Args:
        messages: List of message dicts in LangChain format.

    Returns:
        Stripped response string, or ``None`` on error.
    """
    try:
        response = await ainvoke_llm(messages)
        return response.content.strip()
    except RuntimeError as e:
        logger.exception(f"invokeLargeLLM: unexpected error | error={e}")
    return None


async def llm_extract(system: str, human: str) -> dict:
    """Invoke the lightweight LLM and return a parsed JSON dict.

    Similar to ``invokeLLM_json`` but returns an empty dict instead of
    ``None`` on failure, making it safe to use without ``None`` guards.

    Args:
        system: System-role prompt string.
        human: User-role prompt string.

    Returns:
        Parsed dict, or ``{}`` on failure.
    """
    raw = ""
    try:
        llm = get_llama1()
        response = await llm.ainvoke([("system", system), ("human", human)])
        raw = response.content.strip()
        return json.loads(clear_markdown(raw))
    except json.JSONDecodeError as e:
        logger.warning(f"llm_extract: failed to parse JSON | error={e} | raw={raw[:300]!r}", exc_info=True)
    except RuntimeError as e:
        logger.exception(f"llm_extract: unexpected error | error={e}")
    return {}


async def is_emergency(text: str, system_prompt: str) -> bool:
    """Detect whether user text signals a medical emergency.

    Invokes the LLM with a yes/no emergency-classification prompt.

    Args:
        text: Patient utterance to evaluate.
        system_prompt: System prompt instructing the LLM to reply YES or NO.

    Returns:
        ``True`` if the LLM responds with ``"YES"`` (case-insensitive),
        ``False`` otherwise or on error.
    """
    try:
        response = await invokeLLM(user_prompt=text, system_prompt=system_prompt)
        return (response or "").strip().upper() == "YES"  
    except RuntimeError:
        logger.exception("is_emergency: unexpected error")
        return False
 