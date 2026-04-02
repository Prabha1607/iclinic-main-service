import logging
from src.control.voice_assistance.prompts.query_intent_node_prompt import build_intent_system, build_out_of_context_prompt
from src.control.voice_assistance.utils.llm_utils import invokeLLM_json
from src.control.voice_assistance.utils.state_utils import reset_from_date, reset_from_doctor, reset_from_slot

logger = logging.getLogger(__name__)

async def query_intent_node(state: dict) -> dict:
    
    user_text = state.get("speech_user_text")

    if not user_text:
        logger.info("Empty speech input — skipping intent processing")
        return {**state, "speech_user_text": None}

    cleaned = user_text  
    active_node = state.get("active_node")

    logger.info(f"Query intent processing | node={active_node} | text='{cleaned}'")

    base_state = {
        **state,
        "speech_user_text": cleaned,
        "user_change_request": None,
        "is_out_of_context": False,
        "speak_only": False
    }

    try:
        intent_system = build_intent_system(state)
    except Exception as e:
        logger.error(f"Failed to build intent system | error={e}")
        return base_state

    if active_node == "pre_confirmation":
        logger.info("Running change detection (pre_confirmation stage)")
        try:
            parsed = await invokeLLM_json(system_prompt=intent_system, user_prompt=cleaned)
        except Exception as e:
            logger.error(f"Intent detection failed | error={e}")
            return base_state

        if not isinstance(parsed, dict):
            logger.warning(f"Invalid LLM response: {parsed}")
            return base_state

        intent = parsed.get("intent", "none")
        logger.info(f"Detected intent (pre_confirmation): {intent}")

        if intent == "change_doctor":
            return reset_from_doctor(base_state, cleaned)

        if intent == "change_date":
            return reset_from_date(base_state, cleaned)

        if intent == "change_slot":
            return reset_from_slot(base_state, cleaned)

        return base_state

    try:
        context_prompt = build_out_of_context_prompt(state)
        context_check = await invokeLLM_json(system_prompt=context_prompt, user_prompt=cleaned)
    except Exception as e:
        logger.error(f"Context check failed | error={e}")
        context_check = {}

    if isinstance(context_check, dict) and context_check.get("is_out_of_context"):
        logger.warning("Out-of-context detected")
        return {**base_state, "is_out_of_context": True}

    try:
        parsed = await invokeLLM_json(system_prompt=intent_system, user_prompt=cleaned)
    except Exception as e:
        logger.error(f"Intent detection failed | error={e}")
        return base_state

    if not isinstance(parsed, dict):
        logger.warning(f"Invalid intent response: {parsed}")
        return base_state

    intent = parsed.get("intent", "none")
    logger.info(f"Detected intent: {intent}")

    if intent == "change_doctor":
        if not state.get("doctor_confirmed_id"):
            logger.info("Doctor change requested but no doctor selected yet")
            if active_node == "doctor_selection":
                return base_state
            return {**base_state, "speech_ai_text": "You haven't selected a doctor yet — let's go ahead and pick one now.", "speak_only": True}
        logger.info("Doctor change detected — resetting from doctor")
        return reset_from_doctor(base_state, cleaned)

    if intent == "change_date":
        if not state.get("slot_chosen_date"):
            logger.info("Date change requested but no date selected yet")
            if active_node == "booking_slot_selection":
                return base_state
            return {**base_state, "speech_ai_text": "No date has been chosen yet — let's continue and pick one.", "speak_only": True}
        logger.info("Date change detected — resetting from date")
        return reset_from_date(base_state, cleaned)

    if intent == "change_slot":
        if not state.get("slot_selected"):
            logger.info("Time change requested but no slot selected yet")
            if active_node == "booking_slot_selection":
                return base_state
            return {**base_state, "speech_ai_text": "No time has been chosen yet — let's continue and pick one.", "speak_only": True}
        logger.info("Time change detected — resetting from slot")
        return reset_from_slot(base_state, cleaned)

    logger.info("No change detected — continuing flow")
    return base_state