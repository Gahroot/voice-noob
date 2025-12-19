"""Factory for creating calendar provider instances."""

from typing import Any

from app.services.calendar_providers.base import CalendarProvider
from app.services.calendar_providers.calcom_provider import CalComProvider
from app.services.calendar_providers.calendly_provider import CalendlyProvider
from app.services.calendar_providers.gohighlevel_provider import GoHighLevelProvider
from app.services.calendar_providers.google_calendar_provider import GoogleCalendarProvider


class ProviderFactory:
    """Factory for creating calendar provider instances."""

    @staticmethod
    def create_provider(
        provider_name: str,
        credentials: dict[str, Any],
    ) -> CalendarProvider:
        """Create a calendar provider instance.

        Args:
            provider_name: Provider identifier (cal-com, google-calendar, etc.)
            credentials: Provider credentials dict

        Returns:
            CalendarProvider instance

        Raises:
            ValueError: If provider is not supported
        """
        if provider_name == "cal-com":
            return CalComProvider(
                api_key=credentials.get("api_key", ""),
                event_type_id=credentials.get("event_type_id"),
            )
        if provider_name == "calendly":
            return CalendlyProvider(
                access_token=credentials.get("access_token", ""),
            )
        if provider_name == "gohighlevel":
            return GoHighLevelProvider(
                access_token=credentials.get("access_token", ""),
                location_id=credentials.get("location_id", ""),
                calendar_id=credentials.get("calendar_id"),
            )
        if provider_name == "google-calendar":
            return GoogleCalendarProvider(
                access_token=credentials.get("access_token", ""),
                refresh_token=credentials.get("refresh_token"),
                calendar_id=credentials.get("calendar_id", "primary"),
                client_id=credentials.get("client_id"),
                client_secret=credentials.get("client_secret"),
            )
        raise ValueError(f"Unsupported calendar provider: {provider_name}")
