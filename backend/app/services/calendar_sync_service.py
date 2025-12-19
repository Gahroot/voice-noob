"""Calendar sync service for syncing appointments to external calendars.

This background worker:
1. Polls for pending sync queue entries
2. Syncs appointments to external calendars (Cal.com, Calendly, GoHighLevel)
3. Handles retries with exponential backoff
4. Updates appointment sync status
"""

import asyncio
import contextlib
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

        # Circuit breakers per provider (configurable via settings)
        self._circuit_breakers: dict[str, CircuitBreaker] = {
            provider: CircuitBreaker(
                provider,
                failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                timeout=settings.CIRCUIT_BREAKER_TIMEOUT,
            )
            for provider in ["cal-com", "calendly", "gohighlevel", "google-calendar"]
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
            from app.core.auth import user_id_to_uuid

            integrations = await get_workspace_integrations(
                user_id=user_id_to_uuid(entry.workspace.user_id),
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

    async def _sync_to_provider(
        self,
        entry: CalendarSyncQueue,
        credentials: dict[str, Any],
        db: AsyncSession,  # noqa: ARG002
    ) -> None:
        """Sync appointment to external calendar provider using Strategy Pattern."""
        from app.services.calendar_providers.factory import ProviderFactory

        # Get appointment
        appointment = entry.appointment
        if not appointment:
            raise ValueError("Appointment not found")

        # Create provider instance using factory
        provider = ProviderFactory.create_provider(
            provider_name=entry.calendar_provider,
            credentials=credentials,
        )

        try:
            # Route operation to provider
            if entry.operation == "create":
                result = await provider.create_event(
                    appointment=appointment,
                    contact_name=f"{appointment.contact.first_name} {appointment.contact.last_name or ''}".strip(),
                    contact_email=appointment.contact.email,
                    notes=appointment.notes,
                )
            elif entry.operation == "update":
                if not appointment.external_event_id and not appointment.external_event_uid:
                    raise ValueError("No external event ID/UID for update")

                event_id = appointment.external_event_uid or appointment.external_event_id
                if not event_id:
                    raise ValueError("No external event ID/UID for update")
                result = await provider.update_event(
                    event_id=event_id,
                    appointment=appointment,
                )
            elif entry.operation == "cancel":
                if not appointment.external_event_id and not appointment.external_event_uid:
                    raise ValueError("No external event ID/UID for cancellation")

                event_id = appointment.external_event_uid or appointment.external_event_id
                if not event_id:
                    raise ValueError("No external event ID/UID for cancellation")
                result = await provider.cancel_event(
                    event_id=event_id,
                    reason="Appointment cancelled",
                )
            else:
                raise ValueError(f"Unknown operation: {entry.operation}")

            # Update appointment with sync results
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
            await provider.close()


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
