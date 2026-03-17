from fastapi_mail import ConnectionConfig

from src.config.settings import settings

conf = ConnectionConfig(
    MAIL_USERNAME=settings.EMAIL_USERNAME,
    MAIL_PASSWORD=settings.EMAIL_PASSWORD,
    MAIL_FROM=settings.EMAIL_FROM,
    MAIL_PORT=settings.EMAIL_PORT,
    MAIL_SERVER=settings.EMAIL_SERVER,
    MAIL_STARTTLS=settings.EMAIL_STARTTLS,
    MAIL_SSL_TLS=settings.EMAIL_SSL_TLS,
    USE_CREDENTIALS=settings.EMAIL_USE_CREDENTIALS,
)
