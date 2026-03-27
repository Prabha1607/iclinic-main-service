import json
import logging
from src.control.voice_assistance.utils.common import clear_markdown
from src.control.voice_assistance.models import ainvoke_llm, get_llama1

logger = logging.getLogger(__name__)


async def invokeLLM_json(system_prompt: str, user_prompt: str) -> dict | None:
    raw = ""
    try:
        llm = get_llama1()
        response = await llm.ainvoke([("system", system_prompt), ("human", user_prompt)])
        raw = response.content.strip()
        cleaned = clear_markdown(raw)
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"invokeLLM_json: failed to parse JSON | error={e} | raw={raw[:300]!r}")
    except Exception as e:
        logger.error(f"invokeLLM_json: unexpected error | error={e}")
    return None


async def invokeLLM(system_prompt: str, user_prompt: str) -> str | None:
    try:
        llm = get_llama1()
        response = await llm.ainvoke([("system", system_prompt), ("human", user_prompt)])
        return response.content.strip()
    except Exception as e:
        logger.error(f"invokeLLM: unexpected error | error={e}")
    return None


async def invokeLargeLLM_json(messages) -> dict | None:
    raw = ""
    try:
        response = await ainvoke_llm(messages)
        raw = response.content.strip()
        cleaned = clear_markdown(raw)
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"invokeLargeLLM_json: failed to parse JSON | error={e} | raw={raw[:500]!r}")
    except Exception as e:
        logger.error(f"invokeLargeLLM_json: unexpected error | error={e}")
    return None


async def invokeLargeLLM(messages) -> str | None:
    try:
        response = await ainvoke_llm(messages)
        return response.content.strip()
    except Exception as e:
        logger.error(f"invokeLargeLLM: unexpected error | error={e}")
    return None


async def llm_extract(system: str, human: str) -> dict:
    raw = ""
    try:
        llm = get_llama1()
        response = await llm.ainvoke([("system", system), ("human", human)])
        raw = response.content.strip()
        return json.loads(clear_markdown(raw))
    except json.JSONDecodeError as e:
        logger.warning(f"llm_extract: failed to parse JSON | error={e} | raw={raw[:300]!r}")
    except Exception as e:
        logger.error(f"llm_extract: unexpected error | error={e}")
    return {}


async def is_emergency(text: str, system_prompt: str) -> bool:
    try:
        response = await invokeLLM(user_prompt=text, system_prompt=system_prompt)
        return (response or "").strip().upper() == "YES"  
    except Exception:
        return False
 