import logging
from datetime import UTC, datetime
from datetime import date as date_type

from sqlalchemy import and_, select

from src.control.voice_assistance.utils.llm_utils import invokeLLM
from src.control.voice_assistance.prompts.cancel_appointment_node_prompt import (
    DB_ERROR_RESPONSE,
    ERROR_RESPONSE,
    NO_APPOINTMENTS_RESPONSE,
    SELECT_DATE_PROMPT,
    SELECT_SLOT_PROMPT,
)
from src.control.voice_assistance.utils.state_utils import update_state
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.appointment_type import AppointmentType
from src.data.models.postgres.ENUM import AppointmentStatus

logger = logging.getLogger(__name__)


async def _fetch_upcoming_appointments(user_id: int) -> list:
    
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Appointment, AppointmentType.name.label("type_name"))
            .join(AppointmentType, Appointment.appointment_type_id == AppointmentType.id)
            .where(
                and_(
                    Appointment.user_id == user_id,
                    Appointment.status == AppointmentStatus.SCHEDULED,
                    Appointment.is_active,
                    Appointment.scheduled_date >= date_type.today(),
                )
            )
            .order_by(
                Appointment.scheduled_date.asc(),
                Appointment.scheduled_start_time.asc(),
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



def _build_appointments_list(rows: list) -> list[dict]:
    
    return [
        {
            "id":         appointment.id,
            "date":       str(appointment.scheduled_date),
            "start_time": str(appointment.scheduled_start_time),
            "end_time":   str(appointment.scheduled_end_time),
            "reason":     appointment.reason_for_visit or "Not specified",
            "type_name":  type_name,
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


def _history_append(state: dict, role: str, content: str) -> list[dict]:
    
    history = list(state.get("cancellation_slot_selection_history") or [])
    history.append({"role": role, "content": content})
    return history


def _state_from_chosen(state: dict, chosen: dict, history: list[dict], extra: dict) -> dict:
    
    return update_state(
        state,
        active_node                         = "cancellation_slot_selection",
        cancellation_slot_selection_history = history,
        cancellation_appointments_list      = state.get("cancellation_appointments_list"),
        cancellation_appointment            = chosen,
        cancellation_appointment_id         = chosen["id"],
        cancellation_slot_date              = chosen["date"],
        cancellation_slot_start_time        = chosen["start_time"],
        cancellation_slot_end_time          = chosen["end_time"],
        cancellation_slot_type_name         = chosen["type_name"],
        cancellation_slot_reason            = chosen["reason"],
        **extra,
    )


async def _handle_initial(state: dict, user_id: int) -> dict:
    
    try:
        rows = await _fetch_upcoming_appointments(user_id)
    except Exception:
        logger.exception(
            "Database fetch failed for upcoming appointments for user_id=%s.", user_id
        )
        history = _history_append(state, "assistant", DB_ERROR_RESPONSE)
        return update_state(
            state,
            active_node                         = "cancellation_slot_selection",
            cancellation_slot_selection_history = history,
            cancellation_complete               = True,
            speech_ai_text                      = DB_ERROR_RESPONSE,
        )

    if not rows:
        history = _history_append(state, "assistant", NO_APPOINTMENTS_RESPONSE)
        return update_state(
            state,
            active_node                         = "cancellation_slot_selection",
            cancellation_slot_selection_history = history,
            cancellation_complete               = True,
            speech_ai_text                      = NO_APPOINTMENTS_RESPONSE,
        )

    appointments_list = _build_appointments_list(rows)
    dates             = _unique_dates(appointments_list)
    date_lines        = "\n".join(f"  - {d}" for d in dates)

    if len(dates) == 1 and len(appointments_list) == 1:
        chosen  = appointments_list[0]
        ai_text = (
            f"You have one upcoming appointment on {dates[0]}: "
            f"{chosen['type_name']} from {chosen['start_time']} to {chosen['end_time']}. "
            f"{_reason_line(chosen)}"
            f"Would you like to cancel this appointment?"
        )
        history = _history_append(state, "assistant", ai_text)
        return _state_from_chosen(
            state, chosen, history,
            extra=dict(
                cancellation_appointments_list    = appointments_list,
                cancellation_stage                = "ask_confirm",
                cancellation_awaiting_fresh_input = True,
                speech_ai_text                    = ai_text,
            ),
        )

    if len(dates) == 1:
        ai_text = (
            f"You have an upcoming appointment on {dates[0]}. "
            f"{_spoken_slots(appointments_list)}. "
            f"Which one would you like to cancel?"
        )
        history = _history_append(state, "assistant", ai_text)
        return update_state(
            state,
            active_node                         = "cancellation_slot_selection",
            cancellation_slot_selection_history = history,
            cancellation_appointments_list      = appointments_list,
            cancellation_stage                  = "ask_slot",
            speech_ai_text                      = ai_text,
        )

    ai_text = (
        f"You have upcoming appointments on the following dates:\n{date_lines}\n"
        "Which date would you like to cancel?"
    )
    history = _history_append(state, "assistant", ai_text)
    return update_state(
        state,
        active_node                         = "cancellation_slot_selection",
        cancellation_slot_selection_history = history,
        cancellation_appointments_list      = appointments_list,
        cancellation_stage                  = "ask_date",
        speech_ai_text                      = ai_text,
    )


async def _handle_ask_date(state: dict, user_text: str) -> dict:
    
    appointments_list = state.get("cancellation_appointments_list") or []
    dates             = _unique_dates(appointments_list)

    if user_text:
        history = _history_append(state, "user", user_text)
    else:
        history = list(state.get("cancellation_slot_selection_history") or [])

    if not user_text:
        date_lines = "\n".join(f"  - {d}" for d in dates)
        ai_text    = f"Please tell me which date. Available dates:\n{date_lines}"
        history    = _history_append({"cancellation_slot_selection_history": history}, "assistant", ai_text)
        return update_state(
            state,
            active_node                         = "cancellation_slot_selection",
            cancellation_slot_selection_history = history,
            speech_ai_text                      = ai_text,
        )

    try:
        dates_list   = "\n".join(f"  - {d}" for d in dates)
        matched_date = await invokeLLM(
            system_prompt=SELECT_DATE_PROMPT.format(dates_list=dates_list, user_text=user_text),
            user_prompt=user_text,
        )
    except Exception:
        logger.exception(
            "LLM date resolution failed in ask_date stage for user_text=%r.", user_text
        )
        history = _history_append({"cancellation_slot_selection_history": history}, "assistant", ERROR_RESPONSE)
        return update_state(
            state,
            active_node                         = "cancellation_slot_selection",
            cancellation_slot_selection_history = history,
            cancellation_complete               = True,
            speech_ai_text                      = ERROR_RESPONSE,
        )

    if matched_date == "UNKNOWN":
        date_lines = "\n".join(f"  - {d}" for d in dates)
        ai_text    = (
            f"I couldn't understand that date. Your upcoming appointments are on:\n{date_lines}\n"
            "Which date would you like to cancel?"
        )
        history = _history_append({"cancellation_slot_selection_history": history}, "assistant", ai_text)
        return update_state(
            state,
            active_node                         = "cancellation_slot_selection",
            cancellation_slot_selection_history = history,
            speech_ai_text                      = ai_text,
        )

    slots_on_date = [a for a in appointments_list if a["date"] == matched_date]

    if not slots_on_date:
        date_lines = "\n".join(f"  - {d}" for d in dates)
        ai_text    = (
            f"I couldn't find any appointments on {matched_date}. "
            f"Your upcoming appointments are on:\n{date_lines}\n"
            "Which date would you like to cancel?"
        )
        history = _history_append({"cancellation_slot_selection_history": history}, "assistant", ai_text)
        return update_state(
            state,
            active_node                         = "cancellation_slot_selection",
            cancellation_slot_selection_history = history,
            speech_ai_text                      = ai_text,
        )

    if len(slots_on_date) == 1:
        chosen  = slots_on_date[0]
        ai_text = (
            f"I found your {chosen['type_name']} appointment on {chosen['date']} "
            f"from {chosen['start_time']} to {chosen['end_time']}. "
            f"{_reason_line(chosen)}"
            f"Are you sure you want to cancel this appointment?"
        )
        history = _history_append({"cancellation_slot_selection_history": history}, "assistant", ai_text)
        return _state_from_chosen(
            state, chosen, history,
            extra=dict(
                cancellation_stage                = "ask_confirm",
                cancellation_awaiting_fresh_input = True,
                speech_ai_text                    = ai_text,
            ),
        )

    ai_text = (
        f"You have {len(slots_on_date)} appointments on {matched_date}. "
        f"{_spoken_slots(slots_on_date)}. "
        f"Which time slot would you like to cancel?"
    )
    history = _history_append({"cancellation_slot_selection_history": history}, "assistant", ai_text)
    return update_state(
        state,
        active_node                         = "cancellation_slot_selection",
        cancellation_slot_selection_history = history,
        cancellation_stage                  = "ask_slot",
        cancellation_slot_date              = matched_date,
        speech_ai_text                      = ai_text,
    )


async def _handle_ask_slot(state: dict, user_text: str) -> dict:
    
    appointments_list = state.get("cancellation_appointments_list") or []
    resolved_date     = state.get("cancellation_slot_date")

    slots = (
        [a for a in appointments_list if a["date"] == resolved_date]
        if resolved_date
        else appointments_list
    )

    if user_text:
        history = _history_append(state, "user", user_text)
    else:
        history = list(state.get("cancellation_slot_selection_history") or [])

    if not user_text:
        ai_text = "Please say which time slot you would like to cancel."
        history = _history_append({"cancellation_slot_selection_history": history}, "assistant", ai_text)
        return update_state(
            state,
            active_node                         = "cancellation_slot_selection",
            cancellation_slot_selection_history = history,
            speech_ai_text                      = ai_text,
        )

    try:
        slots_text    = "\n".join(
            f"{i + 1}. {a['type_name']} from {a['start_time']} to {a['end_time']}"
            for i, a in enumerate(slots)
        )
        matched_index = await invokeLLM(
            system_prompt=SELECT_SLOT_PROMPT.format(
                date       = slots[0]["date"] if slots else "",
                slots_list = slots_text,
                user_text  = user_text,
            ),
            user_prompt=user_text,
        )
    except Exception:
        logger.exception(
            "LLM slot resolution failed in ask_slot stage for user_text=%r.", user_text
        )
        history = _history_append({"cancellation_slot_selection_history": history}, "assistant", ERROR_RESPONSE)
        return update_state(
            state,
            active_node                         = "cancellation_slot_selection",
            cancellation_slot_selection_history = history,
            cancellation_complete               = True,
            speech_ai_text                      = ERROR_RESPONSE,
        )

    if matched_index == "UNKNOWN":
        spoken  = ", ".join(
            f"{i + 1}. {a['start_time']} to {a['end_time']}"
            for i, a in enumerate(slots)
        )
        ai_text = f"I could not understand. Please say one of these slots: {spoken}."
        history = _history_append({"cancellation_slot_selection_history": history}, "assistant", ai_text)
        return update_state(
            state,
            active_node                         = "cancellation_slot_selection",
            cancellation_slot_selection_history = history,
            speech_ai_text                      = ai_text,
        )

    try:
        chosen = slots[int(matched_index) - 1]
    except (ValueError, IndexError):
        logger.warning(
            "LLM returned an invalid slot index %r for %d available slots.",
            matched_index,
            len(slots),
        )
        ai_text = "I could not find that slot. Please say the time or number of the appointment you want to cancel."
        history = _history_append({"cancellation_slot_selection_history": history}, "assistant", ai_text)
        return update_state(
            state,
            active_node                         = "cancellation_slot_selection",
            cancellation_slot_selection_history = history,
            speech_ai_text                      = ai_text,
        )

    ai_text = (
        f"You selected the {chosen['type_name']} appointment "
        f"from {chosen['start_time']} to {chosen['end_time']} on {chosen['date']}. "
        f"{_reason_line(chosen)}"
        f"Are you sure you want to cancel this appointment?"
    )
    history = _history_append({"cancellation_slot_selection_history": history}, "assistant", ai_text)
    return _state_from_chosen(
        state, chosen, history,
        extra=dict(
            cancellation_stage                = "ask_confirm",
            cancellation_awaiting_fresh_input = True,
            speech_ai_text                    = ai_text,
        ),
    )


async def cancellation_slot_selection_node(state: dict) -> dict:
    """Route the cancellation slot selection pipeline to the appropriate stage handler.

    Dispatches to one of three handlers based on the current ``cancellation_stage``:

    - "None" — fetches upcoming appointments and branches into the first
      appropriate stage.
    - "ask_date" — resolves the patient's spoken date against available
      appointment dates.
    - "ask_slot" — resolves the patient's spoken choice to a specific slot.

    Once a slot is unambiguously identified, the stage advances to
    "ask_confirm" and control is handed to :func:`cancel_appointment_node`.
    Unrecognised stages are passed through unchanged with a warning.

    Args:
        state: The current pipeline state dict. Relevant keys:
            - identity_patient_id (int | None): The patient's identifier.
            - speech_user_text (str | None): The latest transcribed utterance.
            - cancellation_stage (str | None): The current stage; one of
              "None", "ask_date", or "ask_slot".

    Returns:
        An updated state dict with "active_node" set to
        "cancellation_slot_selection" and "speech_ai_text" populated.
    """
    user_id   = state.get("identity_patient_id")
    user_text = (state.get("speech_user_text") or "").strip()
    stage     = state.get("cancellation_stage")

    logger.info(
        "cancellation_slot_selection_node entered: user_id=%s, stage=%r, user_text=%r.",
        user_id,
        stage,
        user_text,
    )

    if stage is None:
        return await _handle_initial(state, user_id)

    if stage == "ask_date":
        return await _handle_ask_date(state, user_text)

    if stage == "ask_slot":
        return await _handle_ask_slot(state, user_text)

    logger.warning(
        "Unhandled cancellation_stage=%r — passing through unchanged.", stage
    )
    return {**state, "active_node": "cancellation_slot_selection"}


