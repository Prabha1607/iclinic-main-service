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
from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import AppointmentStatus, BookingChannel, SlotStatus
from src.data.repositories.generic_crud import insert_instance, bulk_get_instance
from src.control.voice_assistance.utils.date_utils import (
    today_ist, now_time_ist, format_date, format_time,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def extract_appointment_context(conversation_history: list | str) -> dict:
    history_text = build_history_text(conversation_history)
    try:
        return await invokeLLM_json(
            system_prompt=EXTRACT_CONTEXT_PROMPT,
            user_prompt=f"Conversation:\n{history_text}",
        )
    except Exception:
        logger.warning(
            "Failed to extract appointment context; falling back to DEFAULT_CONTEXT.",
            exc_info=True,
        )
        return DEFAULT_CONTEXT


async def _fetch_alternate_slots(
    doctor_id: int,
    booked_date: str,
    booked_start_time: str,
) -> list[dict]:
    """
    Returns up to 3 alternate future slots for the doctor,
    excluding the slot that just got taken.
    Reuses the same DB pattern as booking_slot_selection_node.
    """
    try:
        from datetime import date as dt_date
        async with AsyncSessionLocal() as db:
            today    = today_ist()
            now_time = now_time_ist()
            slots = await bulk_get_instance(
                AvailableSlot, db, provider_id=doctor_id, is_active=True
            )
            alternates = []
            for s in slots:
                if s.status != SlotStatus.AVAILABLE:
                    continue
                if s.availability_date < today:
                    continue
                if s.availability_date == today and s.start_time <= now_time:
                    continue
                # Exclude the slot that was just taken
                if (
                    s.availability_date.isoformat() == booked_date
                    and s.start_time.strftime("%H:%M") == booked_start_time
                ):
                    continue
                alternates.append({
                    "date":         s.availability_date.isoformat(),
                    "start_time":   s.start_time.strftime("%H:%M"),
                    "date_display": format_date(s.availability_date),
                    "time_display": f"{format_time(s.start_time)} to {format_time(s.end_time)}",
                    "full_display": (
                        f"{format_date(s.availability_date)}, "
                        f"{format_time(s.start_time)} to {format_time(s.end_time)}"
                    ),
                })
            # Sort by date then time, return top 3
            alternates.sort(key=lambda x: (x["date"], x["start_time"]))
            return alternates[:3]
    except Exception as e:
        logger.warning(f"_fetch_alternate_slots: failed | doctor_id={doctor_id} | error={e}")
        return []


def _build_slot_taken_message(
    doctor_name: str,
    slot_display: str,
    alternates: list[dict],
) -> str:
    """
    Builds the AI response when a slot gets taken mid-booking.
    """
    if not alternates:
        return (
            f"I'm sorry, {slot_display} with {doctor_name} has just been taken by another patient. "
            "Unfortunately there are no other slots available right now. "
            "Please call us back shortly and we'll find something for you."
        )

    options = ", ".join(a["full_display"] for a in alternates)
    return (
        f"I'm sorry, {slot_display} with {doctor_name} was just booked by another patient "
        f"while we were processing yours. "
        f"The next available slots are: {options}. "
        "Which of these would work for you?"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN NODE
# ═══════════════════════════════════════════════════════════════════════════════

async def book_appointment_node(state: dict) -> dict:
    if state.get("slot_stage") != "ready_to_book":
        logger.info("Skipping book_appointment_node: slot_stage is not 'ready_to_book'.")
        return {**state, "active_node": "book_appointment", "booking_appointment_completed": False}

    matched = state.get("slot_selected")
    if not matched:
        logger.error("book_appointment_node called with no slot_selected in state.")
        return {**state, "active_node": "book_appointment", "booking_appointment_completed": False}

    # ── Parse date/time fields ─────────────────────────────────────────────────
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

    doctor_id           = state.get("doctor_confirmed_id")
    doctor_name         = state.get("doctor_confirmed_name", "the doctor")
    patient_id          = state.get("identity_patient_id")
    appointment_type_id = state.get("mapping_appointment_type_id")
    patient_name        = state.get("identity_user_name", "the patient")
    conversation_history = list(state.get("clarify_conversation_history") or [])

    # Keep string versions for alternate-slot lookup (before date/time got converted above)
    booked_date_iso  = matched["date"].isoformat() if isinstance(matched["date"], date) else matched["date"]
    booked_start_str = matched["start_time"].strftime("%H:%M") if isinstance(matched["start_time"], time_type) else matched["start_time"]

    context          = await extract_appointment_context(conversation_history)
    reason_for_visit = context.get("reason_for_visit")
    notes            = context.get("notes")
    instructions     = context.get("instructions")

    # ── Attempt to book ────────────────────────────────────────────────────────
    try:
        async with AsyncSessionLocal() as db:

            # ── Race-condition guard: re-check slot status inside the same session ──
            live_slots = await bulk_get_instance(
                AvailableSlot, db,
                id=matched["id"],
                is_active=True,
            )
            if not live_slots or live_slots[0].status != SlotStatus.AVAILABLE:
                raise _SlotTakenError()

            payload = {
                "user_id":               patient_id,
                "provider_id":           doctor_id,
                "appointment_type_id":   appointment_type_id,
                "patient_name":          patient_name,
                "availability_slot_id":  matched["id"],
                "scheduled_date":        matched["date"],
                "scheduled_start_time":  matched["start_time"],
                "scheduled_end_time":    matched["end_time"],
                "status":                AppointmentStatus.SCHEDULED,
                "booking_channel":       BookingChannel.VOICE,
                "reason_for_visit":      reason_for_visit,
                "notes":                 notes,
                "instructions":          instructions,
                "is_active":             True,
            }
            await insert_instance(Appointment, db, **payload)
            await change_slot_status(db=db, slot_id=matched["id"], new_status=SlotStatus.BOOKED)

    except _SlotTakenError:
        # ── Slot was grabbed by another user between selection and booking ─────
        logger.warning(
            f"book_appointment_node: slot already taken | "
            f"slot_id={matched['id']} doctor_id={doctor_id} patient_id={patient_id}"
        )
        alternates = await _fetch_alternate_slots(doctor_id, booked_date_iso, booked_start_str)
        ai_text    = _build_slot_taken_message(doctor_name, matched["full_display"], alternates)
        conversation_history.append({"role": "assistant", "content": ai_text})

        return update_state(
            state,
            active_node                      = "book_appointment",
            booking_appointment_completed    = False,
            # Reset slot selection so the graph routes back to booking_slot_selection
            slot_stage                       = "ask_date",
            slot_selected                    = None,
            slot_selected_display            = None,
            slot_selected_start_time         = None,
            slot_selected_end_time           = None,
            slot_chosen_date                 = None,
            slot_chosen_period               = None,
            slot_time_hint                   = None,
            booking_slot_selection_completed = False,
            clarify_conversation_history     = conversation_history,
            speech_ai_text                   = ai_text,
        )

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

    # ── Success ────────────────────────────────────────────────────────────────
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


# ── Sentinel exception (internal use only) ────────────────────────────────────
class _SlotTakenError(Exception):
    pass