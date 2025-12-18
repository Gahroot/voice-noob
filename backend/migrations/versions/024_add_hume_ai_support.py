"""Add Hume AI credentials and emotion data support.

Revision ID: 024_add_hume_ai_support
Revises: 023_add_slicktext_text_agent
Create Date: 2025-12-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "024_add_hume_ai_support"
down_revision: str | None = "023_slicktext_default_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add Hume AI credentials to user_settings
    op.add_column(
        "user_settings",
        sa.Column(
            "hume_api_key",
            sa.Text(),
            nullable=True,
            comment="Hume AI API key for EVI and Octave TTS",
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "hume_secret_key",
            sa.Text(),
            nullable=True,
            comment="Hume AI Secret key for OAuth token generation",
        ),
    )

    # Add emotion_data JSONB column to call_records for storing Hume expression measurements
    op.add_column(
        "call_records",
        sa.Column(
            "emotion_data",
            sa.JSON(),
            nullable=True,
            comment="Hume AI emotion/expression measurements per conversation turn",
        ),
    )


def downgrade() -> None:
    op.drop_column("call_records", "emotion_data")
    op.drop_column("user_settings", "hume_secret_key")
    op.drop_column("user_settings", "hume_api_key")
