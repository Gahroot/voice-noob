"""Telnyx telephony service implementation."""

import httpx
import structlog
import telnyx

from app.services.telephony.base import (
    CallDirection,
    CallInfo,
    CallStatus,
    PhoneNumber,
    TelephonyProvider,
)

logger = structlog.get_logger()

# HTTP status codes
UNPROCESSABLE_ENTITY = 422


class TelnyxService(TelephonyProvider):
    """Telnyx telephony service for voice calls and phone number management."""

    def __init__(self, api_key: str, public_key: str | None = None):
        """Initialize Telnyx client.

        Args:
            api_key: Telnyx API Key
            public_key: Telnyx Public Key (for webhook verification)
        """
        self.api_key = api_key
        self.public_key = public_key
        telnyx.api_key = api_key  # type: ignore[attr-defined]
        self.logger = logger.bind(provider="telnyx")
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for TeXML API calls."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url="https://api.telnyx.com/v2",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._http_client

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,  # type: ignore[type-arg]
        params: dict | None = None,  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Make HTTP request to Telnyx API with comprehensive logging and error details.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint (e.g., '/calls', '/call_control_applications')
            json_data: Request body
            params: Query parameters

        Returns:
            Response data dictionary

        Raises:
            ValueError: If request fails with details from Telnyx
        """
        client = await self._get_http_client()

        self.logger.info(
            "telnyx_api_request_start",
            method=method,
            endpoint=endpoint,
            has_json=json_data is not None,
            has_params=params is not None,
        )

        # Log sanitized request details (don't log sensitive data)
        if json_data:
            sanitized_data = {k: ("***" if k == "webhook_url" else v) for k, v in json_data.items()}
            self.logger.debug("request_payload", payload=sanitized_data)

        try:
            response = await client.request(method, endpoint, json=json_data, params=params)

            # Log response status and headers
            self.logger.debug(
                "telnyx_api_response",
                status=response.status_code,
                content_length=len(response.content),
            )

            # Try to parse response body
            try:
                response_body = response.json()
            except Exception:
                response_body = {"raw_content": response.text[:500]}

            # Check for errors
            http_error_status = 400
            if response.status_code >= http_error_status:
                error_msg = "Telnyx API Error"

                # Extract error details from Telnyx response
                if "errors" in response_body:
                    errors = response_body.get("errors", [])
                    error_details = []
                    for error in errors:
                        if isinstance(error, dict):
                            error_details.append(
                                f"{error.get('code', 'UNKNOWN')}: {error.get('detail', error.get('message', 'Unknown error'))}"
                            )
                        else:
                            error_details.append(str(error))
                    error_msg = " | ".join(error_details) if error_details else error_msg

                self.logger.error(
                    "telnyx_api_error",
                    status=response.status_code,
                    error_message=error_msg,
                    request_id=response_body.get("request_id", "unknown"),
                    full_response=response_body,
                )

                error_detail = (
                    f"Telnyx API {response.status_code}: {error_msg}\n"
                    f"Request ID: {response_body.get('request_id', 'unknown')}\n"
                    f"Full response: {response_body}"
                )
                raise ValueError(error_detail) from None  # noqa: TRY301

            response.raise_for_status()
            self.logger.debug("telnyx_api_success", endpoint=endpoint, status=response.status_code)
            return response_body  # type: ignore[no-any-return]

        except httpx.HTTPError as e:
            self.logger.exception(
                "telnyx_http_error", method=method, endpoint=endpoint, error=str(e)
            )
            raise ValueError(f"HTTP error calling Telnyx {endpoint}: {e!s}") from e
        except ValueError:
            raise
        except Exception as e:
            self.logger.exception("telnyx_unexpected_error", method=method, endpoint=endpoint)
            raise ValueError(f"Unexpected error calling Telnyx {endpoint}: {e!s}") from e

    async def initiate_call(
        self,
        to_number: str,
        from_number: str,
        webhook_url: str,
        agent_id: str | None = None,
    ) -> CallInfo:
        """Initiate an outbound call via Telnyx Call Control API.

        Args:
            to_number: Destination phone number (E.164 format)
            from_number: Source phone number (E.164 format)
            webhook_url: URL for call event webhooks
            agent_id: Optional agent ID for context

        Returns:
            CallInfo with call details

        Raises:
            ValueError: If call initiation fails
        """
        # Normalize phone numbers to E.164 format
        to_number = self._normalize_e164(to_number)
        from_number = self._normalize_e164(from_number)

        self.logger.info(
            "initiating_call",
            to=to_number,
            from_=from_number,
            webhook_url=webhook_url,
            agent_id=agent_id,
        )

        # Validate configuration before proceeding
        self._validate_api_key()

        # Additional validation
        if not to_number:
            msg = "Destination phone number is required"
            self.logger.error("missing_to_number")
            raise ValueError(msg) from None
        if not from_number:
            msg = "Source phone number is required"
            self.logger.error("missing_from_number")
            raise ValueError(msg) from None

        try:
            self.logger.info("initiating_voice_api_call")
            # Get or create Call Control Application with webhook
            connection_id = await self._get_call_control_application_id(webhook_url)
            self.logger.debug("using_connection_id", connection_id=connection_id)

            payload = {
                "to": to_number,
                "from": from_number,
                "connection_id": connection_id,
            }

            self.logger.info(
                "sending_call_request", to=to_number, from_=from_number, connection_id=connection_id
            )
            call_response = await self._make_request("POST", "/calls", json_data=payload)
            call_data = call_response.get("data", {})
            call_control_id = call_data.get("call_control_id", "")

            if not call_control_id:
                msg = "No call_control_id returned from Telnyx API"
                self.logger.error("no_call_control_id", response_data=call_response)
                raise ValueError(msg) from None  # noqa: TRY301

            self.logger.info(
                "call_initiated",
                call_control_id=call_control_id,
                to=to_number,
                from_=from_number,
            )

            return CallInfo(
                call_id=call_control_id,
                call_control_id=call_control_id,
                from_number=from_number,
                to_number=to_number,
                direction=CallDirection.OUTBOUND,
                status=CallStatus.INITIATED,
                agent_id=agent_id,
            )

        except ValueError:
            raise
        except Exception as e:
            self.logger.exception(
                "call_initiation_failed",
                to=to_number,
                from_=from_number,
                error=str(e),
            )
            raise ValueError(f"Failed to initiate Telnyx call: {e!s}") from e

    async def hangup_call(self, call_id: str) -> bool:
        """Hang up an active Telnyx call.

        Args:
            call_id: Telnyx Call Control ID

        Returns:
            True if successful
        """
        self.logger.info("hanging_up_call", call_control_id=call_id)

        try:
            client = await self._get_http_client()
            response = await client.post(f"/calls/{call_id}/actions/hangup", json={})
            # 422 means the call is already disconnected, which is fine
            if response.status_code == UNPROCESSABLE_ENTITY:
                self.logger.info("hangup_call_already_disconnected", call_control_id=call_id)
                return True
            response.raise_for_status()
            return True
        except Exception:
            self.logger.exception("hangup_failed", call_control_id=call_id)
            return False

    async def answer_call(self, call_control_id: str, webhook_url: str | None = None) -> bool:
        """Answer an incoming call.

        Args:
            call_control_id: Telnyx Call Control ID
            webhook_url: Optional webhook URL for call events

        Returns:
            True if successful
        """
        self.logger.info("answering_call", call_control_id=call_control_id)

        try:
            client = await self._get_http_client()
            payload: dict[str, str] = {}
            if webhook_url:
                payload["webhook_url"] = webhook_url

            response = await client.post(
                f"/calls/{call_control_id}/actions/answer",
                json=payload,
            )
            response.raise_for_status()
            return True
        except Exception:
            self.logger.exception("answer_failed", call_control_id=call_control_id)
            return False

    async def start_streaming(self, call_control_id: str, stream_url: str) -> bool:
        """Start media streaming on a call to a WebSocket URL.

        This is for Call Control API - sends audio to a WebSocket endpoint.

        Args:
            call_control_id: Telnyx Call Control ID
            stream_url: WebSocket URL to stream audio to (wss://...)

        Returns:
            True if streaming started successfully
        """
        self.logger.info(
            "starting_streaming",
            call_control_id=call_control_id,
            stream_url=stream_url,
        )

        try:
            client = await self._get_http_client()
            payload = {
                "stream_url": stream_url,
                "stream_track": "inbound_track",  # Only receive caller's audio (prevents AI hearing itself)
                "stream_bidirectional_mode": "rtp",  # Enable sending audio back to caller
                "stream_bidirectional_codec": "PCMU",  # Use PCMU codec (mulaw) at 8kHz
            }

            self.logger.debug("streaming_start_payload", payload=payload)

            response = await client.post(
                f"/calls/{call_control_id}/actions/streaming_start",
                json=payload,
            )

            if response.status_code == UNPROCESSABLE_ENTITY:
                # Call might already be disconnected
                self.logger.warning(
                    "streaming_start_failed_422",
                    call_control_id=call_control_id,
                    response_text=response.text,
                )
                return False

            response.raise_for_status()
            self.logger.info(
                "streaming_started_successfully",
                call_control_id=call_control_id,
            )
            return True
        except Exception as e:
            self.logger.exception(
                "streaming_start_failed",
                call_control_id=call_control_id,
                error=str(e),
            )
            return False

    async def stream_audio(
        self,
        call_control_id: str,
        stream_url: str,
        stream_track: str = "both_tracks",
    ) -> bool:
        """Start streaming audio to/from a WebSocket.

        Args:
            call_control_id: Telnyx Call Control ID
            stream_url: WebSocket URL for audio streaming
            stream_track: Which tracks to stream (inbound_track, outbound_track, both_tracks)

        Returns:
            True if successful
        """
        self.logger.info(
            "starting_stream",
            call_control_id=call_control_id,
            stream_url=stream_url,
        )

        try:
            client = await self._get_http_client()
            response = await client.post(
                f"/calls/{call_control_id}/actions/streaming_start",
                json={
                    "stream_url": stream_url,
                    "stream_track": stream_track,
                },
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.exception(
                "stream_start_failed", call_control_id=call_control_id, error=str(e)
            )
            return False

    async def list_phone_numbers(self) -> list[PhoneNumber]:
        """List all Telnyx phone numbers.

        Returns:
            List of PhoneNumber objects
        """
        self.logger.info("listing_phone_numbers")

        numbers = []
        client = await self._get_http_client()

        response = await client.get("/phone_numbers")
        response.raise_for_status()
        data = response.json()

        for number in data.get("data", []):
            numbers.append(
                PhoneNumber(
                    id=number.get("id", ""),
                    phone_number=number.get("phone_number", ""),
                    friendly_name=number.get("connection_name"),
                    provider="telnyx",
                    capabilities={
                        "voice": True,
                        "sms": number.get("messaging_profile_id") is not None,
                    },
                )
            )

        self.logger.info("phone_numbers_listed", count=len(numbers))
        return numbers

    async def search_phone_numbers(
        self,
        country: str = "US",
        area_code: str | None = None,
        contains: str | None = None,
        limit: int = 10,
    ) -> list[PhoneNumber]:
        """Search for available Telnyx phone numbers.

        Args:
            country: Country code (e.g., "US")
            area_code: Area code filter (NPA)
            contains: Pattern to match
            limit: Maximum results

        Returns:
            List of available PhoneNumber objects
        """
        self.logger.info(
            "searching_phone_numbers",
            country=country,
            area_code=area_code,
            contains=contains,
        )

        client = await self._get_http_client()

        params: dict[str, str | int | bool] = {
            "filter[country_code]": country,
            "filter[features]": "voice",
            "filter[limit]": limit,
        }
        if area_code:
            params["filter[national_destination_code]"] = area_code
        if contains:
            params["filter[phone_number][contains]"] = contains

        response = await client.get("/available_phone_numbers", params=params)
        response.raise_for_status()
        data = response.json()

        numbers = []
        for number in data.get("data", []):
            numbers.append(
                PhoneNumber(
                    id="",  # Not purchased yet
                    phone_number=number.get("phone_number", ""),
                    friendly_name=number.get("region_information", [{}])[0].get("region_name"),
                    provider="telnyx",
                    capabilities={
                        "voice": "voice" in number.get("features", []),
                        "sms": "sms" in number.get("features", []),
                    },
                )
            )

        self.logger.info("phone_numbers_found", count=len(numbers))
        return numbers

    async def purchase_phone_number(self, phone_number: str) -> PhoneNumber:
        """Purchase a Telnyx phone number.

        Args:
            phone_number: Phone number to purchase (E.164 format)

        Returns:
            Purchased PhoneNumber object
        """
        self.logger.info("purchasing_phone_number", phone_number=phone_number)

        client = await self._get_http_client()

        # First, create a number order
        response = await client.post(
            "/number_orders",
            json={
                "phone_numbers": [{"phone_number": phone_number}],
            },
        )
        response.raise_for_status()
        order_data = response.json()

        # Get the phone number ID from the order
        phone_numbers = order_data.get("data", {}).get("phone_numbers", [])
        if not phone_numbers:
            raise ValueError("No phone number returned from order")

        number_data = phone_numbers[0]

        self.logger.info("phone_number_purchased", id=number_data.get("id"))

        return PhoneNumber(
            id=number_data.get("id", ""),
            phone_number=number_data.get("phone_number", phone_number),
            friendly_name=None,
            provider="telnyx",
            capabilities={"voice": True, "sms": True},
        )

    async def release_phone_number(self, phone_number_id: str) -> bool:
        """Release a Telnyx phone number.

        Args:
            phone_number_id: Phone number ID to release

        Returns:
            True if successful
        """
        self.logger.info("releasing_phone_number", id=phone_number_id)

        try:
            client = await self._get_http_client()
            response = await client.delete(f"/phone_numbers/{phone_number_id}")
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.exception("release_failed", id=phone_number_id, error=str(e))
            return False

    async def configure_phone_number(
        self,
        phone_number_id: str,
        connection_id: str | None = None,
        texml_application_id: str | None = None,
    ) -> bool:
        """Configure a phone number with connection or TeXML application.

        Args:
            phone_number_id: Phone number ID
            connection_id: Telnyx connection ID for Call Control
            texml_application_id: Telnyx TeXML Application ID

        Returns:
            True if successful
        """
        self.logger.info(
            "configuring_phone_number",
            id=phone_number_id,
            connection_id=connection_id,
            texml_application_id=texml_application_id,
        )

        try:
            client = await self._get_http_client()
            payload: dict[str, str] = {}

            if connection_id:
                payload["connection_id"] = connection_id
            if texml_application_id:
                payload["texml_application_id"] = texml_application_id

            response = await client.patch(
                f"/phone_numbers/{phone_number_id}",
                json=payload,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.exception("configure_failed", id=phone_number_id, error=str(e))
            return False

    def _validate_api_key(self) -> None:
        """Validate that API key is configured.

        Raises:
            ValueError: If API key is not configured
        """
        if not self.api_key:
            msg = "Telnyx API key is not configured"
            self.logger.error("api_key_not_configured")
            raise ValueError(msg) from None

    def _normalize_e164(self, phone_number: str) -> str:
        """Normalize a phone number to E.164 format.

        Args:
            phone_number: Phone number in any format

        Returns:
            Phone number in E.164 format (+countrycode...)

        Raises:
            ValueError: If phone number cannot be normalized
        """
        # Remove all non-digit characters except leading +
        cleaned = phone_number.strip()
        if cleaned.startswith("+"):
            digits = (
                cleaned[1:]
                .replace("-", "")
                .replace(" ", "")
                .replace("(", "")
                .replace(")", "")
                .replace(".", "")
            )
            if not digits.isdigit():
                msg = f"Invalid phone number format: {phone_number}"
                raise ValueError(msg) from None
            return f"+{digits}"

        # If no + prefix, assume US number and add +1
        digits = (
            cleaned.replace("-", "")
            .replace(" ", "")
            .replace("(", "")
            .replace(")", "")
            .replace(".", "")
        )
        if not digits.isdigit():
            msg = f"Invalid phone number format: {phone_number}"
            raise ValueError(msg) from None

        # Default to US country code if not specified
        # US phone numbers have 10 digits without country code
        if len(digits) == 10:  # noqa: PLR2004
            return f"+1{digits}"

        # Already has country code
        return f"+{digits}"

    async def _ensure_outbound_profile(self) -> str:
        """Get or create an Outbound Voice Profile for making outbound calls.

        Outbound Voice Profiles are REQUIRED by Telnyx for Call Control API outbound calls.
        They manage billing, destination whitelisting, and concurrency limits.

        Returns:
            Outbound Voice Profile ID string

        Raises:
            ValueError: If profile cannot be created or retrieved
        """
        try:
            self.logger.info("checking_for_existing_outbound_profiles")
            # List existing profiles
            data = await self._make_request("GET", "/outbound_voice_profiles")
            profiles = data.get("data", [])

            if profiles:
                # Use the first enabled profile
                for profile in profiles:
                    if profile.get("enabled", False):
                        profile_id = profile.get("id")
                        self.logger.info("using_existing_outbound_profile", profile_id=profile_id)
                        return str(profile_id)

            # Create new profile if none exist
            self.logger.info("creating_new_outbound_voice_profile")
            profile_response = await self._make_request(
                "POST",
                "/outbound_voice_profiles",
                json_data={
                    "name": "voice-agent-outbound-profile",
                    "enabled": True,
                },
            )

            profile_id = profile_response.get("data", {}).get("id")
            if not profile_id:
                msg = "No outbound voice profile ID returned from Telnyx API"
                self.logger.error("no_profile_id_returned")
                raise ValueError(msg) from None  # noqa: TRY301

            self.logger.info("outbound_voice_profile_created", profile_id=profile_id)
            return str(profile_id)

        except ValueError:
            raise
        except Exception as e:
            self.logger.exception("failed_to_ensure_outbound_profile", error=str(e))
            raise ValueError(f"Failed to manage Outbound Voice Profile: {e!s}") from e

    async def _assign_outbound_profile_to_app(
        self, app_id: str, profile_id: str, channel_limit: int = 10
    ) -> None:
        """Assign an Outbound Voice Profile to a Call Control Application.

        Args:
            app_id: Call Control Application ID
            profile_id: Outbound Voice Profile ID
            channel_limit: Max concurrent outbound calls (default: 10)

        Raises:
            ValueError: If assignment fails
        """
        try:
            self.logger.info(
                "assigning_outbound_profile_to_app",
                app_id=app_id,
                profile_id=profile_id,
                channel_limit=channel_limit,
            )

            await self._make_request(
                "PATCH",
                f"/call_control_applications/{app_id}",
                json_data={
                    "outbound": {
                        "outbound_voice_profile_id": profile_id,
                        "channel_limit": channel_limit,
                    }
                },
            )

            self.logger.info("outbound_profile_assigned_successfully", app_id=app_id)

        except Exception as e:
            self.logger.exception(
                "failed_to_assign_outbound_profile",
                app_id=app_id,
                profile_id=profile_id,
                error=str(e),
            )
            raise ValueError(f"Failed to assign outbound profile: {e!s}") from e

    async def _get_call_control_application_id(self, webhook_event_url: str | None = None) -> str:
        """Get or create a Telnyx Call Control Application for outbound calls.

        Call Control Applications are required for the Call Control API.
        They define how calls should be handled and where webhooks are sent.

        Args:
            webhook_event_url: Optional webhook URL for call events. If creating a new app,
                              this will be set as the application's webhook_event_url.

        Returns:
            Call Control Application ID string

        Raises:
            ValueError: If no application ID is found or created
        """
        try:
            self.logger.info("fetching_call_control_applications", webhook_url=webhook_event_url)
            # List existing Call Control Applications
            data = await self._make_request("GET", "/call_control_applications")

            applications = data.get("data", [])
            self.logger.debug("applications_list_count", count=len(applications))

            if applications:
                # Find the first application with a valid webhook_event_url
                self.logger.info("checking_existing_applications", count=len(applications))
                for i, app in enumerate(applications):
                    app_id = app.get("id")
                    webhook_url = app.get("webhook_event_url")

                    self.logger.debug(
                        "application_details",
                        index=i,
                        app_id=app_id,
                        webhook_url=webhook_url,
                        application_name=app.get("application_name", "unknown"),
                    )

                    if app_id and webhook_url:
                        self.logger.info(
                            "using_existing_call_control_application",
                            app_id=app_id,
                            application_name=app.get("application_name", "unknown"),
                            has_webhook=True,
                        )
                        # Ensure outbound profile is assigned to this app
                        profile_id = await self._ensure_outbound_profile()
                        await self._assign_outbound_profile_to_app(app_id, profile_id)
                        return str(app_id)

                # If we found apps but none have valid webhooks, we need to create a new one
                # (or update the existing one - but creation is safer)
                self.logger.warning(
                    "existing_applications_found_but_no_valid_webhook",
                    count=len(applications),
                )

            # Create a new Call Control Application if none exists or none have valid webhooks
            self.logger.info("creating_new_call_control_application", webhook_url=webhook_event_url)
            app_payload = {
                "application_name": "voice-agent-application",
                "active": True,
            }

            # Add webhook_event_url if provided (REQUIRED by Telnyx for Call Control API)
            if webhook_event_url:
                # Extract just the base path for webhook URL (remove query parameters)
                # Telnyx requires the webhook URL to be clean without query params
                base_webhook_url = (
                    webhook_event_url.split("?")[0]
                    if "?" in webhook_event_url
                    else webhook_event_url
                )
                app_payload["webhook_event_url"] = base_webhook_url
                self.logger.debug("webhook_event_url_added", url=base_webhook_url)
            else:
                msg = "webhook_event_url is required for Call Control Application creation"
                self.logger.error("webhook_event_url_missing")
                raise ValueError(msg) from None  # noqa: TRY301

            new_data = await self._make_request(
                "POST",
                "/call_control_applications",
                json_data=app_payload,
            )
            app_id = new_data.get("data", {}).get("id")

            if not app_id:
                msg = "No call control application ID returned from Telnyx API"
                raise ValueError(msg) from None  # noqa: TRY301

            self.logger.info("call_control_application_created", app_id=app_id)

            # Ensure outbound profile is assigned to this new app
            profile_id = await self._ensure_outbound_profile()
            await self._assign_outbound_profile_to_app(app_id, profile_id)

            return str(app_id)

        except ValueError:
            raise
        except Exception as e:
            self.logger.exception("failed_to_get_or_create_call_control_application", error=str(e))
            raise ValueError(
                f"Failed to get or create Telnyx Call Control Application: {e!s}"
            ) from e

    def generate_answer_response(self, websocket_url: str, agent_id: str | None = None) -> str:  # noqa: ARG002
        """Generate TeXML response to answer a call and stream to WebSocket.

        Args:
            websocket_url: WebSocket URL for media streaming
            agent_id: Optional agent ID for context

        Returns:
            TeXML response string
        """
        # Build TeXML with proper XML escaping for & in URLs
        escaped_ws_url = websocket_url.replace("&", "&amp;")

        texml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{escaped_ws_url}" />
    </Connect>
</Response>"""

        return texml

    def generate_gather_response(
        self,
        message: str,
        action_url: str,
        num_digits: int = 1,
        timeout: int = 5,
    ) -> str:
        """Generate TeXML response to gather DTMF input.

        Args:
            message: Message to speak before gathering
            action_url: URL to send gathered digits to
            num_digits: Number of digits to gather
            timeout: Timeout in seconds

        Returns:
            TeXML response string
        """
        escaped_action_url = action_url.replace("&", "&amp;")

        texml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="{num_digits}" action="{escaped_action_url}" method="POST" timeout="{timeout}">
        <Say>{message}</Say>
    </Gather>
</Response>"""

        return texml

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
