"""Add slicktext_default_text_agent_id to user_settings.

Revision ID: 023_slicktext_default_agent
Revises: 022_add_conv_initiated_by
Create Date: 2025-12-11

This migration adds:
- slicktext_default_text_agent_id field to user_settings
- Allows setting a default text agent for SlickText phone numbers
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "023_slicktext_default_agent"
down_revision = "022_add_conv_initiated_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add slicktext_default_text_agent_id to user_settings
    op.add_column(
        "user_settings",
        sa.Column(
            "slicktext_default_text_agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
            comment="Default text agent for SlickText SMS conversations",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "slicktext_default_text_agent_id")
