from sqlalchemy import Column, Integer, DateTime, ForeignKey, Boolean, Date, Time, Text, Enum, UniqueConstraint, func
from sqlalchemy.orm import relationship
from src.data.models.postgres.ENUM import SlotStatus
from src.data.clients.postgres_client import Base


class AvailableSlot(Base):
    __tablename__ = "available_slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    availability_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    status = Column(Enum(SlotStatus), default=SlotStatus.AVAILABLE,
                    server_default="AVAILABLE", nullable=False)

    created_by = Column(Integer, ForeignKey("users.id"))
    notes = Column(Text)

    is_active = Column(Boolean, default=True, server_default="true", nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    provider = relationship("User", foreign_keys=[
                            provider_id], backref="available_slots")

    __table_args__ = (
        UniqueConstraint('provider_id', 'availability_date', 'start_time',
                         'end_time', name='unique_available_slot'),
    )
