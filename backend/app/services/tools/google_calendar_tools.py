"""Google Calendar integration tools for voice agents."""

from datetime import datetime, timedelta
from typing import Any

import structlog
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build  # type: ignore[import-untyped]
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]

logger = structlog.get_logger()


class GoogleCalendarTools:
    """Google Calendar API v3 integration tools.

    Provides tools for:
    - Creating calendar events when appointments are booked
    - Updating events when appointments are rescheduled
    - Canceling events when appointments are cancelled
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: str | None = None,
        calendar_id: str = "primary",
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        """Initialize Google Calendar tools.

        Args:
            access_token: OAuth 2.0 access token
            refresh_token: OAuth 2.0 refresh token (for auto-refresh)
            calendar_id: Calendar ID to use (default: "primary")
            client_id: OAuth client ID (for token refresh)
            client_secret: OAuth client secret (for token refresh)
        """
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.calendar_id = calendar_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._service = None
        self.logger = logger.bind(component="google_calendar_tools")

    def _get_service(self) -> Any:
        """Get or create Google Calendar service client."""
        if self._service is None:
            # Create credentials from access token
            creds = Credentials(  # type: ignore[no-untyped-call]
                token=self.access_token,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",  # noqa: S106
                client_id=self.client_id,
                client_secret=self.client_secret,
            )

            self._service = build("calendar", "v3", credentials=creds)

        return self._service

    async def create_event(
        self,
        summary: str,
        start_time: str,
        duration_minutes: int,
        attendee_email: str | None = None,
        attendee_name: str | None = None,
        description: str | None = None,
        timezone: str = "UTC",
    ) -> dict[str, Any]:
        """Create a calendar event.

        Args:
            summary: Event title/summary
            start_time: Start time in ISO 8601 format
            duration_minutes: Event duration in minutes
            attendee_email: Optional attendee email
            attendee_name: Optional attendee name
            description: Optional event description
            timezone: Timezone (default: UTC)

        Returns:
            Event creation result with event_id
        """
        try:
            service = self._get_service()

            # Parse start time
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))

            # Calculate end time
            end_dt = start_dt + timedelta(minutes=duration_minutes)

            # Build event body
            event = {
                "summary": summary,
                "description": description or "",
                "start": {
                    "dateTime": start_dt.isoformat(),
                    "timeZone": timezone,
                },
                "end": {
                    "dateTime": end_dt.isoformat(),
                    "timeZone": timezone,
                },
            }

            # Add attendee if provided
            if attendee_email:
                attendees: list[dict[str, str]] = [
                    {
                        "email": attendee_email,
                        "displayName": attendee_name or attendee_email,
                    }
                ]
                event["attendees"] = attendees  # type: ignore[assignment]

            # Create event
            created_event = (
                service.events()
                .insert(
                    calendarId=self.calendar_id,
                    body=event,
                    sendUpdates="all" if attendee_email else "none",
                )
                .execute()
            )

            self.logger.info(
                "google_calendar_event_created",
                event_id=created_event.get("id"),
                summary=summary,
                start_time=start_time,
            )

            return {
                "success": True,
                "event_id": created_event.get("id"),
                "event_link": created_event.get("htmlLink"),
                "message": f"Event '{summary}' created successfully",
            }

        except HttpError as e:
            self.logger.exception(
                "google_calendar_create_event_error",
                error=str(e),
                status_code=e.resp.status,
            )
            return {
                "success": False,
                "error": f"Google Calendar API error: {e._get_reason()}",  # noqa: SLF001
            }
        except Exception as e:
            self.logger.exception("google_calendar_create_event_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def update_event(
        self,
        event_id: str,
        start_time: str | None = None,
        duration_minutes: int | None = None,
        summary: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing calendar event.

        Args:
            event_id: Google Calendar event ID
            start_time: New start time (optional)
            duration_minutes: New duration (optional)
            summary: New summary (optional)
            description: New description (optional)

        Returns:
            Update result
        """
        try:
            service = self._get_service()

            # Get existing event
            event = service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()

            # Update fields if provided
            if summary:
                event["summary"] = summary

            if description is not None:
                event["description"] = description

            if start_time:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                event["start"]["dateTime"] = start_dt.isoformat()

                if duration_minutes:
                    end_dt = start_dt + timedelta(minutes=duration_minutes)
                    event["end"]["dateTime"] = end_dt.isoformat()

            # Update event
            updated_event = (
                service.events()
                .update(
                    calendarId=self.calendar_id, eventId=event_id, body=event, sendUpdates="all"
                )
                .execute()
            )

            self.logger.info(
                "google_calendar_event_updated",
                event_id=event_id,
            )

            return {
                "success": True,
                "event_id": updated_event.get("id"),
                "message": "Event updated successfully",
            }

        except HttpError as e:
            self.logger.exception(
                "google_calendar_update_event_error",
                error=str(e),
                event_id=event_id,
            )
            return {
                "success": False,
                "error": f"Google Calendar API error: {e._get_reason()}",  # noqa: SLF001
            }
        except Exception as e:
            self.logger.exception("google_calendar_update_event_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def cancel_event(
        self,
        event_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Cancel (delete) a calendar event.

        Args:
            event_id: Google Calendar event ID
            reason: Cancellation reason (added to description)

        Returns:
            Cancellation result
        """
        try:
            service = self._get_service()

            if reason:
                # Add cancellation reason to description before deleting
                event = (
                    service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()
                )

                event["description"] = f"{event.get('description', '')}\n\nCancelled: {reason}"
                event["status"] = "cancelled"

                service.events().update(
                    calendarId=self.calendar_id, eventId=event_id, body=event, sendUpdates="all"
                ).execute()
            else:
                # Delete event directly
                service.events().delete(
                    calendarId=self.calendar_id, eventId=event_id, sendUpdates="all"
                ).execute()

            self.logger.info(
                "google_calendar_event_cancelled",
                event_id=event_id,
                reason=reason,
            )

            return {
                "success": True,
                "message": "Event cancelled successfully",
            }

        except HttpError as e:
            self.logger.exception(
                "google_calendar_cancel_event_error",
                error=str(e),
                event_id=event_id,
            )
            return {
                "success": False,
                "error": f"Google Calendar API error: {e._get_reason()}",  # noqa: SLF001
            }
        except Exception as e:
            self.logger.exception("google_calendar_cancel_event_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def close(self) -> None:
        """Close resources (no-op for Google client)."""
