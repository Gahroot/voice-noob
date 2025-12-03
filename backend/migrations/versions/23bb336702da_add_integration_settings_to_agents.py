"""add_integration_settings_to_agents

Revision ID: 23bb336702da
Revises: c1a2629e6aad
Create Date: 2025-12-03 10:10:35.609173

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23bb336702da'
down_revision: Union[str, Sequence[str], None] = 'c1a2629e6aad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('agents', sa.Column('integration_settings', sa.JSON(), nullable=False, server_default='{}', comment="Per-integration settings (e.g., {'cal-com': {'default_event_type_id': 123}})"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('agents', 'integration_settings')
