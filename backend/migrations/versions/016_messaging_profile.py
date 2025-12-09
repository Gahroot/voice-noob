"""Add telnyx_messaging_profile_id to user_settings.

Revision ID: 016_messaging_profile
Revises: 015_add_sms_tables
Create Date: 2025-01-09

This migration adds the messaging_profile_id field required for Telnyx SMS.
Without a messaging profile ID, SMS messages may not be delivered.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016_messaging_profile"
down_revision: str | None = "015_add_sms_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column(
            "telnyx_messaging_profile_id",
            sa.String(255),
            nullable=True,
            comment="Telnyx Messaging Profile ID for SMS",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "telnyx_messaging_profile_id")
