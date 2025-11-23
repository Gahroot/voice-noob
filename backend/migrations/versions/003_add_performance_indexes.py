"""Add performance indexes

Revision ID: 003_add_performance_indexes
Revises: 002_add_crm_models
Create Date: 2025-11-23

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "003_add_performance_indexes"
down_revision: Union[str, None] = "002_add_crm_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add composite indexes for improved query performance."""
    # Contacts table composite indexes
    op.create_index(
        "ix_contacts_user_id_created_at",
        "contacts",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_contacts_user_id_status",
        "contacts",
        ["user_id", "status"],
        unique=False,
    )

    # Appointments table composite indexes
    op.create_index(
        "ix_appointments_contact_id_scheduled_at",
        "appointments",
        ["contact_id", "scheduled_at"],
        unique=False,
    )
    op.create_index(
        "ix_appointments_contact_id_status",
        "appointments",
        ["contact_id", "status"],
        unique=False,
    )

    # Call interactions table composite index
    op.create_index(
        "ix_call_interactions_contact_id_call_started_at",
        "call_interactions",
        ["contact_id", "call_started_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove composite indexes."""
    # Drop call_interactions indexes
    op.drop_index(
        "ix_call_interactions_contact_id_call_started_at",
        table_name="call_interactions",
    )

    # Drop appointments indexes
    op.drop_index("ix_appointments_contact_id_status", table_name="appointments")
    op.drop_index(
        "ix_appointments_contact_id_scheduled_at",
        table_name="appointments",
    )

    # Drop contacts indexes
    op.drop_index("ix_contacts_user_id_status", table_name="contacts")
    op.drop_index("ix_contacts_user_id_created_at", table_name="contacts")
