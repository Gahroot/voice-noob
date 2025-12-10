"""Add SlickText V1 API credentials.

Revision ID: 020_add_slicktext_v1_credentials
Revises: 019_add_slicktext_phone_number
Create Date: 2025-12-10

SlickText has two API versions:
- V1 (Legacy): For accounts created before Jan 22, 2025. Uses public/private key pair.
- V2: For accounts created after Jan 22, 2025. Uses Bearer token.

This migration adds V1 API credential fields to support legacy accounts.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "020_add_slicktext_v1_credentials"
down_revision = "019_add_slicktext_phone_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add V1 API credentials for legacy SlickText accounts
    op.add_column(
        "user_settings",
        sa.Column(
            "slicktext_public_key",
            sa.Text(),
            nullable=True,
            comment="SlickText Public Key (v1 API)",
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "slicktext_private_key",
            sa.Text(),
            nullable=True,
            comment="SlickText Private Key (v1 API)",
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "slicktext_textword_id",
            sa.String(50),
            nullable=True,
            comment="SlickText Textword ID (v1 API, for sending)",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "slicktext_textword_id")
    op.drop_column("user_settings", "slicktext_private_key")
    op.drop_column("user_settings", "slicktext_public_key")
