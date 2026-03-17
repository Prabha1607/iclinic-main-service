from uuid import UUID


def to_uuid(value: str) -> UUID:
    return UUID(value)
