"""Calendar sync models for bidirectional sync with external calendars."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.workspace import Workspace


class CalendarSyncQueue(Base, TimestampMixin):
    """Queue for syncing appointments to external calendars."""

    __tablename__ = "calendar_sync_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Operation details
    operation: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="create, update, cancel",
    )  # create, update, cancel
    calendar_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="cal-com, calendly, gohighlevel",
    )  # cal-com, calendly, gohighlevel

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
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="For exponential backoff retry scheduling",
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Payload
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Full appointment data for sync",
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    appointment: Mapped["Appointment"] = relationship("Appointment")

    def __repr__(self) -> str:
        """String representation."""
        return f"<CalendarSyncQueue {self.id} - {self.operation} ({self.status})>"


class CalendarWebhookEvent(Base):
    """Calendar webhook events for idempotency and debugging."""

    __tablename__ = "calendar_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Event details
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="cal-com, calendly, gohighlevel",
    )  # cal-com, calendly, gohighlevel
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="booking.created, booking.rescheduled, etc.",
    )
    external_event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Event ID from external provider",
    )

    # Payload and processing
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full webhook payload",
    )
    processed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # Relationships
    workspace: Mapped["Workspace | None"] = relationship("Workspace")

    def __repr__(self) -> str:
        """String representation."""
        return f"<CalendarWebhookEvent {self.id} - {self.provider} {self.event_type}>"
