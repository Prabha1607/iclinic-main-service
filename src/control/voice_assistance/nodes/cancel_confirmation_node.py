import logging

from fastapi_mail import FastMail, MessageSchema

from src.control.voice_assistance.config import conf

logger = logging.getLogger(__name__)


async def _send_cancellation_email(to_email: str, body: str) -> None:
    
    message = MessageSchema(
        subject="Your Appointment has been Cancelled",
        recipients=[to_email],
        body=body,
        subtype="plain",
    )
    fm = FastMail(conf)
    await fm.send_message(message)


def _build_cancellation_email_body(state: dict) -> str:
    
    appointment = state.get("cancellation_appointment") or {}
    patient_name = state.get("identity_user_name", "Patient")
    appointment_type = appointment.get("type_name", "your appointment")
    date = appointment.get("date", "N/A")
    start_time = appointment.get("start_time", "N/A")
    end_time = appointment.get("end_time", "N/A")
    reason = appointment.get("reason")

    lines = [
        f"Dear {patient_name},",
        "",
        "Your appointment has been successfully cancelled.",
        "",
        f"  Appointment Type : {appointment_type}",
        f"  Date             : {date}",
        f"  Time             : {start_time} to {end_time}",
    ]

    if reason and reason != "Not specified":
        lines.append(f"  Reason           : {reason}")

    lines += [
        "",
        "If this was a mistake or you wish to rebook, please contact us.",
        "",
        "Best regards,",
        "The Appointments Team",
    ]

    return "\n".join(lines)


async def cancel_confirmation_node(state: dict) -> dict:
    """Send an appointment cancellation confirmation email after a successful cancellation.

    Skips silently if the cancellation has not been confirmed or if no recipient
    email is present in state. Email delivery failures are logged but do not raise,
    ensuring the pipeline continues regardless of mail transport issues.

    Args:
        state: The current pipeline state dict. Relevant keys:
            - cancellation_confirmed (bool | None): Must be truthy to proceed.
            - identity_user_email (str | None): Recipient address; absence
              short-circuits the node.
            - All keys consumed by :func:`_build_cancellation_email_body`.

    Returns:
        The unchanged state dict.
    """
    if not state.get("cancellation_confirmed"):
        logger.info("Skipping cancel_confirmation_node: cancellation_confirmed is not set.")
        return state

    email = state.get("identity_user_email")
    if not email:
        logger.warning(
            "Skipping cancellation email: no identity_user_email found in state.",
        )
        return state

    try:
        await _send_cancellation_email(email, _build_cancellation_email_body(state))
    except Exception:
        logger.exception(
            "Failed to send cancellation email to %s.",
            email,
        )

    return state