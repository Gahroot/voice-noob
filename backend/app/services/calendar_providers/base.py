"""Abstract base class for calendar provider implementations."""

from abc import ABC, abstractmethod
from typing import Any

from app.models.appointment import Appointment


class CalendarProvider(ABC):
    """Abstract base class for calendar provider integrations.

    All calendar providers must implement this interface to ensure
    consistent behavior across different calendar systems.
    """

    @abstractmethod
    async def create_event(
        self,
        appointment: Appointment,
        contact_name: str,
        contact_email: str | None,
        notes: str | None,
    ) -> dict[str, Any]:
        """Create a calendar event.

        Args:
            appointment: Appointment model instance
            contact_name: Full name of attendee
            contact_email: Email of attendee (optional)
            notes: Additional notes for the event

        Returns:
            Dict with keys:
            - success: bool
            - event_id: str | None (provider's unique event ID)
            - event_uid: str | None (for providers like Cal.com)
            - error: str | None
        """

    @abstractmethod
    async def update_event(
        self,
        event_id: str,
        appointment: Appointment,
    ) -> dict[str, Any]:
        """Update an existing calendar event.

        Args:
            event_id: Provider's event ID or UID
            appointment: Updated appointment model

        Returns:
            Dict with keys:
            - success: bool
            - error: str | None
        """

    @abstractmethod
    async def cancel_event(
        self,
        event_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Cancel/delete a calendar event.

        Args:
            event_id: Provider's event ID or UID
            reason: Cancellation reason (optional)

        Returns:
            Dict with keys:
            - success: bool
            - error: str | None
        """

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources (HTTP clients, etc.)."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier (e.g., 'cal-com', 'google-calendar')."""
