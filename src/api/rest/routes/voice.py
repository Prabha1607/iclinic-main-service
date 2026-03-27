import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from twilio.twiml.voice_response import VoiceResponse
from src.api.rest.dependencies import get_current_user, get_db
from src.config.settings import settings
from src.control.voice_assistance.graph import build_call_graph, build_response_graph
from src.control.voice_assistance.session_store import (
    delete_session,
    get_session,
    set_session,
)
from src.control.voice_assistance.utils.state_utils import fresh_state
from src.control.voice_assistance.utils.twilio_utils import make_gather, say
from src.core.services.appointment_types import get_appointment_types

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["Voice Assistance"])

call_graph = build_call_graph()
response_graph = build_response_graph()

FALLBACK_TEXT = "I am sorry, something went wrong. Please try again."
NO_SPEECH_TEXT = "Could you please repeat that?"
RETRY_TEXT = "Sorry, I did not catch that. Please go ahead and speak."
TIMEOUT_TEXT = "I still could not hear you. Thank you for calling. Goodbye."

_startup_done = False




def _build_appointment_types(appointment_types: list) -> dict:
    return {at.id: [at.name, at.description] for at in appointment_types}


def _is_call_complete(result: dict) -> bool:
    identity_confirmation_completed = result.get("identity_confirmation_completed", False)
    identity_confirmed_user = result.get("identity_confirmed_user", False)

    return (
        (identity_confirmation_completed and not identity_confirmed_user)
        or result.get("slot_booked_id") is not None
        or result.get("cancellation_complete", False)
    )


def _build_twiml(ai_text: str, emergency: bool, call_complete: bool) -> str:
    twiml = VoiceResponse()

    if emergency:
        say(twiml, ai_text)
        twiml.dial(settings.EMERGENCY_FORWARD_NUMBER)
        return str(twiml)

    if call_complete:
        say(twiml, ai_text)
        twiml.hangup()
        return str(twiml)

    gather = make_gather()
    say(gather, ai_text)
    twiml.append(gather)

    retry = make_gather()
    say(retry, RETRY_TEXT)
    twiml.append(retry)

    say(twiml, TIMEOUT_TEXT)
    twiml.hangup()

    return str(twiml)


@router.post("/make-call")
async def make_call(
    request: Request,
    to_number: str = Query(...),
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Initiate an outbound voice call to the specified number.

    Fetches available appointment types, builds the initial call state, invokes
    the call graph, and persists the resulting session for subsequent voice
    interactions.

    Args:
        request:      Incoming HTTP request (used to extract the Authorization header).
        to_number:    Destination phone number passed as a query parameter.
        current_user: Authenticated user payload injected by ``get_current_user``.
        db:           Async database session injected by ``get_db``.

    Returns:
        dict: ``{"status": "call_placed", "call_sid": <sid>}`` on success,
              or ``{"status": "error", "detail": <reason>}`` on failure.

    Raises:
        HTTPException 404: When no appointment types are found in the database.
        HTTPException 400: When the Authorization header is missing.
        HTTPException 500: When appointment-type retrieval fails unexpectedly.
    """
    try:
        appointment_types = await get_appointment_types(db)
        if not appointment_types:
            logger.warning("No appointment types found in database")
            raise HTTPException(status_code=404, detail="appointment_types not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch appointment types", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Internal error")

    credential = request.headers.get("Authorization")
    if credential is None:
        logger.warning("Missing Authorization header on make-call request")
        return JSONResponse(
            status_code=400,
            content={"detail": "Bearer authorization required"},
        )

    _, _, token = credential.partition(" ")

    initial_state = fresh_state(
        call_to_number=to_number,
        identity_patient_id=current_user.get("id"),
        token=token,
        appointment_types=_build_appointment_types(appointment_types),
        identity_user_name=current_user.get("name"),
        identity_user_email=current_user.get("email"),
        identity_user_phone=current_user.get("phone_number"),
    )

    try:
        result = await call_graph.ainvoke(initial_state)
    except Exception as e:
        logger.error("Response graph invocation failed", exc_info=True, extra={"call_sid": call_sid, "error": str(e)})
        return {"status": "error", "detail": "Failed to place call"}

    if result.get("speech_error"):
        logger.error(
            "Call graph returned a speech error",
            extra={"to_number": to_number, "error": result["speech_error"]},
        )
        return {"status": "error", "detail": result["speech_error"]}

    call_sid = result.get("call_sid")

    try:
        await set_session(call_sid, {**result, "call_to_number": to_number, "call_sid": call_sid})
    except Exception as e:
        logger.error("Failed to persist call session", extra={"call_sid": call_sid, "error": str(e)})
        return {"status": "error", "detail": "Failed to initialize session"}

    logger.info("Outbound call placed successfully", extra={"call_sid": call_sid, "to_number": to_number})
    return {"status": "call_placed", "call_sid": call_sid}


@router.post("/voice-response")
async def voice_response(request: Request):
    """
    Handle an inbound Twilio voice webhook for an in-progress call.

    Parses the Twilio form payload, loads the existing session state, appends
    the caller's transcribed speech, invokes the response graph, and returns
    a TwiML document instructing Twilio how to continue the call. Terminates
    the session and hangs up when the conversation is deemed complete or an
    emergency is detected.

    Args:
        request: Incoming HTTP request containing the Twilio form payload
                 (``CallSid``, ``SpeechResult``, ``To``, etc.).

    Returns:
        Response: An ``application/xml`` TwiML response that either gathers
                  further speech, dials an emergency number, or hangs up.
    """

    try:
        form = await request.form()
        call_sid = form.get("CallSid", "unknown")
        speech = form.get("SpeechResult")
    except Exception as e:
        logger.error("Failed to parse Twilio form payload", extra={"error": str(e)})
        return Response(
            content=_build_twiml(FALLBACK_TEXT, False, True),
            media_type="application/xml",
        )

    logger.info("Voice webhook received", extra={"call_sid": call_sid, "has_speech": bool(speech)})

    try:
        state = await get_session(call_sid) or fresh_state(
            call_to_number=form.get("To"), call_sid=call_sid
        )
        state["speech_user_text"] = speech.strip() if speech else None
    except Exception as e:
        logger.error("Failed to load call session", extra={"call_sid": call_sid, "error": str(e)})
        return Response(
            content=_build_twiml(FALLBACK_TEXT, False, True),
            media_type="application/xml",
        )

    try:
        result = await response_graph.ainvoke(state)
    except Exception as e:
        logger.error("Response graph invocation failed", extra={"call_sid": call_sid, "error": str(e)})
        result = {**state, "speech_ai_text": FALLBACK_TEXT}

    ai_text = result.get("speech_ai_text") or NO_SPEECH_TEXT
    emergency = result.get("mapping_emergency", False)
    call_complete = _is_call_complete(result)

    if emergency:
        logger.warning("Emergency detected — forwarding call", extra={"call_sid": call_sid})

    if call_complete:
        logger.info("Call complete — terminating session", extra={"call_sid": call_sid})

    try:
        if call_complete:
            await delete_session(call_sid)
        else:
            await set_session(call_sid, result)
    except Exception as e:
        logger.warning(
            "Failed to update session state after response",
            extra={"call_sid": call_sid, "error": str(e)},
        )

    return Response(
        content=_build_twiml(ai_text, emergency, call_complete),
        media_type="application/xml",
    )