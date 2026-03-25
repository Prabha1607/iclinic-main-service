import json
import logging
from typing import Dict, Any
from src.control.voice_assistance.prompts.pre_confirmation_noode_prompt import (
    INTENT_DETECTION_SYSTEM_PROMPT,
    PRE_CONFIRMATION_SYSTEM_PROMPT,
)
from src.control.voice_assistance.utils.state_utils import update_state
from src.control.voice_assistance.utils.llm_utils import invokeLLM, invokeLLM_json

logger = logging.getLogger(__name__)


# ---------------------------
# HELPERS
# ---------------------------

def _build_snapshot(state: dict) -> dict:
    slot = state.get("slot_selected") or {}
    slot_display = (
        slot.get("full_display")
        or slot.get("time_display")
        or state.get("slot_booked_display")
    )

    return {
        "patient_name": state.get("identity_user_name"),
        "doctor_name": state.get("doctor_confirmed_name"),
        "appointment_slot": slot_display,
        "appointment_date": slot.get("date") or slot.get("date_display"),
        "appointment_time": (
            f"{slot.get('start_time')} – {slot.get('end_time')}"
            if slot.get("start_time") else None
        ),
        "appointment_type_id": state.get("mapping_appointment_type_id"),
        "symptoms_summary": state.get("clarify_symptoms_text"),
        "reason_for_visit": state.get("booking_reason_for_visit"),
    }


def _fallback_confirmation(state: dict) -> str:
    slot = state.get("slot_selected") or {}
    slot_display = (
        slot.get("full_display")
        or slot.get("time_display")
        or state.get("slot_booked_display")
    )

    return (
        f"I'd like to confirm your appointment with "
        f"{state.get('doctor_confirmed_name', 'the doctor')} "
        f"on {slot_display or 'the selected slot'}. "
        "Shall I go ahead and book this for you?"
    )


async def _generate_confirmation_message(snapshot: dict) -> str:
    try:
        user_prompt = f"Booking details:\n{json.dumps(snapshot, default=str, indent=2)}"

        result = await invokeLLM(
            system_prompt=PRE_CONFIRMATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        return str(result or "").strip()

    except Exception:
        logger.exception("Failed to generate confirmation message")
        return ""


def _safe_intent_parse(response: Any, user_text: str) -> Dict[str, bool]:
    
    if not response or not isinstance(response, dict):
        logger.warning(
            "Invalid LLM intent response",
            extra={
                "response": str(response),
                "user_text": user_text,
            },
        )
        return {"confirmed": False, "uncertain": True}

    confirmed = str(response.get("confirmed", "")).lower() in ["true", "yes"]
    uncertain = str(response.get("uncertain", "")).lower() in ["true", "yes"]

    return {
        "confirmed": confirmed,
        "uncertain": uncertain,
    }


# ---------------------------
# MAIN NODE
# ---------------------------

async def pre_confirmation_node(state: dict) -> dict:
    try:

        awaiting = state.get("booking_awaiting_confirmation", False)

        # ── Awaiting user confirmation ──────────────────────────────────────
        if awaiting:
            user_text = (state.get("speech_user_text") or "").strip()

            if not user_text:
                logger.warning("Empty user input while awaiting confirmation")
                intent = {"confirmed": False, "uncertain": True}
            else:
                try:
                    raw_response = await invokeLLM_json(
                        system_prompt=INTENT_DETECTION_SYSTEM_PROMPT,
                        user_prompt=f'Patient reply: "{user_text}"',
                    )
                except Exception:
                    logger.exception("LLM intent detection crashed")
                    raw_response = None

                intent = _safe_intent_parse(raw_response, user_text)

            confirmed = intent["confirmed"]
            uncertain = intent["uncertain"]

            if confirmed:
                logger.info("Appointment confirmed by patient")
                return update_state(
                    state,
                    active_node="pre_confirmation",
                    booking_awaiting_confirmation=False,
                    pre_confirmation_completed=True,
                    pre_confirmation_retry_count=0,
                    speech_ai_text=None,
                )

            if uncertain:
                retry_count = state.get("pre_confirmation_retry_count", 0) + 1

                if retry_count >= 3:
                    logger.info("Max retries reached → fallback to slot selection")
                    return update_state(
                        state,
                        active_node="booking_slot_selection",
                        booking_awaiting_confirmation=False,
                        pre_confirmation_completed=False,
                        pre_confirmation_retry_count=0,
                        speech_ai_text="Let me help you pick the slot again.",
                    )

                snapshot = _build_snapshot(state)

                try:
                    confirmation_msg = await _generate_confirmation_message(snapshot)
                    if not confirmation_msg:
                        raise ValueError("Empty confirmation message")
                except Exception:
                    confirmation_msg = _fallback_confirmation(state)

                return update_state(
                    state,
                    active_node="pre_confirmation",
                    booking_awaiting_confirmation=True,
                    pre_confirmation_completed=False,
                    pre_confirmation_retry_count=retry_count,
                    speech_ai_text=f"Sorry, I didn't catch that. {confirmation_msg}",
                )

            logger.info("Patient declined → returning to slot selection")
            return update_state(
                state,
                active_node="booking_slot_selection",
                booking_awaiting_confirmation=False,
                pre_confirmation_completed=False,
                pre_confirmation_retry_count=0,
                speech_ai_text="No problem, let me show you available slots again.",
            )

        # ── First entry → generate confirmation ─────────────────────────────
        snapshot = _build_snapshot(state)

        try:
            confirmation_text = await _generate_confirmation_message(snapshot)
            if not confirmation_text:
                raise ValueError("Empty LLM response")
        except Exception:
            logger.warning("Using fallback confirmation message")
            confirmation_text = _fallback_confirmation(state)

        logger.info("Presenting confirmation to patient")

        return update_state(
            state,
            active_node="pre_confirmation",
            booking_awaiting_confirmation=True,
            pre_confirmation_completed=False,
            pre_confirmation_retry_count=0,
            booking_context_snapshot=snapshot,
            speech_ai_text=confirmation_text,
        )

    except Exception:
        logger.exception("pre_confirmation_node crashed")

        return update_state(
            state,
            active_node="booking_slot_selection",
            booking_awaiting_confirmation=False,
            pre_confirmation_completed=False,
            speech_ai_text="Something went wrong. Let me help you pick a slot again.",
        )