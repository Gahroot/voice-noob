"""FollowUpBoss CRM tools for voice agents.

Provides tools for:
- Searching and managing contacts/people
- Creating leads with event tracking
- Updating contact information

API Docs: https://docs.followupboss.com/reference/getting-started
Base URL: https://api.followupboss.com/v1
"""

from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

import httpx
import structlog

# Type alias for tool handler functions
ToolHandler = Callable[..., Awaitable[dict[str, Any]]]

logger = structlog.get_logger()

# FollowUpBoss API base URL
FUB_BASE_URL = "https://api.followupboss.com/v1"

# System identification headers (required for Inbox Apps API)
FUB_SYSTEM_NAME = "Prestyj-Real-Estate"
FUB_SYSTEM_KEY = "f8037a8664edce80ecc4532956114464"


class FollowUpBossTools:
    """FollowUpBoss CRM tools for voice agents.

    Provides tools for:
    - Searching people by phone/email/name
    - Creating contacts and leads
    - Updating contact information
    - Creating events (preferred for lead capture with automations)
    """

    def __init__(self, api_key: str) -> None:
        """Initialize FollowUpBoss tools.

        Args:
            api_key: FollowUpBoss API key (used as username in Basic Auth)
        """
        self.api_key = api_key
        self.logger = logger.bind(component="followupboss_tools")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with Basic Auth and system headers."""
        if self._client is None:
            # FollowUpBoss uses Basic Auth: API key as username, blank password
            self._client = httpx.AsyncClient(
                base_url=FUB_BASE_URL,
                auth=(self.api_key, ""),  # Basic Auth with API key as username
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-System-Name": FUB_SYSTEM_NAME,  # Required for Inbox Apps API
                    "X-System-Key": FUB_SYSTEM_KEY,  # Required for Inbox Apps API
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def get_tool_definitions() -> list[dict[str, Any]]:
        """Get OpenAI function calling tool definitions.

        Returns:
            List of tool definitions for GPT Realtime API
        """
        return [
            {
                "type": "function",
                "name": "fub_search_person",
                "description": "Search for a person in FollowUpBoss by phone number, email, or name",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Phone number, email, or name to search for",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "type": "function",
                "name": "fub_get_person",
                "description": "Get full details of a person by their FollowUpBoss person ID",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "person_id": {
                            "type": "string",
                            "description": "FollowUpBoss person ID",
                        },
                    },
                    "required": ["person_id"],
                },
            },
            {
                "type": "function",
                "name": "fub_create_lead",
                "description": (
                    "Create a new lead in FollowUpBoss with event tracking. "
                    "This is the preferred method as it triggers automations and prevents duplicates."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "first_name": {"type": "string", "description": "First name"},
                        "last_name": {"type": "string", "description": "Last name"},
                        "phone": {"type": "string", "description": "Phone number"},
                        "email": {"type": "string", "description": "Email address"},
                        "source": {
                            "type": "string",
                            "description": "Lead source (e.g., Voice Agent, Phone Call)",
                        },
                        "message": {
                            "type": "string",
                            "description": "Notes or message about the inquiry",
                        },
                    },
                    "required": ["first_name", "phone"],
                },
            },
            {
                "type": "function",
                "name": "fub_create_person",
                "description": (
                    "Create a new person in FollowUpBoss without event tracking. "
                    "Note: This does NOT trigger automations. Use fub_create_lead for leads."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "first_name": {"type": "string", "description": "First name"},
                        "last_name": {"type": "string", "description": "Last name"},
                        "phone": {"type": "string", "description": "Phone number"},
                        "email": {"type": "string", "description": "Email address"},
                    },
                    "required": ["first_name"],
                },
            },
            {
                "type": "function",
                "name": "fub_update_person",
                "description": "Update an existing person in FollowUpBoss",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "person_id": {"type": "string", "description": "Person ID to update"},
                        "first_name": {"type": "string", "description": "First name"},
                        "last_name": {"type": "string", "description": "Last name"},
                        "phone": {"type": "string", "description": "Phone number"},
                        "email": {"type": "string", "description": "Email address"},
                    },
                    "required": ["person_id"],
                },
            },
            {
                "type": "function",
                "name": "fub_add_note",
                "description": "Add a note to a person in FollowUpBoss",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "person_id": {"type": "string", "description": "Person ID"},
                        "subject": {"type": "string", "description": "Note subject"},
                        "body": {"type": "string", "description": "Note content"},
                    },
                    "required": ["person_id", "body"],
                },
            },
        ]

    async def fub_search_person(self, query: str) -> dict[str, Any]:
        """Search for a person by phone, email, or name.

        Args:
            query: Search query

        Returns:
            Person information or error
        """
        try:
            client = await self._get_client()

            # FollowUpBoss search endpoint
            response = await client.get(
                "/people",
                params={
                    "query": query,
                    "limit": 5,
                },
            )

            if response.status_code != HTTPStatus.OK:
                self.logger.warning(
                    "fub_search_person_failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                return {"success": False, "error": f"API error: {response.status_code}"}

            data = response.json()
            people = data.get("people", [])

            if not people:
                return {
                    "success": True,
                    "found": False,
                    "message": f"No person found matching '{query}'",
                }

            # Format results
            person_list = [
                {
                    "id": p.get("id"),
                    "name": f"{p.get('firstName', '')} {p.get('lastName', '')}".strip(),
                    "first_name": p.get("firstName"),
                    "last_name": p.get("lastName"),
                    "email": p.get("emails", [{}])[0].get("value") if p.get("emails") else None,
                    "phone": p.get("phones", [{}])[0].get("value") if p.get("phones") else None,
                    "source": p.get("source"),
                }
                for p in people[:3]
            ]

            return {
                "success": True,
                "found": True,
                "count": len(person_list),
                "people": person_list,
            }

        except Exception as e:
            self.logger.exception("fub_search_person_error", query=query, error=str(e))
            return {"success": False, "error": str(e)}

    async def fub_get_person(self, person_id: str) -> dict[str, Any]:
        """Get full person details.

        Args:
            person_id: FollowUpBoss person ID

        Returns:
            Person details or error
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/people/{person_id}")

            if response.status_code != HTTPStatus.OK:
                return {"success": False, "error": f"Person not found: {response.status_code}"}

            person = response.json()

            return {
                "success": True,
                "person": {
                    "id": person.get("id"),
                    "first_name": person.get("firstName"),
                    "last_name": person.get("lastName"),
                    "name": f"{person.get('firstName', '')} {person.get('lastName', '')}".strip(),
                    "emails": [e.get("value") for e in person.get("emails", [])],
                    "phones": [p.get("value") for p in person.get("phones", [])],
                    "source": person.get("source"),
                    "stage": person.get("stage"),
                    "created": person.get("created"),
                },
            }

        except Exception as e:
            self.logger.exception("fub_get_person_error", person_id=person_id, error=str(e))
            return {"success": False, "error": str(e)}

    async def fub_create_lead(
        self,
        first_name: str,
        phone: str,
        last_name: str | None = None,
        email: str | None = None,
        source: str = "Voice Agent",
        message: str | None = None,
    ) -> dict[str, Any]:
        """Create a new lead using events endpoint (recommended).

        This triggers automations and handles duplicates properly.

        Args:
            first_name: First name
            phone: Phone number
            last_name: Last name
            email: Email address
            source: Lead source
            message: Notes or message

        Returns:
            Created person info or error
        """
        try:
            client = await self._get_client()

            # Build person object
            person_data: dict[str, Any] = {
                "firstName": first_name,
                "phones": [{"value": phone}],
            }

            if last_name:
                person_data["lastName"] = last_name
            if email:
                person_data["emails"] = [{"value": email}]

            # Build event payload
            payload: dict[str, Any] = {
                "source": source,
                "type": "Phone Lead",
                "person": person_data,
            }

            if message:
                payload["message"] = message

            response = await client.post("/events", json=payload)

            if response.status_code not in (HTTPStatus.OK, HTTPStatus.CREATED):
                self.logger.warning(
                    "fub_create_lead_failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                return {"success": False, "error": f"Failed to create lead: {response.text}"}

            data = response.json()
            person = data.get("person", {})

            return {
                "success": True,
                "person_id": person.get("id"),
                "message": f"Created lead for {first_name} {last_name or ''}".strip(),
            }

        except Exception as e:
            self.logger.exception("fub_create_lead_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def fub_create_person(
        self,
        first_name: str,
        last_name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any]:
        """Create a new person (without automation triggers).

        Note: This does NOT trigger automations. Use fub_create_lead instead for leads.

        Args:
            first_name: First name
            last_name: Last name
            phone: Phone number
            email: Email address

        Returns:
            Created person info or error
        """
        try:
            client = await self._get_client()

            payload: dict[str, Any] = {
                "firstName": first_name,
            }

            if last_name:
                payload["lastName"] = last_name
            if phone:
                payload["phones"] = [{"value": phone}]
            if email:
                payload["emails"] = [{"value": email}]

            response = await client.post("/people", json=payload)

            if response.status_code not in (HTTPStatus.OK, HTTPStatus.CREATED):
                self.logger.warning(
                    "fub_create_person_failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                return {"success": False, "error": f"Failed to create person: {response.text}"}

            person = response.json()

            return {
                "success": True,
                "person_id": person.get("id"),
                "message": f"Created person for {first_name} {last_name or ''}".strip(),
            }

        except Exception as e:
            self.logger.exception("fub_create_person_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def fub_update_person(
        self,
        person_id: str,
        first_name: str | None = None,
        last_name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing person.

        Args:
            person_id: Person ID
            first_name: First name
            last_name: Last name
            phone: Phone number
            email: Email address

        Returns:
            Update result
        """
        try:
            client = await self._get_client()

            payload: dict[str, Any] = {}
            if first_name:
                payload["firstName"] = first_name
            if last_name:
                payload["lastName"] = last_name
            if phone:
                payload["phones"] = [{"value": phone}]
            if email:
                payload["emails"] = [{"value": email}]

            if not payload:
                return {"success": False, "error": "No fields to update"}

            response = await client.put(f"/people/{person_id}", json=payload)

            if response.status_code != HTTPStatus.OK:
                return {"success": False, "error": f"Failed to update person: {response.text}"}

            return {
                "success": True,
                "person_id": person_id,
                "message": "Person updated successfully",
            }

        except Exception as e:
            self.logger.exception("fub_update_person_error", person_id=person_id, error=str(e))
            return {"success": False, "error": str(e)}

    async def fub_add_note(
        self,
        person_id: str,
        body: str,
        subject: str | None = None,
    ) -> dict[str, Any]:
        """Add a note to a person.

        Args:
            person_id: Person ID
            body: Note content
            subject: Note subject

        Returns:
            Result
        """
        try:
            client = await self._get_client()

            payload: dict[str, Any] = {
                "personId": person_id,
                "body": body,
            }

            if subject:
                payload["subject"] = subject

            response = await client.post("/notes", json=payload)

            if response.status_code not in (HTTPStatus.OK, HTTPStatus.CREATED):
                return {"success": False, "error": f"Failed to add note: {response.text}"}

            note = response.json()

            return {
                "success": True,
                "note_id": note.get("id"),
                "message": "Note added successfully",
            }

        except Exception as e:
            self.logger.exception("fub_add_note_error", person_id=person_id, error=str(e))
            return {"success": False, "error": str(e)}

    async def fub_send_inbox_message(
        self,
        person_id: str,
        message: str,
        source: str = "SMS",
    ) -> dict[str, Any]:
        """Send message to FollowUpBoss Inbox API.

        This syncs messages to FUB's Inbox Apps feature for tracking all
        customer communications in one place.

        Args:
            person_id: FUB person ID
            message: Message content
            source: Message source (default: "SMS")

        Returns:
            Result with message_id or error
        """
        try:
            client = await self._get_client()

            payload: dict[str, Any] = {
                "personId": person_id,
                "message": message,
                "source": source,
            }

            response = await client.post("/inbox/messages", json=payload)

            if response.status_code not in (HTTPStatus.OK, HTTPStatus.CREATED):
                self.logger.warning(
                    "fub_send_inbox_message_failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                return {
                    "success": False,
                    "error": f"Failed to send inbox message: {response.text}",
                }

            data = response.json()

            return {
                "success": True,
                "message_id": data.get("id"),
                "message": "Message sent to FUB Inbox successfully",
            }

        except Exception as e:
            self.logger.exception("fub_send_inbox_message_error", person_id=person_id, error=str(e))
            return {"success": False, "error": str(e)}

    async def fub_find_or_create_person(
        self,
        phone: str,
        first_name: str = "Unknown",
        last_name: str | None = None,
    ) -> dict[str, Any]:
        """Find person by phone or create new if not found.

        This is a convenience method that searches by phone first,
        then creates a new person if not found.

        Args:
            phone: Phone number (E.164 format recommended)
            first_name: First name (default: "Unknown")
            last_name: Last name (optional)

        Returns:
            {success: True, person_id: "...", created: bool} or error
        """
        try:
            # Step 1: Search for existing person by phone
            search_result = await self.fub_search_person(query=phone)

            if search_result.get("success") and search_result.get("found"):
                # Person found
                people = search_result.get("people", [])
                if people:
                    return {
                        "success": True,
                        "person_id": people[0]["id"],
                        "created": False,
                        "message": f"Found existing person: {people[0].get('name', 'Unknown')}",
                    }

            # Step 2: Person not found, create new
            create_result = await self.fub_create_person(
                first_name=first_name,
                last_name=last_name,
                phone=phone,
            )

            if create_result.get("success"):
                return {
                    "success": True,
                    "person_id": create_result["person_id"],
                    "created": True,
                    "message": create_result.get("message", "Created new person in FUB"),
                }

            # Creation failed
            return create_result

        except Exception as e:
            self.logger.exception("fub_find_or_create_person_error", phone=phone, error=str(e))
            return {"success": False, "error": str(e)}

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a FollowUpBoss tool by name.

        Args:
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result
        """
        tool_map: dict[str, ToolHandler] = {
            "fub_search_person": self.fub_search_person,
            "fub_get_person": self.fub_get_person,
            "fub_create_lead": self.fub_create_lead,
            "fub_create_person": self.fub_create_person,
            "fub_update_person": self.fub_update_person,
            "fub_add_note": self.fub_add_note,
        }

        handler = tool_map.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        result: dict[str, Any] = await handler(**arguments)
        return result
