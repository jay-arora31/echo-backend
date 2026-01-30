"""User routes - API endpoints for user operations."""

from fastapi import APIRouter, HTTPException
from uuid import UUID

from app.api.deps import DBSession
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.user_service import UserService

router = APIRouter()


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(user_data: UserCreate, db: DBSession):
    """Create a new user."""
    service = UserService(db)
    
    # Check if user with phone number already exists
    existing = await service.get_user_by_phone(user_data.phone_number)
    if existing:
        raise HTTPException(status_code=400, detail="User with this phone number already exists")

    return await service.create_user(user_data)


@router.get("/phone/{phone_number}", response_model=UserResponse)
async def get_user_by_phone(phone_number: str, db: DBSession):
    """Get a user by phone number."""
    service = UserService(db)
    user = await service.get_user_by_phone(phone_number)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, db: DBSession):
    """Get a user by ID."""
    service = UserService(db)
    user = await service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: UUID, user_data: UserUpdate, db: DBSession):
    """Update a user."""
    service = UserService(db)
    user = await service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return await service.update_user(user, user_data)


@router.post("/identify", response_model=UserResponse)
async def identify_or_create_user(user_data: UserCreate, db: DBSession):
    """Identify user by phone number, create if not exists."""
    service = UserService(db)
    return await service.identify_or_create_user(user_data)
