import logging
from src.control.voice_assistance.prompts.stt_node_prompt import build_intent_system,build_out_of_context_prompt
from src.control.voice_assistance.utils.llm_utils import invokeLLM_json, is_emergency
from src.control.voice_assistance.utils.state_utils import reset_from_date,reset_from_doctor,reset_from_slot
from src.control.voice_assistance.prompts.emergency_prompt import EMERGENCY_SYSTEM_PROMPT,EMERGENCY_RESPONSE
from src.control.voice_assistance.utils.state_utils import update_state
logger = logging.getLogger(__name__)


async def stt_node(state: dict) -> dict:
    """
    Process raw speech input and classify the patient's intent before routing.

    Normalises the transcribed user utterance, then applies a two-stage LLM
    classification pipeline:

    1. **Out-of-context check** (non-pre_confirmation nodes only) — determines
       whether the utterance is completely unrelated to the appointment flow. If
       so, sets ``is_out_of_context: True`` to route the call to general
       assistance without further processing.

    2. **Change-intent detection** — compares the utterance against the
       currently confirmed selections (doctor, date, period, slot) using a
       context-aware prompt. Detected change intents trigger the appropriate
       state reset so downstream nodes start fresh from the correct point:

       - ``change_doctor`` → full reset via ``_reset_from_doctor``
       - ``change_date``   → date and slot fields reset via ``_reset_from_date``
       - ``change_slot``   → slot fields reset via ``_reset_from_slot``

    At the ``pre_confirmation`` stage the out-of-context check is skipped and
    change-intent detection runs first, ensuring that phrases like
    "I'd like 11:30" are recognised as a slot change rather than a confirmation
    of the currently displayed time.

    If no change intent is detected and the utterance is in context, the state
    is returned unchanged except for the normalised ``speech_user_text`` and a
    cleared ``user_change_request``.

    Args:
        state: Current conversation state dict. Relevant keys include:
               - ``speech_user_text`` (str | None): Raw transcribed speech from Twilio.
               - ``active_node`` (str | None): The node currently handling the call.
               - ``doctor_confirmed_id`` (int | None): ID of the confirmed doctor.
               - ``doctor_confirmed_name`` (str | None): Display name of the confirmed doctor.
               - ``slot_chosen_date`` (date | str | None): Currently chosen appointment date.
               - ``slot_chosen_period`` (str | None): Chosen period (morning/afternoon).
               - ``slot_selected`` (str | None): Selected slot identifier.
               - ``slot_selected_display`` (str | None): Human-readable selected slot.

    Returns:
        dict: Updated state with one of the following outcomes:
              - Unchanged base state when ``speech_user_text`` is empty or ``None``.
              - Base state with ``is_out_of_context: True`` when the utterance is
                off-topic.
              - Reset state from ``_reset_from_doctor``, ``_reset_from_date``, or
                ``_reset_from_slot`` when a change intent is detected.
              - Base state with normalised ``speech_user_text`` and cleared
                ``user_change_request`` for all other in-context utterances.
    """


    user_text: str | None = state.get("speech_user_text")

    if not user_text:
        logger.info("stt_node received empty speech input — skipping classification")
        return {**state, "speech_user_text": None}

    if await is_emergency(
        
        user_text, system_prompt=EMERGENCY_SYSTEM_PROMPT
    ):
        return update_state(
            state,
            speech_ai_text=EMERGENCY_RESPONSE,
            mapping_emergency=True
        )
    
    cleaned = " ".join(user_text.split()).strip()
    active_node = state.get("active_node")

    logger.info(
        "stt_node processing utterance",
        extra={"active_node": active_node, "text_length": len(cleaned)},
    )

    base_state = {
        **state,
        "speech_user_text":  cleaned,
        "user_change_request": None,
        "is_out_of_context": False,
    }

    try:
        stt_intent_system = build_intent_system(state)
    except Exception as e:
        logger.error("Failed to build intent system prompt", extra={"error": str(e)})
        return base_state

    if active_node == "pre_confirmation":
        logger.info("Running change-intent check at pre_confirmation stage")
        try:
            parsed = await invokeLLM_json(system_prompt=stt_intent_system, user_prompt=cleaned)
            intent = parsed.get("intent", "none") if isinstance(parsed, dict) else "none"
            logger.info(
                "pre_confirmation intent classified",
                extra={
                    "intent": intent,
                    "doctor": state.get("doctor_confirmed_name"),
                    "date": state.get("slot_chosen_date"),
                    "period": state.get("slot_chosen_period"),
                    "slot": state.get("slot_selected_display"),
                },
            )
        except Exception as e:
            logger.error(
                "Intent classification failed at pre_confirmation — returning base state",
                extra={"error": str(e)},
            )
            return base_state

        if intent == "change_doctor" and state.get("doctor_confirmed_id") is not None:
            logger.info("Change-doctor intent detected at pre_confirmation — resetting from doctor")
            return reset_from_doctor(base_state, cleaned)

        if intent == "change_date" and state.get("slot_chosen_date") is not None:
            logger.info("Change-date intent detected at pre_confirmation — resetting from date")
            return reset_from_date(base_state, cleaned)

        if intent == "change_slot":
            logger.info("Change-slot intent detected at pre_confirmation — resetting from slot")
            return reset_from_slot(base_state, cleaned)

        return base_state

    try:
        out_of_context_system = build_out_of_context_prompt(state)
        context_check = await invokeLLM_json(
            system_prompt=out_of_context_system,
            user_prompt=cleaned,
        )
    except Exception as e:
        logger.error(
            "Out-of-context classification failed — treating as in-context",
            extra={"active_node": active_node, "error": str(e)},
        )
        context_check = {}

    if isinstance(context_check, dict) and context_check.get("is_out_of_context"):
        logger.warning(
            "Out-of-context utterance detected — routing to general assistance",
            extra={"active_node": active_node},
        )
        return {**base_state, "is_out_of_context": True}

    try:
        parsed = await invokeLLM_json(system_prompt=stt_intent_system, user_prompt=cleaned)
        intent = parsed.get("intent", "none") if isinstance(parsed, dict) else "none"
        logger.info(
            "Change-intent classified",
            extra={"active_node": active_node, "intent": intent},
        )
    except Exception as e:
        logger.error(
            "Change-intent classification failed — returning base state",
            extra={"active_node": active_node, "error": str(e)},
        )
        return base_state

    if intent == "change_doctor" and state.get("doctor_confirmed_id") is not None:
        logger.info("Change-doctor intent detected — resetting from doctor")
        return reset_from_doctor(base_state, cleaned)

    if intent == "change_date" and state.get("slot_chosen_date") is not None:
        logger.info("Change-date intent detected — resetting from date")
        return reset_from_date(base_state, cleaned)

    if intent == "change_slot" and state.get("slot_selected") is not None:
        logger.info("Change-slot intent detected — resetting from slot")
        return reset_from_slot(base_state, cleaned)

    logger.info("No change intent detected — returning base state", extra={"active_node": active_node})
    return base_state

