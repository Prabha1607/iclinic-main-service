import json
import traceback

from src.control.voice_assistance.models import get_llama1
from src.control.voice_assistance.prompts.book_appointment_node_prompt import (
    DEFAULT_CONTEXT,
    EXTRACT_CONTEXT_PROMPT,
)
from src.control.voice_assistance.utils import clear_markdown, update_state
from src.core.services.available_slots import change_slot_status
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.ENUM import AppointmentStatus, BookingChannel, SlotStatus
from src.data.repositories.generic_crud import insert_instance


def _build_history_text(conversation_history: list | str) -> str:
    if not isinstance(conversation_history, list):
        return str(conversation_history)

    lines = []

    for turn in conversation_history:
        if isinstance(turn, dict):
            role = turn.get("role", "unknown").capitalize()
            text = turn.get("content", "")

        elif isinstance(turn, (list, tuple)) and len(turn) == 2:
            role, text = turn[0].capitalize(), turn[1]

        else:
            continue

        lines.append(f"{role}: {text}")

    return "\n".join(lines)


async def extract_appointment_context(conversation_history: list | str) -> dict:
    history_text = _build_history_text(conversation_history)

    try:
        llm = get_llama1()
        response = await llm.ainvoke(
            [
                ("system", EXTRACT_CONTEXT_PROMPT),
                ("human", f"Conversation:\n{history_text}"),
            ]
        )
        parsed = json.loads(clear_markdown(response.content.strip()))
        return parsed

    except Exception:
        return DEFAULT_CONTEXT


async def book_appointment_node(state: dict) -> dict:
    print("\n[book_appointment_node] --------------------------------")

    if state.get("slot_stage") != "ready_to_book":
        print("[SKIP] Slot stage not ready")
        return {**state, "booking_appointment_completed": False}

    matched = state.get("slot_selected")
    doctor_id = state.get("doctor_confirmed_id")
    doctor_name = state.get("doctor_confirmed_name", "the doctor")

    patient_id = state.get("identity_patient_id")
    appointment_type_id = state.get("mapping_appointment_type_id")
    patient_name = state.get("identity_user_name", "the patient")

    conversation_history = list(state.get("clarify_conversation_history") or [])

    if not matched:
        print("[ERROR] No slot selected")
        return {**state, "booking_appointment_completed": False}

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

        print(json.dumps(payload, indent=2, default=str))

        async with AsyncSessionLocal() as db:
            await insert_instance(Appointment, db, **payload)
            await change_slot_status(
                db=db, slot_id=matched["id"], new_status=SlotStatus.BOOKED
            )

    except Exception:
        traceback.print_exc()
        return update_state(
            state,
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
