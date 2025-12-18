"""Add indexes for query optimization based on common access patterns.

Revision ID: 025_add_optimization_indexes
Revises: 024_add_hume_ai_support
Create Date: 2025-12-18

These indexes address bottlenecks identified in API query analysis:
- call_records.direction - frequently filtered for inbound/outbound
- call_records.status - frequently filtered for completed/in_progress
- agents.is_active - filtered for active agents
- agents.is_published - filtered for published agents
- Composite indexes for common filter+sort patterns
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "025_add_optimization_indexes"
down_revision: str | None = "024_add_hume_ai_support"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add indexes for commonly queried columns."""
    # Call records - direction and status are frequently filtered but not indexed
    op.create_index(
        "ix_call_records_direction",
        "call_records",
        ["direction"],
        unique=False,
    )
    op.create_index(
        "ix_call_records_status",
        "call_records",
        ["status"],
        unique=False,
    )

    # Composite index for agent stats queries (agent_id + user_id + status/direction)
    op.create_index(
        "ix_call_records_agent_user_direction",
        "call_records",
        ["agent_id", "user_id", "direction"],
        unique=False,
    )

    # Agents - is_active and is_published are filtered but not indexed
    op.create_index(
        "ix_agents_is_active",
        "agents",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "ix_agents_is_published",
        "agents",
        ["is_published"],
        unique=False,
    )

    # Composite index for listing published/active agents by user
    op.create_index(
        "ix_agents_user_id_is_active_is_published",
        "agents",
        ["user_id", "is_active", "is_published"],
        unique=False,
    )

    # SMS conversations - status filtering with workspace
    op.create_index(
        "ix_sms_conversations_workspace_status",
        "sms_conversations",
        ["workspace_id", "status"],
        unique=False,
    )

    # SMS messages - conversation ordering
    op.create_index(
        "ix_sms_messages_conversation_created",
        "sms_messages",
        ["conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove optimization indexes."""
    op.drop_index("ix_sms_messages_conversation_created", table_name="sms_messages")
    op.drop_index("ix_sms_conversations_workspace_status", table_name="sms_conversations")
    op.drop_index("ix_agents_user_id_is_active_is_published", table_name="agents")
    op.drop_index("ix_agents_is_published", table_name="agents")
    op.drop_index("ix_agents_is_active", table_name="agents")
    op.drop_index("ix_call_records_agent_user_direction", table_name="call_records")
    op.drop_index("ix_call_records_status", table_name="call_records")
    op.drop_index("ix_call_records_direction", table_name="call_records")
