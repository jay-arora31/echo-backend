from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from livekit.api import AccessToken, VideoGrants
from app.config import settings
import uuid

router = APIRouter()


class RoomCreateResponse(BaseModel):
    """Response for room creation."""
    room_name: str
    message: str


class TokenRequest(BaseModel):
    """Request for generating a token."""
    room_name: str
    participant_name: str = "user"


class TokenResponse(BaseModel):
    """Response with access token."""
    token: str
    room_name: str
    livekit_url: str


@router.post("/create", response_model=RoomCreateResponse)
async def create_room():
    """Generate a room name. Room auto-creates when participant joins with token."""
    # Just generate a unique room name - no need to call LiveKit API
    # LiveKit automatically creates the room when the first participant joins
    room_name = f"voice-room-{uuid.uuid4().hex[:8]}"

    return RoomCreateResponse(
        room_name=room_name,
        message="Room name generated",
    )


@router.post("/token", response_model=TokenResponse)
async def get_token(request: TokenRequest):
    """Generate a participant token for joining a room."""
    try:
        # Create access token with chained methods
        token = (
            AccessToken(
                api_key=settings.livekit_api_key,
                api_secret=settings.livekit_api_secret,
            )
            .with_identity(request.participant_name)
            .with_name(request.participant_name)
            .with_grants(
                VideoGrants(
                    room_join=True,
                    room=request.room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
        )

        # Generate JWT
        jwt_token = token.to_jwt()

        return TokenResponse(
            token=jwt_token,
            room_name=request.room_name,
            livekit_url=settings.livekit_url,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate token: {str(e)}")
