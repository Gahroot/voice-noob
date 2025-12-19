"""Add calendar sync support for bidirectional sync with external calendars.

Revision ID: 026_add_calendar_sync
Revises: 025_add_optimization_indexes
Create Date: 2025-12-19

Adds:
- Calendar sync tracking fields to appointments table
- Calendar sync queue table for async processing
- Calendar webhook events table for idempotency
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "026_add_calendar_sync"
down_revision: str | None = "025_add_optimization_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add calendar sync support."""
    # Add calendar sync fields to appointments table
    op.add_column(
        "appointments",
        sa.Column(
            "external_calendar_id",
            sa.String(length=50),
            nullable=True,
            comment="Calendar provider: cal-com, calendly, gohighlevel",
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "external_event_id",
            sa.String(length=255),
            nullable=True,
            comment="Unique event ID from external calendar",
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "external_event_uid",
            sa.String(length=255),
            nullable=True,
            comment="Event UID for Cal.com/Calendly",
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "sync_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
            comment="pending, synced, failed, conflict",
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful sync timestamp",
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "sync_error",
            sa.Text(),
            nullable=True,
            comment="Error message if sync failed",
        ),
    )

    # Create indexes for sync queries
    op.create_index(
        "ix_appointments_sync_status",
        "appointments",
        ["sync_status"],
        unique=False,
    )
    op.create_index(
        "ix_appointments_external_calendar_id",
        "appointments",
        ["external_calendar_id"],
        unique=False,
    )
    op.create_index(
        "ix_appointments_external_event_uid",
        "appointments",
        ["external_event_uid"],
        unique=False,
    )

    # Create calendar_sync_queue table
    op.create_table(
        "calendar_sync_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "operation",
            sa.String(length=20),
            nullable=False,
            comment="create, update, cancel",
        ),
        sa.Column(
            "calendar_provider",
            sa.String(length=50),
            nullable=False,
            comment="cal-com, calendly, gohighlevel",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
            comment="pending, processing, completed, failed",
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="For exponential backoff retry scheduling",
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Full appointment data for sync",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["appointments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for sync queue
    op.create_index(
        "ix_calendar_sync_queue_status",
        "calendar_sync_queue",
        ["status", "scheduled_at"],
        unique=False,
    )
    op.create_index(
        "ix_calendar_sync_queue_workspace",
        "calendar_sync_queue",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_calendar_sync_queue_appointment",
        "calendar_sync_queue",
        ["appointment_id"],
        unique=False,
    )

    # Create calendar_webhook_events table for idempotency
    op.create_table(
        "calendar_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "provider",
            sa.String(length=50),
            nullable=False,
            comment="cal-com, calendly, gohighlevel",
        ),
        sa.Column(
            "event_type",
            sa.String(length=100),
            nullable=False,
            comment="booking.created, booking.rescheduled, etc.",
        ),
        sa.Column(
            "external_event_id",
            sa.String(length=255),
            nullable=False,
            comment="Event ID from external provider",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Full webhook payload",
        ),
        sa.Column(
            "processed", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create unique constraint to prevent duplicate webhook processing
    op.create_index(
        "ix_calendar_webhook_events_unique",
        "calendar_webhook_events",
        ["provider", "external_event_id"],
        unique=True,
    )
    op.create_index(
        "ix_calendar_webhook_events_processed",
        "calendar_webhook_events",
        ["provider", "processed"],
        unique=False,
    )


def downgrade() -> None:
    """Remove calendar sync support."""
    # Drop webhook events table
    op.drop_index(
        "ix_calendar_webhook_events_processed", table_name="calendar_webhook_events"
    )
    op.drop_index(
        "ix_calendar_webhook_events_unique", table_name="calendar_webhook_events"
    )
    op.drop_table("calendar_webhook_events")

    # Drop sync queue table
    op.drop_index("ix_calendar_sync_queue_appointment", table_name="calendar_sync_queue")
    op.drop_index("ix_calendar_sync_queue_workspace", table_name="calendar_sync_queue")
    op.drop_index("ix_calendar_sync_queue_status", table_name="calendar_sync_queue")
    op.drop_table("calendar_sync_queue")

    # Drop appointment sync fields
    op.drop_index("ix_appointments_external_event_uid", table_name="appointments")
    op.drop_index("ix_appointments_external_calendar_id", table_name="appointments")
    op.drop_index("ix_appointments_sync_status", table_name="appointments")
    op.drop_column("appointments", "sync_error")
    op.drop_column("appointments", "last_synced_at")
    op.drop_column("appointments", "sync_status")
    op.drop_column("appointments", "external_event_uid")
    op.drop_column("appointments", "external_event_id")
    op.drop_column("appointments", "external_calendar_id")
