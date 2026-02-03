"""Summary routes - API endpoints for call summary operations."""

from fastapi import APIRouter, HTTPException
from uuid import UUID

from app.api.deps import DBSession
from app.schemas.summary import SummaryCreate, SummaryResponse
from app.services.summary_service import SummaryService

router = APIRouter()


@router.post("/", response_model=SummaryResponse, status_code=201)
async def create_summary(summary_data: SummaryCreate, db: DBSession):
    """Store a call summary."""
    service = SummaryService(db)
    return await service.create_summary(summary_data)


@router.get("/session/{session_id}", response_model=SummaryResponse)
async def get_summary_by_session(session_id: str, db: DBSession):
    """Get a summary by session ID."""
    service = SummaryService(db)
    summary = await service.get_summary_by_session(session_id)

    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")

    return summary


@router.get("/user/{user_id}", response_model=list[SummaryResponse])
async def get_user_summaries(user_id: UUID, db: DBSession):
    """Get all summaries for a user."""
    service = SummaryService(db)
    return await service.get_user_summaries(user_id)


@router.get("/{summary_id}", response_model=SummaryResponse)
async def get_summary(summary_id: UUID, db: DBSession):
    """Get a summary by ID."""
    service = SummaryService(db)
    summary = await service.get_summary_by_id(summary_id)

    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")

    return summary


# ==================== GENERATE SUMMARY WITH COST ====================

from pydantic import BaseModel
from typing import Optional
import openai
from app.config import settings


# Pricing constants (copied from voice_agent to avoid importing heavy LiveKit dependencies)
PRICING = {
    "deepgram_per_min": 0.0043,           # Nova-2 Pay-as-you-go
    "cartesia_per_1k_chars": 0.099,       # Sonic TTS
    "openai_input_per_1m": 0.15,          # GPT-4o-mini input
    "openai_output_per_1m": 0.60,         # GPT-4o-mini output
    "avatar_per_min": 0.03,               # Beyond Presence estimate
}


def calculate_call_cost(cost_tracking: dict) -> dict:
    """Calculate estimated cost breakdown from usage metrics."""
    stt_minutes = cost_tracking.get("stt_seconds", 0) / 60
    tts_chars = cost_tracking.get("tts_characters", 0)
    llm_input = cost_tracking.get("llm_input_tokens", 0)
    llm_output = cost_tracking.get("llm_output_tokens", 0)
    avatar_minutes = cost_tracking.get("avatar_seconds", 0) / 60
    
    stt_cost = stt_minutes * PRICING["deepgram_per_min"]
    tts_cost = (tts_chars / 1000) * PRICING["cartesia_per_1k_chars"]
    llm_input_cost = (llm_input / 1_000_000) * PRICING["openai_input_per_1m"]
    llm_output_cost = (llm_output / 1_000_000) * PRICING["openai_output_per_1m"]
    llm_cost = llm_input_cost + llm_output_cost
    avatar_cost = avatar_minutes * PRICING["avatar_per_min"]
    
    total_cost = stt_cost + tts_cost + llm_cost + avatar_cost
    
    return {
        "deepgram_stt": round(stt_cost, 6),
        "cartesia_tts": round(tts_cost, 6),
        "openai_llm": round(llm_cost, 6),
        "beyond_presence_avatar": round(avatar_cost, 6),
        "total": round(total_cost, 6),
        "usage": {
            "stt_minutes": round(stt_minutes, 2),
            "tts_characters": tts_chars,
            "llm_input_tokens": llm_input,
            "llm_output_tokens": llm_output,
            "avatar_minutes": round(avatar_minutes, 2),
        }
    }


class CostTrackingData(BaseModel):
    """Usage metrics from the call."""
    stt_seconds: float = 0.0
    tts_characters: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    avatar_seconds: float = 0.0


class CostBreakdown(BaseModel):
    """Estimated cost breakdown by service."""
    deepgram_stt: float = 0.0
    cartesia_tts: float = 0.0
    openai_llm: float = 0.0
    beyond_presence_avatar: float = 0.0
    total: float = 0.0
    usage: Optional[dict] = None


class GenerateSummaryRequest(BaseModel):
    """Request to generate an AI summary of the call."""
    room_name: str
    user_name: Optional[str] = None
    transcript: Optional[list[dict]] = None
    messages: Optional[list[dict]] = None  # Alias for transcript (frontend uses 'messages')
    duration_seconds: Optional[int] = None
    appointments_booked: Optional[list[dict]] = None
    cost_tracking: Optional[CostTrackingData] = None
    tool_calls: Optional[list[str]] = None  # Tools used during call


class GenerateSummaryResponse(BaseModel):
    """Response with AI-generated summary and cost breakdown."""
    summary: str
    user_name: Optional[str] = None
    appointments_booked: Optional[list[dict]] = None
    cost: Optional[CostBreakdown] = None


@router.post("/generate", response_model=GenerateSummaryResponse)
async def generate_summary(request: GenerateSummaryRequest, db: DBSession):
    """Generate an AI summary of the call with cost estimation."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Generate AI summary from transcript
    summary_text = "Call completed."
    
    # Use transcript if provided, otherwise fall back to messages
    conversation_data = request.transcript or request.messages
    
    if conversation_data and len(conversation_data) > 0:
        try:
            # Format transcript for summarization
            conversation_text = "\n".join([
                f"{msg.get('role', 'unknown').capitalize()}: {msg.get('content', '')}" 
                for msg in conversation_data[-20:]
            ])
            
            # Call OpenAI for AI-generated summary
            client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You are summarizing a voice call between a user and an AI appointment booking assistant.
Generate a concise but detailed summary including:
- Who the caller was (name/phone if mentioned)
- What actions were taken (appointments booked, cancelled, modified)
- Key details (dates, times, any issues encountered)
- User's preferences or requests

Keep it to 2-3 sentences max. Be specific about dates and times mentioned."""
                    },
                    {
                        "role": "user", 
                        "content": f"Summarize this conversation:\n\n{conversation_text}"
                    }
                ],
                max_tokens=150,
                temperature=0.3,
            )
            summary_text = response.choices[0].message.content or "Call completed."
            logger.info(f"AI-generated summary: {summary_text[:50]}...")
        except Exception as e:
            logger.error(f"AI summary generation failed: {e}")
            summary_text = "Call completed."
    
    # Calculate cost breakdown
    cost_breakdown = None
    if request.cost_tracking:
        cost_data = calculate_call_cost(request.cost_tracking.model_dump())
        cost_breakdown = CostBreakdown(**cost_data)
    elif request.duration_seconds:
        # Fallback estimation based on duration
        estimated_tracking = {
            "stt_seconds": request.duration_seconds * 0.4,  # ~40% user speaking
            "tts_characters": request.duration_seconds * 15,  # ~15 chars/sec avg
            "llm_input_tokens": request.duration_seconds * 10,
            "llm_output_tokens": request.duration_seconds * 20,
            "avatar_seconds": request.duration_seconds,
        }
        cost_data = calculate_call_cost(estimated_tracking)
        cost_breakdown = CostBreakdown(**cost_data)
    
    return GenerateSummaryResponse(
        summary=summary_text,
        user_name=request.user_name,
        appointments_booked=request.appointments_booked,
        cost=cost_breakdown,
    )
