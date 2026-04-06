"""
Application settings for the iClinic main service.

Loads and validates all environment variables required by the service
using pydantic-settings, sourcing values from the ``.env`` file.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Centralised configuration for the iClinic main service.

    All fields are populated from environment variables or the ``.env`` file.
    Covers database, authentication, third-party integrations (Twilio, Groq,
    Deepgram), email, voice assistance, and inter-service communication.
    """

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: str
    DATABASE_URL: str

    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    ALGORITHM: str
    ACCESS_SECRET_KEY: str
    REFRESH_SECRET_KEY: str

    GROQ_API_KEYS: str
    DEEPGRAM_API_KEY: str
    TWILIO_SID: str
    TWILIO_AUTH: str
    TWILIO_NUMBER: str
    MY_PHONE: str
    PUBLIC_BASE_URL: str

    VOICE: str
    LANGUAGE: str
    SPEECH_TIMEOUT: str
    ACTION_ON_EMPTY_RESULT: str
    GATHER_TIMEOUT: int

    SPEAKING_RATE: str
    SESSION_TTL_SECONDS: int

    EMAIL_USERNAME: str
    EMAIL_PASSWORD: str
    EMAIL_FROM: str
    EMAIL_PORT: int
    EMAIL_SERVER: str
    EMAIL_STARTTLS: bool
    EMAIL_SSL_TLS: bool
    EMAIL_USE_CREDENTIALS: bool

    EMERGENCY_FORWARD_NUMBER: str
    TWILIO_VERIFY_SERVICE_SID: str

    AUTH_SERVICE_URL: str

    @property
    def groq_keys_list(self) -> list[str]:
        """
        Parse the comma-separated ``GROQ_API_KEYS`` string into a list.

        Returns:
            list[str]: Individual Groq API key strings with whitespace stripped.
        """
        return [k.strip() for k in self.GROQ_API_KEYS.split(",")]

    class Config:
        """Pydantic configuration — specifies the ``.env`` file as the settings source."""

        env_file = ".env"


settings = Settings()