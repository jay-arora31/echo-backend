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


# ==================== PRE-WARM FUNCTIONALITY ====================

import logging
import asyncio
from typing import Optional
from threading import Lock
from livekit.api import LiveKitAPI, CreateRoomRequest

logger = logging.getLogger(__name__)

# Track pre-warmed rooms
prewarmed_rooms: dict = {}
_prewarm_lock = Lock()


class PreWarmResponse(BaseModel):
    """Response for pre-warm request."""
    room_name: str
    token: str
    livekit_url: str
    status: str
    message: str


async def trigger_agent_warmup(room_name: str):
    """
    Trigger the LiveKit agent to join the room and start warming the avatar.
    We do this by creating the room explicitly via LiveKit API.
    The agent worker will receive a job dispatch when the room is created.
    """
    try:
        async with LiveKitAPI(
            url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        ) as api:
            # Create the room explicitly - this triggers agent dispatch
            request = CreateRoomRequest(
                name=room_name,
                empty_timeout=120,  # Keep room alive for 2 minutes even if empty
                max_participants=10,
            )
            await api.room.create_room(request)
            logger.info(f"Created room for pre-warming: {room_name}")
            
            # Update status with thread-safe lock
            with _prewarm_lock:
                if room_name in prewarmed_rooms:
                    prewarmed_rooms[room_name]["status"] = "ready"
                
    except Exception as e:
        logger.error(f"Failed to create room for pre-warming: {e}")


@router.post("/prewarm", response_model=PreWarmResponse)
async def prewarm_room():
    """
    Pre-warm a room by creating it and triggering the agent to start.
    This is called by the frontend to reduce perceived latency.
    Returns room name and token so frontend can join when ready.
    """
    # Generate a unique room name
    room_name = f"voice-room-{uuid.uuid4().hex[:8]}"
    
    # Mark as warming
    with _prewarm_lock:
        prewarmed_rooms[room_name] = {
            "status": "warming",
            "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0,
        }
    
    # Trigger agent warmup in background
    asyncio.create_task(trigger_agent_warmup(room_name))
    
    # Generate token for the user
    token = (
        AccessToken(
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
        .with_identity("user")
        .with_name("user")
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
    )
    jwt_token = token.to_jwt()
    
    return PreWarmResponse(
        room_name=room_name,
        token=jwt_token,
        livekit_url=settings.livekit_url,
        status="warming",
        message="Agent warmup triggered",
    )

