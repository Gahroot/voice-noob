"""FollowUpBoss inbox sync service for syncing SMS messages to FUB Inbox.

This background worker:
1. Polls for pending FUB message sync queue entries
2. Syncs SMS messages to FollowUpBoss Inbox API
3. Handles retries with exponential backoff
4. Updates sync status and FUB message IDs
"""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.integrations import get_workspace_integrations
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.fub_sync import FUBMessageSyncQueue
from app.services.tools.followupboss_tools import FollowUpBossTools

logger = structlog.get_logger()


class FUBInboxSyncService:
    """Background service for syncing SMS messages to FollowUpBoss Inbox."""

    def __init__(self, poll_interval: int = 30):
        """Initialize the FUB inbox sync service.

        Args:
            poll_interval: How often to poll for sync queue entries (seconds)
        """
        self.poll_interval = poll_interval
        self.running = False
        self.logger = logger.bind(component="fub_inbox_sync")
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the FUB inbox sync service."""
        if self.running:
            self.logger.warning("FUB inbox sync service already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        self.logger.info("FUB inbox sync service started", poll_interval=self.poll_interval)

    async def stop(self) -> None:
        """Stop the FUB inbox sync service."""
        self.running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.logger.info("FUB inbox sync service stopped")

    async def _run_loop(self) -> None:
        """Main polling loop."""
        while self.running:
            try:
                await self._process_sync_queue()
            except Exception:
                self.logger.exception("Error in FUB inbox sync loop")

            await asyncio.sleep(self.poll_interval)

    async def _process_sync_queue(self) -> None:
        """Process pending sync queue entries."""
        async with AsyncSessionLocal() as db:
            # Get pending entries with row locking
            stmt = (
                select(FUBMessageSyncQueue)
                .options(
                    selectinload(FUBMessageSyncQueue.sms_message),
                    selectinload(FUBMessageSyncQueue.workspace),
                )
                .where(
                    FUBMessageSyncQueue.status == "pending",
                    FUBMessageSyncQueue.retry_count < FUBMessageSyncQueue.max_retries,
                    or_(
                        FUBMessageSyncQueue.scheduled_at.is_(None),
                        FUBMessageSyncQueue.scheduled_at <= datetime.now(UTC),
                    ),
                )
                .order_by(FUBMessageSyncQueue.created_at)
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
                        sms_message_id=str(entry.sms_message_id),
                    )

    async def _process_entry(self, entry: FUBMessageSyncQueue, db: AsyncSession) -> None:
        """Process a single sync queue entry."""
        log = self.logger.bind(
            entry_id=str(entry.id),
            sms_message_id=str(entry.sms_message_id),
            workspace_id=str(entry.workspace_id),
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

            if "followupboss" not in integrations:
                raise ValueError("FollowUpBoss integration not connected")  # noqa: TRY301

            credentials = integrations["followupboss"]
            api_key = credentials.get("api_key")

            if not api_key:
                raise ValueError("FollowUpBoss API key not found in credentials")  # noqa: TRY301

            # Sync to FollowUpBoss Inbox
            await self._sync_to_fub_inbox(entry, api_key, db)

            entry.status = "completed"
            entry.processed_at = datetime.now(UTC)
            log.info("FUB inbox sync completed successfully")

        except Exception as e:
            entry.retry_count += 1
            entry.error_message = str(e)

            if entry.retry_count >= entry.max_retries:
                entry.status = "failed"
                log.exception(
                    "FUB inbox sync failed permanently",
                    retry_count=entry.retry_count,
                )
            else:
                # Exponential backoff
                delay_minutes = 2**entry.retry_count
                entry.scheduled_at = datetime.now(UTC) + timedelta(minutes=delay_minutes)
                entry.status = "pending"
                log.warning(
                    "FUB inbox sync failed, will retry",
                    retry_count=entry.retry_count,
                    delay_minutes=delay_minutes,
                    error=str(e),
                )

        await db.commit()

    async def _sync_to_fub_inbox(
        self,
        entry: FUBMessageSyncQueue,
        api_key: str,
        db: AsyncSession,  # noqa: ARG002
    ) -> None:
        """Sync SMS message to FollowUpBoss Inbox API."""
        # Get SMS message
        sms_message = entry.sms_message
        if not sms_message:
            raise ValueError("SMS message not found")

        # Extract payload data
        payload = entry.payload
        person_id = payload.get("person_id")
        message_body = payload.get("message_body")
        direction = payload.get("direction")

        if not person_id:
            raise ValueError("FUB person_id not found in payload")

        if not message_body:
            raise ValueError("Message body not found in payload")

        # Create FollowUpBoss tools instance
        fub_tools = FollowUpBossTools(api_key=api_key)

        try:
            # Determine source based on direction
            source = "SMS"
            if direction == "inbound":
                source = "SMS (Inbound)"
            elif direction == "outbound":
                source = "SMS (Outbound)"

            # Send message to FUB Inbox API
            result = await fub_tools.fub_send_inbox_message(
                person_id=person_id,
                message=message_body,
                source=source,
            )

            if not result.get("success"):
                raise ValueError(result.get("error", "Unknown error syncing to FUB Inbox"))

            # Update entry with FUB message ID
            if "message_id" in result:
                entry.fub_message_id = result["message_id"]

            self.logger.info(
                "Message synced to FUB Inbox",
                entry_id=str(entry.id),
                fub_message_id=entry.fub_message_id,
                person_id=person_id,
                direction=direction,
            )

        finally:
            await fub_tools.close()


# Global service instance
_fub_inbox_sync_service: FUBInboxSyncService | None = None


async def start_fub_inbox_sync(poll_interval: int | None = None) -> None:
    """Start the FUB inbox sync service."""
    global _fub_inbox_sync_service

    if not settings.FUB_INBOX_SYNC_ENABLED:
        logger.info("FUB inbox sync disabled in settings")
        return

    if _fub_inbox_sync_service is not None:
        logger.warning("FUB inbox sync service already started")
        return

    poll_interval = poll_interval or settings.FUB_INBOX_SYNC_POLL_INTERVAL
    _fub_inbox_sync_service = FUBInboxSyncService(poll_interval=poll_interval)
    await _fub_inbox_sync_service.start()


async def stop_fub_inbox_sync() -> None:
    """Stop the FUB inbox sync service."""
    global _fub_inbox_sync_service

    if _fub_inbox_sync_service is None:
        return

    await _fub_inbox_sync_service.stop()
    _fub_inbox_sync_service = None


async def start_fub_inbox_sync_if_needed(db: AsyncSession) -> None:
    """Start FUB inbox sync service if any FollowUpBoss integrations exist.

    This checks if there are any active FollowUpBoss integrations across all
    workspaces. If found, it starts the sync service.

    Args:
        db: Database session
    """
    # If service is already running, nothing to do
    if _fub_inbox_sync_service is not None:
        return

    # If sync is disabled in settings, skip
    if not settings.FUB_INBOX_SYNC_ENABLED:
        logger.debug("FUB inbox sync disabled in settings")
        return

    # Check if any FollowUpBoss integrations exist
    from app.models.user_integration import UserIntegration

    stmt = select(UserIntegration).where(
        UserIntegration.integration_id == "followupboss",
        UserIntegration.is_active.is_(True),
    )
    result = await db.execute(stmt)
    fub_integration = result.scalars().first()

    if fub_integration:
        logger.info(
            "FollowUpBoss integration detected, starting FUB inbox sync service",
            integration_id=str(fub_integration.id),
        )
        await start_fub_inbox_sync()
    else:
        logger.debug("No active FollowUpBoss integrations found, skipping sync service start")
