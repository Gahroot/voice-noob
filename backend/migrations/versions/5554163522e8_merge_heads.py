"""merge_heads

Revision ID: 5554163522e8
Revises: 23bb336702da, 2aeb78a98185
Create Date: 2025-12-05 12:04:01.533968

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5554163522e8'
down_revision: Union[str, Sequence[str], None] = ('23bb336702da', '2aeb78a98185')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
