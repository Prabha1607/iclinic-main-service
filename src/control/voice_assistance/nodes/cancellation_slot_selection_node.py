from datetime import UTC, datetime
from datetime import date as date_type

from sqlalchemy import and_, select

from src.control.voice_assistance.models import get_llama1
from src.control.voice_assistance.prompts.cancel_appointment_node_prompt import (
    DB_ERROR_RESPONSE,
    ERROR_RESPONSE,
    NO_APPOINTMENTS_RESPONSE,
    SELECT_DATE_PROMPT,
    SELECT_SLOT_PROMPT,
)
from src.control.voice_assistance.utils import update_state
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.appointment_type import AppointmentType
from src.data.models.postgres.ENUM import AppointmentStatus


async def _fetch_upcoming_appointments(user_id: int) -> list:
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Appointment, AppointmentType.name.label("type_name"))
            .join(
                AppointmentType, Appointment.appointment_type_id == AppointmentType.id
            )
            .where(
                and_(
                    Appointment.user_id == user_id,
                    Appointment.status == AppointmentStatus.SCHEDULED,
                    Appointment.is_active,
                    Appointment.scheduled_date >= date_type.today(),
                )
            )
            .order_by(
                Appointment.scheduled_date.asc(), Appointment.scheduled_start_time.asc()
            )
        )
        result = await session.execute(stmt)
        rows = result.all()

    return [
        row
        for row in rows
        if datetime.combine(
            row[0].scheduled_date,
            row[0].scheduled_start_time,
        ).replace(tzinfo=UTC)
        > now
    ]


async def _llm_invoke(system: str, human: str) -> str:
    model = get_llama1()
    response = await model.ainvoke([("system", system), ("human", human)])
    return response.content.strip()


def _build_appointments_list(rows: list) -> list[dict]:
    return [
        {
            "id": appointment.id,
            "date": str(appointment.scheduled_date),
            "start_time": str(appointment.scheduled_start_time),
            "end_time": str(appointment.scheduled_end_time),
            "reason": appointment.reason_for_visit or "Not specified",
            "type_name": type_name,
        }
        for appointment, type_name in rows
    ]


def _reason_line(chosen: dict) -> str:
    return (
        f"The reason you booked this was: {chosen['reason']}. "
        if chosen["reason"] != "Not specified"
        else ""
    )


def _spoken_slots(appointments_list: list[dict]) -> str:
    return ", ".join(
        f"{i + 1}. {a['type_name']} from {a['start_time']} to {a['end_time']}"
        for i, a in enumerate(appointments_list)
    )


def _unique_dates(appointments_list: list[dict]) -> list[str]:
    seen = []
    for a in appointments_list:
        if a["date"] not in seen:
            seen.append(a["date"])
    return seen


async def _handle_initial(state: dict, user_id: int) -> dict:
    try:
        rows = await _fetch_upcoming_appointments(user_id)
        print(f"[cancellation_slot_selection_node] Upcoming appointments: {len(rows)}")
    except Exception as e:
        print(f"[cancellation_slot_selection_node] DB ERROR: {type(e).__name__}: {e}")
        return update_state(
            state, active_node="cancellation_slot_selection", speech_ai_text=DB_ERROR_RESPONSE, cancellation_complete=True
        )

    if not rows:
        return update_state(
            state,
            active_node="cancellation_slot_selection",
            cancellation_complete=True,
            speech_ai_text=NO_APPOINTMENTS_RESPONSE,
        )

    appointments_list = _build_appointments_list(rows)
    dates = _unique_dates(appointments_list)
    date_lines = "\n".join(f"  - {d}" for d in dates)

    if len(dates) == 1:
        if len(appointments_list) == 1:
            chosen = appointments_list[0]
            return update_state(
                state,
                active_node="cancellation_slot_selection",
                appointments_list=appointments_list,
                cancellation_appointment=chosen,
                cancellation_stage="ask_confirm",
                cancellation_awaiting_fresh_input=True,
                speech_ai_text=(
                    f"You have one upcoming appointment on {dates[0]}: "
                    f"{chosen['type_name']} from {chosen['start_time']} "
                    f"to {chosen['end_time']}. "
                    f"{_reason_line(chosen)}"
                    f"Would you like to cancel this appointment?"
                ),
            )

        return update_state(
            state,
            active_node="cancellation_slot_selection",
            appointments_list=appointments_list,
            cancellation_stage="ask_slot",
            speech_ai_text=(
                f"You have an upcoming appointment on {dates[0]}. "
                f"{_spoken_slots(appointments_list)}. "
                f"Which one would you like to cancel?"
            ),
        )

    return update_state(
        state,
        active_node="cancellation_slot_selection",
        appointments_list=appointments_list,
        cancellation_stage="ask_date",
        speech_ai_text=(
            f"You have upcoming appointments on the following dates:\n{date_lines}\n"
            "Which date would you like to cancel?"
        ),
    )


async def _handle_ask_date(state: dict, user_text: str) -> dict:
    appointments_list = state.get("appointments_list", [])
    dates = _unique_dates(appointments_list)

    if not user_text:
        date_lines = "\n".join(f"  - {d}" for d in dates)
        return update_state(
            state,
            active_node="cancellation_slot_selection",
            speech_ai_text=f"Please tell me which date. Available dates:\n{date_lines}",
        )

    try:
        dates_list = "\n".join(f"  - {d}" for d in dates)
        matched_date = await _llm_invoke(
            system=SELECT_DATE_PROMPT.format(
                dates_list=dates_list, user_text=user_text
            ),
            human=user_text,
        )
        print(f"[cancellation_slot_selection_node] Matched date: '{matched_date}'")
    except Exception as e:
        print(f"[cancellation_slot_selection_node] LLM ERROR: {type(e).__name__}: {e}")
        return update_state(
            state, active_node="cancellation_slot_selection", speech_ai_text=ERROR_RESPONSE, cancellation_complete=True
        )

    if matched_date == "UNKNOWN":
        date_lines = "\n".join(f"  - {d}" for d in dates)
        return update_state(
            state,
            active_node="cancellation_slot_selection",
            speech_ai_text=(
                f"I couldn't understand that date. Your upcoming appointments are on:\n{date_lines}\n"
                "Which date would you like to cancel?"
            ),
        )

    slots_on_date = [a for a in appointments_list if a["date"] == matched_date]

    if not slots_on_date:
        date_lines = "\n".join(f"  - {d}" for d in dates)
        return update_state(
            state,
            active_node="cancellation_slot_selection",
            speech_ai_text=(
                f"I couldn't find any appointments on {matched_date}. "
                f"Your upcoming appointments are on:\n{date_lines}\n"
                "Which date would you like to cancel?"
            ),
        )

    if len(slots_on_date) == 1:
        chosen = slots_on_date[0]
        return update_state(
            state,
            active_node="cancellation_slot_selection",
            cancellation_appointment=chosen,
            cancellation_stage="ask_confirm",
            cancellation_awaiting_fresh_input=True,
            speech_ai_text=(
                f"I found your {chosen['type_name']} appointment on {chosen['date']} "
                f"from {chosen['start_time']} to {chosen['end_time']}. "
                f"{_reason_line(chosen)}"
                f"Are you sure you want to cancel this appointment?"
            ),
        )

    return update_state(
        state,
        active_node="cancellation_slot_selection",
        cancellation_stage="ask_slot",
        speech_ai_text=(
            f"You have {len(slots_on_date)} appointments on {matched_date}. "
            f"{_spoken_slots(slots_on_date)}. "
            f"Which time slot would you like to cancel?"
        ),
    )


async def _handle_ask_slot(state: dict, user_text: str) -> dict:
    appointments_list = state.get("appointments_list", [])

    if not user_text:
        return update_state(
            state, active_node="cancellation_slot_selection", speech_ai_text="Please say which time slot you would like to cancel."
        )

    try:
        slots_text = "\n".join(
            f"{i + 1}. {a['type_name']} from {a['start_time']} to {a['end_time']}"
            for i, a in enumerate(appointments_list)
        )
        matched_index = await _llm_invoke(
            system=SELECT_SLOT_PROMPT.format(
                date=appointments_list[0]["date"] if appointments_list else "",
                slots_list=slots_text,
                user_text=user_text,
            ),
            human=user_text,
        )
        print(
            f"[cancellation_slot_selection_node] LLM matched slot index: '{matched_index}'"
        )
    except Exception as e:
        print(f"[cancellation_slot_selection_node] LLM ERROR: {type(e).__name__}: {e}")
        return update_state(
            state, active_node="cancellation_slot_selection", speech_ai_text=ERROR_RESPONSE, cancellation_complete=True
        )

    if matched_index == "UNKNOWN":
        spoken = ", ".join(
            f"{i + 1}. {a['start_time']} to {a['end_time']}"
            for i, a in enumerate(appointments_list)
        )
        return update_state(
            state,
            active_node="cancellation_slot_selection",
            speech_ai_text=f"I could not understand. Please say one of these slots: {spoken}.",
        )

    try:
        chosen = appointments_list[int(matched_index) - 1]
    except (ValueError, IndexError):
        return update_state(
            state,
            active_node="cancellation_slot_selection",
            speech_ai_text="I could not find that slot. Please say the time or number of the appointment you want to cancel.",
        )

    return update_state(
        state,
        active_node="cancellation_slot_selection",
        cancellation_appointment=chosen,
        cancellation_stage="ask_confirm",
        cancellation_awaiting_fresh_input=True,
        speech_ai_text=(
            f"You selected the {chosen['type_name']} appointment "
            f"from {chosen['start_time']} to {chosen['end_time']} on {chosen['date']}. "
            f"{_reason_line(chosen)}"
            f"Are you sure you want to cancel this appointment?"
        ),
    )


async def cancellation_slot_selection_node(state: dict) -> dict:
    """
    Responsible for:
      - Fetching upcoming appointments (stage=None)
      - Asking which date     (stage="ask_date")
      - Asking which slot     (stage="ask_slot")

    Transitions to cancel_appointment_node once cancellation_stage="ask_confirm"
    and cancellation_appointment is set.
    """
    print("[cancellation_slot_selection_node] -----------------------------")

    user_id = state.get("identity_patient_id")
    user_text = state.get("speech_user_text")
    stage = state.get("cancellation_stage")

    print(
        f"[cancellation_slot_selection_node] user_id={user_id}, stage={stage}, user_text={user_text}"
    )

    if stage is None:
        return await _handle_initial(state, user_id)

    if stage == "ask_date":
        return await _handle_ask_date(state, user_text)

    if stage == "ask_slot":
        return await _handle_ask_slot(state, user_text)

    print(
        f"[cancellation_slot_selection_node] WARNING: Unhandled stage='{stage}' — passing through."
    )
    return {**state, "active_node": "cancellation_slot_selection"}

