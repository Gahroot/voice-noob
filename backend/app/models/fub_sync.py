"""FollowUpBoss sync models for bidirectional SMS message sync."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.sms import SMSMessage
    from app.models.workspace import Workspace


class FUBMessageSyncQueue(Base, TimestampMixin):
    """Queue for syncing SMS messages to FollowUpBoss Inbox."""

    __tablename__ = "fub_message_sync_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    sms_message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sms_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="pending, processing, completed, failed",
    )  # pending, processing, completed, failed
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Scheduling
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(UTC),
        comment="For exponential backoff retry scheduling",
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Payload (message data for sync)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        comment="Message data (direction, from_number, to_number, body)",
    )

    # FUB response tracking
    fub_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="FUB Inbox message ID (from sync response)",
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", lazy="selectin")
    sms_message: Mapped["SMSMessage"] = relationship("SMSMessage", lazy="selectin")

    def __repr__(self) -> str:
        """String representation."""
        return f"<FUBMessageSyncQueue {self.id} - {self.status}>"
