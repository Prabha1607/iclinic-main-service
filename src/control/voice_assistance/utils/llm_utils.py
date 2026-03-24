import asyncio
import json
import logging
from typing import Callable, Any

from src.control.voice_assistance.utils.common import clear_markdown
from src.control.voice_assistance.models import ainvoke_llm, get_llama1

logger = logging.getLogger(__name__)


async def _retry_with_backoff(
    func: Callable,
    *args,
    retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    exceptions: tuple = (Exception,),
    **kwargs,
) -> Any:
    for attempt in range(retries):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            if attempt == retries - 1:
                raise

            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                "Retrying after error",
                extra={"attempt": attempt + 1, "delay": delay, "error": str(e)},
            )
            await asyncio.sleep(delay)


async def invokeLLM_json(system_prompt: str, user_prompt: str) -> dict | None:
    async def _call():
        llm = get_llama1()
        response = await llm.ainvoke([("system", system_prompt), ("human", user_prompt)])
        return json.loads(clear_markdown(response.content.strip()))

    try:
        return await _retry_with_backoff(
            _call,
            retries=4,
            exceptions=(json.JSONDecodeError, Exception),
        )
    except json.JSONDecodeError as e:
        logger.warning("invokeLLM_json: failed to parse JSON response", extra={"error": str(e)})
    except Exception as e:
        logger.error("invokeLLM_json: unexpected error", extra={"error": str(e)})
    return None


async def invokeLLM(system_prompt: str, user_prompt: str) -> str | None:
    async def _call():
        llm = get_llama1()
        response = await llm.ainvoke([("system", system_prompt), ("human", user_prompt)])
        return response.content.strip()

    try:
        return await _retry_with_backoff(_call, retries=4)
    except Exception as e:
        logger.error("invokeLLM: unexpected error", extra={"error": str(e)})
    return None


async def invokeLargeLLM_json(messages) -> dict | None:
    async def _call():
        response = await ainvoke_llm(messages)
        return json.loads(clear_markdown(response.content.strip()))

    try:
        return await _retry_with_backoff(
            _call,
            retries=4,
            exceptions=(json.JSONDecodeError, Exception),
        )
    except json.JSONDecodeError as e:
        logger.warning("invokeLargeLLM_json: failed to parse JSON response", extra={"error": str(e)})
    except Exception as e:
        logger.error("invokeLargeLLM_json: unexpected error", extra={"error": str(e)})
    return None


async def invokeLargeLLM(messages) -> str | None:
    async def _call():
        response = await ainvoke_llm(messages)
        return response.content.strip()

    try:
        return await _retry_with_backoff(_call, retries=4)
    except Exception as e:
        logger.error("invokeLargeLLM: unexpected error", extra={"error": str(e)})
    return None


async def llm_extract(system: str, human: str) -> dict:
    async def _call():
        llm = get_llama1()
        response = await llm.ainvoke([("system", system), ("human", human)])
        return json.loads(clear_markdown(response.content.strip()))

    try:
        return await _retry_with_backoff(
            _call,
            retries=4,
            exceptions=(json.JSONDecodeError, Exception),
        )
    except json.JSONDecodeError as e:
        logger.warning("llm_extract: failed to parse JSON response", extra={"error": str(e)})
    except Exception as e:
        logger.error("llm_extract: unexpected error", extra={"error": str(e)})
    return {}


async def is_emergency(text: str, system_prompt: str) -> bool:
    try:
        response = await invokeLLM(user_prompt=text,system_prompt=system_prompt)
        return response.content.strip().upper() == "EMERGENCY"
    except Exception as exc:
        return False
