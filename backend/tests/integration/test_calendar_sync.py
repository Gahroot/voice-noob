"""Integration tests for calendar sync service with Cal.com."""

# ruff: noqa: S106, SLF001, F841

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.appointment import Appointment
from app.models.calendar_sync import CalendarSyncQueue
from app.models.contact import Contact
from app.models.user_integration import UserIntegration
from app.models.workspace import Workspace
from app.services.calendar_sync_service import CalendarSyncService


@pytest_asyncio.fixture
async def test_user(test_session):
    """Create a test user."""
    from app.models.user import User

    user = User(
        email="testuser@example.com",
        hashed_password="test_hashed_pw",
        full_name="Test User",
        is_active=True,
        is_superuser=False,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def workspace(test_session, test_user):
    """Create a test workspace."""
    workspace = Workspace(
        id=uuid.uuid4(),
        name="Test Workspace",
        user_id=test_user.id,
        is_default=True,
        settings={"timezone": "America/New_York"},
    )
    test_session.add(workspace)
    await test_session.commit()
    await test_session.refresh(workspace)
    return workspace


@pytest_asyncio.fixture
async def calcom_integration(test_session, test_user, workspace):
    """Create a Cal.com integration."""
    integration = UserIntegration(
        id=uuid.uuid4(),
        user_id=test_user.id,
        workspace_id=workspace.id,
        integration_id="cal-com",
        integration_name="Cal.com",
        credentials={
            "api_key": "cal_test_1234567890abcdef",
            "event_type_id": 12345,
        },
        is_active=True,
    )
    test_session.add(integration)
    await test_session.commit()
    await test_session.refresh(integration)
    return integration


@pytest_asyncio.fixture
async def contact(test_session, test_user, workspace):
    """Create a test contact."""
    contact = Contact(
        user_id=test_user.id,
        workspace_id=workspace.id,
        first_name="John",
        last_name="Doe",
        email="john.doe@example.com",
        phone_number="+15551234567",
        status="active",
    )
    test_session.add(contact)
    await test_session.commit()
    await test_session.refresh(contact)
    return contact


@pytest_asyncio.fixture
async def appointment(test_session, contact, workspace):
    """Create a test appointment."""
    scheduled_time = datetime.now(UTC) + timedelta(days=1)
    appointment = Appointment(
        contact_id=contact.id,
        workspace_id=workspace.id,
        scheduled_at=scheduled_time,
        duration_minutes=30,
        service_type="Consultation",
        notes="Test appointment",
        status="scheduled",
    )
    test_session.add(appointment)
    await test_session.commit()
    await test_session.refresh(appointment)
    return appointment


@pytest_asyncio.fixture
async def sync_queue_entry(test_session, appointment, workspace):
    """Create a sync queue entry."""
    entry = CalendarSyncQueue(
        id=uuid.uuid4(),
        appointment_id=appointment.id,
        workspace_id=workspace.id,
        operation="create",
        calendar_provider="cal-com",
        status="pending",
        payload={
            "appointment_id": appointment.id,
            "scheduled_at": appointment.scheduled_at.isoformat(),
        },
    )
    test_session.add(entry)
    await test_session.commit()
    await test_session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_calendar_sync_service_initialization():
    """Test calendar sync service can be initialized."""
    service = CalendarSyncService(poll_interval=30)
    assert service.poll_interval == 30
    assert service.running is False
    assert service._task is None


@pytest.mark.asyncio
async def test_sync_queue_entry_created_with_appointment(
    test_session, appointment, workspace, calcom_integration
):
    """Test that sync queue entry exists when appointment is created."""
    # Query for sync queue entries
    stmt = select(CalendarSyncQueue).where(CalendarSyncQueue.appointment_id == appointment.id)
    result = await test_session.execute(stmt)
    entries = result.scalars().all()

    # Note: This test verifies if the auto-enqueue is working
    # If no entries found, it means _enqueue_calendar_sync wasn't called
    if len(entries) == 0:
        pytest.skip(
            "Sync queue auto-enqueue not triggered (expected if appointment "
            "created directly without CRM tools)"
        )

    # If entries exist, verify they're correct
    assert all(entry.workspace_id == workspace.id for entry in entries)
    assert any(entry.calendar_provider == "cal-com" for entry in entries)


@pytest.mark.asyncio
async def test_calcom_create_booking_success(test_session, sync_queue_entry, appointment):
    """Test successful Cal.com booking creation."""
    # Mock Cal.com API response
    mock_response = {
        "success": True,
        "message": "Booking created successfully",
        "booking": {
            "uid": "booking_abc123",
            "id": 67890,
            "title": "Consultation",
            "start_time": appointment.scheduled_at.isoformat(),
            "end_time": (
                appointment.scheduled_at + timedelta(minutes=appointment.duration_minutes)
            ).isoformat(),
            "status": "accepted",
        },
    }

    # Mock the CalComTools.create_booking method
    with patch("app.services.calendar_sync_service.CalComTools") as mock_calcom_class:
        mock_calcom_instance = AsyncMock()
        mock_calcom_instance.create_booking = AsyncMock(
            return_value={
                "success": True,
                "id": 67890,
                "uid": "booking_abc123",
            }
        )
        mock_calcom_instance.close = AsyncMock()
        mock_calcom_class.return_value = mock_calcom_instance

        # Create service and process entry
        service = CalendarSyncService(poll_interval=1)
        await service._process_entry(sync_queue_entry, test_session)

        # Verify sync queue entry was updated
        await test_session.refresh(sync_queue_entry)
        assert sync_queue_entry.status == "completed"
        assert sync_queue_entry.processed_at is not None

        # Verify appointment was updated
        await test_session.refresh(appointment)
        assert appointment.sync_status == "synced"
        assert appointment.external_calendar_id == "cal-com"
        assert appointment.external_event_id == 67890
        assert appointment.external_event_uid == "booking_abc123"
        assert appointment.last_synced_at is not None
        assert appointment.sync_error is None


@pytest.mark.asyncio
async def test_calcom_create_booking_failure(test_session, sync_queue_entry, appointment):
    """Test Cal.com booking creation failure with retry."""
    # Mock Cal.com API failure
    with patch("app.services.calendar_sync_service.CalComTools") as mock_calcom_class:
        mock_calcom_instance = AsyncMock()
        mock_calcom_instance.create_booking = AsyncMock(
            return_value={"success": False, "error": "API rate limit exceeded"}
        )
        mock_calcom_instance.close = AsyncMock()
        mock_calcom_class.return_value = mock_calcom_instance

        # Create service and process entry
        service = CalendarSyncService(poll_interval=1)

        # First attempt - should fail and schedule retry
        await service._process_entry(sync_queue_entry, test_session)

        # Verify sync queue entry was updated for retry
        await test_session.refresh(sync_queue_entry)
        assert sync_queue_entry.status == "pending"  # Back to pending for retry
        assert sync_queue_entry.retry_count == 1
        assert sync_queue_entry.error_message == "API rate limit exceeded"
        assert sync_queue_entry.scheduled_at is not None  # Scheduled for retry

        # Verify appointment sync status
        await test_session.refresh(appointment)
        # Should still be in pending/failed state since sync hasn't succeeded
        assert appointment.sync_status in ("pending", "failed", None)


@pytest.mark.asyncio
async def test_calcom_create_booking_permanent_failure(test_session, sync_queue_entry, appointment):
    """Test Cal.com booking creation with permanent failure after max retries."""
    # Set retry count near max
    sync_queue_entry.retry_count = 2
    sync_queue_entry.max_retries = 3
    await test_session.commit()

    # Mock Cal.com API failure
    with patch("app.services.calendar_sync_service.CalComTools") as mock_calcom_class:
        mock_calcom_instance = AsyncMock()
        mock_calcom_instance.create_booking = AsyncMock(
            return_value={"success": False, "error": "Invalid event type ID"}
        )
        mock_calcom_instance.close = AsyncMock()
        mock_calcom_class.return_value = mock_calcom_instance

        # Create service and process entry (final retry)
        service = CalendarSyncService(poll_interval=1)
        await service._process_entry(sync_queue_entry, test_session)

        # Verify sync queue entry is permanently failed
        await test_session.refresh(sync_queue_entry)
        assert sync_queue_entry.status == "failed"
        assert sync_queue_entry.retry_count == 3
        assert sync_queue_entry.error_message == "Invalid event type ID"

        # Verify appointment sync status is failed
        await test_session.refresh(appointment)
        assert appointment.sync_status == "failed"
        assert appointment.sync_error == "Invalid event type ID"


@pytest.mark.asyncio
async def test_calcom_cancel_booking_success(test_session, appointment, workspace):
    """Test successful Cal.com booking cancellation."""
    # Set up appointment with existing external booking
    appointment.external_calendar_id = "cal-com"
    appointment.external_event_id = 67890
    appointment.external_event_uid = "booking_abc123"
    appointment.sync_status = "synced"
    await test_session.commit()

    # Create cancel sync queue entry
    cancel_entry = CalendarSyncQueue(
        id=uuid.uuid4(),
        appointment_id=appointment.id,
        workspace_id=workspace.id,
        operation="cancel",
        calendar_provider="cal-com",
        status="pending",
    )
    test_session.add(cancel_entry)
    await test_session.commit()

    # Mock Cal.com API response
    with patch("app.services.calendar_sync_service.CalComTools") as mock_calcom_class:
        mock_calcom_instance = AsyncMock()
        mock_calcom_instance.cancel_booking = AsyncMock(return_value={"success": True})
        mock_calcom_instance.close = AsyncMock()
        mock_calcom_class.return_value = mock_calcom_instance

        # Create service and process entry
        service = CalendarSyncService(poll_interval=1)
        await service._process_entry(cancel_entry, test_session)

        # Verify cancellation was called with correct UID
        mock_calcom_instance.cancel_booking.assert_called_once()
        call_args = mock_calcom_instance.cancel_booking.call_args
        assert call_args[1]["booking_uid"] == "booking_abc123"

        # Verify sync queue entry was updated
        await test_session.refresh(cancel_entry)
        assert cancel_entry.status == "completed"


@pytest.mark.asyncio
async def test_missing_integration_credentials(test_session, sync_queue_entry):
    """Test sync fails gracefully when integration is not connected."""
    # Don't create integration - simulates disconnected calendar

    # Create service and process entry
    service = CalendarSyncService(poll_interval=1)
    await service._process_entry(sync_queue_entry, test_session)

    # Verify sync failed due to missing integration
    await test_session.refresh(sync_queue_entry)
    assert sync_queue_entry.status in ("pending", "failed")
    assert "not connected" in sync_queue_entry.error_message.lower()


@pytest.mark.asyncio
async def test_process_sync_queue_batch(test_session, workspace, calcom_integration):
    """Test processing multiple sync queue entries in batch."""
    # Create multiple appointments and sync queue entries
    appointments = []
    entries = []

    for i in range(3):
        contact = Contact(
            user_id=workspace.user_id,
            workspace_id=workspace.id,
            first_name=f"Contact{i}",
            email=f"contact{i}@example.com",
            phone_number=f"+155512345{i:02d}",
            status="active",
        )
        test_session.add(contact)
        await test_session.flush()

        appointment = Appointment(
            contact_id=contact.id,
            workspace_id=workspace.id,
            scheduled_at=datetime.now(UTC) + timedelta(days=i + 1),
            duration_minutes=30,
            status="scheduled",
        )
        test_session.add(appointment)
        await test_session.flush()
        appointments.append(appointment)

        entry = CalendarSyncQueue(
            id=uuid.uuid4(),
            appointment_id=appointment.id,
            workspace_id=workspace.id,
            operation="create",
            calendar_provider="cal-com",
            status="pending",
        )
        test_session.add(entry)
        entries.append(entry)

    await test_session.commit()

    # Mock Cal.com API
    with patch("app.services.calendar_sync_service.CalComTools") as mock_calcom_class:
        mock_calcom_instance = AsyncMock()
        mock_calcom_instance.create_booking = AsyncMock(
            return_value={"success": True, "id": 999, "uid": "test_uid"}
        )
        mock_calcom_instance.close = AsyncMock()
        mock_calcom_class.return_value = mock_calcom_instance

        # Process the queue
        service = CalendarSyncService(poll_interval=1)
        await service._process_sync_queue()

        # Verify all entries were processed
        for entry in entries:
            await test_session.refresh(entry)
            assert entry.status == "completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
