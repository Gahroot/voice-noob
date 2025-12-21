"""add_fub_sync_and_contact_fub_person_id

Revision ID: 7daa5cef25ce
Revises: 026_add_calendar_sync
Create Date: 2025-12-21 14:57:31.704890

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7daa5cef25ce'
down_revision: Union[str, Sequence[str], None] = '026_add_calendar_sync'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add fub_person_id to contacts table
    op.add_column(
        'contacts',
        sa.Column('fub_person_id', sa.String(length=255), nullable=True, comment='FollowUpBoss person ID for sync')
    )
    op.create_index(op.f('ix_contacts_fub_person_id'), 'contacts', ['fub_person_id'], unique=False)

    # Create fub_message_sync_queue table
    op.create_table(
        'fub_message_sync_queue',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('sms_message_id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, comment='pending, processing, completed, failed'),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False, comment='For exponential backoff retry scheduling'),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False, comment='Message data (direction, from_number, to_number, body)'),
        sa.Column('fub_message_id', sa.String(length=255), nullable=True, comment='FUB Inbox message ID (from sync response)'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['sms_message_id'], ['sms_messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_fub_message_sync_queue_sms_message_id'), 'fub_message_sync_queue', ['sms_message_id'], unique=False)
    op.create_index(op.f('ix_fub_message_sync_queue_workspace_id'), 'fub_message_sync_queue', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_fub_message_sync_queue_status'), 'fub_message_sync_queue', ['status'], unique=False)
    op.create_index(op.f('ix_fub_message_sync_queue_scheduled_at'), 'fub_message_sync_queue', ['scheduled_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop fub_message_sync_queue table
    op.drop_index(op.f('ix_fub_message_sync_queue_scheduled_at'), table_name='fub_message_sync_queue')
    op.drop_index(op.f('ix_fub_message_sync_queue_status'), table_name='fub_message_sync_queue')
    op.drop_index(op.f('ix_fub_message_sync_queue_workspace_id'), table_name='fub_message_sync_queue')
    op.drop_index(op.f('ix_fub_message_sync_queue_sms_message_id'), table_name='fub_message_sync_queue')
    op.drop_table('fub_message_sync_queue')

    # Remove fub_person_id from contacts table
    op.drop_index(op.f('ix_contacts_fub_person_id'), table_name='contacts')
    op.drop_column('contacts', 'fub_person_id')
