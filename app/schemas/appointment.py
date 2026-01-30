from pydantic import BaseModel, Field
from datetime import datetime, date, time
from uuid import UUID
from app.models.appointment import AppointmentStatus


class AppointmentBase(BaseModel):
    """Base appointment schema."""
    appointment_date: date = Field(..., description="Appointment date (YYYY-MM-DD)")
    appointment_time: time = Field(..., description="Appointment time (HH:MM)")
    notes: str | None = Field(None, description="Optional notes")


class AppointmentCreate(AppointmentBase):
    """Schema for creating an appointment."""
    user_id: UUID = Field(..., description="User ID")


class AppointmentUpdate(BaseModel):
    """Schema for updating an appointment."""
    appointment_date: date | None = None
    appointment_time: time | None = None
    status: AppointmentStatus | None = None
    notes: str | None = None


class AppointmentResponse(AppointmentBase):
    """Schema for appointment response."""
    id: UUID
    user_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AvailableSlot(BaseModel):
    """Schema for available slot."""
    date: date
    time: time
    formatted: str = Field(..., description="Human-readable format")

