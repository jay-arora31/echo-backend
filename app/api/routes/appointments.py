"""Appointment routes - API endpoints for appointment operations."""

from fastapi import APIRouter, HTTPException
from uuid import UUID

from app.api.deps import DBSession
from app.models.appointment import AppointmentStatus
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentResponse,
    AvailableSlot,
)
from app.services.appointment_service import AppointmentService

router = APIRouter()


@router.get("/slots", response_model=list[AvailableSlot])
async def get_available_slots(db: DBSession, days_ahead: int = 7):
    """Get available appointment slots for the next N days."""
    service = AppointmentService(db)
    return await service.get_available_slots(days_ahead)


@router.post("/", response_model=AppointmentResponse, status_code=201)
async def create_appointment(appointment_data: AppointmentCreate, db: DBSession):
    """Create a new appointment."""
    service = AppointmentService(db)

    # Verify user exists
    if not await service.user_exists(appointment_data.user_id):
        raise HTTPException(status_code=404, detail="User not found")

    # Check for double-booking
    is_available = await service.check_slot_available(
        appointment_data.appointment_date,
        appointment_data.appointment_time,
    )
    if not is_available:
        raise HTTPException(
            status_code=409,
            detail="This time slot is already booked. Please choose another slot.",
        )

    return await service.create_appointment(appointment_data)


@router.get("/user/{user_id}", response_model=list[AppointmentResponse])
async def get_user_appointments(
    user_id: UUID,
    db: DBSession,
    status: AppointmentStatus | None = None,
):
    """Get all appointments for a user."""
    service = AppointmentService(db)
    return await service.get_user_appointments(user_id, status)


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(appointment_id: UUID, db: DBSession):
    """Get an appointment by ID."""
    service = AppointmentService(db)
    appointment = await service.get_appointment_by_id(appointment_id)

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    return appointment


@router.patch("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: UUID,
    appointment_data: AppointmentUpdate,
    db: DBSession,
):
    """Update an appointment (modify date/time or status)."""
    service = AppointmentService(db)
    appointment = await service.get_appointment_by_id(appointment_id)

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # If changing date/time, check for double-booking
    update_data = appointment_data.model_dump(exclude_unset=True)
    new_date = update_data.get("appointment_date", appointment.appointment_date)
    new_time = update_data.get("appointment_time", appointment.appointment_time)

    if new_date != appointment.appointment_date or new_time != appointment.appointment_time:
        is_available = await service.check_slot_available(new_date, new_time, exclude_id=appointment_id)
        if not is_available:
            raise HTTPException(
                status_code=409,
                detail="This time slot is already booked. Please choose another slot.",
            )

    return await service.update_appointment(appointment, appointment_data)


@router.delete("/{appointment_id}", response_model=AppointmentResponse)
async def cancel_appointment(appointment_id: UUID, db: DBSession):
    """Cancel an appointment (soft delete by changing status)."""
    service = AppointmentService(db)
    appointment = await service.get_appointment_by_id(appointment_id)

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appointment.status == AppointmentStatus.CANCELLED.value:
        raise HTTPException(status_code=400, detail="Appointment is already cancelled")

    return await service.cancel_appointment(appointment)
