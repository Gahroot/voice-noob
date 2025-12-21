"""Calendar sync retry and health check endpoints for appointments."""

import logging
import uuid as uuid_module
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.integrations import get_workspace_integrations
from app.models.appointment import Appointment
from app.models.calendar_sync import CalendarSyncQueue
from app.models.contact import Contact
from app.models.fub_sync import FUBMessageSyncQueue

logger = logging.getLogger(__name__)


async def enqueue_calendar_sync_retry(
    appointment: Appointment,
    operation: str,
    db: AsyncSession,
    user_id: uuid_module.UUID,
) -> dict[str, Any]:
    """Enqueue appointment for sync to external calendars.

    Args:
        appointment: Appointment to sync
        operation: Sync operation (create, update, cancel)
        db: Database session
        user_id: User ID for integration lookup

    Returns:
        Dict with sync queue status
    """
    if not appointment.workspace_id:
        return {"queued_providers": [], "message": "No workspace associated with appointment"}

    try:
        # Get workspace integrations
        integrations = await get_workspace_integrations(
            user_id=user_id,
            workspace_id=appointment.workspace_id,
            db=db,
        )

        queued_providers = []

        # Queue sync for each connected calendar provider
        for provider in ["cal-com", "calendly", "gohighlevel", "google-calendar"]:
            if provider in integrations:
                # Check if pending sync already exists
                existing = await db.execute(
                    select(CalendarSyncQueue).where(
                        CalendarSyncQueue.appointment_id == appointment.id,
                        CalendarSyncQueue.calendar_provider == provider,
                        CalendarSyncQueue.operation == operation,
                        CalendarSyncQueue.status.in_(["pending", "processing"]),
                    )
                )
                if existing.scalar_one_or_none():
                    logger.debug(
                        "Sync already queued, skipping: appointment_id=%d, provider=%s",
                        appointment.id,
                        provider,
                    )
                    continue

                # Reset failed sync if exists
                failed_sync = await db.execute(
                    select(CalendarSyncQueue).where(
                        CalendarSyncQueue.appointment_id == appointment.id,
                        CalendarSyncQueue.calendar_provider == provider,
                        CalendarSyncQueue.status == "failed",
                    )
                )
                if failed_entry := failed_sync.scalar_one_or_none():
                    # Reset retry count and status for failed entry
                    failed_entry.status = "pending"
                    failed_entry.retry_count = 0
                    failed_entry.scheduled_at = None
                    queued_providers.append(provider)
                    logger.info(
                        "Reset failed sync for retry: appointment_id=%d, provider=%s",
                        appointment.id,
                        provider,
                    )
                else:
                    # Create new sync entry
                    sync_entry = CalendarSyncQueue(
                        id=uuid_module.uuid4(),
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
                    db.add(sync_entry)
                    queued_providers.append(provider)

                    logger.info(
                        "Calendar sync enqueued: appointment_id=%d, provider=%s, operation=%s",
                        appointment.id,
                        provider,
                        operation,
                    )

        await db.commit()

        return {
            "queued_providers": queued_providers,
            "message": f"Sync queued for {len(queued_providers)} calendar provider(s)",
        }

    except Exception as e:
        logger.exception(
            "Failed to enqueue calendar sync: appointment_id=%d",
            appointment.id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enqueue calendar sync: {e!s}",
        ) from e


async def get_calendar_sync_health(
    user_id: int,
    workspace_id: str | None,
    db: AsyncSession,
) -> dict[str, Any]:
    """Get calendar sync health statistics for a workspace.

    Args:
        user_id: User ID
        workspace_id: Workspace ID (optional)
        db: Database session

    Returns:
        Dict with sync health metrics
    """
    try:
        # Base query for user's appointments
        query = select(Appointment).join(Contact).where(Contact.user_id == user_id)

        # Filter by workspace if provided
        if workspace_id:
            query = query.where(Appointment.workspace_id == workspace_id)

        result = await db.execute(query)
        appointments = result.scalars().all()

        # Calculate sync statistics
        total = len(appointments)
        synced = sum(1 for a in appointments if a.sync_status == "synced")
        pending = sum(1 for a in appointments if a.sync_status == "pending")
        failed = sum(1 for a in appointments if a.sync_status == "failed")
        conflict = sum(1 for a in appointments if a.sync_status == "conflict")

        # Get recent failed syncs with errors
        failed_appointments = [
            {
                "id": a.id,
                "scheduled_at": a.scheduled_at.isoformat(),
                "sync_error": a.sync_error,
                "external_calendar_id": a.external_calendar_id,
            }
            for a in appointments
            if a.sync_status == "failed" and a.sync_error
        ][:5]  # Limit to 5 most recent

        return {
            "total_appointments": total,
            "synced": synced,
            "pending": pending,
            "failed": failed,
            "conflict": conflict,
            "sync_rate": round((synced / total * 100) if total > 0 else 0, 1),
            "recent_failures": failed_appointments,
        }

    except DBAPIError as e:
        logger.exception("Database error getting calendar sync health")
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable. Please try again later.",
        ) from e


async def get_fub_sync_health(
    workspace_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Get FollowUpBoss sync health statistics for a workspace.

    Args:
        workspace_id: Workspace ID
        db: Database session

    Returns:
        Dict with sync health metrics
    """
    try:
        # Query FUBMessageSyncQueue for the workspace
        query = select(FUBMessageSyncQueue).where(FUBMessageSyncQueue.workspace_id == workspace_id)

        result = await db.execute(query)
        sync_entries = result.scalars().all()

        # Calculate sync statistics
        total_messages = len(sync_entries)
        synced = sum(1 for entry in sync_entries if entry.status == "completed")
        pending = sum(1 for entry in sync_entries if entry.status == "pending")
        failed = sum(1 for entry in sync_entries if entry.status == "failed")
        processing = sum(1 for entry in sync_entries if entry.status == "processing")

        # Get recent failed syncs with errors
        recent_failures = [
            {
                "id": str(entry.id),
                "error_message": entry.error_message,
                "created_at": entry.created_at.isoformat(),
                "payload": entry.payload,
            }
            for entry in sync_entries
            if entry.status == "failed" and entry.error_message
        ][:5]  # Limit to 5 most recent

        return {
            "total_messages": total_messages,
            "synced": synced,
            "pending": pending,
            "failed": failed,
            "processing": processing,
            "sync_rate": round((synced / total_messages * 100) if total_messages > 0 else 0, 1),
            "recent_failures": recent_failures,
        }

    except DBAPIError as e:
        logger.exception("Database error getting FUB sync health")
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable. Please try again later.",
        ) from e
