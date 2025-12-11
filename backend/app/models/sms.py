"""SMS models for conversations, messages, and campaigns."""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.contact import Contact
    from app.models.workspace import Workspace


class MessageDirection(str, Enum):
    """SMS message direction."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(str, Enum):
    """SMS message delivery status."""

    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    UNDELIVERED = "undelivered"
    RECEIVED = "received"  # For inbound messages


class SMSCampaignStatus(str, Enum):
    """SMS campaign status."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELED = "canceled"


class SMSCampaignContactStatus(str, Enum):
    """Status of a contact within an SMS campaign."""

    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    REPLIED = "replied"
    FAILED = "failed"
    OPTED_OUT = "opted_out"
    COMPLETED = "completed"


class SMSConversation(Base):
    """SMS conversation thread with a contact.

    Groups all messages between a phone number and a contact.
    """

    __tablename__ = "sms_conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True, comment="Owner user ID"
    )

    # Workspace isolation
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Workspace this conversation belongs to",
    )

    # Contact (nullable for unknown senders)
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Associated contact if known",
    )

    # Phone numbers involved
    from_number: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="Our phone number (E.164)"
    )
    to_number: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="Contact's phone number (E.164)"
    )

    # Conversation metadata
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
        index=True,
        comment="Conversation status: active, archived, blocked",
    )
    unread_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of unread inbound messages"
    )

    # Last message preview (denormalized for list view)
    last_message_preview: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Preview of last message"
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="When last message was sent/received",
    )
    last_message_direction: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="Direction of last message"
    )

    # Conversation origin tracking
    initiated_by: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="platform",
        index=True,
        comment="Who initiated the conversation: 'platform' (we sent first) or 'external' (they texted first)",
    )

    # AI Text Agent assignment
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Text agent assigned to handle this conversation",
    )
    ai_enabled: Mapped[bool] = mapped_column(
        default=True, comment="Whether AI auto-responds to this conversation"
    )
    ai_paused: Mapped[bool] = mapped_column(
        default=False, comment="Temporarily pause AI responses (human takeover)"
    )
    ai_paused_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Resume AI responses after this time",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", lazy="selectin")
    contact: Mapped["Contact | None"] = relationship("Contact", lazy="selectin")
    messages: Mapped[list["SMSMessage"]] = relationship(
        "SMSMessage", back_populates="conversation", cascade="all, delete-orphan", lazy="selectin"
    )
    assigned_agent: Mapped["Agent | None"] = relationship(
        "Agent", foreign_keys=[assigned_agent_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<SMSConversation(id={self.id}, from={self.from_number}, to={self.to_number})>"


class SMSMessage(Base):
    """Individual SMS message."""

    __tablename__ = "sms_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Conversation association
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sms_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Provider tracking
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, default="telnyx", comment="SMS provider: telnyx, twilio"
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="Provider's message ID"
    )

    # Message details
    direction: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="inbound or outbound"
    )
    from_number: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Sender phone number (E.164)"
    )
    to_number: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Recipient phone number (E.164)"
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, comment="Message content")

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=MessageStatus.QUEUED.value,
        index=True,
        comment="Delivery status",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Error code if failed"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error details if failed"
    )

    # Metadata
    segment_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="Number of SMS segments"
    )
    is_read: Mapped[bool] = mapped_column(
        default=False, comment="Whether inbound message has been read"
    )

    # Agent association (if sent by AI agent)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Agent that sent this message (if AI-sent)",
    )

    # Campaign association (if part of campaign)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sms_campaigns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Campaign this message belongs to",
    )

    # Timestamps
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When message was sent"
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When message was delivered"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )

    # Relationships
    conversation: Mapped["SMSConversation"] = relationship(
        "SMSConversation", back_populates="messages"
    )
    agent: Mapped["Agent | None"] = relationship("Agent", lazy="selectin")

    def __repr__(self) -> str:
        return f"<SMSMessage(id={self.id}, direction={self.direction}, status={self.status})>"


class SMSCampaign(Base):
    """SMS campaign for lead qualification.

    Manages bulk SMS outreach to contacts with AI-powered responses.
    """

    __tablename__ = "sms_campaigns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True, comment="Owner user ID"
    )

    # Workspace isolation
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Workspace this campaign belongs to",
    )

    # Agent for AI responses (optional - can be manual-only campaign)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Agent that handles AI responses",
    )

    # Campaign details
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Campaign name")
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Campaign description"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=SMSCampaignStatus.DRAFT.value,
        index=True,
        comment="Campaign status",
    )

    # Phone number to send from
    from_phone_number: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Phone number to send from (E.164 format)"
    )

    # Initial message template
    initial_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Initial message template. Supports {first_name}, {company_name} placeholders",
    )

    # AI behavior settings
    ai_enabled: Mapped[bool] = mapped_column(
        default=True, comment="Whether AI auto-responds to replies"
    )
    ai_system_prompt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="System prompt for AI responses (overrides agent default)",
    )
    qualification_criteria: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Criteria for qualifying leads (shown to AI)",
    )

    # Scheduling
    scheduled_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When to start the campaign"
    )
    scheduled_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When to end the campaign"
    )

    # Sending hours (time windows when messages are allowed)
    sending_hours_start: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="Start of daily sending window (e.g., 09:00)"
    )
    sending_hours_end: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="End of daily sending window (e.g., 17:00)"
    )
    sending_days: Mapped[list[int] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Days of week to send (0=Mon, 6=Sun). Null means all days.",
    )
    timezone: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default="UTC", comment="Timezone for sending hours"
    )

    # Rate limiting
    messages_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, comment="Max messages to send per minute"
    )
    max_messages_per_contact: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, comment="Max total messages per contact (including AI)"
    )

    # Follow-up settings
    follow_up_enabled: Mapped[bool] = mapped_column(
        default=False, comment="Whether to send follow-up messages"
    )
    follow_up_delay_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, default=24, comment="Hours to wait before follow-up"
    )
    follow_up_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Follow-up message template"
    )
    max_follow_ups: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, comment="Max follow-up messages to send"
    )

    # Statistics (denormalized for performance)
    total_contacts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Total contacts in campaign"
    )
    messages_sent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Total messages sent"
    )
    messages_delivered: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Messages confirmed delivered"
    )
    messages_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Messages that failed to send"
    )
    replies_received: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Total replies received"
    )
    contacts_qualified: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Contacts marked as qualified"
    )
    contacts_opted_out: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Contacts who opted out"
    )

    # Error tracking
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Most recent error message"
    )
    error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Total number of errors encountered"
    )
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When the last error occurred"
    )

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When the campaign started running"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When the campaign completed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", lazy="selectin")
    agent: Mapped["Agent | None"] = relationship("Agent", lazy="selectin")
    campaign_contacts: Mapped[list["SMSCampaignContact"]] = relationship(
        "SMSCampaignContact",
        back_populates="campaign",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<SMSCampaign(id={self.id}, name={self.name}, status={self.status})>"


class SMSCampaignContact(Base):
    """Junction table linking contacts to SMS campaigns with tracking."""

    __tablename__ = "sms_campaign_contacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sms_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Conversation tracking
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sms_conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Associated conversation thread",
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=SMSCampaignContactStatus.PENDING.value,
        index=True,
        comment="Contact status in this campaign",
    )

    # Message tracking
    messages_sent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of messages sent to this contact"
    )
    messages_received: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of replies from this contact"
    )
    follow_ups_sent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of follow-up messages sent"
    )

    # Timing
    first_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When initial message was sent"
    )
    last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When last message was sent"
    )
    last_reply_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When last reply was received"
    )
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, comment="When to send next follow-up"
    )

    # Qualification
    is_qualified: Mapped[bool] = mapped_column(
        default=False, comment="Whether contact is qualified"
    )
    qualification_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Notes about qualification"
    )
    qualified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When contact was qualified"
    )

    # Opt-out tracking
    opted_out: Mapped[bool] = mapped_column(default=False, comment="Whether contact opted out")
    opted_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When contact opted out"
    )

    # Priority ordering
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Send priority (higher = sooner)"
    )

    # Error tracking
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Last error for this contact"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    campaign: Mapped["SMSCampaign"] = relationship(
        "SMSCampaign", back_populates="campaign_contacts"
    )
    contact: Mapped["Contact"] = relationship("Contact", lazy="selectin")
    conversation: Mapped["SMSConversation | None"] = relationship(
        "SMSConversation", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<SMSCampaignContact(campaign_id={self.campaign_id}, contact_id={self.contact_id}, status={self.status})>"
