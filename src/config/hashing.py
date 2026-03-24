import logging

from passlib.context import CryptContext
from passlib.exc import UnknownHashError

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def get_password_hash(password: str) -> str:
    logger.info("Hashing password")
    try:
        hashed = pwd_context.hash(password)
        logger.info("Password hashed successfully")
        return hashed
    except Exception as e:
        logger.error("Failed to hash password", extra={"error": str(e)})
        raise


def verify_password(plain_password: str, hashed_password: str) -> bool:
    logger.info("Verifying password")
    try:
        is_valid = pwd_context.verify(plain_password, hashed_password)
        if is_valid:
            logger.info("Password verification succeeded")
        else:
            logger.warning("Password verification failed — incorrect password")
        return is_valid
    except UnknownHashError as e:
        logger.error("Password verification failed — unrecognised hash format", extra={"error": str(e)})
        raise
    except Exception as e:
        logger.error("Unexpected error during password verification", extra={"error": str(e)})
        raise