"""SlickText inbox polling service for receiving inbound SMS messages via API.

This background worker polls the SlickText V1 (legacy) API for new inbound messages
instead of relying on webhooks. Useful for tech demos and environments
where webhooks are not available.

NOTE: Only V1 API supports message polling (GET /messages endpoint).
V2 API (dev.slicktext.com) does NOT have an inbox/messages polling endpoint.
"""

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any

import httpx
import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.phone_number import PhoneNumber
from app.models.sms import SMSConversation, SMSMessage
from app.models.user_settings import UserSettings
from app.services.text_agent_service import schedule_ai_response

logger = structlog.get_logger()

# Default poll interval in seconds
DEFAULT_POLL_INTERVAL_SECONDS = 10


class SlickTextPollingService:
    """Background service for polling SlickText V1 (legacy) API for new messages.

    NOTE: Only V1 API supports message polling. V2 API does not have inbox endpoints.
    """

    # V1 API (legacy accounts) - the only API that supports message polling
    BASE_URL_V1 = "https://api.slicktext.com/v1"

    def __init__(self, poll_interval: int = DEFAULT_POLL_INTERVAL_SECONDS) -> None:
        """Initialize the polling service.

        Args:
            poll_interval: Seconds between poll cycles (default 30)
        """
        self.poll_interval = poll_interval
        self.running = False
        self.logger = logger.bind(component="slicktext_polling")
        self._task: asyncio.Task[None] | None = None
        # Track last seen message IDs per workspace to avoid duplicates
        self._last_seen_messages: dict[str, set[str]] = {}
        # Track last poll time per workspace
        self._last_poll_time: dict[str, datetime] = {}

    async def start(self) -> None:
        """Start the polling service background task."""
        if self.running:
            self.logger.warning("SlickText polling service already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        self.logger.info(
            "SlickText polling service started",
            poll_interval=self.poll_interval,
        )

    async def stop(self) -> None:
        """Stop the polling service."""
        self.running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.logger.info("SlickText polling service stopped")

    async def _run_loop(self) -> None:
        """Main worker loop that polls for new messages."""
        while self.running:
            try:
                await self._poll_all_workspaces()
            except Exception:
                self.logger.exception("Error in SlickText polling loop")

            await asyncio.sleep(self.poll_interval)

    async def _poll_all_workspaces(self) -> None:
        """Poll SlickText inbox for all configured workspaces."""
        async with AsyncSessionLocal() as db:
            # Find all user settings with SlickText credentials
            result = await db.execute(
                select(UserSettings).where(
                    # Must have either V1 or V2 credentials
                    (UserSettings.slicktext_api_key.isnot(None))
                    | (
                        and_(
                            UserSettings.slicktext_public_key.isnot(None),
                            UserSettings.slicktext_private_key.isnot(None),
                        )
                    )
                )
            )
            settings_list = result.scalars().all()

            if not settings_list:
                return

            self.logger.debug(
                "Polling SlickText for workspaces",
                count=len(settings_list),
            )

            for user_settings in settings_list:
                try:
                    await self._poll_workspace(user_settings, db)
                except Exception:
                    self.logger.exception(
                        "Error polling workspace",
                        workspace_id=str(user_settings.workspace_id),
                        user_id=str(user_settings.user_id),
                    )

    async def _poll_workspace(
        self,
        user_settings: UserSettings,
        db: AsyncSession,
    ) -> None:
        """Poll SlickText inbox for a specific workspace.

        Args:
            user_settings: User settings with SlickText credentials
            db: Database session
        """
        workspace_key = str(user_settings.workspace_id or user_settings.user_id)
        log = self.logger.bind(
            workspace_id=str(user_settings.workspace_id),
            user_id=str(user_settings.user_id),
        )

        # Determine which API to use
        # V1 (legacy) API supports GET /messages endpoint for polling
        # V2 API does NOT have an inbox/messages polling endpoint - only contacts/lists/campaigns
        has_v1_credentials = bool(
            user_settings.slicktext_public_key and user_settings.slicktext_private_key
        )

        if has_v1_credentials:
            await self._poll_v1_api(user_settings, db, workspace_key, log)
        else:
            # V2 API doesn't support inbox polling - skip with debug log
            log.debug(
                "Skipping SlickText polling - V2 API does not support inbox polling. "
                "Configure V1 credentials (public_key/private_key) to enable polling."
            )

    async def _poll_v1_api(
        self,
        user_settings: UserSettings,
        db: AsyncSession,
        workspace_key: str,
        log: structlog.stdlib.BoundLogger,
    ) -> None:
        """Poll SlickText V1 API for new inbound messages.

        V1 API uses the inbox/chat endpoint:
        - GET /inbox - returns chatThreads (conversations)
        - GET /inbox/{thread_id}/messages - returns chatMessages with inbound flag

        Messages with inbound=1 are received from contacts.
        """
        async with httpx.AsyncClient(
            base_url=self.BASE_URL_V1,
            auth=(
                user_settings.slicktext_public_key or "",
                user_settings.slicktext_private_key or "",
            ),
            timeout=30.0,
        ) as client:
            try:
                # Get recent inbox threads (conversations)
                inbox_response = await client.get("/inbox", params={"limit": 20})

                if inbox_response.status_code != HTTPStatus.OK:
                    log.warning(
                        "SlickText V1 inbox API error",
                        status=inbox_response.status_code,
                        response=inbox_response.text[:200],
                    )
                    return

                inbox_data = inbox_response.json()
                threads = inbox_data.get("chatThreads", [])

                if not threads:
                    log.debug("No inbox threads found")
                    return

                # Collect all inbound messages from recent threads
                all_inbound_messages: list[dict[str, Any]] = []

                for thread in threads:
                    thread_id = thread.get("id")
                    if not thread_id:
                        continue

                    # Get messages for this thread
                    messages_response = await client.get(
                        f"/inbox/{thread_id}/messages",
                        params={"limit": 20},
                    )

                    if messages_response.status_code != HTTPStatus.OK:
                        continue

                    messages_data = messages_response.json()
                    chat_messages = messages_data.get("chatMessages", [])

                    # Filter to inbound messages only (inbound=1)
                    for msg in chat_messages:
                        if msg.get("inbound") == 1:
                            # Add thread context for phone number
                            msg["_thread_phone"] = thread.get("with")
                            all_inbound_messages.append(msg)

                if all_inbound_messages:
                    log.debug(
                        "Found inbound messages from inbox",
                        count=len(all_inbound_messages),
                    )

                await self._process_messages(
                    messages=all_inbound_messages,
                    user_settings=user_settings,
                    db=db,
                    workspace_key=workspace_key,
                    log=log,
                )

            except httpx.TimeoutException:
                log.warning("SlickText V1 API timeout")
            except Exception as e:
                log.exception("SlickText V1 polling error", error=str(e))

    async def _process_messages(
        self,
        messages: list[dict[str, Any]],
        user_settings: UserSettings,
        db: AsyncSession,
        workspace_key: str,
        log: structlog.stdlib.BoundLogger,
    ) -> None:
        """Process polled messages and create SMS records for new ones.

        Args:
            messages: List of message dictionaries from V1 API
            user_settings: User settings
            db: Database session
            workspace_key: Key for tracking seen messages
            log: Logger instance
        """
        if workspace_key not in self._last_seen_messages:
            # First poll - just record IDs, don't process to avoid duplicates
            self._last_seen_messages[workspace_key] = set()
            for msg in messages:
                msg_id = self._get_message_id(msg)
                if msg_id:
                    self._last_seen_messages[workspace_key].add(msg_id)
            log.info(
                "Initial poll - recorded existing messages",
                count=len(self._last_seen_messages[workspace_key]),
            )
            return

        seen_ids = self._last_seen_messages[workspace_key]
        new_messages = []

        for msg in messages:
            msg_id = self._get_message_id(msg)
            if msg_id and msg_id not in seen_ids:
                new_messages.append(msg)
                seen_ids.add(msg_id)

        if not new_messages:
            return

        log.info("Found new inbound messages", count=len(new_messages))

        # Get phone number for this workspace
        our_phone = user_settings.slicktext_phone_number
        if not our_phone:
            # Try to find from phone numbers table
            phone_result = await db.execute(
                select(PhoneNumber).where(
                    PhoneNumber.workspace_id == user_settings.workspace_id,
                    PhoneNumber.can_receive_sms == True,  # noqa: E712
                )
            )
            phone_number = phone_result.scalar_one_or_none()
            if phone_number:
                our_phone = phone_number.phone_number

        if not our_phone:
            log.warning("No phone number configured for SlickText workspace")
            return

        # Process each new message
        for msg in new_messages:
            await self._create_message_record(
                msg=msg,
                user_settings=user_settings,
                our_phone=our_phone,
                db=db,
                log=log,
            )

        await db.commit()

    def _get_message_id(self, msg: dict[str, Any]) -> str | None:
        """Extract message ID from V1 inbox API response.

        V1 inbox chatMessages have an 'id' field for inbound messages.
        """
        msg_id = msg.get("id") or msg.get("message_id")
        if msg_id:
            return str(msg_id)
        # Fallback: create unique ID from thread + sent time
        thread_id = msg.get("chatThreadId")
        sent = msg.get("sent")
        if thread_id and sent:
            return f"{thread_id}_{sent}"
        return None

    async def _create_message_record(
        self,
        msg: dict[str, Any],
        user_settings: UserSettings,
        our_phone: str,
        db: AsyncSession,
        log: structlog.stdlib.BoundLogger,
    ) -> None:
        """Create SMS message and conversation records for a polled message.

        Args:
            msg: Message dictionary from V1 inbox API (chatMessages format)
            user_settings: User settings
            our_phone: Our SlickText phone number
            db: Database session
            log: Logger instance

        V1 inbox API chatMessages format:
        {
            "id": 47162892,
            "chatThreadId": 11226872,
            "to": "+18337551307",  # our number
            "from": "+12482259677",  # sender
            "body": "message text",
            "inbound": 1,
            "sent": "2025-12-10 12:53:51"
        }
        """
        # Extract message details from V1 inbox API response
        # "from" is the sender's phone for inbound messages
        from_phone = msg.get("from") or msg.get("_thread_phone")
        body = msg.get("body", "")
        provider_msg_id = self._get_message_id(msg) or ""

        if not from_phone or not body:
            log.debug("Skipping message without from_phone or body", msg=msg)
            return

        # Normalize phone numbers
        if not from_phone.startswith("+"):
            from_phone = f"+{from_phone}"
        if not our_phone.startswith("+"):
            our_phone = f"+{our_phone}"

        log.info(
            "Processing polled message",
            from_phone=from_phone,
            provider_msg_id=provider_msg_id,
        )

        # Check if message already exists
        existing = await db.execute(
            select(SMSMessage).where(
                SMSMessage.provider_message_id == provider_msg_id,
                SMSMessage.provider == "slicktext",
            )
        )
        if existing.scalar_one_or_none():
            log.debug("Message already exists", provider_msg_id=provider_msg_id)
            return

        # SAFETY: Only process messages for EXISTING conversations
        # This ensures we only respond to contacts we've previously messaged through voice-noob
        # We do NOT create new conversations for random inbound messages
        workspace_id = user_settings.workspace_id

        conv_result = await db.execute(
            select(SMSConversation).where(
                SMSConversation.workspace_id == workspace_id,
                SMSConversation.from_number == our_phone,
                SMSConversation.to_number == from_phone,
            )
        )
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            # No existing conversation - this is someone we haven't messaged before
            # Skip to avoid AI responding to random people outside of voice-noob
            log.debug(
                "Skipping message from unknown contact (no existing conversation)",
                from_phone=from_phone,
                our_phone=our_phone,
            )
            return

        # EXISTING conversation - auto-assign default agent if it's platform-initiated
        # but doesn't have an agent yet (for backward compatibility)
        if (
            conversation.initiated_by == "platform"
            and not conversation.assigned_agent_id
            and user_settings.slicktext_default_text_agent_id
        ):
            conversation.assigned_agent_id = user_settings.slicktext_default_text_agent_id
            conversation.ai_enabled = True
            log.info(
                "auto_assigned_agent_to_existing_conversation",
                conversation_id=str(conversation.id),
                agent_id=str(user_settings.slicktext_default_text_agent_id),
            )

        # Create the message record
        sms_message = SMSMessage(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            provider="slicktext",
            provider_message_id=provider_msg_id,
            direction="inbound",
            from_number=from_phone,
            to_number=our_phone,
            body=body,
            status="received",
            is_read=False,
            created_at=datetime.now(UTC),
        )
        db.add(sms_message)

        # Update conversation
        conversation.last_message_preview = body[:255] if body else None
        conversation.last_message_at = datetime.now(UTC)
        conversation.last_message_direction = "inbound"
        conversation.unread_count = (conversation.unread_count or 0) + 1
        conversation.updated_at = datetime.now(UTC)

        await db.flush()

        log.info(
            "Created message record from polled data",
            message_id=str(sms_message.id),
            conversation_id=str(conversation.id),
        )

        # Schedule AI response if agent assigned and AI enabled
        if (
            conversation.assigned_agent_id
            and conversation.ai_enabled
            and not conversation.ai_paused
            and workspace_id
        ):
            log.info("Scheduling AI response for polled message")
            await schedule_ai_response(
                conversation_id=conversation.id,
                workspace_id=workspace_id,
                provider="slicktext",
            )


# Global service instance
_slicktext_polling_service: SlickTextPollingService | None = None


async def start_slicktext_polling(
    poll_interval: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> SlickTextPollingService:
    """Start the global SlickText polling service.

    Args:
        poll_interval: Seconds between poll cycles

    Returns:
        SlickText polling service instance
    """
    global _slicktext_polling_service
    if _slicktext_polling_service is None:
        _slicktext_polling_service = SlickTextPollingService(poll_interval=poll_interval)
        await _slicktext_polling_service.start()
    return _slicktext_polling_service


async def stop_slicktext_polling() -> None:
    """Stop the global SlickText polling service."""
    global _slicktext_polling_service
    if _slicktext_polling_service:
        await _slicktext_polling_service.stop()
        _slicktext_polling_service = None


def get_slicktext_polling_service() -> SlickTextPollingService | None:
    """Get the global SlickText polling service instance.

    Returns:
        SlickText polling service or None if not started
    """
    return _slicktext_polling_service
