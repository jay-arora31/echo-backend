"""User service - Business logic for user operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    """Service class for user operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user."""
        user = User(**user_data.model_dump())
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """Get a user by ID."""
        return await self.db.get(User, user_id)

    async def get_user_by_phone(self, phone_number: str) -> User | None:
        """Get a user by phone number."""
        result = await self.db.execute(
            select(User).where(User.phone_number == phone_number)
        )
        return result.scalar_one_or_none()

    async def update_user(self, user: User, user_data: UserUpdate) -> User:
        """Update a user."""
        update_data = user_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def identify_or_create_user(self, user_data: UserCreate) -> User:
        """Identify user by phone number, create if not exists."""
        user = await self.get_user_by_phone(user_data.phone_number)

        if user:
            # Update name if provided and user doesn't have one
            if user_data.name and not user.name:
                user.name = user_data.name
                await self.db.flush()
                await self.db.refresh(user)
            return user

        # Create new user
        return await self.create_user(user_data)
