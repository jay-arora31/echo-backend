"""Summary service - Business logic for call summary operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.models.summary import CallSummary
from app.schemas.summary import SummaryCreate


class SummaryService:
    """Service class for summary operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_summary(self, summary_data: SummaryCreate) -> CallSummary:
        """Store a call summary."""
        summary = CallSummary(**summary_data.model_dump())
        self.db.add(summary)
        await self.db.flush()
        await self.db.refresh(summary)
        return summary

    async def get_summary_by_id(self, summary_id: UUID) -> CallSummary | None:
        """Get a summary by ID."""
        return await self.db.get(CallSummary, summary_id)

    async def get_summary_by_session(self, session_id: str) -> CallSummary | None:
        """Get a summary by session ID."""
        result = await self.db.execute(
            select(CallSummary).where(CallSummary.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_user_summaries(self, user_id: UUID) -> list[CallSummary]:
        """Get all summaries for a user."""
        result = await self.db.execute(
            select(CallSummary)
            .where(CallSummary.user_id == user_id)
            .order_by(CallSummary.created_at.desc())
        )
        return list(result.scalars().all())
