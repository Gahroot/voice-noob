"""Cal.com provider implementation."""

from typing import Any

import structlog

from app.models.appointment import Appointment
from app.services.calendar_providers.base import CalendarProvider
from app.services.tools.calcom_tools import CalComTools

logger = structlog.get_logger()


class CalComProvider(CalendarProvider):
    """Cal.com provider implementation.

    Cal.com supports direct booking via API, making it ideal for voice agents.
    """

    def __init__(
        self,
        api_key: str,
        event_type_id: int | None = None,
    ) -> None:
        """Initialize Cal.com provider.

        Args:
            api_key: Cal.com API key
            event_type_id: Optional default event type ID for bookings
        """
        self.tools = CalComTools(api_key=api_key, event_type_id=event_type_id)
        self.logger = logger.bind(component="calcom_provider")

    @property
    def provider_name(self) -> str:
        """Return provider identifier."""
        return "cal-com"

    async def create_event(
        self,
        appointment: Appointment,
        contact_name: str,
        contact_email: str | None,
        notes: str | None,
    ) -> dict[str, Any]:
        """Create a Cal.com booking.

        Args:
            appointment: Appointment model instance
            contact_name: Full name of attendee
            contact_email: Email of attendee (optional)
            notes: Additional notes for the booking

        Returns:
            Dict with success, event_id, event_uid, error
        """
        try:
            # Determine timezone
            timezone = "UTC"
            if appointment.scheduled_at.tzinfo:
                timezone = str(appointment.scheduled_at.tzinfo)

            # Use default event type ID or raise error
            event_type_id = self.tools.event_type_id
            if not event_type_id:
                return {
                    "success": False,
                    "error": "No event_type_id configured for Cal.com provider",
                }

            result = await self.tools.create_booking(
                event_type_id=event_type_id,
                start_time=appointment.scheduled_at.isoformat(),
                attendee_email=contact_email or "noemail@example.com",
                attendee_name=contact_name,
                attendee_timezone=timezone,
                notes=notes,
            )

            if result.get("success"):
                booking = result.get("booking", {})
                return {
                    "success": True,
                    "event_id": str(booking.get("id")),
                    "event_uid": booking.get("uid"),
                }

            return result

        except Exception as e:
            self.logger.exception("calcom_create_booking_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def update_event(
        self,
        event_id: str,
        appointment: Appointment,
    ) -> dict[str, Any]:
        """Reschedule a Cal.com booking.

        Args:
            event_id: Cal.com booking UID
            appointment: Updated appointment model

        Returns:
            Dict with success, error
        """
        try:
            result = await self.tools.reschedule_booking(
                booking_uid=event_id,
                new_start_time=appointment.scheduled_at.isoformat(),
                reason="Appointment rescheduled",
            )

            return result

        except Exception as e:
            self.logger.exception("calcom_reschedule_booking_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def cancel_event(
        self,
        event_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Cancel a Cal.com booking.

        Args:
            event_id: Cal.com booking UID
            reason: Cancellation reason (optional)

        Returns:
            Dict with success, error
        """
        try:
            result = await self.tools.cancel_booking(
                booking_uid=event_id,
                reason=reason or "Appointment cancelled",
            )

            return result

        except Exception as e:
            self.logger.exception("calcom_cancel_booking_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def close(self) -> None:
        """Clean up resources."""
        await self.tools.close()
