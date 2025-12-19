"""Calendly provider implementation."""

from typing import Any

import structlog

from app.models.appointment import Appointment
from app.services.calendar_providers.base import CalendarProvider
from app.services.tools.calendly_tools import CalendlyTools

logger = structlog.get_logger()


class CalendlyProvider(CalendarProvider):
    """Calendly provider implementation.

    Note: Calendly API does not support direct booking. This provider creates
    scheduling links that customers must use to self-schedule. For sync purposes,
    we can only cancel existing events.
    """

    def __init__(
        self,
        access_token: str,
    ) -> None:
        """Initialize Calendly provider.

        Args:
            access_token: Calendly Personal Access Token
        """
        self.tools = CalendlyTools(access_token=access_token)
        self.logger = logger.bind(component="calendly_provider")

    @property
    def provider_name(self) -> str:
        """Return provider identifier."""
        return "calendly"

    async def create_event(
        self,
        _appointment: Appointment,
        contact_name: str,
        contact_email: str | None,
        _notes: str | None,
    ) -> dict[str, Any]:
        """Create a Calendly scheduling link.

        Note: Calendly does not support direct booking. This creates a one-time
        scheduling link that the customer must visit to complete booking.

        Args:
            _appointment: Appointment model instance (not used - API limitation)
            contact_name: Full name of attendee
            contact_email: Email of attendee (optional)
            _notes: Additional notes (not used - API limitation)

        Returns:
            Dict with success=False and explanatory error message
        """
        try:
            # Calendly API limitation: cannot create appointments directly
            # Only create scheduling links
            self.logger.warning(
                "calendly_direct_booking_not_supported",
                contact_email=contact_email,
                note="Calendly API does not support direct booking. Customer must use scheduling link.",
            )

            # Could create a scheduling link, but that doesn't actually book the appointment
            if contact_email:
                result = await self.tools.create_scheduling_link(
                    invitee_email=contact_email,
                    invitee_name=contact_name,
                )

                if result.get("success"):
                    self.logger.info(
                        "calendly_scheduling_link_created",
                        booking_url=result.get("booking_url"),
                    )

                    return {
                        "success": False,
                        "error": "Calendly requires customer to self-schedule via link. Created scheduling link but appointment not booked.",
                        "booking_url": result.get("booking_url"),
                    }

            return {
                "success": False,
                "error": "Calendly API does not support direct appointment booking. Use Cal.com or Google Calendar for automated booking.",
            }

        except Exception as e:
            self.logger.exception("calendly_create_event_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def update_event(
        self,
        event_id: str,
        _appointment: Appointment,
    ) -> dict[str, Any]:
        """Update a Calendly event.

        Note: Calendly API does not support rescheduling via API.

        Args:
            event_id: Calendly event UUID
            _appointment: Updated appointment model (not used - API limitation)

        Returns:
            Dict with success=False and explanatory error message
        """
        self.logger.warning(
            "calendly_reschedule_not_supported",
            event_uuid=event_id,
            note="Calendly API does not support rescheduling. Customer must reschedule via Calendly link.",
        )

        return {
            "success": False,
            "error": "Calendly API does not support rescheduling. Customer must reschedule via Calendly.",
        }

    async def cancel_event(
        self,
        event_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Cancel a Calendly event.

        Args:
            event_id: Calendly event UUID
            reason: Cancellation reason (optional)

        Returns:
            Dict with success, error
        """
        try:
            result = await self.tools.cancel_event(
                event_uuid=event_id,
                reason=reason,
            )

            return result

        except Exception as e:
            self.logger.exception("calendly_cancel_event_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def close(self) -> None:
        """Clean up resources."""
        await self.tools.close()
