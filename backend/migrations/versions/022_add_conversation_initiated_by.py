"""Add initiated_by field to sms_conversations for origin tracking.

Revision ID: 022_add_conv_initiated_by
Revises: 021_add_text_agent_support
Create Date: 2025-12-10

This migration adds:
- initiated_by field to track if conversation was started by platform or external party
- Only platform-initiated conversations will have AI auto-responses enabled
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "022_add_conv_initiated_by"
down_revision = "021_add_text_agent_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add initiated_by field to sms_conversations table
    op.add_column(
        "sms_conversations",
        sa.Column(
            "initiated_by",
            sa.String(20),
            nullable=False,
            server_default="platform",
            comment="Who initiated: 'platform' (we sent first) or 'external' (they texted first)",
        ),
    )

    # Add index for filtering by initiated_by
    op.create_index(
        "ix_sms_conversations_initiated_by",
        "sms_conversations",
        ["initiated_by"],
    )


def downgrade() -> None:
    op.drop_index("ix_sms_conversations_initiated_by", table_name="sms_conversations")
    op.drop_column("sms_conversations", "initiated_by")
