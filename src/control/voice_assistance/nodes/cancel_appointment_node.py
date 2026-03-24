import logging
from datetime import UTC, datetime

from src.control.voice_assistance.utils.llm_utils import invokeLLM
from src.control.voice_assistance.prompts.cancel_appointment_node_prompt import (
    CANCEL_ERROR_RESPONSE,
    CONFIRM_PROMPT,
    ERROR_RESPONSE,
)
from src.control.voice_assistance.utils.state_utils import update_state
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.ENUM import AppointmentStatus
from src.data.repositories.generic_crud import update_instance

logger = logging.getLogger(__name__)


async def _cancel_appointment_in_db(appointment_id: int) -> None:
    
    async with AsyncSessionLocal() as session:
        await update_instance(
            id=appointment_id,
            model=Appointment,
            db=session,
            status=AppointmentStatus.CANCELLED,
            cancelled_at=datetime.now(UTC),
            cancellation_reason="Cancelled via voice assistant",
            is_active=False,
        )


def _parse_decision(raw: str) -> str:
    
    first_word = raw.strip().split()[0].upper().rstrip(".,;:")
    if first_word == "YES":
        return "YES"
    return "NO"


async def _handle_ask_confirm(state: dict, user_text: str) -> dict:
    
    appointment_data = state.get("cancellation_appointment")

    if not user_text:
        return update_state(
            state,
            active_node="cancel_appointment",
            speech_ai_text="Please confirm. Would you like to cancel this appointment? Say yes or no.",
        )

    try:
        raw_decision = await invokeLLM(
            system_prompt=CONFIRM_PROMPT.format(
                date=appointment_data["date"],
                start_time=appointment_data["start_time"],
                end_time=appointment_data["end_time"],
                appointment_type=appointment_data["type_name"],
                reason=appointment_data["reason"],
                user_text=user_text,
            ),
            user_prompt=user_text,
        )
        decision = _parse_decision(raw_decision)
        logger.info(
            "Cancellation decision for appointment_id=%s: raw=%r parsed=%s.",
            appointment_data.get("id"),
            raw_decision,
            decision,
        )
    except Exception:
        logger.exception(
            "LLM invocation failed during cancellation confirmation for appointment_id=%s.",
            appointment_data.get("id"),
        )
        return update_state(
            state,
            active_node="cancel_appointment",
            speech_ai_text=ERROR_RESPONSE,
            cancellation_complete=True,
        )

    if decision != "YES":
        return update_state(
            state,
            active_node="cancel_appointment",
            cancellation_stage="done",
            cancellation_complete=True,
            speech_ai_text=(
                f"Okay, your {appointment_data['type_name']} appointment on "
                f"{appointment_data['date']} remains scheduled."
            ),
        )

    try:
        await _cancel_appointment_in_db(appointment_data["id"])
        logger.info(
            "Appointment appointment_id=%s successfully cancelled in the database.",
            appointment_data["id"],
        )
    except Exception:
        logger.exception(
            "Database cancellation failed for appointment_id=%s.",
            appointment_data.get("id"),
        )
        return update_state(
            state,
            active_node="cancel_appointment",
            speech_ai_text=CANCEL_ERROR_RESPONSE,
            cancellation_complete=True,
        )

    return update_state(
        state,
        active_node="cancel_appointment",
        cancellation_stage="done",
        cancellation_complete=True,
        cancellation_confirmed=True,
        speech_ai_text=(
            f"Your {appointment_data['type_name']} appointment on {appointment_data['date']} "
            f"from {appointment_data['start_time']} to {appointment_data['end_time']} "
            f"has been successfully cancelled. "
            f"You will receive a confirmation email shortly."
        ),
    )


async def cancel_appointment_node(state: dict) -> dict:
    """Route the cancellation pipeline to the appropriate stage handler.

    Skips processing when awaiting a fresh user input turn, delegates
    confirmation handling to :func:`_handle_ask_confirm` when in the
    ``ask_confirm`` stage, and passes through unrecognised stages unchanged.

    Args:
        state: The current pipeline state dict. Relevant keys:
            - cancellation_awaiting_fresh_input (bool | None): When truthy,
              clears the flag and returns immediately.
            - speech_user_text (str | None): The latest user utterance.
            - cancellation_stage (str | None): The current cancellation stage;
              ``"ask_confirm"`` is the only handled value.

    Returns:
        An updated state dict with ``active_node`` set to
        ``"cancel_appointment"``.
    """
    if state.get("cancellation_awaiting_fresh_input"):
        logger.info("Awaiting fresh user input — skipping confirmation check.")
        return update_state(
            state,
            active_node="cancel_appointment",
            cancellation_awaiting_fresh_input=False,
        )

    user_text = state.get("speech_user_text")
    stage = state.get("cancellation_stage")

    if stage == "ask_confirm":
        return await _handle_ask_confirm(state, user_text)

    logger.warning(
        "Unhandled cancellation_stage=%r — passing through unchanged.",
        stage,
    )
    return {**state, "active_node": "cancel_appointment"}