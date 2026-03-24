import logging

from fastapi import APIRouter, HTTPException, status
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from src.schemas.twilio_verify import OTPVerifyRequest, PhoneRequest
from src.config.settings import settings

logger = logging.getLogger(__name__)

twilio_client = Client(settings.TWILIO_SID, settings.TWILIO_AUTH)
VERIFY_SID = settings.TWILIO_VERIFY_SERVICE_SID

router = APIRouter(prefix="/verify", tags=["Twilio Verification"])


@router.post("/lookup", summary="Validate phone number format & existence")
async def lookup_phone(body: PhoneRequest):
    """
    Validate the format and existence of a phone number via Twilio Lookups V2.

    Queries the Twilio Lookups API to confirm whether the supplied phone number
    is a real, dialable number and returns normalised carrier metadata.

    Args:
        body: Request payload containing the ``phone_number`` to look up.

    Returns:
        dict: Lookup result with the following fields:
            - ``valid`` (bool): Whether the number is a valid, active number.
            - ``phone_number`` (str): E.164-formatted phone number.
            - ``country_code`` (str): ISO 3166-1 alpha-2 country code.
            - ``national_format`` (str): Locally formatted number string.
            - ``calling_country_code`` (str): International dialling prefix.

    Raises:
        HTTPException 400: When Twilio rejects the number or the lookup fails.
    """
    logger.info("Phone lookup requested", extra={"phone_number": body.phone_number})
    try:
        result = twilio_client.lookups.v2.phone_numbers(body.phone_number).fetch()
        logger.info(
            "Phone lookup successful",
            extra={
                "phone_number": result.phone_number,
                "valid": result.valid,
                "country_code": result.country_code,
            },
        )
        return {
            "valid":                result.valid,
            "phone_number":         result.phone_number,
            "country_code":         result.country_code,
            "national_format":      result.national_format,
            "calling_country_code": result.calling_country_code,
        }
    except TwilioRestException as e:
        logger.warning(
            "Phone lookup failed",
            extra={"phone_number": body.phone_number, "twilio_error": e.msg, "twilio_code": e.code},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Twilio Lookup error: {e.msg}",
        )


@router.post("/send-otp", status_code=status.HTTP_200_OK, summary="Send OTP to phone number via SMS")
async def send_otp(body: PhoneRequest):
    """
    Send a one-time password to a phone number via SMS using Twilio Verify V2.

    Creates a new verification request against the configured Verify service.
    Twilio generates and delivers the OTP; the caller is responsible for
    collecting it from the user and submitting it to ``/check-otp``.

    Args:
        body: Request payload containing the ``phone_number`` to send the OTP to.

    Returns:
        dict: Verification initiation result with the following fields:
            - ``message`` (str): Human-readable confirmation string.
            - ``status`` (str): Twilio verification status (e.g. ``"pending"``).
            - ``to`` (str): E.164-formatted destination number.

    Raises:
        HTTPException 400: When Twilio fails to dispatch the OTP.
    """
    logger.info("OTP send requested", extra={"phone_number": body.phone_number})
    try:
        verification = twilio_client.verify.v2.services(VERIFY_SID).verifications.create(
            to=body.phone_number,
            channel="sms",
        )
        logger.info(
            "OTP sent successfully",
            extra={
                "phone_number": verification.to,
                "status": verification.status,
                "verify_sid": VERIFY_SID,
            },
        )
        return {
            "message": "OTP sent successfully",
            "status":  verification.status,
            "to":      verification.to,
        }
    except TwilioRestException as e:
        logger.error(
            "Failed to send OTP",
            extra={"phone_number": body.phone_number, "twilio_error": e.msg, "twilio_code": e.code},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to send OTP: {e.msg}",
        )


@router.post("/check-otp", status_code=status.HTTP_200_OK, summary="Verify OTP entered by user")
async def check_otp(body: OTPVerifyRequest):
    """
    Verify a one-time password submitted by the user against Twilio Verify V2.

    Submits the user-supplied code to the Twilio Verify service for the given
    phone number. Returns a verified confirmation on success, or raises an
    error if the code is wrong or has expired.

    Args:
        body: Request payload containing ``phone_number`` and ``otp_code``.

    Returns:
        dict: Verification outcome with the following fields:
            - ``verified`` (bool): ``True`` when the OTP is accepted.
            - ``message`` (str): Human-readable confirmation string.
            - ``phone_number`` (str): The verified E.164-formatted number.

    Raises:
        HTTPException 400: When the OTP is invalid, expired, or Twilio returns
                           an error during the verification check.
    """
    logger.info("OTP check requested", extra={"phone_number": body.phone_number})
    try:
        check = twilio_client.verify.v2.services(VERIFY_SID).verification_checks.create(
            to=body.phone_number,
            code=body.otp_code,
        )
        if check.status == "approved":
            logger.info(
                "OTP verified successfully",
                extra={"phone_number": body.phone_number, "status": check.status},
            )
            return {
                "verified":     True,
                "message":      "Phone number verified successfully",
                "phone_number": body.phone_number,
            }
        logger.warning(
            "OTP check failed — invalid or expired",
            extra={"phone_number": body.phone_number, "status": check.status},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP. Please try again.",
        )
    except TwilioRestException as e:
        logger.error(
            "OTP check encountered Twilio error",
            extra={"phone_number": body.phone_number, "twilio_error": e.msg, "twilio_code": e.code},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OTP check failed: {e.msg}",
        )


@router.post("/caller-id", status_code=status.HTTP_200_OK, summary="Register a phone number as a Twilio Caller ID")
async def verify_caller_id(body: PhoneRequest):
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
        dict: Validation request details with the following fields:
            - ``message`` (str): Instruction to enter the code when prompted.
            - ``validation_code`` (str): Code that Twilio will read over the call.
            - ``phone_number`` (str): E.164-formatted number being registered.
            - ``friendly_name`` (str): Label attached to the Caller ID record.
            - ``account_sid`` (str): Twilio account that owns the request.

    Raises:
        HTTPException 400: When Twilio rejects the validation request.
    """
    logger.info("Caller ID verification requested", extra={"phone_number": body.phone_number})
    try:
        validation = twilio_client.validation_requests.create(
            phone_number=body.phone_number,
            friendly_name=f"Verified: {body.phone_number}",
        )
        logger.info(
            "Caller ID validation initiated",
            extra={
                "phone_number": validation.phone_number,
                "validation_code": validation.validation_code,
                "friendly_name": validation.friendly_name,
            },
        )
        return {
            "message":         "Twilio is calling the number now. Enter the code when prompted.",
            "validation_code": validation.validation_code,
            "phone_number":    validation.phone_number,
            "friendly_name":   validation.friendly_name,
            "account_sid":     validation.account_sid,
        }
    except TwilioRestException as e:
        logger.error(
            "Caller ID verification failed",
            extra={"phone_number": body.phone_number, "twilio_error": e.msg, "twilio_code": e.code},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Caller ID verification failed: {e.msg}",
        )