"""Add SlickText credentials to user_settings.

Revision ID: 017_add_slicktext_credentials
Revises: 016_messaging_profile
Create Date: 2024-12-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017_add_slicktext_credentials"
down_revision: str | None = "016_messaging_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add SlickText credential columns to user_settings table."""
    op.add_column(
        "user_settings",
        sa.Column(
            "slicktext_public_key",
            sa.Text(),
            nullable=True,
            comment="SlickText Public API Key",
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "slicktext_private_key",
            sa.Text(),
            nullable=True,
            comment="SlickText Private API Key",
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "slicktext_webhook_secret",
            sa.Text(),
            nullable=True,
            comment="SlickText Webhook Secret for signature verification",
        ),
    )


def downgrade() -> None:
    """Remove SlickText credential columns from user_settings table."""
    op.drop_column("user_settings", "slicktext_webhook_secret")
    op.drop_column("user_settings", "slicktext_private_key")
    op.drop_column("user_settings", "slicktext_public_key")
