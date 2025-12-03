"""Cal.com integration tools for voice agents."""

from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


class CalComTools:
    """Cal.com API v2 integration tools.

    Provides tools for:
    - Getting available event types
    - Checking available time slots
    - Creating bookings directly (unlike Calendly which requires scheduling links)
    - Listing bookings
    - Getting booking details
    - Canceling/rescheduling bookings
    """

    BASE_URL = "https://api.cal.com/v2"
    API_VERSION = "2024-08-13"  # Cal.com API version header

    def __init__(self, api_key: str, event_type_id: int | None = None) -> None:
        """Initialize Cal.com tools.

        Args:
            api_key: Cal.com API key
            event_type_id: Optional default event type ID for bookings
        """
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None
        self.event_type_id = event_type_id

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "cal-api-version": self.API_VERSION,
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def get_tool_definitions() -> list[dict[str, Any]]:
        """Get OpenAI function calling tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "calcom_get_event_types",
                    "description": "Get available event types (meeting types) that can be scheduled on Cal.com",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calcom_get_availability",
                    "description": "Get available time slots for booking on a specific date range",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_type_id": {
                                "type": "integer",
                                "description": "The event type ID (from calcom_get_event_types)",
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Start date for availability check (YYYY-MM-DD format)",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date for availability check (YYYY-MM-DD format)",
                            },
                        },
                        "required": ["event_type_id", "start_date", "end_date"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calcom_create_booking",
                    "description": "Create a booking/appointment directly on Cal.com. Unlike Calendly, Cal.com supports direct booking without requiring the customer to click a link.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_type_id": {
                                "type": "integer",
                                "description": "The event type ID to book",
                            },
                            "start_time": {
                                "type": "string",
                                "description": "Start time in ISO 8601 format (e.g., '2024-01-20T10:00:00Z')",
                            },
                            "attendee_email": {
                                "type": "string",
                                "description": "Email of the person booking the appointment",
                            },
                            "attendee_name": {
                                "type": "string",
                                "description": "Full name of the person booking",
                            },
                            "attendee_timezone": {
                                "type": "string",
                                "description": "Attendee's timezone (e.g., 'America/New_York', 'UTC')",
                            },
                            "notes": {
                                "type": "string",
                                "description": "Additional notes or special requests for the booking",
                            },
                        },
                        "required": [
                            "event_type_id",
                            "start_time",
                            "attendee_email",
                            "attendee_name",
                        ],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calcom_list_bookings",
                    "description": "List bookings/appointments, optionally filtered by date range or status",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": ["upcoming", "past", "cancelled"],
                                "description": "Filter bookings by status",
                            },
                            "after_start": {
                                "type": "string",
                                "description": "Filter bookings starting after this date (ISO 8601)",
                            },
                            "before_start": {
                                "type": "string",
                                "description": "Filter bookings starting before this date (ISO 8601)",
                            },
                            "attendee_email": {
                                "type": "string",
                                "description": "Filter bookings by attendee email",
                            },
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calcom_get_booking",
                    "description": "Get details of a specific booking by UID",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "booking_uid": {
                                "type": "string",
                                "description": "The booking UID",
                            },
                        },
                        "required": ["booking_uid"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calcom_cancel_booking",
                    "description": "Cancel a booking/appointment",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "booking_uid": {
                                "type": "string",
                                "description": "The booking UID to cancel",
                            },
                            "reason": {
                                "type": "string",
                                "description": "Reason for cancellation (sent to attendee)",
                            },
                        },
                        "required": ["booking_uid"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calcom_reschedule_booking",
                    "description": "Reschedule an existing booking to a new time",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "booking_uid": {
                                "type": "string",
                                "description": "The booking UID to reschedule",
                            },
                            "new_start_time": {
                                "type": "string",
                                "description": "New start time in ISO 8601 format",
                            },
                            "reason": {
                                "type": "string",
                                "description": "Reason for rescheduling",
                            },
                        },
                        "required": ["booking_uid", "new_start_time"],
                    },
                },
            },
        ]

    async def get_event_types(self) -> dict[str, Any]:
        """Get available event types."""
        try:
            response = await self.client.get("/event-types")

            if response.status_code != HTTPStatus.OK:
                return {
                    "success": False,
                    "error": f"Failed to get event types: {response.text}",
                }

            data = response.json()
            event_types = []

            # Cal.com v2 API returns event types in 'data' field
            for et in data.get("data", []):
                event_types.append(
                    {
                        "id": et["id"],
                        "title": et.get("title", et.get("slug")),
                        "slug": et["slug"],
                        "length": et.get("lengthInMinutes", et.get("length")),
                        "description": et.get("description"),
                    }
                )

            return {"success": True, "event_types": event_types}

        except Exception as e:
            logger.exception("calcom_get_event_types_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def get_availability(
        self, event_type_id: int, start_date: str, end_date: str
    ) -> dict[str, Any]:
        """Get available time slots for an event type.

        Args:
            event_type_id: Event type ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        """
        try:
            # Cal.com v2 API uses /slots endpoint with query params
            params: dict[str, str | int] = {
                "eventTypeId": event_type_id,
                "start": f"{start_date}T00:00:00Z",
                "end": f"{end_date}T23:59:59Z",
            }

            response = await self.client.get("/slots/", params=params)

            if response.status_code != HTTPStatus.OK:
                return {
                    "success": False,
                    "error": f"Failed to get availability: {response.text}",
                }

            data = response.json()
            slots = []

            # Cal.com returns slots grouped by date
            slots_data = data.get("data", {}).get("slots", {})
            for _date_key, date_slots in slots_data.items():
                for slot in date_slots:
                    slots.append(
                        {
                            "start_time": slot["time"],
                            "duration_minutes": event_type_id,  # Get from event type
                        }
                    )

            return {"success": True, "available_slots": slots, "total": len(slots)}

        except Exception as e:
            logger.exception("calcom_get_availability_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def create_booking(
        self,
        event_type_id: int,
        start_time: str,
        attendee_email: str,
        attendee_name: str,
        attendee_timezone: str = "UTC",
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Create a booking directly on Cal.com.

        Args:
            event_type_id: Event type to book
            start_time: Start time in ISO 8601 format (e.g., '2024-01-20T10:00:00Z')
            attendee_email: Attendee email
            attendee_name: Attendee full name
            attendee_timezone: Attendee timezone (default: UTC)
            notes: Optional notes
        """
        try:
            # Payload structure matching working implementations from livekit/agents and agno-agi
            payload: dict[str, Any] = {
                "start": start_time,  # ISO 8601 format in UTC
                "eventTypeId": event_type_id,
                "attendee": {
                    "name": attendee_name,
                    "email": attendee_email,
                    "timeZone": attendee_timezone,
                },
            }

            if notes:
                payload["metadata"] = {"notes": notes}

            response = await self.client.post("/bookings", json=payload)

            if response.status_code not in (HTTPStatus.OK, HTTPStatus.CREATED):
                return {
                    "success": False,
                    "error": f"Failed to create booking: {response.text}",
                }

            booking = response.json().get("data", {})

            return {
                "success": True,
                "message": f"Booking created successfully for {attendee_name}",
                "booking": {
                    "uid": booking.get("uid"),
                    "id": booking.get("id"),
                    "title": booking.get("title"),
                    "start_time": booking.get("startTime"),
                    "end_time": booking.get("endTime"),
                    "attendee_email": attendee_email,
                    "attendee_name": attendee_name,
                    "status": booking.get("status"),
                },
            }

        except Exception as e:
            logger.exception("calcom_create_booking_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def list_bookings(
        self,
        status: str | None = None,
        after_start: str | None = None,
        before_start: str | None = None,
        attendee_email: str | None = None,
    ) -> dict[str, Any]:
        """List bookings."""
        try:
            params: dict[str, Any] = {}

            if status:
                params["status"] = status
            if after_start:
                params["afterStart"] = after_start
            if before_start:
                params["beforeStart"] = before_start
            if attendee_email:
                params["attendeeEmail"] = attendee_email

            response = await self.client.get("/bookings", params=params)

            if response.status_code != HTTPStatus.OK:
                return {
                    "success": False,
                    "error": f"Failed to list bookings: {response.text}",
                }

            data = response.json()
            bookings = []

            for booking in data.get("data", []):
                bookings.append(
                    {
                        "uid": booking.get("uid"),
                        "id": booking.get("id"),
                        "title": booking.get("title"),
                        "start_time": booking.get("startTime"),
                        "end_time": booking.get("endTime"),
                        "status": booking.get("status"),
                        "attendees": [
                            {
                                "name": att.get("name"),
                                "email": att.get("email"),
                            }
                            for att in booking.get("attendees", [])
                        ],
                    }
                )

            return {"success": True, "bookings": bookings, "total": len(bookings)}

        except Exception as e:
            logger.exception("calcom_list_bookings_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def get_booking(self, booking_uid: str) -> dict[str, Any]:
        """Get details of a specific booking."""
        try:
            response = await self.client.get(f"/bookings/{booking_uid}")

            if response.status_code != HTTPStatus.OK:
                return {
                    "success": False,
                    "error": f"Failed to get booking: {response.text}",
                }

            booking = response.json().get("data", {})

            return {
                "success": True,
                "booking": {
                    "uid": booking.get("uid"),
                    "id": booking.get("id"),
                    "title": booking.get("title"),
                    "description": booking.get("description"),
                    "start_time": booking.get("startTime"),
                    "end_time": booking.get("endTime"),
                    "status": booking.get("status"),
                    "attendees": [
                        {
                            "name": att.get("name"),
                            "email": att.get("email"),
                            "timezone": att.get("timeZone"),
                        }
                        for att in booking.get("attendees", [])
                    ],
                    "location": booking.get("location"),
                    "metadata": booking.get("metadata"),
                },
            }

        except Exception as e:
            logger.exception("calcom_get_booking_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def cancel_booking(self, booking_uid: str, reason: str | None = None) -> dict[str, Any]:
        """Cancel a booking."""
        try:
            # Cal.com API accepts cancellation reason as query param or in request body via POST
            # Using query params for simplicity
            params: dict[str, str] = {}
            if reason:
                params["cancellationReason"] = reason

            response = await self.client.delete(f"/bookings/{booking_uid}", params=params)

            if response.status_code not in (HTTPStatus.OK, HTTPStatus.NO_CONTENT):
                return {
                    "success": False,
                    "error": f"Failed to cancel booking: {response.text}",
                }

            return {
                "success": True,
                "message": f"Booking {booking_uid} has been canceled",
                "reason": reason,
            }

        except Exception as e:
            logger.exception("calcom_cancel_booking_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def reschedule_booking(
        self, booking_uid: str, new_start_time: str, reason: str | None = None
    ) -> dict[str, Any]:
        """Reschedule a booking to a new time."""
        try:
            payload: dict[str, Any] = {
                "start": new_start_time,
            }

            if reason:
                payload["reschedulingReason"] = reason

            # Cal.com uses PATCH for rescheduling
            response = await self.client.patch(f"/bookings/{booking_uid}/reschedule", json=payload)

            if response.status_code != HTTPStatus.OK:
                return {
                    "success": False,
                    "error": f"Failed to reschedule booking: {response.text}",
                }

            booking = response.json().get("data", {})

            return {
                "success": True,
                "message": f"Booking {booking_uid} has been rescheduled",
                "booking": {
                    "uid": booking.get("uid"),
                    "new_start_time": booking.get("startTime"),
                    "new_end_time": booking.get("endTime"),
                },
            }

        except Exception as e:
            logger.exception("calcom_reschedule_booking_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a Cal.com tool by name."""
        tool_map: dict[str, ToolHandler] = {
            "calcom_get_event_types": self.get_event_types,
            "calcom_get_availability": self.get_availability,
            "calcom_create_booking": self.create_booking,
            "calcom_list_bookings": self.list_bookings,
            "calcom_get_booking": self.get_booking,
            "calcom_cancel_booking": self.cancel_booking,
            "calcom_reschedule_booking": self.reschedule_booking,
        }

        handler = tool_map.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        result: dict[str, Any] = await handler(**arguments)
        return result
