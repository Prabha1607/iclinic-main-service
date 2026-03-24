import json
import logging

from src.control.voice_assistance.prompts.pre_confirmation_noode_prompt import (
    INTENT_DETECTION_SYSTEM_PROMPT,
    PRE_CONFIRMATION_SYSTEM_PROMPT,
)
from src.control.voice_assistance.utils.state_utils import update_state
from src.control.voice_assistance.utils.llm_utils import invokeLLM, invokeLLM_json

logger = logging.getLogger(__name__)


def _build_snapshot(state: dict) -> dict:
    """Build a booking details snapshot from the current pipeline state.

    Args:
        state: The current pipeline state dict. Relevant keys:
            - identity_user_name (str | None): Patient's display name.
            - doctor_confirmed_name (str | None): Confirmed doctor's display name.
            - slot_selected (dict | None): Selected slot with ``full_display``,
              ``date``, ``start_time``, and ``end_time`` fields.
            - slot_booked_display (str | None): Fallback slot display string.
            - mapping_appointment_type_id (str | int | None): Appointment type ID.
            - clarify_symptoms_text (str | None): Summary of reported symptoms.
            - booking_reason_for_visit (str | None): Stated reason for the visit.

    Returns:
        A dict summarising the booking details suitable for LLM consumption.
    """
    slot = state.get("slot_selected") or {}
    return {
        "patient_name": state.get("identity_user_name"),
        "doctor_name": state.get("doctor_confirmed_name"),
        "appointment_slot": slot.get("full_display") or state.get("slot_booked_display"),
        "appointment_date": slot.get("date"),
        "appointment_time": (
            f"{slot.get('start_time')} – {slot.get('end_time')}"
            if slot.get("start_time")
            else None
        ),
        "appointment_type_id": state.get("mapping_appointment_type_id"),
        "symptoms_summary": state.get("clarify_symptoms_text"),
        "reason_for_visit": state.get("booking_reason_for_visit"),
    }


async def _generate_confirmation_message(snapshot: dict) -> str:
    """Generate a natural-language appointment confirmation message via LLM.

    Args:
        snapshot: A booking details dict as produced by :func:`_build_snapshot`.

    Returns:
        A stripped confirmation message string.

    Raises:
        LLM client exceptions propagate to the caller.
    """
    user_prompt = f"Booking details:\n{json.dumps(snapshot, default=str, indent=2)}"
    response = invokeLLM(system_prompt=PRE_CONFIRMATION_SYSTEM_PROMPT, user_prompt=user_prompt)
    return response.content.strip()


async def pre_confirmation_node(state: dict) -> dict:
    """Manage the pre-booking confirmation dialogue with the patient.

    Handles three distinct cases in order:

    1. **Change request detected** — if ``user_change_request`` is set in state,
       defers immediately to slot selection without treating the current turn as
       a confirmation reply.
    2. **Awaiting confirmation** — interprets the patient's reply via the LLM
       intent detector. Confirmed replies advance the pipeline; declined replies
       reset slot selection; uncertain replies re-prompt up to three times before
       falling back to slot selection.
    3. **Initial prompt** — generates and presents the confirmation message,
       transitioning the pipeline into the awaiting-confirmation state.

    Args:
        state: The current pipeline state dict. Relevant keys:
            - user_change_request (str | None): When set, bypasses confirmation
              and redirects to slot selection.
            - booking_awaiting_confirmation (bool): Whether the node is currently
              waiting for the patient's yes/no reply.
            - speech_user_text (str | None): The latest transcribed user utterance.
            - pre_confirmation_retry_count (int): Number of uncertain-reply retries
              so far; resets to 0 on success or slot-selection fallback.
            - booking_context_snapshot (dict | None): Cached snapshot from a
              previous uncertain-reply re-prompt; avoids redundant LLM calls.
            - All keys consumed by :func:`_build_snapshot`.

    Returns:
        An updated state dict. ``active_node`` is always set. On confirmation,
        ``pre_confirmation_completed`` is ``True``. On decline or retry exhaustion,
        slot selection state is reset. On LLM failure during initial generation,
        a hardcoded fallback confirmation message is used.
    """
    if state.get("user_change_request"):
        logger.info(
            "Change request detected (%r) — deferring to slot selection.",
            state["user_change_request"],
        )
        return update_state(
            state,
            active_node="booking_slot_selection",
            booking_awaiting_confirmation=False,
            pre_confirmation_completed=False,
        )

    awaiting = state.get("booking_awaiting_confirmation", False)

    if awaiting:
        user_text = (state.get("speech_user_text") or "").strip()

        try:
            response = await invokeLLM_json(
                INTENT_DETECTION_SYSTEM_PROMPT, f'Patient reply: "{user_text}"'
            )
        except Exception:
            logger.exception(
                "LLM intent detection failed during pre-confirmation for user_text=%r.",
                user_text,
            )
            return update_state(
                state,
                active_node="pre_confirmation",
                booking_awaiting_confirmation=False,
                pre_confirmation_completed=False,
                pre_confirmation_retry_count=0,
                slot_selected=None,
                slot_stage="ask_date",
                booking_slot_selection_completed=False,
                speech_ai_text=(
                    "I'm sorry, I ran into an issue processing your response. "
                    "Let me take you back to slot selection so we can try again."
                ),
            )

        confirmed = bool(response.get("confirmed"))
        uncertain = bool(response.get("uncertain"))

        if confirmed:
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
            logger.info(
                "Uncertain confirmation reply (attempt %d) for user_text=%r.",
                retry_count,
                user_text,
            )

            if retry_count >= 3:
                logger.warning(
                    "Too many uncertain confirmation replies (%d) — resetting to slot selection.",
                    retry_count,
                )
                return update_state(
                    state,
                    active_node="pre_confirmation",
                    booking_awaiting_confirmation=False,
                    pre_confirmation_completed=False,
                    pre_confirmation_retry_count=0,
                    slot_selected=None,
                    slot_stage="ask_date",
                    booking_slot_selection_completed=False,
                    speech_ai_text=(
                        "I'm having a little trouble hearing you clearly. "
                        "Let me take you back to the slot selection so we can start fresh."
                    ),
                )

            snapshot = state.get("booking_context_snapshot") or _build_snapshot(state)

            try:
                confirmation_msg = await _generate_confirmation_message(snapshot)
            except Exception:
                logger.exception(
                    "LLM confirmation message generation failed on retry %d.",
                    retry_count,
                )
                slot = state.get("slot_selected") or {}
                confirmation_msg = (
                    f"I'd like to confirm your appointment with "
                    f"{state.get('doctor_confirmed_name', 'the doctor')} "
                    f"on {slot.get('full_display', 'the selected slot')}. "
                    "Shall I go ahead and book this for you? Please say yes or no."
                )

            return update_state(
                state,
                active_node="pre_confirmation",
                booking_awaiting_confirmation=True,
                pre_confirmation_completed=False,
                pre_confirmation_retry_count=retry_count,
                speech_ai_text=f"Sorry, I didn't quite catch that. {confirmation_msg}",
            )

        return update_state(
            state,
            active_node="pre_confirmation",
            booking_awaiting_confirmation=False,
            pre_confirmation_completed=False,
            pre_confirmation_retry_count=0,
            slot_selected=None,
            slot_stage="ask_date",
            booking_slot_selection_completed=False,
            speech_ai_text=(
                "No problem! Let me show you the available slots again "
                "so you can pick a different time."
            ),
        )

    snapshot = _build_snapshot(state)
    try:
        confirmation_text = await _generate_confirmation_message(snapshot)
    except Exception:
        logger.exception("LLM confirmation message generation failed; using fallback message.")
        slot = state.get("slot_selected") or {}
        confirmation_text = (
            f"I'd like to confirm your appointment with "
            f"{state.get('doctor_confirmed_name', 'the doctor')} "
            f"on {slot.get('full_display', 'the selected slot')}. "
            "Shall I go ahead and book this for you? Please say yes or no."
        )

    return update_state(
        state,
        active_node="pre_confirmation",
        booking_awaiting_confirmation=True,
        pre_confirmation_completed=False,
        pre_confirmation_retry_count=0,
        booking_context_snapshot=snapshot,
        speech_ai_text=confirmation_text,
    )