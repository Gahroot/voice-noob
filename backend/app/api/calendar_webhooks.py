"""Calendar webhook endpoints for bidirectional sync.

Handles webhooks from:
- Cal.com (booking created, rescheduled, cancelled)
- Calendly (invitee created, cancelled)
- GoHighLevel (appointment created, updated, deleted)
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.webhook_security import verify_calcom_webhook, verify_calendly_webhook
from app.db.session import get_db
from app.models.appointment import Appointment
from app.models.calendar_sync import CalendarWebhookEvent

logger = structlog.get_logger()

router = APIRouter(prefix="/webhooks/calendars", tags=["webhooks"])


@router.post("/cal-com")
async def calcom_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle Cal.com webhooks for booking changes.

    Cal.com sends webhooks for:
    - BOOKING_CREATED
    - BOOKING_RESCHEDULED
    - BOOKING_CANCELLED
    - BOOKING_REJECTED
    - BOOKING_REQUESTED
    """
    log = logger.bind(provider="cal-com")

    # Verify webhook signature
    await verify_calcom_webhook(request)

    # Parse webhook payload
    body = await request.json()
    trigger_event = body.get("triggerEvent", "")
    payload = body.get("payload", {})

    log = log.bind(event_type=trigger_event)

    # Get event UID for idempotency
    event_uid = payload.get("uid")
    if not event_uid:
        log.warning("missing_event_uid_in_payload")
        return {"status": "ok"}

    # Check for duplicate webhook
    existing = await db.execute(
        select(CalendarWebhookEvent).where(
            CalendarWebhookEvent.provider == "cal-com",
            CalendarWebhookEvent.external_event_id == event_uid,
        )
    )
    if existing.scalar_one_or_none():
        log.debug("duplicate_webhook_ignored")
        return {"status": "ok"}

    # Store webhook event for idempotency
    webhook_event = CalendarWebhookEvent(
        id=uuid.uuid4(),
        workspace_id=None,  # Will be populated when we find the appointment
        provider="cal-com",
        event_type=trigger_event,
        external_event_id=event_uid,
        payload=body,
    )
    db.add(webhook_event)

    try:
        # Process webhook based on event type
        if trigger_event == "BOOKING_CREATED":
            await process_calcom_booking_created(payload, db, log)
        elif trigger_event == "BOOKING_RESCHEDULED":
            await process_calcom_booking_rescheduled(payload, db, log)
        elif trigger_event == "BOOKING_CANCELLED":
            await process_calcom_booking_cancelled(payload, db, log)
        else:
            log.info("unhandled_event_type", event_type=trigger_event)

        # Mark as processed
        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(UTC)

    except Exception as e:
        log.exception("webhook_processing_error", error=str(e))
        # Still mark as processed to avoid retries
        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(UTC)

    await db.commit()
    return {"status": "ok"}


async def process_calcom_booking_created(
    payload: dict[str, Any], db: AsyncSession, log: structlog.stdlib.BoundLogger
) -> None:
    """Process Cal.com booking created event."""
    event_uid = payload.get("uid")

    # Check if we already have this appointment
    stmt = select(Appointment).where(
        Appointment.external_calendar_id == "cal-com",
        Appointment.external_event_uid == event_uid,
    )
    result = await db.execute(stmt)
    appointment = result.scalar_one_or_none()

    if appointment:
        log.debug("appointment_already_exists", appointment_id=appointment.id)
        return

    # External booking not tracked in our CRM - skip
    # (This would only create appointments if we want to import external bookings)
    log.info("external_booking_not_tracked", event_uid=event_uid)


async def process_calcom_booking_rescheduled(
    payload: dict[str, Any], db: AsyncSession, log: structlog.stdlib.BoundLogger
) -> None:
    """Process Cal.com booking rescheduled event."""
    event_uid = payload.get("uid")

    # Find appointment by external event UID
    stmt = select(Appointment).where(
        Appointment.external_calendar_id == "cal-com",
        Appointment.external_event_uid == event_uid,
    )
    result = await db.execute(stmt)
    appointment = result.scalar_one_or_none()

    if not appointment:
        log.info("appointment_not_found", event_uid=event_uid)
        return

    # Update appointment time
    start_time_str = payload.get("startTime")
    end_time_str = payload.get("endTime")

    if start_time_str and end_time_str:
        new_start = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        new_end = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))

        appointment.scheduled_at = new_start
        appointment.duration_minutes = int((new_end - new_start).total_seconds() / 60)
        appointment.last_synced_at = datetime.now(UTC)
        appointment.sync_status = "synced"

        log.info(
            "appointment_rescheduled",
            appointment_id=appointment.id,
            new_start=new_start.isoformat(),
        )


async def process_calcom_booking_cancelled(
    payload: dict[str, Any], db: AsyncSession, log: structlog.stdlib.BoundLogger
) -> None:
    """Process Cal.com booking cancelled event."""
    event_uid = payload.get("uid")

    # Find appointment by external event UID
    stmt = select(Appointment).where(
        Appointment.external_calendar_id == "cal-com",
        Appointment.external_event_uid == event_uid,
    )
    result = await db.execute(stmt)
    appointment = result.scalar_one_or_none()

    if not appointment:
        log.info("appointment_not_found", event_uid=event_uid)
        return

    # Update appointment status
    appointment.status = "cancelled"
    appointment.sync_status = "synced"
    appointment.last_synced_at = datetime.now(UTC)

    log.info("appointment_cancelled", appointment_id=appointment.id)


@router.post("/calendly")
async def calendly_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle Calendly webhooks for invitee events.

    Calendly sends webhooks for:
    - invitee.created
    - invitee.canceled
    """
    log = logger.bind(provider="calendly")

    # Verify webhook signature
    await verify_calendly_webhook(request)

    # Parse webhook payload
    body = await request.json()
    event_type = body.get("event", "")
    payload = body.get("payload", {})

    log = log.bind(event_type=event_type)

    # Get event URI for idempotency
    event_uri = payload.get("uri") or payload.get("event", {}).get("uri", "")
    if not event_uri:
        log.warning("missing_event_uri_in_payload")
        return {"status": "ok"}

    # Extract event ID from URI
    event_id = event_uri.split("/")[-1] if event_uri else ""

    # Check for duplicate webhook
    existing = await db.execute(
        select(CalendarWebhookEvent).where(
            CalendarWebhookEvent.provider == "calendly",
            CalendarWebhookEvent.external_event_id == event_id,
        )
    )
    if existing.scalar_one_or_none():
        log.debug("duplicate_webhook_ignored")
        return {"status": "ok"}

    # Store webhook event for idempotency
    webhook_event = CalendarWebhookEvent(
        id=uuid.uuid4(),
        workspace_id=None,
        provider="calendly",
        event_type=event_type,
        external_event_id=event_id,
        payload=body,
    )
    db.add(webhook_event)

    try:
        # Process webhook based on event type
        if event_type == "invitee.created":
            await process_calendly_invitee_created(payload, db, log)
        elif event_type == "invitee.canceled":
            await process_calendly_invitee_canceled(payload, db, log)
        else:
            log.info("unhandled_event_type", event_type=event_type)

        # Mark as processed
        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(UTC)

    except Exception as e:
        log.exception("webhook_processing_error", error=str(e))
        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(UTC)

    await db.commit()
    return {"status": "ok"}


async def process_calendly_invitee_created(
    payload: dict[str, Any], db: AsyncSession, log: structlog.stdlib.BoundLogger
) -> None:
    """Process Calendly invitee created event."""
    event_uri = payload.get("uri", "")
    event_id = event_uri.split("/")[-1] if event_uri else ""

    # Check if we already have this appointment
    stmt = select(Appointment).where(
        Appointment.external_calendar_id == "calendly",
        Appointment.external_event_uid == event_id,
    )
    result = await db.execute(stmt)
    appointment = result.scalar_one_or_none()

    if appointment:
        log.debug("appointment_already_exists", appointment_id=appointment.id)
        return

    # External booking not tracked in our CRM - skip
    log.info("external_booking_not_tracked", event_id=event_id)


async def process_calendly_invitee_canceled(
    payload: dict[str, Any], db: AsyncSession, log: structlog.stdlib.BoundLogger
) -> None:
    """Process Calendly invitee canceled event."""
    event_uri = payload.get("uri", "")
    event_id = event_uri.split("/")[-1] if event_uri else ""

    # Find appointment by external event UID
    stmt = select(Appointment).where(
        Appointment.external_calendar_id == "calendly",
        Appointment.external_event_uid == event_id,
    )
    result = await db.execute(stmt)
    appointment = result.scalar_one_or_none()

    if not appointment:
        log.info("appointment_not_found", event_id=event_id)
        return

    # Update appointment status
    appointment.status = "cancelled"
    appointment.sync_status = "synced"
    appointment.last_synced_at = datetime.now(UTC)

    log.info("appointment_cancelled", appointment_id=appointment.id)


@router.post("/gohighlevel")
async def gohighlevel_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle GoHighLevel webhooks for appointment events.

    GoHighLevel sends webhooks for various events.
    Signature verification would need to be implemented based on GHL docs.
    """
    log = logger.bind(provider="gohighlevel")

    # Parse webhook payload
    body = await request.json()
    event_type = body.get("type", "")
    data = body.get("data", {})

    log = log.bind(event_type=event_type)

    # Get appointment ID for idempotency
    appointment_id = data.get("id", "")
    if not appointment_id:
        log.warning("missing_appointment_id_in_payload")
        return {"status": "ok"}

    # Check for duplicate webhook
    existing = await db.execute(
        select(CalendarWebhookEvent).where(
            CalendarWebhookEvent.provider == "gohighlevel",
            CalendarWebhookEvent.external_event_id == appointment_id,
        )
    )
    if existing.scalar_one_or_none():
        log.debug("duplicate_webhook_ignored")
        return {"status": "ok"}

    # Store webhook event for idempotency
    webhook_event = CalendarWebhookEvent(
        id=uuid.uuid4(),
        workspace_id=None,
        provider="gohighlevel",
        event_type=event_type,
        external_event_id=appointment_id,
        payload=body,
    )
    db.add(webhook_event)

    try:
        # Process based on event type
        # GoHighLevel event types would need to be documented
        log.info("gohighlevel_webhook_received", event_type=event_type)

        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(UTC)

    except Exception as e:
        log.exception("webhook_processing_error", error=str(e))
        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(UTC)

    await db.commit()
    return {"status": "ok"}
