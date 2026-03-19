from datetime import UTC, datetime

from src.control.voice_assistance.models import get_llama1
from src.control.voice_assistance.prompts.cancel_appointment_node_prompt import (
    CANCEL_ERROR_RESPONSE,
    CONFIRM_PROMPT,
    ERROR_RESPONSE,
)
from src.control.voice_assistance.utils import update_state
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.ENUM import AppointmentStatus
from src.data.repositories.generic_crud import update_instance


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


async def _llm_invoke(system: str, human: str) -> str:
    model = get_llama1()
    response = await model.ainvoke([("system", system), ("human", human)])
    return response.content.strip()


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
        raw_decision = await _llm_invoke(
            system=CONFIRM_PROMPT.format(
                date=appointment_data["date"],
                start_time=appointment_data["start_time"],
                end_time=appointment_data["end_time"],
                appointment_type=appointment_data["type_name"],
                reason=appointment_data["reason"],
                user_text=user_text,
            ),
            human=user_text,
        )
        decision = _parse_decision(raw_decision)
        print(
            f"[cancel_appointment_node] Raw decision: '{raw_decision}' → Parsed: '{decision}'"
        )
    except Exception as e:
        print(f"[cancel_appointment_node] LLM ERROR: {type(e).__name__}: {e}")
        return update_state(
            state, active_node="cancel_appointment", speech_ai_text=ERROR_RESPONSE, cancellation_complete=True
        )

    if decision != "YES":
        return update_state(
            state,
            active_node="cancel_appointment",
            cancellation_stage="done",
            cancellation_complete=True,
            speech_ai_text=(
                f"Okay, your {appointment_data['type_name']} appointment on "
                f"{appointment_data['date']} remains scheduled. "
            ),
        )

    try:
        await _cancel_appointment_in_db(appointment_data["id"])
        print("[cancel_appointment_node] Appointment cancelled in DB")
    except Exception as e:
        print(f"[cancel_appointment_node] DB ERROR: {type(e).__name__}: {e}")
        return update_state(
            state, active_node="cancel_appointment", speech_ai_text=CANCEL_ERROR_RESPONSE, cancellation_complete=True
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
    print("[cancel_appointment_node] -----------------------------")

    if state.get("cancellation_awaiting_fresh_input"):
        print(
            "[cancel_appointment_node] Awaiting fresh user input — skipping confirmation check."
        )
        return update_state(state, active_node="cancel_appointment", cancellation_awaiting_fresh_input=False)

    user_text = state.get("speech_user_text")
    stage = state.get("cancellation_stage")

    print(f"[cancel_appointment_node] stage={stage}, user_text={user_text}")

    if stage == "ask_confirm":
        return await _handle_ask_confirm(state, user_text)

    print(
        f"[cancel_appointment_node] WARNING: Unhandled stage='{stage}' — passing through."
    )
    return {**state, "active_node": "cancel_appointment"}