"""Contact model for CRM."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.call_interaction import CallInteraction


class Contact(Base, TimestampMixin):
    """Contact model for CRM - represents people who call or are called by voice agents."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Basic info
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Optional company info
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Lead/contact management
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="new",
        index=True,
    )  # new, contacted, qualified, converted, lost

    # Tags as comma-separated values (simple approach)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, deferred=True)

    # Relationships
    appointments: Mapped[list["Appointment"]] = relationship(
        "Appointment",
        back_populates="contact",
        cascade="all, delete-orphan",
    )
    call_interactions: Mapped[list["CallInteraction"]] = relationship(
        "CallInteraction",
        back_populates="contact",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Contact {self.first_name} {self.last_name} ({self.phone_number})>"
