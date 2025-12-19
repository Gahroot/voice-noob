"""Tests for Google Calendar tools."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.tools.google_calendar_tools import GoogleCalendarTools


class TestGoogleCalendarTools:
    """Tests for GoogleCalendarTools class."""

    @pytest.fixture
    def google_calendar_tools(self):
        """Create GoogleCalendarTools instance with mock credentials."""
        return GoogleCalendarTools(
            access_token="mock_access_token",  # noqa: S106
            refresh_token="mock_refresh_token",  # noqa: S106
            calendar_id="primary",
        )

    @pytest.mark.asyncio
    async def test_create_event_success(self, google_calendar_tools):
        """Test successful event creation."""
        with patch.object(google_calendar_tools, "_get_service") as mock_service:
            mock_events = MagicMock()
            mock_events.insert().execute.return_value = {
                "id": "event123",
                "htmlLink": "https://calendar.google.com/event123",
            }
            mock_service.return_value.events.return_value = mock_events

            result = await google_calendar_tools.create_event(
                summary="Test Appointment",
                start_time="2025-12-20T14:00:00Z",
                duration_minutes=30,
                attendee_email="customer@example.com",
                attendee_name="John Doe",
            )

            assert result["success"] is True
            assert result["event_id"] == "event123"
            assert "event_link" in result

    @pytest.mark.asyncio
    async def test_create_event_without_attendee(self, google_calendar_tools):
        """Test event creation without attendee email."""
        with patch.object(google_calendar_tools, "_get_service") as mock_service:
            mock_events = MagicMock()
            mock_events.insert().execute.return_value = {
                "id": "event456",
                "htmlLink": "https://calendar.google.com/event456",
            }
            mock_service.return_value.events.return_value = mock_events

            result = await google_calendar_tools.create_event(
                summary="Test Appointment",
                start_time="2025-12-20T14:00:00Z",
                duration_minutes=30,
            )

            assert result["success"] is True
            assert result["event_id"] == "event456"

    @pytest.mark.asyncio
    async def test_update_event_success(self, google_calendar_tools):
        """Test successful event update."""
        with patch.object(google_calendar_tools, "_get_service") as mock_service:
            mock_events = MagicMock()
            mock_events.get().execute.return_value = {
                "id": "event123",
                "summary": "Old Title",
                "start": {"dateTime": "2025-12-20T14:00:00Z"},
                "end": {"dateTime": "2025-12-20T14:30:00Z"},
            }
            mock_events.update().execute.return_value = {"id": "event123"}
            mock_service.return_value.events.return_value = mock_events

            result = await google_calendar_tools.update_event(
                event_id="event123",
                start_time="2025-12-20T15:00:00Z",
                duration_minutes=60,
            )

            assert result["success"] is True
            assert result["event_id"] == "event123"

    @pytest.mark.asyncio
    async def test_cancel_event_success(self, google_calendar_tools):
        """Test successful event cancellation."""
        with patch.object(google_calendar_tools, "_get_service") as mock_service:
            mock_events = MagicMock()
            mock_events.delete().execute.return_value = None
            mock_service.return_value.events.return_value = mock_events

            result = await google_calendar_tools.cancel_event(
                event_id="event123",
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_cancel_event_with_reason(self, google_calendar_tools):
        """Test event cancellation with reason."""
        with patch.object(google_calendar_tools, "_get_service") as mock_service:
            mock_events = MagicMock()
            mock_events.get().execute.return_value = {
                "id": "event123",
                "summary": "Test Event",
                "description": "Original description",
                "start": {"dateTime": "2025-12-20T14:00:00Z"},
                "end": {"dateTime": "2025-12-20T14:30:00Z"},
            }
            mock_events.update().execute.return_value = {"id": "event123"}
            mock_service.return_value.events.return_value = mock_events

            result = await google_calendar_tools.cancel_event(
                event_id="event123",
                reason="Customer cancelled",
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_create_event_api_error(self, google_calendar_tools):
        """Test handling of Google API errors."""
        from googleapiclient.errors import HttpError

        with patch.object(google_calendar_tools, "_get_service") as mock_service:
            mock_response = MagicMock()
            mock_response.status = 403
            error = HttpError(resp=mock_response, content=b"Forbidden")
            error._get_reason = MagicMock(return_value="Forbidden")  # noqa: SLF001

            mock_events = MagicMock()
            mock_events.insert().execute.side_effect = error
            mock_service.return_value.events.return_value = mock_events

            result = await google_calendar_tools.create_event(
                summary="Test Appointment",
                start_time="2025-12-20T14:00:00Z",
                duration_minutes=30,
            )

            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_close(self, google_calendar_tools):
        """Test close method (no-op)."""
        await google_calendar_tools.close()
        # Should complete without error
