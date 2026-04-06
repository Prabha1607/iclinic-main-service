from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from src.data.clients.postgres_client import Base


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    role_name = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    appointment_type_id = Column(Integer, ForeignKey(
        "appointment_types.id"), nullable=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    country_code = Column(String(5), nullable=False)
    phone_no = Column(String(15), nullable=False, unique=True)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, server_default="true", nullable=False)
    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now(), nullable=False)

    appointment_type = relationship("AppointmentType", back_populates="providers")

    patient_profile = relationship(
        "PatientProfile", back_populates="user", uselist=False)
    provider_profile = relationship(
        "ProviderProfile", back_populates="user", uselist=False)

    booked_appointments = relationship(
        "Appointment", foreign_keys="Appointment.user_id", back_populates="user"
    )
    provider_appointments = relationship(
        "Appointment", foreign_keys="Appointment.provider_id", back_populates="provider"
    )


class PatientProfile(Base):
    __tablename__ = "patient_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    date_of_birth = Column(Date)
    gender = Column(String(20))
    address = Column(String(255))
    preferred_language = Column(String(50))
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="patient_profile")


class ProviderProfile(Base):
    __tablename__ = "provider_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    specialization = Column(String(100))
    qualification = Column(String(255))
    experience = Column(Integer)
    bio = Column(Text)
    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="provider_profile")
