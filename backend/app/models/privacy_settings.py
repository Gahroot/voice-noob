"""Privacy and compliance settings model."""

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConsentType(str, Enum):
    """Types of consent that can be recorded."""

    DATA_PROCESSING = "data_processing"
    CALL_RECORDING = "call_recording"
    MARKETING = "marketing"
    THIRD_PARTY_SHARING = "third_party_sharing"


class PrivacySettings(Base):
    """User privacy settings and preferences."""

    __tablename__ = "privacy_settings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    # GDPR Settings
    privacy_policy_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    privacy_policy_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_retention_days: Mapped[int] = mapped_column(Integer, default=365, nullable=False)

    # DPA/Contract tracking
    openai_dpa_signed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    openai_dpa_signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    telnyx_dpa_signed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    telnyx_dpa_signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deepgram_dpa_signed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deepgram_dpa_signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    elevenlabs_dpa_signed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    elevenlabs_dpa_signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # CCPA Settings
    ccpa_opt_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ccpa_opt_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Data export tracking
    last_data_export_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_data_export_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    def __repr__(self) -> str:
        return f"<PrivacySettings(user_id={self.user_id})>"


class ConsentRecord(Base):
    """Record of user consent for GDPR compliance."""

    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    consent_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ConsentRecord(user_id={self.user_id}, type={self.consent_type}, granted={self.granted})>"
