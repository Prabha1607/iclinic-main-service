from __future__ import annotations

import asyncio
import json
import logging
import re

from src.control.voice_assistance.prompts.clarify_node_prompt import (
    DEFAULT_INTENT,
    EMERGENCY_SYSTEM_PROMPT,
    FALLBACK_RESPONSE,
    FIRST_TURN_TRIGGER,
    MAPPING_HUMAN_TEMPLATE,
    build_clarify_system_prompt,
    build_conversation_string,
    build_mapping_system_prompt,
)
from src.control.voice_assistance.prompts.emergency_prompt import EMERGENCY_RESPONSE
from src.control.voice_assistance.utils.llm_utils import (
    invokeLargeLLM,
    invokeLargeLLM_json,
    invokeLLM_json,
    is_emergency,
)
from src.control.voice_assistance.utils.state_utils import update_state
from src.control.voice_assistance.utils.common import normalise

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fallback_type(appointment_types: dict) -> tuple[int, str]:
    if not appointment_types:
        return -1, DEFAULT_INTENT
    for type_id, value in appointment_types.items():
        if "general" in value[0].lower():
            return type_id, normalise(value[0])
    first_id = next(iter(appointment_types))
    return first_id, normalise(appointment_types[first_id][0])


def _is_clarify_active(history: list[dict]) -> bool:

    return any(t.get("role") == "assistant" for t in history)


def _extract_question_from_plain_text(raw: str) -> dict:
    
    if not raw:
        return {"question": FALLBACK_RESPONSE, "ready": False}

    text = raw.strip().strip('"').strip("'")

    ready_phrases = [
        "i have enough", "i have all", "i'll go ahead", "let me book",
        "booking your appointment", "i will book", "all set", "ready to book",
    ]
    if any(phrase in text.lower() for phrase in ready_phrases):
        logger.info("_extract_question_from_plain_text: detected ready signal in plain text")
        return {"question": None, "ready": True}

    logger.info("_extract_question_from_plain_text: salvaged question from plain text response")
    return {"question": text, "ready": False}


# ---------------------------------------------------------------------------
# Clarify LLM call 
# ---------------------------------------------------------------------------

async def _ask_clarify(history: list[dict], appointment_types: dict) -> dict:
    
    system_prompt = build_clarify_system_prompt(appointment_types)

   
    if not history:
        user_messages = [{"role": "user", "content": FIRST_TURN_TRIGGER}]
    else:
        user_messages = list(history)

    messages = [
        {"role": "system", "content": system_prompt},
        *user_messages,
    ]

    parsed = await invokeLargeLLM_json(messages)
    if parsed is not None:
        question = parsed.get("question")
        ready    = bool(parsed.get("ready", False))
        logger.info("_ask_clarify: JSON parsed successfully, ready=%s", ready)
        return {"question": question, "ready": ready}

    logger.warning("_ask_clarify: JSON parse failed, attempting plain text salvage")
    raw = await invokeLargeLLM(messages)
    if raw:
        return _extract_question_from_plain_text(raw)

    # ── Total failure ──────────────────────────────────────────────────────
    logger.error("_ask_clarify: both JSON and plain text attempts failed")
    return {"question": FALLBACK_RESPONSE, "ready": False}


# ---------------------------------------------------------------------------
# Mapping LLM call
# ---------------------------------------------------------------------------

async def _run_mapping(history: list[dict], appointment_types: dict) -> dict:
    """
    Runs once when clarify signals ready=true.
    Returns a dict with appointment_type_id, intent, reason.
    Falls back to general check-up on any error.
    """
    conversation_str = build_conversation_string(history)
    system_prompt    = build_mapping_system_prompt(appointment_types)
    user_prompt      = MAPPING_HUMAN_TEMPLATE.format(conversation=conversation_str)

    try:
        parsed = await asyncio.wait_for(
            invokeLLM_json(system_prompt, user_prompt),
            timeout=5.0,
        )
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning("_run_mapping: failed or timed out", extra={"error": str(e)})
        parsed = None

    if parsed and parsed.get("appointment_type_id") is not None:
        return {
            "appointment_type_id": int(parsed["appointment_type_id"]),
            "intent":              str(parsed.get("intent", DEFAULT_INTENT)),
            "reason":              str(parsed.get("reason", "")),
        }

    # Fuzzy fallback
    fallback_id, fallback_intent = _fallback_type(appointment_types)
    logger.warning("_run_mapping: using fallback type id=%s", fallback_id)
    return {"appointment_type_id": fallback_id, "intent": fallback_intent, "reason": ""}


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

async def clarify_node(state: dict) -> dict:
    """
    Signal-driven clarification node.

    State keys read:
        speech_user_text               latest patient utterance
        clarify_conversation_history   list[{"role", "content"}]
        appointment_types              {id: (name, description, ...)}
        mapping_history                full conversation for downstream nodes

    State keys written:
        speech_ai_text
        clarify_conversation_history
        clarify_completed
        mapping_intent
        mapping_appointment_type_id
        mapping_appointment_type_completed
        booking_reason_for_visit
        mapping_emergency
        mapping_history
    """
    try:
        history:           list[dict] = list(state.get("clarify_conversation_history") or [])
        user_text:         str        = state.get("speech_user_text")
        appointment_types: dict       = state.get("appointment_types") or {}
        mapping_history:   list[dict] = list(state.get("mapping_history") or [])

        is_first_turn = len(history) == 0 and not user_text

        if user_text:
            user_text = user_text.strip()
            history.append({"role": "user", "content": user_text})
            mapping_history.append({"role": "user", "content": user_text})

            if _is_clarify_active(history) and await is_emergency(
                user_text, system_prompt=EMERGENCY_SYSTEM_PROMPT
            ):
                logger.warning("clarify_node: emergency detected")
                return update_state(
                    state,
                    active_node="clarify",
                    speech_ai_text=EMERGENCY_RESPONSE,
                    mapping_emergency=True,
                    clarify_completed=True,
                    clarify_conversation_history=history,
                    mapping_history=mapping_history,
                )

        clarify_result = await _ask_clarify(history, appointment_types)
        ready    = clarify_result.get("ready", False)
        question = clarify_result.get("question")

        if ready:
            mapping = await _run_mapping(history, appointment_types)

            appointment_type_id = mapping["appointment_type_id"]
            intent              = mapping["intent"]
            reason_for_visit    = mapping["reason"]

            friendly_name = intent.replace("_", " ").title()
            bridge_text = (
                f"Thank you! I'll go ahead and look into booking "
                f"a {friendly_name} appointment for you now."
            )
            mapping_history.append({"role": "assistant", "content": bridge_text})

            logger.info(
                "clarify_node: mapped intent=%s type_id=%s",
                intent, appointment_type_id,
            )
            return update_state(
                state,
                active_node="clarify",
                clarify_conversation_history=history,
                clarify_completed=True,
                mapping_intent=intent,
                mapping_appointment_type_id=appointment_type_id,
                mapping_appointment_type_completed=True,
                booking_reason_for_visit=reason_for_visit,
                speech_ai_text=bridge_text,
                mapping_history=mapping_history,
            )

        if not question:
            logger.warning("clarify_node: no question returned, using fallback")
            question = FALLBACK_RESPONSE

        ai_text = question.strip().strip('"').strip("'")

        history.append({"role": "assistant", "content": ai_text})
        mapping_history.append({"role": "assistant", "content": ai_text})

        logger.info(
            "clarify_node: question sent (first_turn=%s), waiting for patient reply",
            is_first_turn,
        )
        return update_state(
            state,
            active_node="clarify",
            speech_ai_text=ai_text,
            clarify_conversation_history=history,
            clarify_completed=False,
            mapping_history=mapping_history,
        )

    except Exception as exc:
        logger.error("clarify_node: unhandled exception: %s", exc, exc_info=True)
        return update_state(
            state,
            active_node="clarify",
            speech_ai_text=FALLBACK_RESPONSE,
            clarify_completed=False,  
            speech_error=str(exc),
        )