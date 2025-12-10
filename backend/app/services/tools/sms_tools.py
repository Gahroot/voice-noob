"""SMS integration tools for voice agents (Twilio, Telnyx, and SlickText)."""

import time
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


class TwilioSMSTools:
    """Twilio SMS API integration tools.

    Provides tools for:
    - Sending SMS messages
    - Getting message status
    """

    BASE_URL = "https://api.twilio.com/2010-04-01"

    def __init__(self, account_sid: str, auth_token: str, from_number: str) -> None:
        """Initialize Twilio SMS tools.

        Args:
            account_sid: Twilio Account SID
            auth_token: Twilio Auth Token
            from_number: Twilio phone number to send from (E.164 format)
        """
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=f"{self.BASE_URL}/Accounts/{self.account_sid}",
                auth=(self.account_sid, self.auth_token),
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def get_tool_definitions() -> list[dict[str, Any]]:
        """Get OpenAI function calling tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "twilio_send_sms",
                    "description": "Send an SMS message to a phone number",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "Recipient phone number (E.164 format, e.g., +14155551234)",
                            },
                            "body": {
                                "type": "string",
                                "description": "Message content (max 1600 characters)",
                            },
                        },
                        "required": ["to", "body"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "twilio_get_message_status",
                    "description": "Get the delivery status of a sent SMS message",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message_sid": {
                                "type": "string",
                                "description": "The Twilio message SID (starts with SM)",
                            },
                        },
                        "required": ["message_sid"],
                    },
                },
            },
        ]

    async def send_sms(self, to: str, body: str) -> dict[str, Any]:
        """Send an SMS message."""
        try:
            # Validate body length
            max_length = 1600
            if len(body) > max_length:
                return {
                    "success": False,
                    "error": f"Message too long. Max {max_length} characters, got {len(body)}",
                }

            response = await self.client.post(
                "/Messages.json",
                data={
                    "To": to,
                    "From": self.from_number,
                    "Body": body,
                },
            )

            if response.status_code != HTTPStatus.CREATED:
                error_data = response.json()
                return {
                    "success": False,
                    "error": error_data.get("message", response.text),
                }

            data = response.json()
            return {
                "success": True,
                "message_sid": data["sid"],
                "to": data["to"],
                "from": data["from"],
                "status": data["status"],
                "message": f"SMS sent successfully to {to}",
            }

        except Exception as e:
            logger.exception("twilio_send_sms_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def get_message_status(self, message_sid: str) -> dict[str, Any]:
        """Get the status of a sent message."""
        try:
            response = await self.client.get(f"/Messages/{message_sid}.json")

            if response.status_code != HTTPStatus.OK:
                return {
                    "success": False,
                    "error": f"Message not found: {response.text}",
                }

            data = response.json()
            return {
                "success": True,
                "message_sid": data["sid"],
                "to": data["to"],
                "from": data["from"],
                "status": data["status"],
                "date_sent": data.get("date_sent"),
                "error_code": data.get("error_code"),
                "error_message": data.get("error_message"),
            }

        except Exception as e:
            logger.exception("twilio_get_message_status_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a Twilio SMS tool by name."""
        tool_map: dict[str, ToolHandler] = {
            "twilio_send_sms": self.send_sms,
            "twilio_get_message_status": self.get_message_status,
        }

        handler = tool_map.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        result: dict[str, Any] = await handler(**arguments)
        return result


class TelnyxSMSTools:
    """Telnyx SMS API integration tools.

    Provides tools for:
    - Sending SMS messages
    - Getting message status
    """

    BASE_URL = "https://api.telnyx.com/v2"

    def __init__(
        self,
        api_key: str,
        from_number: str,
        messaging_profile_id: str | None = None,
    ) -> None:
        """Initialize Telnyx SMS tools.

        Args:
            api_key: Telnyx API Key
            from_number: Telnyx phone number to send from (E.164 format)
            messaging_profile_id: Optional messaging profile ID for routing
        """
        self.api_key = api_key
        self.from_number = from_number
        self.messaging_profile_id = messaging_profile_id
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def get_tool_definitions() -> list[dict[str, Any]]:
        """Get OpenAI function calling tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "telnyx_send_sms",
                    "description": "Send an SMS message to a phone number via Telnyx",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "Recipient phone number (E.164 format, e.g., +14155551234)",
                            },
                            "body": {
                                "type": "string",
                                "description": "Message content",
                            },
                        },
                        "required": ["to", "body"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "telnyx_get_message_status",
                    "description": "Get the delivery status of a sent SMS message via Telnyx",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message_id": {
                                "type": "string",
                                "description": "The Telnyx message ID (UUID)",
                            },
                        },
                        "required": ["message_id"],
                    },
                },
            },
        ]

    async def send_sms(self, to: str, body: str) -> dict[str, Any]:
        """Send an SMS message."""
        try:
            payload: dict[str, Any] = {
                "to": to,
                "from": self.from_number,
                "text": body,
                "type": "SMS",
            }

            if self.messaging_profile_id:
                payload["messaging_profile_id"] = self.messaging_profile_id

            response = await self.client.post("/messages", json=payload)

            if response.status_code != HTTPStatus.OK:
                error_data = response.json()
                errors = error_data.get("errors", [])
                error_msg = errors[0].get("detail") if errors else response.text
                return {
                    "success": False,
                    "error": error_msg,
                }

            data = response.json()["data"]
            return {
                "success": True,
                "message_id": data["id"],
                "to": data["to"][0]["phone_number"],
                "from": data["from"]["phone_number"],
                "status": data.get("to", [{}])[0].get("status"),
                "message": f"SMS sent successfully to {to}",
            }

        except Exception as e:
            logger.exception("telnyx_send_sms_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def get_message_status(self, message_id: str) -> dict[str, Any]:
        """Get the status of a sent message."""
        try:
            response = await self.client.get(f"/messages/{message_id}")

            if response.status_code != HTTPStatus.OK:
                return {
                    "success": False,
                    "error": f"Message not found: {response.text}",
                }

            data = response.json()["data"]
            to_info = data.get("to", [{}])[0] if data.get("to") else {}

            return {
                "success": True,
                "message_id": data["id"],
                "to": to_info.get("phone_number"),
                "from": data.get("from", {}).get("phone_number"),
                "status": to_info.get("status"),
                "completed_at": data.get("completed_at"),
                "errors": data.get("errors"),
            }

        except Exception as e:
            logger.exception("telnyx_get_message_status_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a Telnyx SMS tool by name."""
        tool_map: dict[str, ToolHandler] = {
            "telnyx_send_sms": self.send_sms,
            "telnyx_get_message_status": self.get_message_status,
        }

        handler = tool_map.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        result: dict[str, Any] = await handler(**arguments)
        return result


class SlickTextSMSTools:
    """SlickText SMS API integration tools supporting both V1 (legacy) and V2 APIs.

    V1 (Legacy) API - for accounts created BEFORE January 22, 2025:
    - Base URL: https://api.slicktext.com/v1/
    - Auth: HTTP Basic with public_key/private_key
    - Direct message sending via POST /messages with action=SEND
    - Docs: https://api.slicktext.com/docs/v1/basics

    V2 API - for accounts created AFTER January 22, 2025:
    - Base URL: https://dev.slicktext.com/v1/
    - Auth: Bearer token
    - Campaign-based sending only
    - Docs: https://api.slicktext.com/docs/v2/overview
    """

    # V2 API (newer accounts)
    BASE_URL_V2 = "https://dev.slicktext.com/v1"
    # V1 API (legacy accounts)
    BASE_URL_V1 = "https://api.slicktext.com/v1"

    def __init__(
        self,
        api_key: str,
        brand_id: str | None = None,
        public_key: str | None = None,
        private_key: str | None = None,
        textword_id: str | None = None,
    ) -> None:
        """Initialize SlickText SMS tools.

        Args:
            api_key: SlickText API Key (V2 Bearer token)
            brand_id: SlickText Brand ID (V2 API, fetched automatically if not provided)
            public_key: SlickText Public Key (V1 API)
            private_key: SlickText Private Key (V1 API)
            textword_id: SlickText Textword ID (V1 API, for sending messages)
        """
        self.api_key = api_key
        self.brand_id = brand_id
        self.public_key = public_key
        self.private_key = private_key
        self.textword_id = textword_id
        self._client: httpx.AsyncClient | None = None
        self._client_v1: httpx.AsyncClient | None = None
        # Determine which API version to use based on provided credentials
        self._use_v1 = bool(public_key and private_key)

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for V2 API with Bearer auth."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL_V2,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        return self._client

    @property
    def client_v1(self) -> httpx.AsyncClient:
        """Get or create HTTP client for V1 API with Basic auth."""
        if self._client_v1 is None:
            self._client_v1 = httpx.AsyncClient(
                base_url=self.BASE_URL_V1,
                auth=(self.public_key or "", self.private_key or ""),
                headers={
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        return self._client_v1

    async def close(self) -> None:
        """Close HTTP clients."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._client_v1:
            await self._client_v1.aclose()
            self._client_v1 = None

    async def _get_brand_id(self) -> str | None:
        """Get the brand ID from the V2 API if not already set.

        V2 API Docs: https://api.slicktext.com/docs/v2/brands
        """
        if self.brand_id:
            return self.brand_id

        try:
            # V2 API: GET /brands
            response = await self.client.get("/brands")
            if response.status_code == HTTPStatus.OK:
                data = response.json()
                # V2 API returns brand_id at top level
                if "brand_id" in data:
                    self.brand_id = str(data["brand_id"])
                    logger.info("slicktext_v2_brand_id", brand_id=self.brand_id)
                    return self.brand_id
                # Fallback: check for data array
                brands = data.get("data", [])
                if brands:
                    brand = brands[0]
                    self.brand_id = str(brand.get("brand_id") or brand.get("id"))
                    logger.info("slicktext_v2_brand_id_from_array", brand_id=self.brand_id)
                    return self.brand_id
            logger.warning(
                "slicktext_v2_get_brand_failed",
                status=response.status_code,
                response=response.text,
            )
            return None
        except Exception as e:
            logger.exception("slicktext_v2_get_brand_error", error=str(e))
            return None

    @staticmethod
    def get_tool_definitions() -> list[dict[str, Any]]:
        """Get OpenAI function calling tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "slicktext_send_sms",
                    "description": "Send an SMS message to a contact via SlickText campaign",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "Recipient phone number (E.164 format, e.g., +14155551234)",
                            },
                            "body": {
                                "type": "string",
                                "description": "Message content",
                            },
                        },
                        "required": ["to", "body"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "slicktext_get_campaign_status",
                    "description": "Get the status of a SlickText campaign",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "campaign_id": {
                                "type": "string",
                                "description": "The SlickText campaign ID",
                            },
                        },
                        "required": ["campaign_id"],
                    },
                },
            },
        ]

    async def _find_or_create_contact(self, phone_number: str) -> str | None:
        """Find existing contact or create new one by phone number.

        V2 API Docs: https://api.slicktext.com/docs/v2/contacts
        """
        brand_id = await self._get_brand_id()
        if not brand_id:
            return None

        try:
            # Normalize phone - ensure E.164 format with + prefix
            if not phone_number.startswith("+"):
                phone_number = f"+{phone_number}"

            # V2 API: GET /brands/{brand_id}/contacts with query params
            response = await self.client.get(
                f"/brands/{brand_id}/contacts",
                params={"mobile_number": phone_number},
            )

            if response.status_code == HTTPStatus.OK:
                data = response.json()
                contacts = data.get("data", [])
                if contacts:
                    # V2 API uses contact_id
                    contact = contacts[0]
                    contact_id = str(contact.get("contact_id") or contact.get("id"))
                    logger.info("slicktext_v2_contact_found", contact_id=contact_id)
                    return contact_id

            # Contact not found, create new one
            # V2 API: POST /brands/{brand_id}/contacts
            # Required: mobile_number (minimum 10 digits)
            create_response = await self.client.post(
                f"/brands/{brand_id}/contacts",
                json={"mobile_number": phone_number},
            )

            if create_response.status_code in (HTTPStatus.OK, HTTPStatus.CREATED):
                contact_data = create_response.json()
                # V2 API returns contact_id at top level
                contact_id = str(
                    contact_data.get("contact_id")
                    or contact_data.get("data", {}).get("contact_id")
                    or contact_data.get("id")
                )
                logger.info("slicktext_v2_contact_created", contact_id=contact_id)
                return contact_id

            logger.warning(
                "slicktext_v2_create_contact_failed",
                status=create_response.status_code,
                response=create_response.text,
            )
            return None

        except Exception as e:
            logger.exception("slicktext_v2_find_or_create_contact_error", error=str(e))
            return None

    async def _create_single_contact_list(self, contact_id: str) -> str | None:
        """Create a temporary list with a single contact for sending.

        V2 API Docs:
        - Create list: https://api.slicktext.com/docs/v2/lists#create-a-list
        - Add contacts: https://api.slicktext.com/docs/v2/lists#add-contacts-to-lists
        """
        brand_id = await self._get_brand_id()
        if not brand_id:
            return None

        try:
            # V2 API: POST /brands/{brand_id}/lists (requires: name)
            list_name = f"API_Send_{int(time.time())}"
            create_response = await self.client.post(
                f"/brands/{brand_id}/lists",
                json={"name": list_name},
            )

            if create_response.status_code not in (HTTPStatus.OK, HTTPStatus.CREATED):
                logger.warning(
                    "slicktext_v2_create_list_failed",
                    status=create_response.status_code,
                    response=create_response.text,
                )
                return None

            list_data = create_response.json()
            # V2 API returns contact_list_id at top level
            list_id = str(
                list_data.get("contact_list_id")
                or list_data.get("id")
                or list_data.get("data", {}).get("contact_list_id")
            )
            logger.info("slicktext_v2_list_created", list_id=list_id)

            # V2 API: POST /brands/{brand_id}/lists/contacts
            # Body: array of {contact_id, lists[]}
            add_response = await self.client.post(
                f"/brands/{brand_id}/lists/contacts",
                json=[{"contact_id": int(contact_id), "lists": [int(list_id)]}],
            )

            if add_response.status_code not in (HTTPStatus.OK, HTTPStatus.CREATED):
                logger.warning(
                    "slicktext_v2_add_contact_to_list_failed",
                    status=add_response.status_code,
                    response=add_response.text,
                )
                # Continue anyway - the list might still work
            else:
                logger.info(
                    "slicktext_v2_contact_added_to_list",
                    contact_id=contact_id,
                    list_id=list_id,
                )

            return list_id

        except Exception as e:
            logger.exception("slicktext_v2_create_single_contact_list_error", error=str(e))
            return None

    async def _send_via_inbox(self, to: str, body: str, brand_id: str) -> dict[str, Any] | None:
        """Try to send message via inbox reply endpoint (for one-off texts).

        SlickText inbox allows replying to conversations.
        Returns None if inbox API fails, otherwise returns result dict.
        """
        try:
            # Normalize phone - ensure E.164 format
            if not to.startswith("+"):
                to = f"+{to}"

            # First, find existing inbox thread for this phone number
            threads_response = await self.client.get(
                f"/brands/{brand_id}/inbox-threads",
                params={"phone_number": to.lstrip("+")},
            )

            thread_id = None
            if threads_response.status_code == HTTPStatus.OK:
                threads_data = threads_response.json()
                threads = threads_data.get("data", [])
                if threads:
                    thread_id = str(threads[0].get("id") or threads[0].get("inbox_thread_id"))
                    logger.info("slicktext_v2_inbox_thread_found", thread_id=thread_id)

            # If no thread found, try to create one or start a new conversation
            if not thread_id:
                # Try creating a new inbox thread/conversation
                create_response = await self.client.post(
                    f"/brands/{brand_id}/inbox-threads",
                    json={"phone_number": to},
                )
                if create_response.status_code in (HTTPStatus.OK, HTTPStatus.CREATED):
                    create_data = create_response.json()
                    thread_id = str(
                        create_data.get("id")
                        or create_data.get("inbox_thread_id")
                        or create_data.get("data", {}).get("id")
                    )
                    logger.info("slicktext_v2_inbox_thread_created", thread_id=thread_id)

            if not thread_id:
                logger.info("slicktext_v2_inbox_not_available")
                return None

            # Send reply to the inbox thread
            reply_response = await self.client.post(
                f"/brands/{brand_id}/inbox-threads/{thread_id}/reply",
                json={"body": body},
            )

            if reply_response.status_code in (HTTPStatus.OK, HTTPStatus.CREATED):
                reply_data = reply_response.json()
                message_id = str(
                    reply_data.get("message_id")
                    or reply_data.get("id")
                    or reply_data.get("data", {}).get("id")
                    or ""
                )
                logger.info("slicktext_v2_inbox_reply_sent", message_id=message_id, to=to)
                return {
                    "success": True,
                    "message_id": message_id,
                    "to": to,
                    "status": "sent",
                    "message": f"SMS sent successfully to {to}",
                }

            logger.warning(
                "slicktext_v2_inbox_reply_failed",
                status=reply_response.status_code,
                response=reply_response.text[:500] if reply_response.text else "",
            )
            return None

        except Exception as e:
            logger.warning("slicktext_v2_inbox_error", error=str(e))
            return None

    async def _send_via_v1_api(self, to: str, body: str) -> dict[str, Any]:
        """Send message via V1 (Legacy) API direct message endpoint.

        V1 API allows direct message sending without campaigns.
        POST /messages with action=SEND

        V1 API Docs: https://api.slicktext.com/docs/v1/messages
        """
        try:
            # Normalize phone - ensure it has digits only for V1 API
            phone_digits = to.lstrip("+")

            # First, we need to find or create a contact to get their ID
            # V1 API: GET /contacts with phone filter
            contacts_response = await self.client_v1.get(
                "/contacts/",
                params={"phone": phone_digits},
            )

            contact_id = None
            if contacts_response.status_code == HTTPStatus.OK:
                contacts_data = contacts_response.json()
                contacts = contacts_data.get("contacts", [])
                if contacts:
                    contact_id = str(contacts[0].get("id"))
                    logger.info("slicktext_v1_contact_found", contact_id=contact_id)

            # If no contact, create one via opt-in
            if not contact_id and self.textword_id:
                optin_response = await self.client_v1.post(
                    "/contacts/",
                    json={
                        "action": "OPTIN",
                        "textword": int(self.textword_id),
                        "phone": phone_digits,
                    },
                )
                if optin_response.status_code in (HTTPStatus.OK, HTTPStatus.CREATED):
                    optin_data = optin_response.json()
                    contact_id = str(optin_data.get("contact_id") or optin_data.get("id", ""))
                    logger.info("slicktext_v1_contact_created", contact_id=contact_id)

            # Now send the message
            # V1 API: POST /messages with action=SEND
            payload: dict[str, Any] = {
                "action": "SEND",
                "body": body,
            }

            # Use contact ID if available, otherwise use textword with phone
            if contact_id:
                payload["contact"] = int(contact_id)
            elif self.textword_id:
                payload["textword"] = int(self.textword_id)
                payload["phone"] = phone_digits  # This opts in and sends
            else:
                return {
                    "success": False,
                    "error": "SlickText V1 API requires a textword_id to send messages",
                }

            logger.info(
                "slicktext_v1_send_message",
                contact_id=contact_id,
                textword_id=self.textword_id,
            )

            response = await self.client_v1.post("/messages/", json=payload)

            logger.info(
                "slicktext_v1_response",
                status_code=response.status_code,
                response_text=response.text[:500] if response.text else "",
            )

            if response.status_code in (HTTPStatus.OK, HTTPStatus.CREATED):
                data = response.json()
                message_id = str(data.get("message_id") or data.get("id", ""))
                logger.info("slicktext_v1_message_sent", message_id=message_id, to=to)
                return {
                    "success": True,
                    "message_id": message_id,
                    "to": to,
                    "status": "sent",
                    "message": f"SMS sent successfully to {to}",
                }

            # Handle error
            try:
                error_data = response.json()
                error_msg = error_data.get("error", error_data.get("message", response.text))
            except Exception:
                error_msg = response.text
            logger.warning(
                "slicktext_v1_send_failed",
                status=response.status_code,
                error=error_msg,
            )
            return {"success": False, "error": str(error_msg)}

        except Exception as e:
            logger.exception("slicktext_v1_send_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def _send_via_campaign(self, to: str, body: str, brand_id: str) -> dict[str, Any]:
        """Send message via campaign-based sending.

        SlickText V2 API only supports sending messages through campaigns.
        This creates a contact, adds them to a temporary list, and sends a campaign.

        V2 API Docs: https://api.slicktext.com/docs/v2/campaigns
        """
        # Find or create the contact
        contact_id = await self._find_or_create_contact(to)
        if not contact_id:
            return {"success": False, "error": "Failed to find or create contact in SlickText"}

        # Create a list with this contact
        list_id = await self._create_single_contact_list(contact_id)
        if not list_id:
            return {"success": False, "error": "Failed to create contact list for sending"}

        # Create and send campaign using V2 API format
        # V2 API: POST /brands/{brand_id}/campaigns/
        campaign_name = f"API_Message_{int(time.time())}"
        payload = {
            "name": campaign_name,
            "body": body,
            "status": "send",
            "audience": {
                "contact_lists": [int(list_id)],
                "segments": [],
            },
        }

        logger.info(
            "slicktext_v2_campaign_create",
            brand_id=brand_id,
            list_id=list_id,
            contact_id=contact_id,
            payload=payload,
        )

        try:
            response = await self.client.post(f"/brands/{brand_id}/campaigns/", json=payload)
        except httpx.TimeoutException:
            logger.exception(
                "slicktext_v2_campaign_timeout",
                brand_id=brand_id,
            )
            return {
                "success": False,
                "error": "SlickText API timed out. The campaign may still be processing.",
            }

        logger.info(
            "slicktext_v2_campaign_response",
            status_code=response.status_code,
            response_text=response.text[:500] if response.text else "",
        )

        if response.status_code not in (HTTPStatus.OK, HTTPStatus.CREATED):
            try:
                error_data = response.json()
                error_msg = error_data.get("error", error_data.get("message", response.text))
                if isinstance(error_msg, list):
                    error_msg = "; ".join(error_msg)
            except Exception:
                error_msg = response.text
            logger.warning(
                "slicktext_v2_campaign_create_failed",
                status=response.status_code,
                error=error_msg,
            )
            # Provide helpful error message for common issues
            if (
                "upgrade" in str(error_msg).lower()
                or response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
            ):
                return {
                    "success": False,
                    "error": (
                        f"SlickText API error: {error_msg}. "
                        "Please check your SlickText account settings or contact SlickText support "
                        "to enable API campaign sending."
                    ),
                }
            return {"success": False, "error": error_msg}

        data = response.json()
        campaign_id = str(data.get("campaign_id") or data.get("id", ""))

        logger.info(
            "slicktext_v2_campaign_sent",
            campaign_id=campaign_id,
            to=to,
        )

        return {
            "success": True,
            "campaign_id": campaign_id,
            "to": to,
            "status": "sent",
            "message": f"SMS sent successfully to {to}",
        }

    async def send_sms(self, to: str, body: str) -> dict[str, Any]:
        """Send an SMS message via SlickText API.

        Tries V1 API first (if credentials provided), then V2 API.

        V1 API (Legacy): Direct message sending via POST /messages
        V2 API: Inbox reply or campaign-based sending
        """
        try:
            # Try V1 API first if we have public/private keys
            if self._use_v1:
                logger.info("slicktext_using_v1_api")
                return await self._send_via_v1_api(to, body)

            # V2 API flow
            brand_id = await self._get_brand_id()
            if not brand_id:
                return {"success": False, "error": "Failed to get SlickText brand ID"}

            # Try inbox reply first (faster for one-off texts)
            inbox_result = await self._send_via_inbox(to, body, brand_id)
            if inbox_result is not None:
                return inbox_result

            logger.info("slicktext_v2_inbox_unavailable_trying_campaign")

            # Fall back to campaign-based sending
            return await self._send_via_campaign(to, body, brand_id)

        except Exception as e:
            logger.exception("slicktext_send_sms_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def get_campaign_status(self, campaign_id: str) -> dict[str, Any]:
        """Get the status of a campaign.

        V2 API Docs: https://api.slicktext.com/docs/v2/campaigns
        """
        try:
            brand_id = await self._get_brand_id()
            if not brand_id:
                return {
                    "success": False,
                    "error": "Failed to get SlickText brand ID",
                }

            # V2 API: GET /brands/{brand_id}/campaigns/{campaign_id}
            response = await self.client.get(f"/brands/{brand_id}/campaigns/{campaign_id}")

            if response.status_code != HTTPStatus.OK:
                return {
                    "success": False,
                    "error": f"Campaign not found: {response.text}",
                }

            data = response.json()
            # V2 API returns campaign_id at top level
            return {
                "success": True,
                "campaign_id": str(data.get("campaign_id") or data.get("id", "")),
                "name": data.get("name"),
                "status": data.get("status", "unknown"),
                "sent_at": data.get("sent_at"),
                "stats": data.get("stats", {}),
            }

        except Exception as e:
            logger.exception("slicktext_v2_get_campaign_status_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a SlickText SMS tool by name."""
        tool_map: dict[str, ToolHandler] = {
            "slicktext_send_sms": self.send_sms,
            "slicktext_get_campaign_status": self.get_campaign_status,
        }

        handler = tool_map.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        result: dict[str, Any] = await handler(**arguments)
        return result
