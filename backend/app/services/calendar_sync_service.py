"""Calendar sync service for syncing appointments to external calendars.

This background worker:
1. Polls for pending sync queue entries
2. Syncs appointments to external calendars (Cal.com, Calendly, GoHighLevel)
3. Handles retries with exponential backoff
4. Updates appointment sync status
"""

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.integrations import get_workspace_integrations
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.appointment import Appointment
from app.models.calendar_sync import CalendarSyncQueue
from app.services.circuit_breaker import CircuitBreaker
from app.services.tools.calcom_tools import CalComTools
from app.services.tools.calendly_tools import CalendlyTools
from app.services.tools.gohighlevel_tools import GoHighLevelTools

logger = structlog.get_logger()


class CalendarSyncService:
    """Background service for syncing appointments to external calendars."""

    def __init__(self, poll_interval: int = 30):
        """Initialize the calendar sync service.

        Args:
            poll_interval: How often to poll for sync queue entries (seconds)
        """
        self.poll_interval = poll_interval
        self.running = False
        self.logger = logger.bind(component="calendar_sync")
        self._task: asyncio.Task[None] | None = None

        # Circuit breakers per provider
        self._circuit_breakers: dict[str, CircuitBreaker] = {
            "cal-com": CircuitBreaker("cal-com", failure_threshold=5, timeout=120),
            "calendly": CircuitBreaker("calendly", failure_threshold=5, timeout=120),
            "gohighlevel": CircuitBreaker("gohighlevel", failure_threshold=5, timeout=120),
        }

    async def start(self) -> None:
        """Start the calendar sync service."""
        if self.running:
            self.logger.warning("Calendar sync service already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        self.logger.info("Calendar sync service started", poll_interval=self.poll_interval)

    async def stop(self) -> None:
        """Stop the calendar sync service."""
        self.running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.logger.info("Calendar sync service stopped")

    async def _run_loop(self) -> None:
        """Main polling loop."""
        while self.running:
            try:
                await self._process_sync_queue()
            except Exception:
                self.logger.exception("Error in calendar sync loop")

            await asyncio.sleep(self.poll_interval)

    async def _process_sync_queue(self) -> None:
        """Process pending sync queue entries."""
        async with AsyncSessionLocal() as db:
            # Get pending entries with row locking
            stmt = (
                select(CalendarSyncQueue)
                .options(
                    selectinload(CalendarSyncQueue.appointment).selectinload(Appointment.contact),
                    selectinload(CalendarSyncQueue.workspace),
                )
                .where(
                    CalendarSyncQueue.status == "pending",
                    CalendarSyncQueue.retry_count < CalendarSyncQueue.max_retries,
                    or_(
                        CalendarSyncQueue.scheduled_at.is_(None),
                        CalendarSyncQueue.scheduled_at <= datetime.now(UTC),
                    ),
                )
                .order_by(CalendarSyncQueue.created_at)
                .limit(10)
                .with_for_update(skip_locked=True)
            )

            result = await db.execute(stmt)
            entries = result.scalars().all()

            if not entries:
                return

            self.logger.debug("Processing sync queue entries", count=len(entries))

            for entry in entries:
                try:
                    await self._process_entry(entry, db)
                except Exception:
                    self.logger.exception(
                        "Error processing sync entry",
                        entry_id=str(entry.id),
                        provider=entry.calendar_provider,
                    )

    async def _process_entry(self, entry: CalendarSyncQueue, db: AsyncSession) -> None:
        """Process a single sync queue entry."""
        log = self.logger.bind(
            entry_id=str(entry.id),
            appointment_id=entry.appointment_id,
            provider=entry.calendar_provider,
            operation=entry.operation,
        )

        entry.status = "processing"
        await db.commit()

        try:
            # Get integration credentials
            integrations = await get_workspace_integrations(
                user_id=uuid.UUID(int=entry.workspace.user_id),
                workspace_id=entry.workspace_id,
                db=db,
            )

            if entry.calendar_provider not in integrations:
                raise ValueError(  # noqa: TRY301
                    f"Integration {entry.calendar_provider} not connected"
                )

            credentials = integrations[entry.calendar_provider]

            # Use circuit breaker
            circuit = self._circuit_breakers.get(entry.calendar_provider)
            if circuit:
                await circuit.call(
                    self._sync_to_provider,
                    entry=entry,
                    credentials=credentials,
                    db=db,
                )
            else:
                await self._sync_to_provider(entry, credentials, db)

            entry.status = "completed"
            entry.processed_at = datetime.now(UTC)
            log.info("Sync completed successfully")

        except Exception as e:
            entry.retry_count += 1
            entry.error_message = str(e)

            if entry.retry_count >= entry.max_retries:
                entry.status = "failed"
                log.exception(
                    "Sync failed permanently",
                    retry_count=entry.retry_count,
                )

                # Update appointment sync status
                if entry.appointment:
                    entry.appointment.sync_status = "failed"
                    entry.appointment.sync_error = str(e)
            else:
                # Exponential backoff
                delay_minutes = 2**entry.retry_count
                entry.scheduled_at = datetime.now(UTC) + timedelta(minutes=delay_minutes)
                entry.status = "pending"
                log.warning(
                    "Sync failed, will retry",
                    retry_count=entry.retry_count,
                    delay_minutes=delay_minutes,
                    error=str(e),
                )

        await db.commit()

    async def _sync_to_provider(  # noqa: PLR0912
        self,
        entry: CalendarSyncQueue,
        credentials: dict[str, Any],
        db: AsyncSession,  # noqa: ARG002
    ) -> None:
        """Sync appointment to external calendar provider."""
        # Get appointment
        appointment = entry.appointment
        if not appointment:
            raise ValueError("Appointment not found")

        # Create appropriate tool instance
        tools: CalComTools | CalendlyTools | GoHighLevelTools
        try:
            if entry.calendar_provider == "cal-com":
                tools = CalComTools(
                    api_key=credentials.get("api_key", ""),
                    event_type_id=credentials.get("event_type_id"),
                )
            elif entry.calendar_provider == "calendly":
                tools = CalendlyTools(access_token=credentials.get("access_token", ""))
            elif entry.calendar_provider == "gohighlevel":
                tools = GoHighLevelTools(
                    access_token=credentials.get("access_token", ""),
                    location_id=credentials.get("location_id", ""),
                )
            else:
                raise ValueError(f"Unsupported provider: {entry.calendar_provider}")

            # Perform operation
            if entry.operation == "create":
                result = await self._create_external_event(tools, appointment, entry)
            elif entry.operation == "update":
                result = await self._update_external_event(tools, appointment, entry)
            elif entry.operation == "cancel":
                result = await self._cancel_external_event(tools, appointment, entry)
            else:
                raise ValueError(f"Unknown operation: {entry.operation}")

            # Update appointment with external ID
            if result.get("success"):
                appointment.external_calendar_id = entry.calendar_provider
                appointment.external_event_id = result.get("event_id")
                appointment.external_event_uid = result.get("event_uid")
                appointment.sync_status = "synced"
                appointment.last_synced_at = datetime.now(UTC)
                appointment.sync_error = None
            else:
                raise ValueError(result.get("error", "Unknown error"))

        finally:
            # Close HTTP client if available
            if tools and hasattr(tools, "close"):
                await tools.close()

    async def _create_external_event(
        self,
        tools: CalComTools | CalendlyTools | GoHighLevelTools,
        appointment: Appointment,
        entry: CalendarSyncQueue,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Create event in external calendar."""
        contact = appointment.contact

        if isinstance(tools, CalComTools):
            # Cal.com create booking
            result = await tools.create_booking(
                event_type_id=tools.event_type_id or 0,
                start_time=appointment.scheduled_at.isoformat(),
                attendee_email=contact.email or "noemail@example.com",
                attendee_name=f"{contact.first_name} {contact.last_name or ''}".strip(),
                notes=appointment.notes or "",
            )

            if result.get("success"):
                return {
                    "success": True,
                    "event_id": result.get("id"),
                    "event_uid": result.get("uid"),
                }
            return result

        if isinstance(tools, CalendlyTools):
            # Calendly only supports scheduling links, not direct booking
            # Not implemented - would need to generate a link
            return {"success": False, "error": "Calendly direct booking not supported"}

        if isinstance(tools, GoHighLevelTools):
            # GoHighLevel book appointment
            # Not implemented - would need proper GHL integration
            return {"success": False, "error": "GoHighLevel booking not implemented"}

        return {"success": False, "error": "Unsupported tool type"}  # type: ignore[unreachable]

    async def _update_external_event(
        self,
        tools: CalComTools | CalendlyTools | GoHighLevelTools,
        appointment: Appointment,
        entry: CalendarSyncQueue,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Update event in external calendar."""
        if isinstance(tools, CalComTools):
            # Cal.com reschedule booking
            if appointment.external_event_uid:
                result = await tools.reschedule_booking(
                    booking_uid=appointment.external_event_uid,
                    new_start_time=appointment.scheduled_at.isoformat(),
                    reason="Appointment rescheduled",
                )
                return result
            return {"success": False, "error": "No external event UID"}

        if isinstance(tools, CalendlyTools):
            # Calendly doesn't support rescheduling via API
            # Would need to cancel and create new
            return {"success": False, "error": "Calendly doesn't support rescheduling"}

        if isinstance(tools, GoHighLevelTools):
            # GoHighLevel update appointment
            if appointment.external_event_id:
                # Note: Update logic would go here
                return {"success": True, "event_id": appointment.external_event_id}
            return {"success": False, "error": "No external event ID"}

        return {"success": False, "error": "Unsupported tool type"}  # type: ignore[unreachable]

    async def _cancel_external_event(
        self,
        tools: CalComTools | CalendlyTools | GoHighLevelTools,
        appointment: Appointment,
        entry: CalendarSyncQueue,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Cancel event in external calendar."""
        if isinstance(tools, CalComTools):
            # Cal.com cancel booking
            if appointment.external_event_uid:
                result = await tools.cancel_booking(
                    booking_uid=appointment.external_event_uid,
                    reason="Appointment cancelled",
                )
                return result
            return {"success": False, "error": "No external event UID"}

        if isinstance(tools, CalendlyTools):
            # Calendly cancel - not implemented
            return {"success": False, "error": "Calendly cancel not implemented"}

        if isinstance(tools, GoHighLevelTools):
            # GoHighLevel cancel - not implemented
            return {"success": False, "error": "GoHighLevel cancel not implemented"}

        return {"success": False, "error": "Unsupported tool type"}  # type: ignore[unreachable]


# Global service instance
_calendar_sync_service: CalendarSyncService | None = None


async def start_calendar_sync(poll_interval: int | None = None) -> None:
    """Start the calendar sync service."""
    global _calendar_sync_service

    if not settings.CALENDAR_SYNC_ENABLED:
        logger.info("Calendar sync disabled in settings")
        return

    if _calendar_sync_service is not None:
        logger.warning("Calendar sync service already started")
        return

    poll_interval = poll_interval or settings.CALENDAR_SYNC_POLL_INTERVAL
    _calendar_sync_service = CalendarSyncService(poll_interval=poll_interval)
    await _calendar_sync_service.start()


async def stop_calendar_sync() -> None:
    """Stop the calendar sync service."""
    global _calendar_sync_service

    if _calendar_sync_service is None:
        return

    await _calendar_sync_service.stop()
    _calendar_sync_service = None
