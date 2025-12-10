"""Update SlickText credentials from v1 (public/private) to v2 (single API key).

Revision ID: 018_update_slicktext_to_v2
Revises: 017_add_slicktext_credentials
Create Date: 2024-12-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "018_update_slicktext_to_v2"
down_revision: str | None = "017_add_slicktext_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Migrate from SlickText v1 (public/private keys) to v2 (single API key)."""
    # Add new column for v2 API key
    op.add_column(
        "user_settings",
        sa.Column(
            "slicktext_api_key",
            sa.Text(),
            nullable=True,
            comment="SlickText API Key (v2 Bearer token)",
        ),
    )

    # Remove old v1 columns
    op.drop_column("user_settings", "slicktext_public_key")
    op.drop_column("user_settings", "slicktext_private_key")


def downgrade() -> None:
    """Revert to SlickText v1 (public/private keys)."""
    # Add back old v1 columns
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

    # Remove v2 column
    op.drop_column("user_settings", "slicktext_api_key")
