import re
from pydantic import BaseModel, field_validator


class PhoneRequest(BaseModel):
    phone_number: str


class PhoneLookupResponse(BaseModel):
    valid: bool
    phone_number: str
    country_code: str
    national_format: str
    calling_country_code: str


class SendOTPResponse(BaseModel):
    message: str
    status: str
    to: str


class CheckOTPResponse(BaseModel):
    verified: bool
    message: str
    phone_number: str


class CallerIDResponse(BaseModel):
    message: str
    validation_code: str
    phone_number: str
    friendly_name: str
    account_sid: str


class OTPVerifyRequest(BaseModel):
    phone_number: str
    otp_code: str

    @field_validator("otp_code")
    @classmethod
    def must_be_6_digits(cls, v: str) -> str:
        if not re.fullmatch(r"\d{6}", v):
            raise ValueError("OTP must be exactly 6 digits")
        return v

