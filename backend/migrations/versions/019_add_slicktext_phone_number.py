"""Add SlickText phone number field.

Revision ID: 019_add_slicktext_phone_number
Revises: 018_update_slicktext_to_v2
Create Date: 2024-12-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019_add_slicktext_phone_number"
down_revision: str | None = "018_update_slicktext_to_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add slicktext_phone_number column to user_settings."""
    op.add_column(
        "user_settings",
        sa.Column(
            "slicktext_phone_number",
            sa.String(50),
            nullable=True,
            comment="SlickText phone number (E.164 format)",
        ),
    )


def downgrade() -> None:
    """Remove slicktext_phone_number column from user_settings."""
    op.drop_column("user_settings", "slicktext_phone_number")
