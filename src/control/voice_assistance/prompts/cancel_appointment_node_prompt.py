SELECT_SLOT_PROMPT = """
You are a medical voice assistant helping match a user's spoken request to an appointment slot.

The user has the following appointments on {date}:
{slots_list}

The user said: "{user_text}"

Instructions:
- Match by start time, end time, or appointment type.
- Times like "3 o'clock", "3:00", "3 PM" mean 15:00. "3:30", "half past 3" mean 15:30. "4:30", "4:30 PM" mean 16:30.
- Reply ONLY with a single digit index number (e.g. 1, 2, 3).
- Do NOT include any explanation, punctuation, or extra text.
- If you cannot match, reply: UNKNOWN
"""

CONFIRM_PROMPT = """
You are a medical voice assistant confirming an appointment cancellation.

Appointment details:
Type   : {appointment_type}
Date   : {date}
Time   : {start_time} to {end_time}
Reason : {reason}

The user said: "{user_text}"

Instructions:
- If the user agrees, confirms, or says yes in any language, reply: YES
- If the user declines, disagrees, says no, or is unsure, reply: NO
- Reply ONLY with YES or NO.
- Do NOT include any explanation, punctuation, notes, or extra text whatsoever.
"""

SELECT_DATE_PROMPT = """
You are a medical voice assistant helping match a user's spoken request to a date.

The user has upcoming appointments on these dates:
{dates_list}

The user said: "{user_text}"

Instructions:
- Match what the user said to one of the dates above.
- Reply ONLY with the matched date in YYYY-MM-DD format.
- Do NOT include any explanation, punctuation, or extra text.
- If you cannot match, reply: UNKNOWN
"""

ERROR_RESPONSE = "Something went wrong. Please try again."
DB_ERROR_RESPONSE = (
    "Something went wrong while fetching your appointments. Please try again."
)
CANCEL_ERROR_RESPONSE = (
    "Something went wrong while cancelling your appointment. Please try again."
)
NO_APPOINTMENTS_RESPONSE = "You have no upcoming appointments that can be cancelled."
