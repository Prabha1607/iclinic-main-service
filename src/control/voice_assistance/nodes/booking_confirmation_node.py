from fastapi_mail import FastMail, MessageSchema

from src.control.voice_assistance.config import conf


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
    print("[booking_confirmation_node] -----------------------------")

    if not state.get("slot_booked_id"):
        return state

    to_email = state.get("identity_user_email")

    if not to_email:
        return state

    try:
        await _send_confirmation_email(to_email, _build_email_body(state))
    except Exception as e:
        print(f"[booking_confirmation_node] Failed to send confirmation email: {e}")

    return state
