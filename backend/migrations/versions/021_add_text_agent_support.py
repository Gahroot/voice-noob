"""Add text agent support for AI-powered SMS conversations.

Revision ID: 021_add_text_agent_support
Revises: 020_add_slicktext_v1_credentials
Create Date: 2025-12-10

This migration adds:
- Text agent settings to agents table (channel_mode, response delay, context limit)
- AI assignment fields to sms_conversations table
- Default text agent to phone_numbers table
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "021_add_text_agent_support"
down_revision = "020_add_slicktext_v1_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add text agent settings to agents table
    op.add_column(
        "agents",
        sa.Column(
            "channel_mode",
            sa.String(20),
            nullable=False,
            server_default="voice",
            comment="Channel mode: voice, text, or both",
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "text_response_delay_ms",
            sa.Integer(),
            nullable=False,
            server_default="3000",
            comment="Delay in ms before responding to text (for message batching)",
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "text_max_context_messages",
            sa.Integer(),
            nullable=False,
            server_default="20",
            comment="Maximum number of messages to include in context for text responses",
        ),
    )

    # Add AI assignment fields to sms_conversations table
    op.add_column(
        "sms_conversations",
        sa.Column(
            "assigned_agent_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
            comment="Text agent assigned to handle this conversation",
        ),
    )
    op.add_column(
        "sms_conversations",
        sa.Column(
            "ai_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Whether AI auto-responds to this conversation",
        ),
    )
    op.add_column(
        "sms_conversations",
        sa.Column(
            "ai_paused",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Temporarily pause AI responses (human takeover)",
        ),
    )
    op.add_column(
        "sms_conversations",
        sa.Column(
            "ai_paused_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Resume AI responses after this time",
        ),
    )

    # Add index for assigned_agent_id
    op.create_index(
        "ix_sms_conversations_assigned_agent_id",
        "sms_conversations",
        ["assigned_agent_id"],
    )

    # Add default text agent to phone_numbers table
    op.add_column(
        "phone_numbers",
        sa.Column(
            "default_text_agent_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
            comment="Default text agent for new SMS conversations on this number",
        ),
    )
    op.create_index(
        "ix_phone_numbers_default_text_agent_id",
        "phone_numbers",
        ["default_text_agent_id"],
    )


def downgrade() -> None:
    # Remove phone_numbers columns
    op.drop_index("ix_phone_numbers_default_text_agent_id", table_name="phone_numbers")
    op.drop_column("phone_numbers", "default_text_agent_id")

    # Remove sms_conversations columns
    op.drop_index("ix_sms_conversations_assigned_agent_id", table_name="sms_conversations")
    op.drop_column("sms_conversations", "ai_paused_until")
    op.drop_column("sms_conversations", "ai_paused")
    op.drop_column("sms_conversations", "ai_enabled")
    op.drop_column("sms_conversations", "assigned_agent_id")

    # Remove agents columns
    op.drop_column("agents", "text_max_context_messages")
    op.drop_column("agents", "text_response_delay_ms")
    op.drop_column("agents", "channel_mode")
