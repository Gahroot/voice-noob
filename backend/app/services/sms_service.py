"""SMS service for sending messages and managing conversations via Telnyx."""

import uuid
from datetime import UTC, datetime

import httpx
import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.fub_sync import FUBMessageSyncQueue
from app.models.sms import (
    MessageDirection,
    MessageStatus,
    SMSCampaign,
    SMSCampaignContact,
    SMSCampaignContactStatus,
    SMSConversation,
    SMSMessage,
)
from app.models.user_integration import UserIntegration

logger = structlog.get_logger()


class SMSService:
    """SMS service for Telnyx messaging.

    Handles:
    - Sending SMS messages
    - Managing conversations
    - Processing inbound messages
    - Tracking delivery status
    """

    BASE_URL = "https://api.telnyx.com/v2"

    def __init__(
        self,
        api_key: str,
        messaging_profile_id: str | None = None,
    ) -> None:
        """Initialize SMS service.

        Args:
            api_key: Telnyx API key
            messaging_profile_id: Optional messaging profile ID for routing
        """
        self.api_key = api_key
        self.messaging_profile_id = messaging_profile_id
        self._client: httpx.AsyncClient | None = None
        self.logger = logger.bind(service="sms")

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

    async def send_message(  # noqa: PLR0915
        self,
        to_number: str,
        from_number: str,
        body: str,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        agent_id: uuid.UUID | None = None,
        campaign_id: uuid.UUID | None = None,
    ) -> SMSMessage:
        """Send an SMS message and store it.

        Args:
            to_number: Recipient phone number (E.164)
            from_number: Sender phone number (E.164)
            body: Message content
            db: Database session
            workspace_id: Workspace ID
            user_id: User ID
            agent_id: Optional agent ID if sent by AI
            campaign_id: Optional campaign ID if part of campaign

        Returns:
            Created SMSMessage record
        """
        log = self.logger.bind(to=to_number, from_=from_number)
        log.info("sending_sms")

        # Get or create conversation
        conversation = await self._get_or_create_conversation(
            db=db,
            from_number=from_number,
            to_number=to_number,
            workspace_id=workspace_id,
            user_id=user_id,
        )

        # Create message record
        message = SMSMessage(
            conversation_id=conversation.id,
            provider="telnyx",
            direction=MessageDirection.OUTBOUND.value,
            from_number=from_number,
            to_number=to_number,
            body=body,
            status=MessageStatus.QUEUED.value,
            agent_id=agent_id,
            campaign_id=campaign_id,
        )
        db.add(message)
        await db.flush()

        # Send via Telnyx
        try:
            payload: dict[str, str] = {
                "to": to_number,
                "from": from_number,
                "text": body,
                "type": "SMS",
            }

            if self.messaging_profile_id:
                payload["messaging_profile_id"] = self.messaging_profile_id

            response = await self.client.post("/messages", json=payload)
            response_data = response.json()

            log.info(
                "telnyx_response",
                status_code=response.status_code,
                response=response_data,
            )

            # Check for success response
            if response.status_code in (200, 202):
                data = response_data.get("data", {})
                message.provider_message_id = data.get("id")
                message.status = MessageStatus.SENT.value
                message.sent_at = datetime.now(UTC)

                # Get segment count
                parts = data.get("parts", 1)
                if isinstance(parts, int):
                    message.segment_count = parts

                # Log delivery status from response
                to_info = data.get("to", [{}])
                if to_info and isinstance(to_info, list):
                    carrier = to_info[0].get("carrier", "unknown")
                    status = to_info[0].get("status", "unknown")
                    log.info(
                        "sms_sent",
                        message_id=message.provider_message_id,
                        carrier=carrier,
                        status=status,
                    )
                else:
                    log.info("sms_sent", message_id=message.provider_message_id)
            else:
                # Parse error from response
                try:
                    error_data = response.json()
                    errors = error_data.get("errors", [])
                    if errors and isinstance(errors[0], dict):
                        error_msg = (
                            errors[0].get("detail") or errors[0].get("title") or str(errors[0])
                        )
                    else:
                        error_msg = str(error_data)
                except Exception:
                    error_msg = response.text

                message.status = MessageStatus.FAILED.value
                message.error_message = error_msg
                message.error_code = str(response.status_code)
                log.error("sms_send_failed", error=error_msg, status_code=response.status_code)

        except Exception as e:
            message.status = MessageStatus.FAILED.value
            message.error_message = str(e)
            log.exception("sms_send_exception", error=str(e))

        # Update conversation
        preview_length = 255
        conversation.last_message_preview = (
            body[:preview_length] if len(body) > preview_length else body
        )
        conversation.last_message_at = datetime.now(UTC)
        conversation.last_message_direction = MessageDirection.OUTBOUND.value

        await db.commit()
        await db.refresh(message)

        # Enqueue for FUB sync if integration is enabled
        await self._enqueue_fub_sync_if_enabled(
            db=db,
            message=message,
            workspace_id=workspace_id,
            user_id=user_id,
        )

        return message

    async def process_inbound_message(
        self,
        db: AsyncSession,
        provider_message_id: str,
        from_number: str,
        to_number: str,
        body: str,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> SMSMessage:
        """Process an inbound SMS message.

        Args:
            db: Database session
            provider_message_id: Telnyx message ID
            from_number: Sender's phone number
            to_number: Our phone number
            body: Message content
            workspace_id: Workspace ID
            user_id: User ID

        Returns:
            Created SMSMessage record
        """
        log = self.logger.bind(
            provider_message_id=provider_message_id,
            from_=from_number,
            to=to_number,
        )
        log.info("processing_inbound_sms")

        # Get or create conversation (swap from/to for inbound)
        conversation = await self._get_or_create_conversation(
            db=db,
            from_number=to_number,  # Our number
            to_number=from_number,  # Their number
            workspace_id=workspace_id,
            user_id=user_id,
        )

        # Create message record
        message = SMSMessage(
            conversation_id=conversation.id,
            provider="telnyx",
            provider_message_id=provider_message_id,
            direction=MessageDirection.INBOUND.value,
            from_number=from_number,
            to_number=to_number,
            body=body,
            status=MessageStatus.RECEIVED.value,
        )
        db.add(message)

        # Update conversation
        preview_length = 255
        conversation.last_message_preview = (
            body[:preview_length] if len(body) > preview_length else body
        )
        conversation.last_message_at = datetime.now(UTC)
        conversation.last_message_direction = MessageDirection.INBOUND.value
        conversation.unread_count += 1

        # Check if this is a reply to a campaign
        await self._process_campaign_reply(db, conversation, body)

        await db.commit()
        await db.refresh(message)

        log.info("inbound_sms_processed", message_id=str(message.id))
        return message

    async def update_message_status(
        self,
        db: AsyncSession,
        provider_message_id: str,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> SMSMessage | None:
        """Update message delivery status.

        Args:
            db: Database session
            provider_message_id: Telnyx message ID
            status: New status
            error_code: Error code if failed
            error_message: Error details if failed

        Returns:
            Updated message or None if not found
        """
        result = await db.execute(
            select(SMSMessage).where(SMSMessage.provider_message_id == provider_message_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            self.logger.warning("message_not_found", provider_message_id=provider_message_id)
            return None

        # Map Telnyx status to our status
        status_map = {
            "queued": MessageStatus.QUEUED.value,
            "sending": MessageStatus.SENDING.value,
            "sent": MessageStatus.SENT.value,
            "delivered": MessageStatus.DELIVERED.value,
            "delivery_failed": MessageStatus.FAILED.value,
            "sending_failed": MessageStatus.FAILED.value,
        }

        message.status = status_map.get(status, status)

        if status == "delivered":
            message.delivered_at = datetime.now(UTC)

        if error_code:
            message.error_code = error_code
        if error_message:
            message.error_message = error_message

        await db.commit()
        await db.refresh(message)

        self.logger.info(
            "message_status_updated",
            message_id=str(message.id),
            status=message.status,
        )

        return message

    async def _get_or_create_conversation(
        self,
        db: AsyncSession,
        from_number: str,
        to_number: str,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        initiated_by: str = "platform",
    ) -> SMSConversation:
        """Get or create a conversation for the given phone numbers.

        Args:
            db: Database session
            from_number: Our phone number
            to_number: Contact's phone number
            workspace_id: Workspace ID
            user_id: User ID
            initiated_by: Who initiated: "platform" or "external"

        Returns:
            Existing or new conversation
        """
        from app.models.phone_number import PhoneNumber

        # Look for existing conversation
        result = await db.execute(
            select(SMSConversation).where(
                SMSConversation.workspace_id == workspace_id,
                SMSConversation.from_number == from_number,
                SMSConversation.to_number == to_number,
            )
        )
        conversation = result.scalar_one_or_none()

        if conversation:
            return conversation

        # Try to find contact by phone number
        contact_result = await db.execute(
            select(Contact).where(
                Contact.workspace_id == workspace_id,
                Contact.phone_number == to_number,
            )
        )
        contact = contact_result.scalar_one_or_none()

        # Look up default text agent from phone number configuration
        default_agent_id = None
        if initiated_by == "platform":
            from sqlalchemy import or_

            phone_result = await db.execute(
                select(PhoneNumber).where(
                    PhoneNumber.user_id == user_id,
                    or_(
                        PhoneNumber.workspace_id == workspace_id,
                        PhoneNumber.workspace_id.is_(None),  # User-level fallback
                    ),
                    PhoneNumber.phone_number == from_number,
                )
            )
            phone_number = phone_result.scalar_one_or_none()
            if phone_number:
                default_agent_id = phone_number.default_text_agent_id

        # Create new conversation - platform-initiated conversations can have AI respond
        conversation = SMSConversation(
            user_id=user_id,
            workspace_id=workspace_id,
            contact_id=contact.id if contact else None,
            from_number=from_number,
            to_number=to_number,
            initiated_by=initiated_by,
            assigned_agent_id=default_agent_id,
            ai_enabled=default_agent_id is not None,
        )
        db.add(conversation)
        await db.flush()

        self.logger.info(
            "conversation_created",
            conversation_id=str(conversation.id),
            contact_id=contact.id if contact else None,
            initiated_by=initiated_by,
            assigned_agent_id=str(default_agent_id) if default_agent_id else None,
        )

        return conversation

    async def _process_campaign_reply(
        self,
        db: AsyncSession,
        conversation: SMSConversation,
        body: str,
    ) -> None:
        """Process a reply that might be from a campaign contact.

        Args:
            db: Database session
            conversation: The conversation
            body: Message content
        """
        # Find campaign contact by conversation
        result = await db.execute(
            select(SMSCampaignContact)
            .join(SMSCampaign)
            .where(
                SMSCampaignContact.conversation_id == conversation.id,
                SMSCampaign.status.in_(["running", "paused"]),
            )
        )
        campaign_contact = result.scalar_one_or_none()

        if not campaign_contact:
            return

        # Update campaign contact
        campaign_contact.messages_received += 1
        campaign_contact.last_reply_at = datetime.now(UTC)

        # Check for opt-out keywords
        opt_out_keywords = ["stop", "unsubscribe", "opt out", "optout", "cancel"]
        if body.lower().strip() in opt_out_keywords:
            campaign_contact.opted_out = True
            campaign_contact.opted_out_at = datetime.now(UTC)
            campaign_contact.status = SMSCampaignContactStatus.OPTED_OUT.value

            # Update campaign stats
            campaign_result = await db.execute(
                select(SMSCampaign).where(SMSCampaign.id == campaign_contact.campaign_id)
            )
            campaign = campaign_result.scalar_one_or_none()
            if campaign:
                campaign.contacts_opted_out += 1
                campaign.replies_received += 1

            self.logger.info(
                "contact_opted_out",
                contact_id=campaign_contact.contact_id,
                campaign_id=str(campaign_contact.campaign_id),
            )
        else:
            # Mark as replied
            if campaign_contact.status == SMSCampaignContactStatus.SENT.value:
                campaign_contact.status = SMSCampaignContactStatus.REPLIED.value

            # Update campaign stats
            campaign_result = await db.execute(
                select(SMSCampaign).where(SMSCampaign.id == campaign_contact.campaign_id)
            )
            campaign = campaign_result.scalar_one_or_none()
            if campaign:
                campaign.replies_received += 1

    async def mark_conversation_read(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
    ) -> None:
        """Mark all messages in a conversation as read.

        Args:
            db: Database session
            conversation_id: Conversation ID
        """
        result = await db.execute(
            select(SMSConversation).where(SMSConversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()

        if conversation:
            conversation.unread_count = 0

            # Mark all inbound messages as read
            messages_result = await db.execute(
                select(SMSMessage).where(
                    SMSMessage.conversation_id == conversation_id,
                    SMSMessage.direction == MessageDirection.INBOUND.value,
                    SMSMessage.is_read == False,  # noqa: E712
                )
            )
            messages = messages_result.scalars().all()
            for message in messages:
                message.is_read = True

            await db.commit()

    async def get_message_status_from_provider(
        self,
        message_id: str,
    ) -> dict[str, str | None]:
        """Get message status from Telnyx.

        Args:
            message_id: Telnyx message ID

        Returns:
            Status information
        """
        try:
            response = await self.client.get(f"/messages/{message_id}")

            if response.status_code == 200:  # noqa: PLR2004
                data = response.json().get("data", {})
                to_info = data.get("to", [{}])[0] if data.get("to") else {}

                return {
                    "status": to_info.get("status"),
                    "completed_at": data.get("completed_at"),
                    "errors": str(data.get("errors")) if data.get("errors") else None,
                }
            return {"status": "unknown", "errors": response.text}

        except Exception as e:
            self.logger.exception("get_message_status_error", error=str(e))
            return {"status": "error", "errors": str(e)}

    async def _enqueue_fub_sync_if_enabled(
        self,
        db: AsyncSession,
        message: SMSMessage,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Enqueue outbound message for FUB sync if integration is enabled.

        Args:
            db: Database session
            message: SMS message to sync
            workspace_id: Workspace ID
            user_id: User ID
        """
        try:
            # Check if workspace has FUB integration enabled
            result = await db.execute(
                select(UserIntegration).where(
                    and_(
                        UserIntegration.user_id == user_id,
                        or_(
                            UserIntegration.workspace_id == workspace_id,
                            UserIntegration.workspace_id.is_(None),
                        ),
                        UserIntegration.integration_id == "followupboss",
                        UserIntegration.is_active.is_(True),
                    )
                )
            )
            fub_integration = result.scalar_one_or_none()

            if not fub_integration:
                # No FUB integration enabled, skip sync
                return

            # Create FUB sync queue entry
            sync_entry = FUBMessageSyncQueue(
                sms_message_id=message.id,
                workspace_id=workspace_id,
                status="pending",
                payload={
                    "direction": "outbound",
                    "from_number": message.from_number,
                    "to_number": message.to_number,
                    "body": message.body,
                },
            )
            db.add(sync_entry)
            await db.commit()

            self.logger.info(
                "fub_sync_enqueued",
                message_id=str(message.id),
                workspace_id=str(workspace_id),
                sync_id=str(sync_entry.id),
            )

        except Exception as e:
            self.logger.warning(
                "fub_sync_enqueue_failed",
                message_id=str(message.id),
                error=str(e),
            )
