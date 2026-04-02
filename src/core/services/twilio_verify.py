import logging
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from fastapi import HTTPException, status
from src.config.settings import settings
from src.schemas.twilio_verify import (
    PhoneLookupResponse,
    SendOTPResponse,
    CheckOTPResponse,
    CallerIDResponse,
)

logger = logging.getLogger(__name__)

twilio_client = Client(settings.TWILIO_SID, settings.TWILIO_AUTH)
VERIFY_SID = settings.TWILIO_VERIFY_SERVICE_SID


async def lookup_phone_service(phone_number: str) -> PhoneLookupResponse:
    logger.info("Phone lookup requested", extra={"phone_number": phone_number})
    try:
        result = twilio_client.lookups.v2.phone_numbers(phone_number).fetch()
        logger.info(
            "Phone lookup successful",
            extra={
                "phone_number": result.phone_number,
                "valid": result.valid,
                "country_code": result.country_code,
            },
        )
        return PhoneLookupResponse(
            valid=result.valid,
            phone_number=result.phone_number,
            country_code=result.country_code,
            national_format=result.national_format,
            calling_country_code=result.calling_country_code,
        )
    except TwilioRestException as e:
        logger.warning(
            "Phone lookup failed",
            extra={"phone_number": phone_number, "twilio_error": e.msg, "twilio_code": e.code},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Twilio Lookup error: {e.msg}",
        )


async def send_otp_service(phone_number: str) -> SendOTPResponse:
    logger.info("OTP send requested", extra={"phone_number": phone_number})
    try:
        verification = twilio_client.verify.v2.services(VERIFY_SID).verifications.create(
            to=phone_number,
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
        return SendOTPResponse(
            message="OTP sent successfully",
            status=verification.status,
            to=verification.to,
        )
    except TwilioRestException as e:
        logger.error(
            "Failed to send OTP",
            extra={"phone_number": phone_number, "twilio_error": e.msg, "twilio_code": e.code},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to send OTP: {e.msg}",
        )


async def check_otp_service(phone_number: str, otp_code: str) -> CheckOTPResponse:
    logger.info("OTP check requested", extra={"phone_number": phone_number})
    try:
        check = twilio_client.verify.v2.services(VERIFY_SID).verification_checks.create(
            to=phone_number,
            code=otp_code,
        )
        if check.status == "approved":
            logger.info(
                "OTP verified successfully",
                extra={"phone_number": phone_number, "status": check.status},
            )
            return CheckOTPResponse(
                verified=True,
                message="Phone number verified successfully",
                phone_number=phone_number,
            )
        logger.warning(
            "OTP check failed — invalid or expired",
            extra={"phone_number": phone_number, "status": check.status},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP. Please try again.",
        )
    except TwilioRestException as e:
        logger.error(
            "OTP check encountered Twilio error",
            extra={"phone_number": phone_number, "twilio_error": e.msg, "twilio_code": e.code},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OTP check failed: {e.msg}",
        )


async def verify_caller_id_service(phone_number: str) -> CallerIDResponse:
    logger.info("Caller ID verification requested", extra={"phone_number": phone_number})
    try:
        validation = twilio_client.validation_requests.create(
            phone_number=phone_number,
            friendly_name=f"Verified: {phone_number}",
        )
        logger.info(
            "Caller ID validation initiated",
            extra={
                "phone_number": validation.phone_number,
                "validation_code": validation.validation_code,
                "friendly_name": validation.friendly_name,
            },
        )
        return CallerIDResponse(
            message="Twilio is calling the number now. Enter the code when prompted.",
            validation_code=validation.validation_code,
            phone_number=validation.phone_number,
            friendly_name=validation.friendly_name,
            account_sid=validation.account_sid,
        )
    except TwilioRestException as e:
        logger.error(
            "Caller ID verification failed",
            extra={"phone_number": phone_number, "twilio_error": e.msg, "twilio_code": e.code},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Caller ID verification failed: {e.msg}",
        )