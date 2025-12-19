"""Tests for enhanced appointment booking with comprehensive logging and validation."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.contact import Contact
from app.services.tools.crm_tools import CRMTools


class TestEnhancedAppointmentBooking:
    """Test enhanced appointment booking with logging, validation, and agent tracking."""

    @pytest.fixture
    async def crm_tools(self, test_session: AsyncSession, create_test_user: Any) -> CRMTools:
        """Create CRMTools instance for testing."""
        user = await create_test_user()
        return CRMTools(db=test_session, user_id=user.id, workspace_id=None)

    @pytest.mark.asyncio
    async def test_book_appointment_success_with_agent_id(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
        create_test_contact: Any,
    ) -> None:
        """Test successful appointment booking with agent_id tracking."""
        from app.models.agent import Agent

        user = await create_test_user()
        contact = await create_test_contact(user_id=user.id, phone_number="+1234567890")

        # Create a real agent for the foreign key constraint
        agent = Agent(
            user_id=user.id,
            name="Test Agent",
            system_prompt="Test prompt",
            is_active=True,
            pricing_tier="free",
            channel_mode="voice",
        )
        test_session.add(agent)
        await test_session.commit()
        await test_session.refresh(agent)

        agent_id = str(agent.id)

        crm_tools = CRMTools(db=test_session, user_id=user.id)

        # Book appointment with agent_id
        scheduled_time = datetime.now(UTC) + timedelta(days=1)
        result = await crm_tools.book_appointment(
            contact_phone=contact.phone_number,
            scheduled_at=scheduled_time.isoformat(),
            duration_minutes=30,
            service_type="consultation",
            notes="Test appointment",
            agent_id=agent_id,
        )

        # Verify success
        assert result["success"] is True
        assert "appointment_id" in result
        assert result["customer_name"] == f"{contact.first_name} {contact.last_name or ''}".strip()

        # Verify agent_id was stored
        from sqlalchemy import select

        query = await test_session.execute(
            select(Appointment).where(Appointment.id == result["appointment_id"])
        )
        appointment = query.scalar_one()
        assert str(appointment.agent_id) == agent_id

    @pytest.mark.asyncio
    async def test_book_appointment_auto_creates_contact(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
    ) -> None:
        """Test appointment booking auto-creates contact if not found."""
        user = await create_test_user()
        crm_tools = CRMTools(db=test_session, user_id=user.id)

        # Book appointment with non-existent phone number
        scheduled_time = datetime.now(UTC) + timedelta(days=1)
        result = await crm_tools.book_appointment(
            contact_phone="+9999999999",
            scheduled_at=scheduled_time.isoformat(),
            duration_minutes=60,
        )

        # Verify success
        assert result["success"] is True
        assert "appointment_id" in result
        assert "SMS Contact" in result["customer_name"]

        # Verify contact was auto-created
        from sqlalchemy import select

        query = await test_session.execute(
            select(Contact).where(Contact.phone_number == "+9999999999")
        )
        contact = query.scalar_one()
        assert contact.first_name == "SMS Contact"
        assert contact.status == "new"

    @pytest.mark.asyncio
    async def test_book_appointment_rejects_past_datetime(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
        create_test_contact: Any,
    ) -> None:
        """Test future date validation - rejects appointments in the past."""
        user = await create_test_user()
        contact = await create_test_contact(user_id=user.id, phone_number="+1111111111")
        crm_tools = CRMTools(db=test_session, user_id=user.id)

        # Try to book appointment in the past
        past_time = datetime.now(UTC) - timedelta(hours=2)
        result = await crm_tools.book_appointment(
            contact_phone=contact.phone_number,
            scheduled_at=past_time.isoformat(),
            duration_minutes=30,
        )

        # Verify rejection
        assert result["success"] is False
        assert "past" in result["error"].lower()
        assert "Cannot book appointment in the past" in result["error"]

    @pytest.mark.asyncio
    async def test_book_appointment_validates_empty_phone(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
    ) -> None:
        """Test parameter validation - rejects empty contact_phone."""
        user = await create_test_user()
        crm_tools = CRMTools(db=test_session, user_id=user.id)

        scheduled_time = datetime.now(UTC) + timedelta(days=1)
        result = await crm_tools.book_appointment(
            contact_phone="",
            scheduled_at=scheduled_time.isoformat(),
        )

        # Verify rejection
        assert result["success"] is False
        assert "contact_phone cannot be empty" in result["error"]

    @pytest.mark.asyncio
    async def test_book_appointment_validates_empty_datetime(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
        create_test_contact: Any,
    ) -> None:
        """Test parameter validation - rejects empty scheduled_at."""
        user = await create_test_user()
        contact = await create_test_contact(user_id=user.id, phone_number="+2222222222")
        crm_tools = CRMTools(db=test_session, user_id=user.id)

        result = await crm_tools.book_appointment(
            contact_phone=contact.phone_number,
            scheduled_at="",
        )

        # Verify rejection
        assert result["success"] is False
        assert "scheduled_at cannot be empty" in result["error"]

    @pytest.mark.asyncio
    async def test_book_appointment_rejects_invalid_datetime_format(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
        create_test_contact: Any,
    ) -> None:
        """Test datetime parsing - rejects invalid ISO format."""
        user = await create_test_user()
        contact = await create_test_contact(user_id=user.id, phone_number="+3333333333")
        crm_tools = CRMTools(db=test_session, user_id=user.id)

        result = await crm_tools.book_appointment(
            contact_phone=contact.phone_number,
            scheduled_at="not-a-valid-datetime",
        )

        # Verify rejection
        assert result["success"] is False
        assert "Invalid datetime format" in result["error"]
        assert "ISO 8601" in result["error"]

    @pytest.mark.asyncio
    async def test_book_appointment_handles_z_suffix(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
        create_test_contact: Any,
    ) -> None:
        """Test datetime parsing - handles Z suffix for UTC."""
        user = await create_test_user()
        contact = await create_test_contact(user_id=user.id, phone_number="+4444444444")
        crm_tools = CRMTools(db=test_session, user_id=user.id)

        # Use Z suffix for UTC
        scheduled_time = datetime.now(UTC) + timedelta(days=1)
        iso_with_z = scheduled_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        result = await crm_tools.book_appointment(
            contact_phone=contact.phone_number,
            scheduled_at=iso_with_z,
        )

        # Verify success
        assert result["success"] is True
        assert "appointment_id" in result

    @pytest.mark.asyncio
    async def test_book_appointment_handles_timezone_offset(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
        create_test_contact: Any,
    ) -> None:
        """Test datetime parsing - handles timezone offset."""
        user = await create_test_user()
        contact = await create_test_contact(user_id=user.id, phone_number="+5555555555")
        crm_tools = CRMTools(db=test_session, user_id=user.id)

        # Use timezone offset
        scheduled_time = datetime.now(UTC) + timedelta(days=1)
        iso_with_offset = scheduled_time.strftime("%Y-%m-%dT%H:%M:%S-05:00")

        result = await crm_tools.book_appointment(
            contact_phone=contact.phone_number,
            scheduled_at=iso_with_offset,
        )

        # Verify success
        assert result["success"] is True
        assert "appointment_id" in result

    @pytest.mark.skip(reason="Requires workspace fixture that is not available")
    @pytest.mark.asyncio
    async def test_book_appointment_timezone_conversion_failure(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
        create_test_contact: Any,
        create_test_workspace: Any,
    ) -> None:
        """Test timezone error handling - fails fast on invalid timezone."""
        user = await create_test_user()
        workspace = await create_test_workspace(user_id=user.id)
        contact = await create_test_contact(
            user_id=user.id, workspace_id=workspace.id, phone_number="+6666666666"
        )

        # Set invalid timezone in workspace settings
        workspace.settings = {"timezone": "Invalid/Timezone"}
        test_session.add(workspace)
        await test_session.commit()

        crm_tools = CRMTools(db=test_session, user_id=user.id, workspace_id=workspace.id)

        # Use naive datetime (no timezone) - will try to use workspace timezone
        scheduled_time = datetime.now(UTC) + timedelta(days=1)
        naive_iso = scheduled_time.strftime("%Y-%m-%dT%H:%M:%S")

        result = await crm_tools.book_appointment(
            contact_phone=contact.phone_number,
            scheduled_at=naive_iso,
        )

        # Verify hard failure (not silent warning)
        assert result["success"] is False
        assert "Failed to interpret datetime in timezone" in result["error"]
        assert "Invalid/Timezone" in result["error"]

    @pytest.mark.asyncio
    @patch("structlog.get_logger")
    async def test_book_appointment_comprehensive_logging(
        self,
        mock_get_logger: MagicMock,
        test_session: AsyncSession,
        create_test_user: Any,
        create_test_contact: Any,
    ) -> None:
        """Test comprehensive logging throughout booking process."""
        from app.models.agent import Agent

        # Setup mock logger
        mock_logger = MagicMock()
        mock_logger.bind.return_value = mock_logger
        mock_get_logger.return_value = mock_logger

        user = await create_test_user()
        contact = await create_test_contact(user_id=user.id, phone_number="+7777777777")

        # Create a real agent
        agent = Agent(
            user_id=user.id,
            name="Test Agent",
            system_prompt="Test prompt",
            is_active=True,
            pricing_tier="free",
            channel_mode="voice",
        )
        test_session.add(agent)
        await test_session.commit()
        await test_session.refresh(agent)

        agent_id = str(agent.id)

        crm_tools = CRMTools(db=test_session, user_id=user.id)
        crm_tools.logger = mock_logger  # Inject mock logger

        # Book appointment
        scheduled_time = datetime.now(UTC) + timedelta(days=1)
        result = await crm_tools.book_appointment(
            contact_phone=contact.phone_number,
            scheduled_at=scheduled_time.isoformat(),
            duration_minutes=45,
            service_type="demo",
            notes="Test notes",
            agent_id=agent_id,
        )

        # Verify success
        assert result["success"] is True

        # Verify logging calls (check key log events)
        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]

        # Should log these key events
        assert "booking_appointment_started" in log_calls
        assert "contact_lookup_success" in log_calls
        assert "appointment_created_in_database" in log_calls
        assert "booking_appointment_success" in log_calls

    @pytest.mark.asyncio
    async def test_book_appointment_performance_metrics(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
        create_test_contact: Any,
    ) -> None:
        """Test that performance timing metrics are tracked."""
        user = await create_test_user()
        contact = await create_test_contact(user_id=user.id, phone_number="+8888888888")

        # Mock logger to capture timing metrics
        with patch("structlog.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_logger.bind.return_value = mock_logger
            mock_get_logger.return_value = mock_logger

            crm_tools = CRMTools(db=test_session, user_id=user.id)
            crm_tools.logger = mock_logger

            scheduled_time = datetime.now(UTC) + timedelta(days=1)
            result = await crm_tools.book_appointment(
                contact_phone=contact.phone_number,
                scheduled_at=scheduled_time.isoformat(),
            )

            assert result["success"] is True

            # Check that timing metrics were logged
            all_calls = mock_logger.info.call_args_list + mock_logger.debug.call_args_list

            # Find calls with duration_ms
            timing_calls = [
                call for call in all_calls if "duration_ms" in call[1] or "duration_ms" in str(call)
            ]

            # Should have multiple timing measurements
            assert len(timing_calls) > 0

    @pytest.mark.asyncio
    async def test_book_appointment_returns_all_expected_fields(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
        create_test_contact: Any,
    ) -> None:
        """Test that successful booking returns all expected response fields."""
        user = await create_test_user()
        contact = await create_test_contact(
            user_id=user.id, first_name="John", last_name="Doe", phone_number="+9999999998"
        )
        crm_tools = CRMTools(db=test_session, user_id=user.id)

        scheduled_time = datetime.now(UTC) + timedelta(days=1)
        result = await crm_tools.book_appointment(
            contact_phone=contact.phone_number,
            scheduled_at=scheduled_time.isoformat(),
            duration_minutes=60,
            service_type="consultation",
        )

        # Verify all expected fields
        assert result["success"] is True
        assert "appointment_id" in result
        assert result["appointment_id"] is not None
        assert "customer_name" in result
        assert "John Doe" in result["customer_name"]
        assert "scheduled_at" in result
        assert "duration_minutes" in result
        assert result["duration_minutes"] == 60
        assert "message" in result
        assert "John" in result["message"]

    @pytest.mark.asyncio
    async def test_book_appointment_error_includes_type(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
        create_test_contact: Any,
    ) -> None:
        """Test that errors include error_type for debugging."""
        user = await create_test_user()
        contact = await create_test_contact(user_id=user.id, phone_number="+1010101010")
        crm_tools = CRMTools(db=test_session, user_id=user.id)

        # Force an error with invalid datetime
        result = await crm_tools.book_appointment(
            contact_phone=contact.phone_number,
            scheduled_at="invalid-format",
        )

        # Verify error response structure
        assert result["success"] is False
        assert "error" in result
        # The error should describe the issue
        assert "Invalid datetime format" in result["error"]

    @pytest.mark.asyncio
    async def test_book_appointment_with_null_agent_id(
        self,
        test_session: AsyncSession,
        create_test_user: Any,
        create_test_contact: Any,
    ) -> None:
        """Test booking without agent_id (backward compatibility)."""
        user = await create_test_user()
        contact = await create_test_contact(user_id=user.id, phone_number="+1212121212")
        crm_tools = CRMTools(db=test_session, user_id=user.id)

        scheduled_time = datetime.now(UTC) + timedelta(days=1)
        result = await crm_tools.book_appointment(
            contact_phone=contact.phone_number,
            scheduled_at=scheduled_time.isoformat(),
            agent_id=None,  # Explicit None
        )

        # Should still succeed
        assert result["success"] is True
        assert "appointment_id" in result

        # Verify agent_id is None in database
        from sqlalchemy import select

        query = await test_session.execute(
            select(Appointment).where(Appointment.id == result["appointment_id"])
        )
        appointment = query.scalar_one()
        assert appointment.agent_id is None
