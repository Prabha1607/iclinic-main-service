"""
Password hashing and verification utilities for the iClinic main service.

Provides Argon2-backed helpers for securely hashing plain-text passwords
and verifying them against stored hashes using passlib.
"""
import logging

from passlib.context import CryptContext
from passlib.exc import UnknownHashError

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """
    Hash a plain-text password using Argon2.

    Args:
        password: The plain-text password to hash.

    Returns:
        str: The Argon2-hashed password string.

    Raises:
        Exception: Re-raises any error encountered during hashing.
    """
    logger.info("Hashing password")
    try:
        hashed = pwd_context.hash(password)
        logger.info("Password hashed successfully")
        return hashed
    except RuntimeError as e:
        logger.exception("Failed to hash password", extra={"error": str(e)})
        raise


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a stored Argon2 hash.

    Args:
        plain_password:   The plain-text password supplied by the user.
        hashed_password:  The stored Argon2 hash to verify against.

    Returns:
        bool: ``True`` if the password matches the hash, ``False`` otherwise.

    Raises:
        UnknownHashError: When the stored hash format is not recognised by passlib.
        Exception: Re-raises any other unexpected error during verification.
    """
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
    except RuntimeError as e:
        logger.exception("Unexpected error during password verification", extra={"error": str(e)})
        raise