from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID


class UserBase(BaseModel):
    """Base user schema."""
    phone_number: str = Field(..., min_length=10, max_length=20, description="User phone number")
    name: str | None = Field(None, max_length=100, description="User name")


class UserCreate(UserBase):
    """Schema for creating a user."""
    pass


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    name: str | None = Field(None, max_length=100)


class UserResponse(UserBase):
    """Schema for user response."""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

