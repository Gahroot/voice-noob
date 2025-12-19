"""CRM tools for voice agents - bookings, contacts, appointments."""

import re
import uuid
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.integrations import get_workspace_integrations
from app.core.auth import user_id_to_uuid
from app.core.cache import cache_invalidate
from app.models.appointment import Appointment
from app.models.calendar_sync import CalendarSyncQueue
from app.models.contact import Contact

logger = structlog.get_logger()


class CRMTools:
    """Internal CRM tools for voice agents.

    Provides tools for:
    - Looking up customers by phone/email/name
    - Creating new contacts
    - Checking appointment availability
    - Booking appointments
    - Viewing upcoming appointments
    - Canceling appointments
    """

    def __init__(
        self,
        db: AsyncSession,
        user_id: int,
        workspace_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize CRM tools.

        Args:
            db: Database session
            user_id: User ID (agent owner) - integer matching Contact.user_id
            workspace_id: Workspace UUID for scoping contacts
        """
        self.db = db
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.logger = logger.bind(
            component="crm_tools", user_id=user_id, workspace_id=str(workspace_id)
        )

    async def _enqueue_calendar_sync(self, appointment: Appointment, operation: str) -> None:
        """Enqueue appointment for sync to external calendars.

        Args:
            appointment: Appointment to sync
            operation: Sync operation (create, update, cancel)
        """
        if not appointment.workspace_id:
            self.logger.debug("skipping_calendar_sync_no_workspace")
            return

        try:
            # Get workspace integrations
            integrations = await get_workspace_integrations(
                user_id=user_id_to_uuid(self.user_id),
                workspace_id=appointment.workspace_id,
                db=self.db,
            )

            # Queue sync for each connected calendar provider
            for provider in ["cal-com", "calendly", "gohighlevel", "google-calendar"]:
                if provider in integrations:
                    # DEDUPLICATION: Check if pending sync already exists
                    existing = await self.db.execute(
                        select(CalendarSyncQueue).where(
                            CalendarSyncQueue.appointment_id == appointment.id,
                            CalendarSyncQueue.calendar_provider == provider,
                            CalendarSyncQueue.operation == operation,
                            CalendarSyncQueue.status.in_(["pending", "processing"]),
                        )
                    )
                    if existing.scalar_one_or_none():
                        self.logger.debug(
                            "sync_already_queued_skipping",
                            appointment_id=appointment.id,
                            provider=provider,
                            operation=operation,
                        )
                        continue

                    sync_entry = CalendarSyncQueue(
                        id=uuid.uuid4(),
                        appointment_id=appointment.id,
                        workspace_id=appointment.workspace_id,
                        operation=operation,
                        calendar_provider=provider,
                        payload={
                            "appointment_id": appointment.id,
                            "scheduled_at": appointment.scheduled_at.isoformat(),
                            "duration_minutes": appointment.duration_minutes,
                            "service_type": appointment.service_type,
                            "notes": appointment.notes,
                        },
                    )
                    self.db.add(sync_entry)

                    self.logger.info(
                        "calendar_sync_enqueued",
                        appointment_id=appointment.id,
                        provider=provider,
                        operation=operation,
                    )

            await self.db.commit()
        except Exception as e:
            self.logger.exception(
                "failed_to_enqueue_calendar_sync",
                appointment_id=appointment.id,
                error=str(e),
            )
            # Don't raise - sync failure shouldn't block appointment creation

    @staticmethod
    def get_tool_definitions() -> list[dict[str, Any]]:
        """Get OpenAI function calling tool definitions.

        Returns:
            List of tool definitions for GPT Realtime API (uses nested function format)
        """
        return [
            {
                "type": "function",
                "name": "search_customer",
                "description": "Search for a customer by phone number, email, or name",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Phone number, email, or name to search for",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "type": "function",
                "name": "create_contact",
                "description": "Create a new contact/customer in the CRM. REQUIRED: first_name and phone_number. OPTIONAL: last_name, email, company_name. Do NOT ask for optional fields unless the customer volunteers the information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "first_name": {
                            "type": "string",
                            "description": "REQUIRED. Customer's first name. Cannot be empty.",
                        },
                        "phone_number": {
                            "type": "string",
                            "description": "REQUIRED. Customer's phone number (7-20 digits). Format: digits only or E.164 format.",
                        },
                        "last_name": {
                            "type": "string",
                            "description": "OPTIONAL. Customer's last name. Only collect if volunteered.",
                        },
                        "email": {
                            "type": "string",
                            "description": "OPTIONAL. Customer's email address. Only collect if volunteered.",
                        },
                        "company_name": {
                            "type": "string",
                            "description": "OPTIONAL. Company or organization name. Only collect if volunteered.",
                        },
                    },
                    "required": ["first_name", "phone_number"],
                },
            },
            {
                "type": "function",
                "name": "check_availability",
                "description": "Check available appointment time slots for a specific date",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Date to check in YYYY-MM-DD format",
                        },
                        "duration_minutes": {
                            "type": "integer",
                            "description": "Desired appointment duration in minutes (default 30)",
                        },
                    },
                    "required": ["date"],
                },
            },
            {
                "type": "function",
                "name": "parse_date",
                "description": "Convert natural language date/time (like 'Tuesday at 9am', 'next Thursday 2pm', 'tomorrow at 3') into proper ISO 8601 format for booking. Use this BEFORE booking if you have ambiguous dates.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date_expression": {
                            "type": "string",
                            "description": "Natural language date/time like 'Tuesday at 9am', 'next week', 'tomorrow 2pm'",
                        },
                    },
                    "required": ["date_expression"],
                },
            },
            {
                "type": "function",
                "name": "book_appointment",
                "description": "Book an appointment for a customer",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "contact_phone": {
                            "type": "string",
                            "description": "Customer's phone number",
                        },
                        "scheduled_at": {
                            "type": "string",
                            "description": "Appointment date and time in ISO 8601 format (YYYY-MM-DDTHH:MM:SS)",
                        },
                        "duration_minutes": {
                            "type": "integer",
                            "description": "Duration in minutes (default 30)",
                        },
                        "service_type": {
                            "type": "string",
                            "description": "Type of service/appointment",
                        },
                        "notes": {"type": "string", "description": "Additional notes"},
                    },
                    "required": ["contact_phone", "scheduled_at"],
                },
            },
            {
                "type": "function",
                "name": "list_appointments",
                "description": "List upcoming appointments, optionally filtered by date or contact",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "contact_phone": {
                            "type": "string",
                            "description": "Filter by customer phone number",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format",
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by status (scheduled, completed, cancelled, no_show)",
                        },
                    },
                    "required": [],
                },
            },
            {
                "type": "function",
                "name": "cancel_appointment",
                "description": "Cancel an existing appointment",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "integer",
                            "description": "Appointment ID to cancel",
                        },
                        "reason": {"type": "string", "description": "Cancellation reason"},
                    },
                    "required": ["appointment_id"],
                },
            },
            {
                "type": "function",
                "name": "reschedule_appointment",
                "description": "Reschedule an existing appointment to a new time",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "integer",
                            "description": "Appointment ID to reschedule",
                        },
                        "new_scheduled_at": {
                            "type": "string",
                            "description": "New appointment time in ISO 8601 format",
                        },
                    },
                    "required": ["appointment_id", "new_scheduled_at"],
                },
            },
        ]

    async def search_customer(self, query: str) -> dict[str, Any]:
        """Search for a customer by phone, email, or name.

        Args:
            query: Search query

        Returns:
            Customer information or error
        """
        try:
            # Search by phone, email, or name - filtered by workspace_id for proper scoping
            # Falls back to user_id if workspace_id not available (backward compatibility)
            # Also search full name (first + last) for queries like "John Smith"
            full_name = func.concat(Contact.first_name, " ", func.coalesce(Contact.last_name, ""))

            # Build base query with search conditions
            search_conditions = (
                (Contact.phone_number.ilike(f"%{query}%"))
                | (Contact.email.ilike(f"%{query}%"))
                | (Contact.first_name.ilike(f"%{query}%"))
                | (Contact.last_name.ilike(f"%{query}%"))
                | (full_name.ilike(f"%{query}%"))
            )

            # Scope by workspace if available, otherwise by user
            if self.workspace_id:
                stmt = select(Contact).where(
                    Contact.workspace_id == self.workspace_id,
                    search_conditions,
                )
            else:
                stmt = select(Contact).where(
                    Contact.user_id == self.user_id,
                    search_conditions,
                )

            result = await self.db.execute(stmt)
            contacts = list(result.scalars().all())

            if not contacts:
                return {
                    "success": True,
                    "found": False,
                    "message": f"No customer found matching '{query}'",
                }

            # Return first match (or all if multiple)
            customer_data = [
                {
                    "id": c.id,
                    "name": f"{c.first_name} {c.last_name or ''}".strip(),
                    "phone": c.phone_number,
                    "email": c.email,
                    "company": c.company_name,
                    "status": c.status,
                }
                for c in contacts[:3]  # Limit to 3 results
            ]

            return {
                "success": True,
                "found": True,
                "count": len(customer_data),
                "customers": customer_data,
            }

        except Exception as e:
            self.logger.exception("search_customer_failed", query=query, error=str(e))
            return {"success": False, "error": str(e)}

    async def create_contact(
        self,
        first_name: str,
        phone_number: str,
        last_name: str | None = None,
        email: str | None = None,
        company_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a new contact.

        Args:
            first_name: First name
            phone_number: Phone number
            last_name: Last name
            email: Email
            company_name: Company

        Returns:
            Created contact info
        """
        try:
            contact = Contact(
                user_id=self.user_id,
                workspace_id=self.workspace_id,
                first_name=first_name,
                last_name=last_name,
                phone_number=phone_number,
                email=email,
                company_name=company_name,
                status="new",
            )

            self.db.add(contact)
            await self.db.commit()
            await self.db.refresh(contact)

            # Invalidate CRM caches so new contacts appear immediately in the UI
            try:
                await cache_invalidate(f"crm:contacts:list:{self.user_id}:*")
                await cache_invalidate("crm:stats:*")
                self.logger.debug("invalidated_crm_cache_after_create_contact")
            except Exception:
                self.logger.exception("failed_to_invalidate_cache_after_create_contact")

            return {
                "success": True,
                "contact_id": contact.id,
                "message": f"Created contact for {first_name} {last_name or ''}",
            }

        except Exception as e:
            self.logger.exception("create_contact_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def check_availability(
        self,
        date: str,
        duration_minutes: int = 30,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Check available time slots for a date.

        Args:
            date: Date in YYYY-MM-DD format
            duration_minutes: Desired duration (reserved for future use)

        Returns:
            Available time slots
        """
        try:
            # Parse date
            target_date = datetime.strptime(date, "%Y-%m-%d").date()

            # Get existing appointments for that day - filtered by workspace or user
            base_stmt = (
                select(Appointment)
                .join(Contact)
                .where(
                    Appointment.scheduled_at >= datetime.combine(target_date, datetime.min.time()),
                    Appointment.scheduled_at < datetime.combine(target_date, datetime.max.time()),
                    Appointment.status == "scheduled",
                )
            )

            if self.workspace_id:
                stmt = base_stmt.where(Contact.workspace_id == self.workspace_id)
            else:
                stmt = base_stmt.where(Contact.user_id == self.user_id)

            result = await self.db.execute(stmt)
            booked_appointments = list(result.scalars().all())

            # Simple availability: 9 AM to 5 PM, hourly slots
            available_slots = []
            for hour in range(9, 17):  # 9 AM to 5 PM
                slot_time = datetime.combine(target_date, datetime.min.time()).replace(hour=hour)

                # Check if slot conflicts with existing appointments
                is_available = True
                for apt in booked_appointments:
                    if apt.scheduled_at.hour == hour:
                        is_available = False
                        break

                if is_available:
                    available_slots.append(slot_time.isoformat())

            return {
                "success": True,
                "date": date,
                "available_slots": available_slots,
                "total_available": len(available_slots),
            }

        except Exception as e:
            self.logger.exception("check_availability_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def parse_date(self, date_expression: str) -> dict[str, Any]:  # noqa: PLR0912, PLR0915
        """Parse natural language date/time into ISO 8601 format.

        Args:
            date_expression: Natural language like "Tuesday at 9am", "next Thursday 2pm"

        Returns:
            Parsed datetime in ISO 8601 format with timezone
        """
        try:
            # Get workspace timezone from user settings
            from zoneinfo import ZoneInfo

            from app.crud import get_user_api_keys  # type: ignore[import-untyped]

            user_settings = await get_user_api_keys(
                uuid.UUID(int=self.user_id), self.db, workspace_id=self.workspace_id
            )
            tz_name = user_settings.timezone if user_settings else "America/New_York"
            tz = ZoneInfo(tz_name)

            # Get current time in workspace timezone
            now = datetime.now(tz)

            # Normalize input
            text = date_expression.lower().strip()

            # Parse time (e.g., "9am", "2pm", "14:00", "9:30am")
            time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
            hour = 9  # default
            minute = 0

            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                am_pm = time_match.group(3)

                # Convert 12-hour to 24-hour
                if am_pm:
                    if am_pm == "pm" and hour != 12:  # noqa: PLR2004
                        hour += 12
                    elif am_pm == "am" and hour == 12:  # noqa: PLR2004
                        hour = 0

            # Parse date
            target_date = now.date()

            # Handle specific day names
            if "monday" in text:
                target_day = 0
            elif "tuesday" in text:
                target_day = 1
            elif "wednesday" in text:
                target_day = 2
            elif "thursday" in text:
                target_day = 3
            elif "friday" in text:
                target_day = 4
            elif "saturday" in text:
                target_day = 5
            elif "sunday" in text:
                target_day = 6
            elif "tomorrow" in text:
                target_date = now.date() + timedelta(days=1)
                target_day = None
            elif "today" in text:
                target_date = now.date()
                target_day = None
            else:
                # Try to parse YYYY-MM-DD
                date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
                if date_match:
                    target_date = datetime.strptime(date_match.group(0), "%Y-%m-%d").date()
                target_day = None

            # If day name specified, find next occurrence
            if target_day is not None:
                days_ahead = target_day - now.weekday()
                if days_ahead <= 0:  # Target day already happened this week
                    days_ahead += 7
                # If "next" is mentioned, add another week
                if "next" in text and days_ahead < 7:  # noqa: PLR2004
                    days_ahead += 7
                target_date = now.date() + timedelta(days=days_ahead)

            # Combine date and time
            result_dt = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                hour,
                minute,
                tzinfo=tz,
            )

            # Format as ISO 8601 with timezone offset
            iso_string = result_dt.isoformat()

            return {
                "success": True,
                "parsed_datetime": iso_string,
                "timezone": tz_name,
                "human_readable": result_dt.strftime("%A, %B %d, %Y at %I:%M %p %Z"),
                "original_expression": date_expression,
            }

        except Exception as e:
            self.logger.exception("parse_date_failed", error=str(e), expression=date_expression)
            return {
                "success": False,
                "error": f"Could not parse '{date_expression}'. Please provide a specific date in format like 'YYYY-MM-DD' or 'Tuesday at 9am'.",
            }

    async def book_appointment(  # noqa: PLR0911, PLR0912, PLR0915
        self,
        contact_phone: str,
        scheduled_at: str,
        duration_minutes: int = 30,
        service_type: str | None = None,
        notes: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Book an appointment.

        Args:
            contact_phone: Customer phone number
            scheduled_at: ISO 8601 datetime
            duration_minutes: Duration
            service_type: Service type
            notes: Notes
            agent_id: Optional agent UUID that is booking this appointment

        Returns:
            Booking confirmation
        """
        import time

        method_entry_time = time.perf_counter()
        contact_id_at_start = None

        # Entry point logging
        self.logger.info(
            "booking_appointment_started",
            contact_phone=contact_phone,
            scheduled_at=scheduled_at,
            duration_minutes=duration_minutes,
            service_type=service_type,
            notes=notes[:50] if notes else None,
            agent_id=agent_id,
        )

        try:
            # Parameter validation
            if not contact_phone or not contact_phone.strip():
                self.logger.error(
                    "booking_appointment_invalid_contact_phone",
                    contact_phone_empty=True,
                )
                return {"success": False, "error": "contact_phone cannot be empty"}

            if not scheduled_at or not scheduled_at.strip():
                self.logger.error(
                    "booking_appointment_invalid_scheduled_at",
                    scheduled_at_empty=True,
                )
                return {"success": False, "error": "scheduled_at cannot be empty"}

            MIN_DURATION = 5  # noqa: N806
            MAX_DURATION = 480  # noqa: N806
            if not (MIN_DURATION <= duration_minutes <= MAX_DURATION):
                self.logger.warning(
                    "booking_appointment_unusual_duration",
                    duration_minutes=duration_minutes,
                    expected_range=f"{MIN_DURATION}-{MAX_DURATION} minutes",
                )

            self.logger.debug(
                "booking_appointment_parameter_validation_passed",
                contact_phone_length=len(contact_phone),
                scheduled_at_length=len(scheduled_at),
                duration_valid=MIN_DURATION <= duration_minutes <= MAX_DURATION,
            )

            # Contact lookup with timing
            lookup_start = time.perf_counter()

            # Find contact - filtered by workspace or user for security
            if self.workspace_id:
                stmt = select(Contact).where(
                    Contact.workspace_id == self.workspace_id,
                    Contact.phone_number == contact_phone,
                )
                scope_type = "workspace"
            else:
                stmt = select(Contact).where(
                    Contact.user_id == self.user_id,
                    Contact.phone_number == contact_phone,
                )
                scope_type = "user"

            self.logger.debug(
                "contact_lookup_query_preparing",
                scope_type=scope_type,
                contact_phone=contact_phone,
            )

            result = await self.db.execute(stmt)
            contact = result.scalar_one_or_none()

            lookup_duration_ms = (time.perf_counter() - lookup_start) * 1000

            if contact:
                contact_id_at_start = contact.id
                self.logger.info(
                    "contact_lookup_success",
                    contact_id=contact.id,
                    contact_name=f"{contact.first_name} {contact.last_name or ''}".strip(),
                    contact_status=contact.status,
                    duration_ms=round(lookup_duration_ms, 2),
                )
            else:
                self.logger.debug(
                    "contact_lookup_no_match",
                    contact_phone=contact_phone,
                    duration_ms=round(lookup_duration_ms, 2),
                )

            if not contact:
                # Auto-create contact for SMS conversations
                # This allows booking without explicit contact creation
                creation_start = time.perf_counter()

                self.logger.warning(
                    "contact_not_found_auto_creating",
                    phone=contact_phone,
                    user_id=self.user_id,
                    workspace_id=str(self.workspace_id),
                    reason="appointment_booking_without_prior_contact_creation",
                )

                contact = Contact(
                    user_id=self.user_id,
                    workspace_id=self.workspace_id,
                    first_name="SMS Contact",
                    phone_number=contact_phone,
                    status="new",
                )
                self.db.add(contact)
                await self.db.flush()
                await self.db.refresh(contact)

                creation_duration_ms = (time.perf_counter() - creation_start) * 1000

                self.logger.info(
                    "contact_auto_created_success",
                    contact_id=contact.id,
                    phone=contact_phone,
                    duration_ms=round(creation_duration_ms, 2),
                    decision_reason="auto_create_on_first_booking",
                )

            # Parse datetime and handle timezone
            parse_start = time.perf_counter()

            self.logger.debug(
                "appointment_datetime_parsing_start",
                input_scheduled_at=scheduled_at,
                input_format="ISO 8601 with optional Z suffix",
            )

            try:
                appointment_time = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            except ValueError as parse_error:
                self.logger.exception(
                    "appointment_datetime_parse_failed",
                    input=scheduled_at,
                    error=str(parse_error),
                    expected_format="ISO 8601 (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DDTHH:MM:SS+HH:MM)",
                )
                return {
                    "success": False,
                    "error": f"Invalid datetime format: {parse_error}. Expected ISO 8601 format (e.g., 2025-12-20T14:30:00 or 2025-12-20T14:30:00-05:00)",
                }

            parse_duration_ms = (time.perf_counter() - parse_start) * 1000

            self.logger.debug(
                "appointment_datetime_parsed",
                parsed_datetime=appointment_time.isoformat(),
                has_timezone=appointment_time.tzinfo is not None,
                duration_ms=round(parse_duration_ms, 2),
            )

            # If datetime is naive (no timezone), interpret it in workspace timezone
            if appointment_time.tzinfo is None and self.workspace_id:
                tz_resolution_start = time.perf_counter()

                self.logger.debug(
                    "appointment_datetime_naive_detected",
                    datetime_value=appointment_time.isoformat(),
                    workspace_id=str(self.workspace_id),
                    next_step="resolve_workspace_timezone",
                )

                from zoneinfo import ZoneInfo

                from app.models.workspace import Workspace

                # Get workspace timezone
                ws_result = await self.db.execute(
                    select(Workspace).where(Workspace.id == self.workspace_id)
                )
                workspace = ws_result.scalar_one_or_none()

                if workspace and workspace.settings:
                    tz_name = workspace.settings.get("timezone", "UTC")
                    self.logger.debug(
                        "workspace_timezone_loaded",
                        timezone=tz_name,
                        workspace_id=str(self.workspace_id),
                    )
                else:
                    tz_name = "UTC"
                    self.logger.warning(
                        "workspace_not_found_using_default_timezone",
                        workspace_id=str(self.workspace_id),
                        fallback_timezone="UTC",
                    )

                try:
                    tz = ZoneInfo(tz_name)
                    # Interpret the naive datetime as being in workspace timezone
                    appointment_time = appointment_time.replace(tzinfo=tz)

                    tz_resolution_duration_ms = (time.perf_counter() - tz_resolution_start) * 1000

                    self.logger.info(
                        "appointment_datetime_timezone_resolved",
                        original_naive=scheduled_at,
                        timezone_name=tz_name,
                        result_with_tz=appointment_time.isoformat(),
                        duration_ms=round(tz_resolution_duration_ms, 2),
                        utc_equivalent=appointment_time.astimezone(ZoneInfo("UTC")).isoformat(),
                    )
                except Exception as tz_error:
                    tz_resolution_duration_ms = (time.perf_counter() - tz_resolution_start) * 1000

                    self.logger.exception(
                        "timezone_conversion_failed_hard_error",
                        timezone=tz_name,
                        error=str(tz_error),
                        error_type=type(tz_error).__name__,
                        duration_ms=round(tz_resolution_duration_ms, 2),
                    )
                    return {
                        "success": False,
                        "error": f"Failed to interpret datetime in timezone {tz_name}: {tz_error}",
                    }
            elif appointment_time.tzinfo is None:
                self.logger.warning(
                    "appointment_datetime_naive_no_workspace",
                    datetime_value=appointment_time.isoformat(),
                    workspace_id=self.workspace_id,
                    note="Naive datetime will be stored without timezone info",
                )

            # Validate appointment is in the future
            from zoneinfo import ZoneInfo

            now_utc = datetime.now(ZoneInfo("UTC"))
            appointment_utc = (
                appointment_time.astimezone(ZoneInfo("UTC"))
                if appointment_time.tzinfo
                else appointment_time
            )

            if appointment_utc <= now_utc:
                time_diff_seconds = (now_utc - appointment_utc).total_seconds()
                self.logger.error(
                    "appointment_datetime_in_past",
                    scheduled_at=appointment_time.isoformat(),
                    now_utc=now_utc.isoformat(),
                    time_diff_seconds=round(time_diff_seconds, 2),
                )
                return {
                    "success": False,
                    "error": f"Cannot book appointment in the past. Scheduled time {appointment_time.isoformat()} is {round(time_diff_seconds / 3600, 1)} hours ago.",
                }

            self.logger.debug(
                "appointment_datetime_future_validation_passed",
                scheduled_at=appointment_time.isoformat(),
                now_utc=now_utc.isoformat(),
                time_until_appointment_hours=round(
                    (appointment_utc - now_utc).total_seconds() / 3600, 2
                ),
            )

            # Create appointment (inherit workspace_id from contact)
            creation_start = time.perf_counter()

            self.logger.debug(
                "appointment_creating",
                contact_id=contact.id,
                workspace_id=str(contact.workspace_id),
                scheduled_at=appointment_time.isoformat(),
                duration_minutes=duration_minutes,
                service_type=service_type,
                agent_id=agent_id,
            )

            # Convert agent_id string to UUID if provided
            import uuid as uuid_module

            agent_uuid = uuid_module.UUID(agent_id) if agent_id else None

            appointment = Appointment(
                contact_id=contact.id,
                workspace_id=contact.workspace_id,
                agent_id=agent_uuid,
                scheduled_at=appointment_time,
                duration_minutes=duration_minutes,
                service_type=service_type,
                notes=notes,
                status="scheduled",
            )

            self.db.add(appointment)

            commit_start = time.perf_counter()
            self.logger.debug(
                "appointment_database_commit_starting",
                contact_id=contact.id,
                workspace_id=str(contact.workspace_id),
            )

            await self.db.commit()
            await self.db.refresh(appointment)

            commit_duration_ms = (time.perf_counter() - commit_start) * 1000
            total_creation_duration_ms = (time.perf_counter() - creation_start) * 1000

            self.logger.info(
                "appointment_created_in_database",
                appointment_id=appointment.id,
                contact_id=appointment.contact_id,
                workspace_id=str(appointment.workspace_id),
                agent_id=str(appointment.agent_id) if appointment.agent_id else None,
                scheduled_at=appointment.scheduled_at.isoformat(),
                status=appointment.status,
                duration_minutes=appointment.duration_minutes,
                service_type=appointment.service_type,
                commit_duration_ms=round(commit_duration_ms, 2),
                total_creation_duration_ms=round(total_creation_duration_ms, 2),
            )

            # Enqueue calendar sync
            sync_start = time.perf_counter()

            self.logger.debug(
                "calendar_sync_enqueueing",
                appointment_id=appointment.id,
                workspace_id=str(appointment.workspace_id),
                operation="create",
            )

            await self._enqueue_calendar_sync(appointment, operation="create")

            sync_duration_ms = (time.perf_counter() - sync_start) * 1000

            self.logger.debug(
                "calendar_sync_enqueued",
                appointment_id=appointment.id,
                workspace_id=str(appointment.workspace_id),
                duration_ms=round(sync_duration_ms, 2),
                status="queued_for_async_processing",
            )

            # Invalidate CRM stats cache after booking
            cache_start = time.perf_counter()

            try:
                self.logger.debug(
                    "cache_invalidation_starting",
                    cache_pattern="crm:stats:*",
                    reason="appointment_created",
                )

                await cache_invalidate("crm:stats:*")

                cache_duration_ms = (time.perf_counter() - cache_start) * 1000

                self.logger.debug(
                    "cache_invalidation_success",
                    cache_pattern="crm:stats:*",
                    duration_ms=round(cache_duration_ms, 2),
                )
            except Exception as cache_error:
                cache_duration_ms = (time.perf_counter() - cache_start) * 1000

                self.logger.exception(
                    "failed_to_invalidate_cache_after_book_appointment",
                    error=str(cache_error),
                    error_type=type(cache_error).__name__,
                    duration_ms=round(cache_duration_ms, 2),
                    impact="cache_hit_may_return_stale_stats",
                )
                # Don't raise - cache failure shouldn't block appointment success

            # Success response
            total_execution_duration_ms = (time.perf_counter() - method_entry_time) * 1000

            self.logger.info(
                "booking_appointment_success",
                appointment_id=appointment.id,
                contact_id=contact.id,
                contact_name=f"{contact.first_name} {contact.last_name or ''}".strip(),
                contact_phone=contact.phone_number,
                scheduled_at=appointment.scheduled_at.isoformat(),
                duration_minutes=appointment.duration_minutes,
                service_type=service_type,
                was_contact_auto_created=(contact_id_at_start is None),
                workspace_id=str(appointment.workspace_id),
                agent_id=str(appointment.agent_id) if appointment.agent_id else None,
                user_id=self.user_id,
                total_duration_ms=round(total_execution_duration_ms, 2),
            )

            return {
                "success": True,
                "appointment_id": appointment.id,
                "customer_name": f"{contact.first_name} {contact.last_name or ''}",
                "scheduled_at": appointment.scheduled_at.isoformat(),
                "duration_minutes": appointment.duration_minutes,
                "message": f"Appointment booked for {contact.first_name} on {appointment.scheduled_at.strftime('%B %d at %I:%M %p')}",
            }

        except Exception as e:
            execution_duration_ms = (
                (time.perf_counter() - method_entry_time) * 1000
                if "method_entry_time" in locals()
                else None
            )

            self.logger.exception(
                "book_appointment_failed",
                error=str(e),
                error_type=type(e).__name__,
                contact_phone=contact_phone,
                scheduled_at=scheduled_at,
                duration_minutes=duration_minutes,
                service_type=service_type,
                agent_id=agent_id,
                user_id=self.user_id,
                workspace_id=str(self.workspace_id),
                execution_duration_ms=round(execution_duration_ms, 2)
                if execution_duration_ms
                else None,
                traceback_available=True,
            )
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "contact_phone": contact_phone,
            }

    async def list_appointments(
        self,
        contact_phone: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """List appointments with optional filters.

        Args:
            contact_phone: Filter by phone
            start_date: Start date filter
            end_date: End date filter
            status: Status filter

        Returns:
            List of appointments
        """
        try:
            # Use selectinload to eagerly load contacts in a single query (fixes N+1)
            # Filter by workspace or user for security
            base_stmt = select(Appointment).join(Contact).options(selectinload(Appointment.contact))

            if self.workspace_id:
                stmt = base_stmt.where(Contact.workspace_id == self.workspace_id)
            else:
                stmt = base_stmt.where(Contact.user_id == self.user_id)

            # Apply filters
            if contact_phone:
                stmt = stmt.where(Contact.phone_number == contact_phone)

            if start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                stmt = stmt.where(Appointment.scheduled_at >= start_dt)

            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                stmt = stmt.where(Appointment.scheduled_at <= end_dt)

            if status:
                stmt = stmt.where(Appointment.status == status)
            else:
                stmt = stmt.where(Appointment.status == "scheduled")

            stmt = stmt.order_by(Appointment.scheduled_at)

            result = await self.db.execute(stmt)
            appointments = list(result.scalars().all())

            # Contact is already loaded via selectinload - no additional queries needed
            appointment_list = [
                {
                    "id": apt.id,
                    "customer_name": f"{apt.contact.first_name} {apt.contact.last_name or ''}",
                    "phone": apt.contact.phone_number,
                    "scheduled_at": apt.scheduled_at.isoformat(),
                    "duration_minutes": apt.duration_minutes,
                    "service_type": apt.service_type,
                    "status": apt.status,
                }
                for apt in appointments
            ]

            return {
                "success": True,
                "total": len(appointment_list),
                "appointments": appointment_list,
            }

        except Exception as e:
            self.logger.exception("list_appointments_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def cancel_appointment(
        self, appointment_id: int, reason: str | None = None
    ) -> dict[str, Any]:
        """Cancel an appointment.

        Args:
            appointment_id: Appointment ID
            reason: Cancellation reason

        Returns:
            Cancellation confirmation
        """
        try:
            # Verify appointment belongs to user's workspace/contact
            base_stmt = select(Appointment).join(Contact).where(Appointment.id == appointment_id)

            if self.workspace_id:
                stmt = base_stmt.where(Contact.workspace_id == self.workspace_id)
            else:
                stmt = base_stmt.where(Contact.user_id == self.user_id)

            result = await self.db.execute(stmt)
            appointment = result.scalar_one_or_none()

            if not appointment:
                return {
                    "success": False,
                    "error": f"Appointment {appointment_id} not found",
                }

            # Update status
            appointment.status = "cancelled"
            if reason:
                appointment.notes = (
                    f"{appointment.notes}\n\nCancellation reason: {reason}"
                    if appointment.notes
                    else f"Cancellation reason: {reason}"
                )

            await self.db.commit()

            # Enqueue calendar sync
            await self._enqueue_calendar_sync(appointment, operation="cancel")

            return {
                "success": True,
                "appointment_id": appointment_id,
                "message": f"Appointment on {appointment.scheduled_at.strftime('%B %d at %I:%M %p')} has been cancelled",
            }

        except Exception as e:
            self.logger.exception("cancel_appointment_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def reschedule_appointment(
        self, appointment_id: int, new_scheduled_at: str
    ) -> dict[str, Any]:
        """Reschedule an appointment.

        Args:
            appointment_id: Appointment ID
            new_scheduled_at: New datetime in ISO 8601 format

        Returns:
            Reschedule confirmation
        """
        try:
            # Verify appointment belongs to user's workspace/contact
            base_stmt = select(Appointment).join(Contact).where(Appointment.id == appointment_id)

            if self.workspace_id:
                stmt = base_stmt.where(Contact.workspace_id == self.workspace_id)
            else:
                stmt = base_stmt.where(Contact.user_id == self.user_id)

            result = await self.db.execute(stmt)
            appointment = result.scalar_one_or_none()

            if not appointment:
                return {
                    "success": False,
                    "error": f"Appointment {appointment_id} not found",
                }

            # Parse new datetime
            new_time = datetime.fromisoformat(new_scheduled_at.replace("Z", "+00:00"))

            old_time = appointment.scheduled_at
            appointment.scheduled_at = new_time

            await self.db.commit()

            # Enqueue calendar sync
            await self._enqueue_calendar_sync(appointment, operation="update")

            return {
                "success": True,
                "appointment_id": appointment_id,
                "old_time": old_time.strftime("%B %d at %I:%M %p"),
                "new_time": new_time.strftime("%B %d at %I:%M %p"),
                "message": f"Appointment rescheduled from {old_time.strftime('%B %d at %I:%M %p')} to {new_time.strftime('%B %d at %I:%M %p')}",
            }

        except Exception as e:
            self.logger.exception("reschedule_appointment_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def execute_tool(  # noqa: PLR0911
        self, tool_name: str, arguments: dict[str, Any], agent_id: str | None = None
    ) -> dict[str, Any]:
        """Execute a CRM tool by name.

        Args:
            tool_name: Tool name
            arguments: Tool arguments
            agent_id: Optional agent UUID for tracking which agent executed the tool

        Returns:
            Tool result
        """
        if tool_name == "search_customer":
            return await self.search_customer(**arguments)
        if tool_name == "create_contact":
            return await self.create_contact(**arguments)
        if tool_name == "check_availability":
            return await self.check_availability(**arguments)
        if tool_name == "book_appointment":
            # Inject agent_id into arguments for book_appointment
            return await self.book_appointment(**arguments, agent_id=agent_id)
        if tool_name == "list_appointments":
            return await self.list_appointments(**arguments)
        if tool_name == "cancel_appointment":
            return await self.cancel_appointment(**arguments)
        if tool_name == "reschedule_appointment":
            return await self.reschedule_appointment(**arguments)
        if tool_name == "parse_date":
            return await self.parse_date(**arguments)
        return {"success": False, "error": f"Unknown tool: {tool_name}"}
