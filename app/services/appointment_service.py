"""Appointment service - Business logic for appointment operations."""

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import date, time, timedelta

from app.models.appointment import Appointment, AppointmentStatus
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate, AvailableSlot


# Hardcoded available slots (as per assignment requirement)
AVAILABLE_SLOTS = [
    {"hour": 9, "minute": 0},
    {"hour": 10, "minute": 0},
    {"hour": 11, "minute": 0},
    {"hour": 14, "minute": 0},  # 2 PM
    {"hour": 15, "minute": 0},  # 3 PM
    {"hour": 16, "minute": 0},  # 4 PM
]


class AppointmentService:
    """Service class for appointment operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_available_slots(self, days_ahead: int = 10) -> list[AvailableSlot]:
        """Get available appointment slots for the next N days."""
        available = []
        today = date.today()

        for day_offset in range(days_ahead):
            slot_date = today + timedelta(days=day_offset)

            # Skip weekends
            if slot_date.weekday() >= 5:
                continue

            for slot in AVAILABLE_SLOTS:
                slot_time = time(hour=slot["hour"], minute=slot["minute"])

                # Check if slot is already booked
                result = await self.db.execute(
                    select(Appointment).where(
                        and_(
                            Appointment.appointment_date == slot_date,
                            Appointment.appointment_time == slot_time,
                            Appointment.status == AppointmentStatus.SCHEDULED.value,
                        )
                    )
                )

                if not result.scalar_one_or_none():
                    formatted = slot_date.strftime("%A, %B %d") + " at " + slot_time.strftime("%I:%M %p")
                    available.append(
                        AvailableSlot(
                            date=slot_date,
                            time=slot_time,
                            formatted=formatted,
                        )
                    )

        return available

    async def get_appointment_by_id(self, appointment_id: UUID) -> Appointment | None:
        """Get an appointment by ID."""
        return await self.db.get(Appointment, appointment_id)

    async def get_user_appointments(
        self, user_id: UUID, status: AppointmentStatus | None = None
    ) -> list[Appointment]:
        """Get all appointments for a user."""
        query = select(Appointment).where(Appointment.user_id == user_id)

        if status:
            query = query.where(Appointment.status == status.value)

        query = query.order_by(Appointment.appointment_date, Appointment.appointment_time)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def check_slot_available(
        self, appointment_date: date, appointment_time: time, exclude_id: UUID | None = None
    ) -> bool:
        """Check if a time slot is available."""
        query = select(Appointment).where(
            and_(
                Appointment.appointment_date == appointment_date,
                Appointment.appointment_time == appointment_time,
                Appointment.status == AppointmentStatus.SCHEDULED.value,
            )
        )

        if exclude_id:
            query = query.where(Appointment.id != exclude_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none() is None

    async def create_appointment(self, appointment_data: AppointmentCreate) -> Appointment:
        """Create a new appointment."""
        appointment = Appointment(**appointment_data.model_dump())
        self.db.add(appointment)
        await self.db.flush()
        await self.db.refresh(appointment)
        return appointment

    async def update_appointment(
        self, appointment: Appointment, appointment_data: AppointmentUpdate
    ) -> Appointment:
        """Update an appointment."""
        update_data = appointment_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(appointment, field, value)
        await self.db.flush()
        await self.db.refresh(appointment)
        return appointment

    async def cancel_appointment(self, appointment: Appointment) -> Appointment:
        """Cancel an appointment (soft delete by changing status)."""
        appointment.status = AppointmentStatus.CANCELLED.value
        await self.db.flush()
        await self.db.refresh(appointment)
        return appointment

    async def user_exists(self, user_id: UUID) -> bool:
        """Check if a user exists."""
        user = await self.db.get(User, user_id)
        return user is not None
