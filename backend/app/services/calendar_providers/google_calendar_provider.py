"""Google Calendar provider implementation."""

from typing import Any

import structlog

from app.models.appointment import Appointment
from app.services.calendar_providers.base import CalendarProvider
from app.services.tools.google_calendar_tools import GoogleCalendarTools

logger = structlog.get_logger()


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar provider implementation.

    This provider wraps GoogleCalendarTools and implements the CalendarProvider interface.
    The service client is cached at the GoogleCalendarTools level for performance.
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: str | None = None,
        calendar_id: str = "primary",
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        """Initialize Google Calendar provider.

        Args:
            access_token: OAuth 2.0 access token
            refresh_token: OAuth 2.0 refresh token (for auto-refresh)
            calendar_id: Calendar ID to use (default: "primary")
            client_id: OAuth client ID (for token refresh)
            client_secret: OAuth client secret (for token refresh)
        """
        self.tools = GoogleCalendarTools(
            access_token=access_token,
            refresh_token=refresh_token,
            calendar_id=calendar_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        self.logger = logger.bind(component="google_calendar_provider")

    @property
    def provider_name(self) -> str:
        """Return provider identifier."""
        return "google-calendar"

    async def create_event(
        self,
        appointment: Appointment,
        contact_name: str,
        contact_email: str | None,
        notes: str | None,
    ) -> dict[str, Any]:
        """Create a Google Calendar event.

        Args:
            appointment: Appointment model instance
            contact_name: Full name of attendee
            contact_email: Email of attendee (optional)
            notes: Additional notes for the event

        Returns:
            Dict with success, event_id, event_uid, error
        """
        try:
            # Determine timezone
            timezone = "UTC"
            if appointment.scheduled_at.tzinfo:
                timezone = str(appointment.scheduled_at.tzinfo)

            result = await self.tools.create_event(
                summary=f"Appointment with {contact_name}",
                start_time=appointment.scheduled_at.isoformat(),
                duration_minutes=appointment.duration_minutes,
                attendee_email=contact_email,
                attendee_name=contact_name,
                description=notes or f"Service: {appointment.service_type or 'General'}",
                timezone=timezone,
            )

            if result.get("success"):
                return {
                    "success": True,
                    "event_id": result.get("event_id"),
                    "event_uid": result.get("event_id"),  # Google uses same ID
                    "event_link": result.get("event_link"),
                }

            return result

        except Exception as e:
            self.logger.exception("google_calendar_create_event_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def update_event(
        self,
        event_id: str,
        appointment: Appointment,
    ) -> dict[str, Any]:
        """Update an existing Google Calendar event.

        Args:
            event_id: Google Calendar event ID
            appointment: Updated appointment model

        Returns:
            Dict with success, error
        """
        try:
            result = await self.tools.update_event(
                event_id=event_id,
                start_time=appointment.scheduled_at.isoformat(),
                duration_minutes=appointment.duration_minutes,
                summary=f"Appointment with {appointment.contact.first_name} {appointment.contact.last_name or ''}".strip(),
                description=appointment.notes
                or f"Service: {appointment.service_type or 'General'}",
            )

            return result

        except Exception as e:
            self.logger.exception("google_calendar_update_event_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def cancel_event(
        self,
        event_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Cancel a Google Calendar event.

        Args:
            event_id: Google Calendar event ID
            reason: Cancellation reason (optional)

        Returns:
            Dict with success, error
        """
        try:
            result = await self.tools.cancel_event(
                event_id=event_id,
                reason=reason,
            )

            return result

        except Exception as e:
            self.logger.exception("google_calendar_cancel_event_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def close(self) -> None:
        """Clean up resources."""
        await self.tools.close()
