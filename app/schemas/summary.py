from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID


class SummaryBase(BaseModel):
    """Base summary schema."""
    session_id: str = Field(..., description="LiveKit session ID")
    summary: str = Field(..., description="Conversation summary text")
    appointments_booked: list[dict] | None = Field(None, description="List of booked appointments")
    user_preferences: dict | None = Field(None, description="User preferences noted")
    duration_seconds: int | None = Field(None, description="Call duration in seconds")


class SummaryCreate(SummaryBase):
    """Schema for creating a summary."""
    user_id: UUID | None = Field(None, description="User ID if identified")


class SummaryResponse(SummaryBase):
    """Schema for summary response."""
    id: UUID
    user_id: UUID | None
    created_at: datetime

    class Config:
        from_attributes = True

