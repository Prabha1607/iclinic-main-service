"""
REST route handlers for Twilio phone verification in the iClinic main service.

Exposes endpoints for phone number lookup, OTP dispatch and verification,
and Twilio Caller ID registration.
"""
import logging

from fastapi import APIRouter, status

from src.schemas.twilio_verify import (
    CallerIDResponse,
    CheckOTPResponse,
    OTPVerifyRequest,
    PhoneLookupResponse,
    PhoneRequest,
    SendOTPResponse,
)
from src.core.services.twilio_verify import (
    check_otp_service,
    lookup_phone_service,
    send_otp_service,
    verify_caller_id_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verify", tags=["Twilio Verification"])


@router.post("/lookup", response_model=PhoneLookupResponse, summary="Validate phone number format & existence")
async def lookup_phone(body: PhoneRequest) -> PhoneLookupResponse:
    """
    Validate the format and existence of a phone number via Twilio Lookups V2.

    Queries the Twilio Lookups API to confirm whether the supplied phone number
    is a real, dialable number and returns normalised carrier metadata.

    Args:
        body: Request payload containing the ``phone_number`` to look up.

    Returns:
        PhoneLookupResponse: Lookup result with validity flag, E.164 number,
        country code, national format, and calling country code.

    Raises:
        HTTPException 400: When Twilio rejects the number or the lookup fails.
    """
    return await lookup_phone_service(phone_number=body.phone_number)


@router.post("/send-otp", response_model=SendOTPResponse, status_code=status.HTTP_200_OK, summary="Send OTP to phone number via SMS")
async def send_otp(body: PhoneRequest) -> SendOTPResponse:
    """
    Send a one-time password to a phone number via SMS using Twilio Verify V2.

    Creates a new verification request against the configured Verify service.
    Twilio generates and delivers the OTP; the caller is responsible for
    collecting it from the user and submitting it to ``/check-otp``.

    Args:
        body: Request payload containing the ``phone_number`` to send the OTP to.

    Returns:
        SendOTPResponse: Verification initiation result with a confirmation
        message, Twilio status (e.g. ``"pending"``), and destination number.

    Raises:
        HTTPException 400: When Twilio fails to dispatch the OTP.
    """
    return await send_otp_service(phone_number=body.phone_number)


@router.post("/check-otp", response_model=CheckOTPResponse, status_code=status.HTTP_200_OK, summary="Verify OTP entered by user")
async def check_otp(body: OTPVerifyRequest) -> CheckOTPResponse:
    """
    Verify a one-time password submitted by the user against Twilio Verify V2.

    Submits the user-supplied code to the Twilio Verify service for the given
    phone number. Returns a verified confirmation on success, or raises an
    error if the code is wrong or has expired.

    Args:
        body: Request payload containing ``phone_number`` and ``otp_code``.

    Returns:
        CheckOTPResponse: Verification outcome with a verified flag, confirmation
        message, and the verified E.164-formatted phone number.

    Raises:
        HTTPException 400: When the OTP is invalid, expired, or Twilio returns
                           an error during the verification check.
    """
    return await check_otp_service(phone_number=body.phone_number, otp_code=body.otp_code)


@router.post("/caller-id", response_model=CallerIDResponse, status_code=status.HTTP_200_OK, summary="Register a phone number as a Twilio Caller ID")
async def verify_caller_id(body: PhoneRequest) -> CallerIDResponse:
    """
    Register a phone number as a verified Twilio Caller ID via an outbound call.

    Submits a validation request to Twilio, which places an automated call to
    the supplied number and reads out a short validation code. The caller must
    enter that code on their keypad to complete registration. The validation
    code is returned in the response so it can be displayed to the user before
    the call arrives.

    Args:
        body: Request payload containing the ``phone_number`` to register.

    Returns:
        CallerIDResponse: Validation request details with an instruction message,
        validation code, E.164-formatted number, friendly name, and account SID.

    Raises:
        HTTPException 400: When Twilio rejects the validation request.
    """
    return await verify_caller_id_service(phone_number=body.phone_number)