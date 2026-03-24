import re
from pydantic import BaseModel, field_validator

class PhoneRequest(BaseModel):
    phone_number: str   


class OTPVerifyRequest(BaseModel):
    phone_number: str
    otp_code: str

    @field_validator("otp_code")
    @classmethod
    def must_be_6_digits(cls, v: str) -> str:
        if not re.fullmatch(r"\d{6}", v):
            raise ValueError("OTP must be exactly 6 digits")
        return v

