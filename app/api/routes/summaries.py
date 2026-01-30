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
