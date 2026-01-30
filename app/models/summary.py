import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class CallSummary(Base):
    """Call summary model - stores conversation summaries."""

    __tablename__ = "call_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    appointments_booked: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    user_preferences: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    duration_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="call_summaries")

    def __repr__(self) -> str:
        return f"<CallSummary {self.session_id}>"

