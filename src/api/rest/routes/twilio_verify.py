import os

from fastapi import APIRouter, HTTPException, status
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from src.config.settings import settings
from src.schemas.twilio_verify import OTPVerifyRequest, PhoneRequest

ACCOUNT_SID = settings.TWILIO_SID
AUTH_TOKEN = settings.TWILIO_AUTH
twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN)
VERIFY_SID = os.getenv("TWILIO_VERIFY_SERVICE_SID")

router = APIRouter(prefix="/verify", tags=["Twilio Verification"])


@router.post("/lookup", summary="Validate phone number format & existence")
async def lookup_phone(body: PhoneRequest):

    try:
        result = twilio_client.lookups.v2.phone_numbers(body.phone_number).fetch()

        return {
            "valid": result.valid,
            "phone_number": result.phone_number,
            "country_code": result.country_code,
            "national_format": result.national_format,
            "calling_country_code": result.calling_country_code,
        }

    except TwilioRestException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Twilio Lookup error: {e.msg}",
        )


@router.post(
    "/send-otp",
    status_code=status.HTTP_200_OK,
    summary="Send OTP to phone number (registration step 1)",
)
async def send_otp(body: PhoneRequest):

    try:
        verification = twilio_client.verify.v2.services(
            VERIFY_SID
        ).verifications.create(to=body.phone_number, channel="sms")

        return {
            "message": "OTP sent successfully",
            "status": verification.status,
            "to": verification.to,
        }

    except TwilioRestException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to send OTP: {e.msg}",
        )


@router.post(
    "/check-otp",
    status_code=status.HTTP_200_OK,
    summary="Check OTP entered by user (registration step 2)",
)
async def check_otp(body: OTPVerifyRequest):

    try:
        check = twilio_client.verify.v2.services(VERIFY_SID).verification_checks.create(
            to=body.phone_number, code=body.otp_code
        )

        if check.status == "approved":
            return {
                "verified": True,
                "message": "Phone number verified successfully ",
                "phone_number": body.phone_number,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP. Please try again.",
            )

    except TwilioRestException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"OTP check failed: {e.msg}"
        )


@router.post(
    "/caller-id",
    status_code=status.HTTP_200_OK,
    summary="Register a phone number as a Twilio Caller ID",
)
async def verify_caller_id(body: PhoneRequest):

    try:
        validation = twilio_client.validation_requests.create(
            phone_number=body.phone_number,
            friendly_name=f"Verified: {body.phone_number}",
        )

        return {
            "message": "Twilio is calling the number now. Enter the code when prompted.",
            "validation_code": validation.validation_code,
            "phone_number": validation.phone_number,
            "friendly_name": validation.friendly_name,
            "account_sid": validation.account_sid,
        }

    except TwilioRestException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Caller ID verification failed: {e.msg}",
        )
