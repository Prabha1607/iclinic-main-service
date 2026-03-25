import logging
from datetime import date, time as time_type

from src.control.voice_assistance.prompts.book_appointment_node_prompt import (
    DEFAULT_CONTEXT,
    EXTRACT_CONTEXT_PROMPT,
    build_history_text,
)
from src.control.voice_assistance.utils.state_utils import update_state
from src.control.voice_assistance.utils.llm_utils import invokeLLM_json
from src.core.services.available_slots import change_slot_status
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.ENUM import AppointmentStatus, BookingChannel, SlotStatus
from src.data.repositories.generic_crud import insert_instance

logger = logging.getLogger(__name__)

async def extract_appointment_context(conversation_history: list | str) -> dict:
    history_text = build_history_text(conversation_history)
    try:
        return await invokeLLM_json(          
            system_prompt=EXTRACT_CONTEXT_PROMPT,
            user_prompt=f"Conversation:\n{history_text}",
        )
    except Exception:
        logger.warning(
            "Failed to extract appointment context from conversation history; "
            "falling back to DEFAULT_CONTEXT.",
            exc_info=True,
        )
        return DEFAULT_CONTEXT

async def book_appointment_node(state: dict) -> dict:
    """Book an appointment for a patient with a confirmed doctor and slot.

    Validates that the booking pipeline is ready, persists the appointment record
    in the database, marks the availability slot as booked, and returns an updated
    state with a confirmation message.

    Args:
        state: The current pipeline state dict. Expected keys include:
            - slot_stage (str): Must be ``"ready_to_book"`` to proceed.
            - slot_selected (dict): The chosen slot with id, date, start_time,
              end_time, and full_display fields.
            - doctor_confirmed_id (str | int): The confirmed doctor's identifier.
            - doctor_confirmed_name (str): The confirmed doctor's display name.
            - identity_patient_id (str | int): The patient's identifier.
            - mapping_appointment_type_id (str | int): The appointment type identifier.
            - identity_user_name (str): The patient's display name.
            - clarify_conversation_history (list[dict]): Prior conversation turns.

    Returns:
        An updated state dict. On success, ``booking_appointment_completed`` is
        ``True`` and ``speech_ai_text`` contains a confirmation message.
        On any failure, ``booking_appointment_completed`` is ``False`` and
        ``speech_ai_text`` contains an error message.
    """
    if state.get("slot_stage") != "ready_to_book":
        logger.info("Skipping book_appointment_node: slot_stage is not 'ready_to_book'.")
        return {**state, "active_node": "book_appointment", "booking_appointment_completed": False}

    matched = state.get("slot_selected")

    if not matched:
        logger.error("book_appointment_node called with no slot_selected in state.")
        return {**state, "active_node": "book_appointment", "booking_appointment_completed": False}

    try:
        if isinstance(matched.get("date"), str):
            matched = {**matched, "date": date.fromisoformat(matched["date"])}
        if isinstance(matched.get("start_time"), str):
            matched = {**matched, "start_time": time_type.fromisoformat(matched["start_time"])}
        if isinstance(matched.get("end_time"), str):
            matched = {**matched, "end_time": time_type.fromisoformat(matched["end_time"])}
    except (ValueError, TypeError):
        logger.exception("Failed to parse date/time fields from slot_selected.")
        return update_state(
            state,
            active_node="book_appointment",
            booking_appointment_completed=False,
            speech_ai_text="Sorry, I was unable to book your appointment. Please try again.",
        )

    doctor_id = state.get("doctor_confirmed_id")
    doctor_name = state.get("doctor_confirmed_name", "the doctor")
    patient_id = state.get("identity_patient_id")
    appointment_type_id = state.get("mapping_appointment_type_id")
    patient_name = state.get("identity_user_name", "the patient")

    conversation_history = list(state.get("clarify_conversation_history") or [])

    context = await extract_appointment_context(conversation_history)
    reason_for_visit = context.get("reason_for_visit")
    notes = context.get("notes")
    instructions = context.get("instructions")

    try:
        payload = {
            "user_id": patient_id,
            "provider_id": doctor_id,
            "appointment_type_id": appointment_type_id,
            "patient_name": patient_name,
            "availability_slot_id": matched["id"],
            "scheduled_date": matched["date"],
            "scheduled_start_time": matched["start_time"],
            "scheduled_end_time": matched["end_time"],
            "status": AppointmentStatus.SCHEDULED,
            "booking_channel": BookingChannel.VOICE,
            "reason_for_visit": reason_for_visit,
            "notes": notes,
            "instructions": instructions,
            "is_active": True,
        }

        async with AsyncSessionLocal() as db:
            await insert_instance(Appointment, db, **payload)
            await change_slot_status(db=db, slot_id=matched["id"], new_status=SlotStatus.BOOKED)

    except Exception:
        logger.exception(
            "Failed to persist appointment for patient_id=%s, slot_id=%s.",
            patient_id,
            matched.get("id"),
        )
        return update_state(
            state,
            active_node="book_appointment",
            booking_appointment_completed=False,
            speech_ai_text="Sorry, I was unable to book your appointment. Please try again.",
        )

    confirmation_text = (
        f"Perfect! Your appointment with {doctor_name} is confirmed for "
        f"{matched['full_display']}. You'll receive a confirmation shortly."
    )

    conversation_history.append({"role": "assistant", "content": confirmation_text})

    return update_state(
        state,
        active_node="book_appointment",
        slot_booked_id=matched["id"],
        slot_booked_display=matched["full_display"],
        slot_stage="done",
        slot_selected=None,
        booking_reason_for_visit=reason_for_visit,
        booking_notes=notes,
        booking_instructions=instructions,
        clarify_conversation_history=conversation_history,
        booking_appointment_completed=True,
        speech_ai_text=confirmation_text,
    )