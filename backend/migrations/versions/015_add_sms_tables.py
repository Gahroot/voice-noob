"""Add SMS tables for conversations, messages, and campaigns.

Revision ID: 015_add_sms_tables
Revises: 014_add_embed_settings
Create Date: 2025-01-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "015_add_sms_tables"
down_revision: str | None = "5554163522e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create sms_conversations table
    op.create_table(
        "sms_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False, comment="Owner user ID"),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            nullable=False,
            comment="Workspace this conversation belongs to",
        ),
        sa.Column(
            "contact_id",
            sa.BigInteger(),
            nullable=True,
            comment="Associated contact if known",
        ),
        sa.Column(
            "from_number",
            sa.String(50),
            nullable=False,
            comment="Our phone number (E.164)",
        ),
        sa.Column(
            "to_number",
            sa.String(50),
            nullable=False,
            comment="Contact's phone number (E.164)",
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="active",
            comment="Conversation status: active, archived, blocked",
        ),
        sa.Column(
            "unread_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of unread inbound messages",
        ),
        sa.Column(
            "last_message_preview",
            sa.String(255),
            nullable=True,
            comment="Preview of last message",
        ),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When last message was sent/received",
        ),
        sa.Column(
            "last_message_direction",
            sa.String(20),
            nullable=True,
            comment="Direction of last message",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sms_conversations_user_id", "sms_conversations", ["user_id"])
    op.create_index("ix_sms_conversations_workspace_id", "sms_conversations", ["workspace_id"])
    op.create_index("ix_sms_conversations_contact_id", "sms_conversations", ["contact_id"])
    op.create_index("ix_sms_conversations_from_number", "sms_conversations", ["from_number"])
    op.create_index("ix_sms_conversations_to_number", "sms_conversations", ["to_number"])
    op.create_index("ix_sms_conversations_status", "sms_conversations", ["status"])
    op.create_index("ix_sms_conversations_last_message_at", "sms_conversations", ["last_message_at"])

    # Create sms_campaigns table (before sms_messages since messages reference campaigns)
    op.create_table(
        "sms_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False, comment="Owner user ID"),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            nullable=False,
            comment="Workspace this campaign belongs to",
        ),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            nullable=True,
            comment="Agent that handles AI responses",
        ),
        sa.Column("name", sa.String(255), nullable=False, comment="Campaign name"),
        sa.Column("description", sa.Text(), nullable=True, comment="Campaign description"),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="draft",
            comment="Campaign status",
        ),
        sa.Column(
            "from_phone_number",
            sa.String(50),
            nullable=False,
            comment="Phone number to send from (E.164 format)",
        ),
        sa.Column(
            "initial_message",
            sa.Text(),
            nullable=False,
            comment="Initial message template",
        ),
        sa.Column(
            "ai_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether AI auto-responds to replies",
        ),
        sa.Column(
            "ai_system_prompt",
            sa.Text(),
            nullable=True,
            comment="System prompt for AI responses",
        ),
        sa.Column(
            "qualification_criteria",
            sa.Text(),
            nullable=True,
            comment="Criteria for qualifying leads",
        ),
        sa.Column(
            "scheduled_start",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When to start the campaign",
        ),
        sa.Column(
            "scheduled_end",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When to end the campaign",
        ),
        sa.Column(
            "sending_hours_start",
            sa.String(10),
            nullable=True,
            comment="Start of daily sending window",
        ),
        sa.Column(
            "sending_hours_end",
            sa.String(10),
            nullable=True,
            comment="End of daily sending window",
        ),
        sa.Column(
            "sending_days",
            postgresql.ARRAY(sa.Integer()),
            nullable=True,
            comment="Days of week to send",
        ),
        sa.Column(
            "timezone",
            sa.String(50),
            nullable=True,
            server_default="UTC",
            comment="Timezone for sending hours",
        ),
        sa.Column(
            "messages_per_minute",
            sa.Integer(),
            nullable=False,
            server_default="10",
            comment="Max messages to send per minute",
        ),
        sa.Column(
            "max_messages_per_contact",
            sa.Integer(),
            nullable=False,
            server_default="5",
            comment="Max total messages per contact",
        ),
        sa.Column(
            "follow_up_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether to send follow-up messages",
        ),
        sa.Column(
            "follow_up_delay_hours",
            sa.Integer(),
            nullable=False,
            server_default="24",
            comment="Hours to wait before follow-up",
        ),
        sa.Column(
            "follow_up_message",
            sa.Text(),
            nullable=True,
            comment="Follow-up message template",
        ),
        sa.Column(
            "max_follow_ups",
            sa.Integer(),
            nullable=False,
            server_default="2",
            comment="Max follow-up messages to send",
        ),
        sa.Column(
            "total_contacts",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Total contacts in campaign",
        ),
        sa.Column(
            "messages_sent",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Total messages sent",
        ),
        sa.Column(
            "messages_delivered",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Messages confirmed delivered",
        ),
        sa.Column(
            "messages_failed",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Messages that failed to send",
        ),
        sa.Column(
            "replies_received",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Total replies received",
        ),
        sa.Column(
            "contacts_qualified",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Contacts marked as qualified",
        ),
        sa.Column(
            "contacts_opted_out",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Contacts who opted out",
        ),
        sa.Column("last_error", sa.Text(), nullable=True, comment="Most recent error message"),
        sa.Column(
            "error_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Total number of errors",
        ),
        sa.Column(
            "last_error_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the last error occurred",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the campaign started running",
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the campaign completed",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sms_campaigns_user_id", "sms_campaigns", ["user_id"])
    op.create_index("ix_sms_campaigns_workspace_id", "sms_campaigns", ["workspace_id"])
    op.create_index("ix_sms_campaigns_agent_id", "sms_campaigns", ["agent_id"])
    op.create_index("ix_sms_campaigns_status", "sms_campaigns", ["status"])

    # Create sms_messages table
    op.create_table(
        "sms_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            sa.String(50),
            nullable=False,
            server_default="telnyx",
            comment="SMS provider: telnyx, twilio",
        ),
        sa.Column(
            "provider_message_id",
            sa.String(255),
            nullable=True,
            comment="Provider's message ID",
        ),
        sa.Column(
            "direction",
            sa.String(20),
            nullable=False,
            comment="inbound or outbound",
        ),
        sa.Column(
            "from_number",
            sa.String(50),
            nullable=False,
            comment="Sender phone number (E.164)",
        ),
        sa.Column(
            "to_number",
            sa.String(50),
            nullable=False,
            comment="Recipient phone number (E.164)",
        ),
        sa.Column("body", sa.Text(), nullable=False, comment="Message content"),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="queued",
            comment="Delivery status",
        ),
        sa.Column("error_code", sa.String(50), nullable=True, comment="Error code if failed"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="Error details if failed"),
        sa.Column(
            "segment_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Number of SMS segments",
        ),
        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether inbound message has been read",
        ),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            nullable=True,
            comment="Agent that sent this message (if AI-sent)",
        ),
        sa.Column(
            "campaign_id",
            sa.Uuid(),
            nullable=True,
            comment="Campaign this message belongs to",
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When message was sent",
        ),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When message was delivered",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["sms_conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["sms_campaigns.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sms_messages_conversation_id", "sms_messages", ["conversation_id"])
    op.create_index("ix_sms_messages_provider_message_id", "sms_messages", ["provider_message_id"])
    op.create_index("ix_sms_messages_direction", "sms_messages", ["direction"])
    op.create_index("ix_sms_messages_status", "sms_messages", ["status"])
    op.create_index("ix_sms_messages_agent_id", "sms_messages", ["agent_id"])
    op.create_index("ix_sms_messages_campaign_id", "sms_messages", ["campaign_id"])
    op.create_index("ix_sms_messages_created_at", "sms_messages", ["created_at"])

    # Create sms_campaign_contacts table
    op.create_table(
        "sms_campaign_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            nullable=True,
            comment="Associated conversation thread",
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="pending",
            comment="Contact status in this campaign",
        ),
        sa.Column(
            "messages_sent",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of messages sent to this contact",
        ),
        sa.Column(
            "messages_received",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of replies from this contact",
        ),
        sa.Column(
            "follow_ups_sent",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of follow-up messages sent",
        ),
        sa.Column(
            "first_sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When initial message was sent",
        ),
        sa.Column(
            "last_sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When last message was sent",
        ),
        sa.Column(
            "last_reply_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When last reply was received",
        ),
        sa.Column(
            "next_follow_up_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When to send next follow-up",
        ),
        sa.Column(
            "is_qualified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether contact is qualified",
        ),
        sa.Column(
            "qualification_notes",
            sa.Text(),
            nullable=True,
            comment="Notes about qualification",
        ),
        sa.Column(
            "qualified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When contact was qualified",
        ),
        sa.Column(
            "opted_out",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether contact opted out",
        ),
        sa.Column(
            "opted_out_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When contact opted out",
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Send priority (higher = sooner)",
        ),
        sa.Column("last_error", sa.Text(), nullable=True, comment="Last error for this contact"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["sms_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["sms_conversations.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sms_campaign_contacts_campaign_id", "sms_campaign_contacts", ["campaign_id"])
    op.create_index("ix_sms_campaign_contacts_contact_id", "sms_campaign_contacts", ["contact_id"])
    op.create_index("ix_sms_campaign_contacts_conversation_id", "sms_campaign_contacts", ["conversation_id"])
    op.create_index("ix_sms_campaign_contacts_status", "sms_campaign_contacts", ["status"])
    op.create_index("ix_sms_campaign_contacts_next_follow_up_at", "sms_campaign_contacts", ["next_follow_up_at"])


def downgrade() -> None:
    op.drop_table("sms_campaign_contacts")
    op.drop_table("sms_messages")
    op.drop_table("sms_campaigns")
    op.drop_table("sms_conversations")
