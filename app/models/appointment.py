import uuid
from datetime import datetime, date, time
from enum import Enum
from sqlalchemy import String, DateTime, Date, Time, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AppointmentStatus(str, Enum):
    """Appointment status enum."""
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Appointment(Base):
    """Appointment model."""

    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appointment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    appointment_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=AppointmentStatus.SCHEDULED.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="appointments")

    # Prevent double-booking (same date+time with scheduled status)
    __table_args__ = (
        UniqueConstraint(
            "appointment_date",
            "appointment_time",
            "status",
            name="unique_scheduled_slot",
        ),
    )

    def __repr__(self) -> str:
        return f"<Appointment {self.appointment_date} {self.appointment_time}>"

