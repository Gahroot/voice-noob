"""Phone number model for telephony management."""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.workspace import Workspace


class TelephonyProvider(str, Enum):
    """Telephony provider options."""

    TELNYX = "telnyx"
    TWILIO = "twilio"


class PhoneNumberStatus(str, Enum):
    """Phone number status."""

    ACTIVE = "active"
    PENDING = "pending"
    SUSPENDED = "suspended"
    RELEASED = "released"


class PhoneNumber(Base):
    """Phone number for telephony.

    Represents a phone number purchased from a telephony provider (Telnyx/Twilio)
    that can be assigned to agents for making/receiving calls.

    Phone numbers can be scoped to workspaces, allowing different clients
    to have their own dedicated phone numbers.
    """

    __tablename__ = "phone_numbers"
    __table_args__ = (UniqueConstraint("user_id", "phone_number", name="uq_user_phone_number"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True, comment="Owner user ID"
    )

    # Workspace reference (for data isolation between clients/workspaces)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Workspace this phone number belongs to",
    )

    # Phone number details
    phone_number: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="E.164 formatted phone number"
    )
    friendly_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="Human-friendly name for the number"
    )

    # Provider info
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=TelephonyProvider.TELNYX.value,
        comment="Telephony provider: telnyx or twilio",
    )
    provider_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Provider's ID for this phone number",
    )

    # Capabilities
    can_receive_calls: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Can receive inbound calls"
    )
    can_make_calls: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Can make outbound calls"
    )
    can_receive_sms: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Can receive SMS"
    )
    can_send_sms: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Can send SMS"
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=PhoneNumberStatus.ACTIVE.value,
        comment="Phone number status",
    )

    # Assignment (currently assigned to which agent)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Agent currently assigned to this number",
    )

    # Additional metadata
    notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Additional notes about this phone number"
    )

    # Timestamps
    purchased_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When the number was purchased"
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
    workspace: Mapped["Workspace | None"] = relationship("Workspace", lazy="selectin")
    assigned_agent: Mapped["Agent | None"] = relationship("Agent", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<PhoneNumber(id={self.id}, number={self.phone_number}, "
            f"provider={self.provider}, status={self.status})>"
        )
