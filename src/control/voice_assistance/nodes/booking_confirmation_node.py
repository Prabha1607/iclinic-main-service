"""
LangGraph node for sending booking confirmation emails in the iClinic voice assistance module.

After a successful appointment booking, builds and dispatches a plain-text
confirmation email to the patient. Email failures are logged and swallowed
so the pipeline continues uninterrupted.
"""
import logging

from fastapi_mail import FastMail, MessageSchema

from src.control.voice_assistance.config import conf

logger = logging.getLogger(__name__)


async def _send_confirmation_email(to_email: str, body: str) -> None:
    
    message = MessageSchema(
        subject="Your Appointment is Confirmed",
        recipients=[to_email],
        body=body,
        subtype="plain",
    )
    fm = FastMail(conf)
    await fm.send_message(message)


def _build_email_body(state: dict) -> str:
    
    doctor_name = state.get("doctor_confirmed_name", "your doctor")
    slot_display = state.get("slot_booked_display", "the scheduled time")
    reason = state.get("booking_reason_for_visit")
    instructions = state.get("booking_instructions")
    patient_name = state.get("identity_user_name", "Patient")

    lines = [
        f"Dear {patient_name},",
        "",
        "Your appointment has been successfully booked.",
        "",
        f"  Doctor  : {doctor_name}",
        f"  Slot    : {slot_display}",
    ]

    if reason:
        lines.append(f"  Reason  : {reason}")
    if instructions:
        lines.append(f"  Instructions : {instructions}")

    lines += [
        "",
        "Please arrive 10 minutes before your scheduled time.",
        "If you need to cancel, contact us as soon as possible.",
        "",
        "Best regards,",
        "The Appointments Team",
    ]

    return "\n".join(lines)


async def booking_confirmation_node(state: dict) -> dict:
    """Send an appointment confirmation email after a successful booking.

    Skips silently if no booked slot or recipient email is present in state.
    Email delivery failures are logged but do not raise, ensuring the pipeline
    continues regardless of mail transport issues.

    Args:
        state: The current pipeline state dict. Relevant keys:
            - slot_booked_id (str | int | None): ID of the booked slot; absence
              short-circuits the node.
            - identity_user_email (str | None): Recipient address; absence
              short-circuits the node.
            - All keys consumed by :func:`_build_email_body`.

    Returns:
        The unchanged state dict.
    """
    if not state.get("slot_booked_id"):
        logger.info("Skipping booking_confirmation_node: no slot_booked_id in state.")
        return state

    to_email = state.get("identity_user_email")

    if not to_email:
        logger.warning(
            "Skipping confirmation email: no identity_user_email found in state "
            "for slot_booked_id=%s.",
            state.get("slot_booked_id"),
        )
        return state

    try:
        await _send_confirmation_email(to_email, _build_email_body(state))
    except RuntimeError as e:
        logger.exception(
            "Failed to send confirmation email to %s for slot_booked_id=%s.",
            to_email,
            state.get("slot_booked_id"),
            extra={"error": str(e)},
        )

    return state