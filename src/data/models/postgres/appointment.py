from sqlalchemy import Column, Integer, DateTime, ForeignKey, Boolean, Date, Time, Text, Enum, String, func
from sqlalchemy.orm import relationship
from src.data.models.postgres.ENUM import AppointmentStatus, BookingChannel
from src.data.clients.postgres_client import Base


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    provider_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    appointment_type_id = Column(Integer, ForeignKey(
        "appointment_types.id"), nullable=False)
    availability_slot_id = Column(Integer, ForeignKey(
        "available_slots.id"), nullable=False)

    patient_name = Column(String(150), nullable=False)

    scheduled_date = Column(Date, nullable=False)
    scheduled_start_time = Column(Time, nullable=False)
    scheduled_end_time = Column(Time, nullable=False)

    status = Column(
        Enum(AppointmentStatus),
        default=AppointmentStatus.SCHEDULED,
        server_default="SCHEDULED",
        nullable=False
    )

    reason_for_visit = Column(Text)
    notes = Column(Text)

    booking_channel = Column(Enum(BookingChannel))
    instructions = Column(Text)

    cancelled_at = Column(DateTime(timezone=True))
    cancellation_reason = Column(Text)

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

    # relationships
    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="booked_appointments"
    )

    provider = relationship(
        "User",
        foreign_keys=[provider_id],
        back_populates="provider_appointments"
    )

    appointment_type = relationship("AppointmentType")
    availability_slot = relationship("AvailableSlot")
