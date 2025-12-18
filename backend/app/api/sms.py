"""SMS API routes for conversations, messages, and campaigns."""

import re
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.settings import get_user_api_keys
from app.core.auth import CurrentUser, user_id_to_uuid
from app.core.limiter import limiter
from app.core.webhook_security import verify_slicktext_webhook, verify_telnyx_webhook
from app.db.session import get_db
from app.models.contact import Contact
from app.models.sms import (
    MessageDirection,
    SMSCampaign,
    SMSCampaignContact,
    SMSCampaignStatus,
    SMSConversation,
    SMSMessage,
)
from app.services.sms_service import SMSService
from app.services.tools.sms_tools import SlickTextSMSTools

router = APIRouter(prefix="/api/v1/sms", tags=["sms"])
webhook_router = APIRouter(prefix="/webhooks/telnyx", tags=["webhooks"])
slicktext_webhook_router = APIRouter(prefix="/webhooks/slicktext", tags=["webhooks"])


def normalize_e164(phone: str) -> str:
    """Normalize phone number to E.164 format.

    Strips non-digit characters (except leading +) and ensures + prefix.
    """
    # Strip whitespace
    phone = phone.strip()

    # Check if it starts with +
    has_plus = phone.startswith("+")

    # Remove all non-digit characters
    digits = re.sub(r"\D", "", phone)

    if not digits:
        raise ValueError("Phone number must contain digits")

    # Add + prefix if missing
    if not has_plus:
        return f"+{digits}"

    return f"+{digits}"


logger = structlog.get_logger()


# =============================================================================
# Pydantic Models
# =============================================================================


class ConversationResponse(BaseModel):
    """SMS conversation response."""

    id: str
    contact_id: int | None = None
    contact_name: str | None = None
    from_number: str
    to_number: str
    status: str
    unread_count: int
    last_message_preview: str | None = None
    last_message_at: str | None = None
    last_message_direction: str | None = None
    created_at: str
    # AI text agent fields
    assigned_agent_id: str | None = None
    assigned_agent_name: str | None = None
    ai_enabled: bool = True
    ai_paused: bool = False


class MessageResponse(BaseModel):
    """SMS message response."""

    id: str
    direction: str
    from_number: str
    to_number: str
    body: str
    status: str
    is_read: bool
    sent_at: str | None = None
    delivered_at: str | None = None
    created_at: str
    agent_id: str | None = None
    error_message: str | None = None


class SendMessageRequest(BaseModel):
    """Request to send an SMS message."""

    to_number: str = Field(..., description="Recipient phone number (E.164)")
    from_number: str = Field(..., description="Sender phone number (E.164)")
    body: str = Field(..., description="Message content", max_length=1600)
    conversation_id: str | None = Field(None, description="Optional existing conversation ID")
    provider: str = Field("telnyx", description="SMS provider: telnyx or slicktext")

    @field_validator("to_number", "from_number")
    @classmethod
    def normalize_phone_number(cls, v: str) -> str:
        """Normalize phone numbers to E.164 format."""
        return normalize_e164(v)


class CreateCampaignRequest(BaseModel):
    """Request to create an SMS campaign."""

    name: str = Field(..., description="Campaign name")
    description: str | None = Field(None, description="Campaign description")
    from_phone_number: str = Field(..., description="Phone number to send from (E.164)")
    initial_message: str = Field(..., description="Initial message template")
    agent_id: str | None = Field(None, description="Agent ID for AI responses")
    ai_enabled: bool = Field(True, description="Whether AI auto-responds")
    ai_system_prompt: str | None = Field(None, description="System prompt for AI")
    qualification_criteria: str | None = Field(None, description="Lead qualification criteria")
    sending_hours_start: str | None = Field(None, description="Start of sending window (HH:MM)")
    sending_hours_end: str | None = Field(None, description="End of sending window (HH:MM)")
    sending_days: list[int] | None = Field(None, description="Days to send (0=Mon)")
    timezone: str = Field("UTC", description="Timezone for sending hours")
    messages_per_minute: int = Field(10, ge=1, le=60)
    follow_up_enabled: bool = Field(False)
    follow_up_delay_hours: int = Field(24, ge=1, le=168)
    follow_up_message: str | None = None
    max_follow_ups: int = Field(2, ge=0, le=10)
    contact_ids: list[int] = Field(default_factory=list, description="Contact IDs to include")

    @field_validator("from_phone_number")
    @classmethod
    def normalize_phone_number(cls, v: str) -> str:
        """Normalize phone number to E.164 format."""
        return normalize_e164(v)


class CampaignResponse(BaseModel):
    """SMS campaign response."""

    id: str
    name: str
    description: str | None
    status: str
    from_phone_number: str
    initial_message: str
    ai_enabled: bool
    agent_id: str | None = None
    agent_name: str | None = None
    total_contacts: int
    messages_sent: int
    messages_delivered: int
    replies_received: int
    contacts_qualified: int
    contacts_opted_out: int
    created_at: str
    started_at: str | None
    completed_at: str | None


class CampaignContactResponse(BaseModel):
    """Campaign contact response."""

    id: str
    contact_id: int
    contact_name: str | None
    contact_phone: str
    status: str
    messages_sent: int
    messages_received: int
    is_qualified: bool
    opted_out: bool
    first_sent_at: str | None
    last_reply_at: str | None


# =============================================================================
# Helper Functions
# =============================================================================


async def get_sms_service(
    user_id: int,
    db: AsyncSession,
    workspace_id: uuid.UUID,
) -> SMSService | None:
    """Get Telnyx SMS service for a user."""
    user_uuid = user_id_to_uuid(user_id)
    user_settings = await get_user_api_keys(user_uuid, db, workspace_id=workspace_id)

    if not user_settings or not user_settings.telnyx_api_key:
        return None

    return SMSService(
        api_key=user_settings.telnyx_api_key,
        messaging_profile_id=getattr(user_settings, "telnyx_messaging_profile_id", None),
    )


async def get_slicktext_service(
    user_id: int,
    db: AsyncSession,
    workspace_id: uuid.UUID,
) -> SlickTextSMSTools | None:
    """Get SlickText SMS service for a user.

    Supports both V1 (legacy) and V2 APIs:
    - V1: Uses public_key + private_key (Basic auth)
    - V2: Uses api_key (Bearer token)
    """
    user_uuid = user_id_to_uuid(user_id)
    user_settings = await get_user_api_keys(user_uuid, db, workspace_id=workspace_id)

    if not user_settings:
        return None

    # Check for V1 API credentials first (legacy accounts)
    has_v1_creds = bool(
        getattr(user_settings, "slicktext_public_key", None)
        and getattr(user_settings, "slicktext_private_key", None)
    )

    # Check for V2 API credentials
    has_v2_creds = bool(user_settings.slicktext_api_key)

    if not has_v1_creds and not has_v2_creds:
        return None

    return SlickTextSMSTools(
        api_key=user_settings.slicktext_api_key or "",
        public_key=getattr(user_settings, "slicktext_public_key", None),
        private_key=getattr(user_settings, "slicktext_private_key", None),
        textword_id=getattr(user_settings, "slicktext_textword_id", None),
    )


# =============================================================================
# Conversation Endpoints
# =============================================================================


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Query(..., description="Workspace ID"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[ConversationResponse]:
    """List SMS conversations."""
    workspace_uuid = uuid.UUID(workspace_id)

    query = (
        select(SMSConversation)
        .options(
            selectinload(SMSConversation.contact),
            selectinload(SMSConversation.assigned_agent),
        )
        .where(SMSConversation.workspace_id == workspace_uuid)
        .order_by(SMSConversation.last_message_at.desc().nulls_last())
        .offset(offset)
        .limit(limit)
    )

    if status:
        query = query.where(SMSConversation.status == status)

    result = await db.execute(query)
    conversations = result.scalars().all()

    return [
        ConversationResponse(
            id=str(conv.id),
            contact_id=conv.contact_id,
            contact_name=(
                f"{conv.contact.first_name} {conv.contact.last_name or ''}".strip()
                if conv.contact
                else None
            ),
            from_number=conv.from_number,
            to_number=conv.to_number,
            status=conv.status,
            unread_count=conv.unread_count,
            last_message_preview=conv.last_message_preview,
            last_message_at=conv.last_message_at.isoformat() if conv.last_message_at else None,
            last_message_direction=conv.last_message_direction,
            created_at=conv.created_at.isoformat(),
            assigned_agent_id=str(conv.assigned_agent_id) if conv.assigned_agent_id else None,
            assigned_agent_name=conv.assigned_agent.name if conv.assigned_agent else None,
            ai_enabled=conv.ai_enabled,
            ai_paused=conv.ai_paused,
        )
        for conv in conversations
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Get a single conversation."""
    result = await db.execute(
        select(SMSConversation)
        .options(
            selectinload(SMSConversation.contact),
            selectinload(SMSConversation.assigned_agent),
        )
        .where(SMSConversation.id == uuid.UUID(conversation_id))
    )
    conv = result.scalar_one_or_none()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationResponse(
        id=str(conv.id),
        contact_id=conv.contact_id,
        contact_name=(
            f"{conv.contact.first_name} {conv.contact.last_name or ''}".strip()
            if conv.contact
            else None
        ),
        from_number=conv.from_number,
        to_number=conv.to_number,
        status=conv.status,
        unread_count=conv.unread_count,
        last_message_preview=conv.last_message_preview,
        last_message_at=conv.last_message_at.isoformat() if conv.last_message_at else None,
        last_message_direction=conv.last_message_direction,
        created_at=conv.created_at.isoformat(),
        assigned_agent_id=str(conv.assigned_agent_id) if conv.assigned_agent_id else None,
        assigned_agent_name=conv.assigned_agent.name if conv.assigned_agent else None,
        ai_enabled=conv.ai_enabled,
        ai_paused=conv.ai_paused,
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_conversation_messages(
    conversation_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[MessageResponse]:
    """Get messages in a conversation."""
    result = await db.execute(
        select(SMSMessage)
        .where(SMSMessage.conversation_id == uuid.UUID(conversation_id))
        .order_by(SMSMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    messages = result.scalars().all()

    return [
        MessageResponse(
            id=str(msg.id),
            direction=msg.direction,
            from_number=msg.from_number,
            to_number=msg.to_number,
            body=msg.body,
            status=msg.status,
            is_read=msg.is_read,
            sent_at=msg.sent_at.isoformat() if msg.sent_at else None,
            delivered_at=msg.delivered_at.isoformat() if msg.delivered_at else None,
            created_at=msg.created_at.isoformat(),
            agent_id=str(msg.agent_id) if msg.agent_id else None,
            error_message=msg.error_message,
        )
        for msg in messages
    ]


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Query(..., description="Workspace ID"),
) -> dict[str, str]:
    """Delete an SMS conversation and all its messages."""
    workspace_uuid = uuid.UUID(workspace_id)
    conv_uuid = uuid.UUID(conversation_id)

    # Verify conversation exists and belongs to workspace
    result = await db.execute(
        select(SMSConversation).where(
            SMSConversation.id == conv_uuid,
            SMSConversation.workspace_id == workspace_uuid,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Delete all messages in the conversation first
    from sqlalchemy import delete

    await db.execute(delete(SMSMessage).where(SMSMessage.conversation_id == conv_uuid))

    # Delete the conversation
    await db.delete(conversation)
    await db.commit()

    return {"status": "deleted"}


@router.post("/conversations/{conversation_id}/read")
async def mark_conversation_read(
    conversation_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Query(..., description="Workspace ID"),
) -> dict[str, str]:
    """Mark all messages in a conversation as read."""
    workspace_uuid = uuid.UUID(workspace_id)
    conv_uuid = uuid.UUID(conversation_id)

    # Verify conversation exists and belongs to workspace
    result = await db.execute(
        select(SMSConversation).where(
            SMSConversation.id == conv_uuid,
            SMSConversation.workspace_id == workspace_uuid,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Reset unread count
    conversation.unread_count = 0

    # Mark all inbound messages as read
    messages_result = await db.execute(
        select(SMSMessage).where(
            SMSMessage.conversation_id == conv_uuid,
            SMSMessage.direction == MessageDirection.INBOUND.value,
            SMSMessage.is_read == False,  # noqa: E712
        )
    )
    messages = messages_result.scalars().all()
    for message in messages:
        message.is_read = True

    await db.commit()
    return {"status": "ok"}


# =============================================================================
# AI Text Agent Endpoints
# =============================================================================


class AssignAgentRequest(BaseModel):
    """Request to assign a text agent to a conversation."""

    agent_id: str | None = Field(None, description="Agent ID to assign (null to unassign)")


class UpdateAISettingsRequest(BaseModel):
    """Request to update AI settings for a conversation."""

    ai_enabled: bool | None = Field(None, description="Enable/disable AI responses")
    ai_paused: bool | None = Field(None, description="Pause/resume AI responses")
    pause_duration_minutes: int | None = Field(
        None, description="Pause duration in minutes (for temporary pause)"
    )


@router.post("/conversations/{conversation_id}/assign-agent")
async def assign_agent_to_conversation(
    conversation_id: str,
    request: AssignAgentRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Assign or unassign a text agent to a conversation."""
    from app.models.agent import Agent

    result = await db.execute(
        select(SMSConversation)
        .options(
            selectinload(SMSConversation.contact),
            selectinload(SMSConversation.assigned_agent),
        )
        .where(SMSConversation.id == uuid.UUID(conversation_id))
    )
    conv = result.scalar_one_or_none()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if request.agent_id:
        # Verify agent exists and supports text
        agent_result = await db.execute(
            select(Agent).where(Agent.id == uuid.UUID(request.agent_id))
        )
        agent = agent_result.scalar_one_or_none()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        if agent.channel_mode not in ("text", "both"):
            raise HTTPException(
                status_code=400,
                detail="Agent does not support text channel. Update agent's channel mode first.",
            )

        conv.assigned_agent_id = uuid.UUID(request.agent_id)
        conv.ai_enabled = True
    else:
        conv.assigned_agent_id = None

    await db.commit()
    await db.refresh(conv)

    # Reload with relationships
    result = await db.execute(
        select(SMSConversation)
        .options(
            selectinload(SMSConversation.contact),
            selectinload(SMSConversation.assigned_agent),
        )
        .where(SMSConversation.id == conv.id)
    )
    conv = result.scalar_one()

    return ConversationResponse(
        id=str(conv.id),
        contact_id=conv.contact_id,
        contact_name=(
            f"{conv.contact.first_name} {conv.contact.last_name or ''}".strip()
            if conv.contact
            else None
        ),
        from_number=conv.from_number,
        to_number=conv.to_number,
        status=conv.status,
        unread_count=conv.unread_count,
        last_message_preview=conv.last_message_preview,
        last_message_at=conv.last_message_at.isoformat() if conv.last_message_at else None,
        last_message_direction=conv.last_message_direction,
        created_at=conv.created_at.isoformat(),
        assigned_agent_id=str(conv.assigned_agent_id) if conv.assigned_agent_id else None,
        assigned_agent_name=conv.assigned_agent.name if conv.assigned_agent else None,
        ai_enabled=conv.ai_enabled,
        ai_paused=conv.ai_paused,
    )


@router.post("/conversations/{conversation_id}/ai-settings")
async def update_conversation_ai_settings(
    conversation_id: str,
    request: UpdateAISettingsRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Update AI settings for a conversation (enable/disable/pause)."""
    from datetime import timedelta

    result = await db.execute(
        select(SMSConversation)
        .options(
            selectinload(SMSConversation.contact),
            selectinload(SMSConversation.assigned_agent),
        )
        .where(SMSConversation.id == uuid.UUID(conversation_id))
    )
    conv = result.scalar_one_or_none()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if request.ai_enabled is not None:
        conv.ai_enabled = request.ai_enabled

    if request.ai_paused is not None:
        conv.ai_paused = request.ai_paused
        if request.ai_paused and request.pause_duration_minutes:
            conv.ai_paused_until = datetime.now(UTC) + timedelta(
                minutes=request.pause_duration_minutes
            )
        elif not request.ai_paused:
            conv.ai_paused_until = None

    await db.commit()
    await db.refresh(conv)

    return ConversationResponse(
        id=str(conv.id),
        contact_id=conv.contact_id,
        contact_name=(
            f"{conv.contact.first_name} {conv.contact.last_name or ''}".strip()
            if conv.contact
            else None
        ),
        from_number=conv.from_number,
        to_number=conv.to_number,
        status=conv.status,
        unread_count=conv.unread_count,
        last_message_preview=conv.last_message_preview,
        last_message_at=conv.last_message_at.isoformat() if conv.last_message_at else None,
        last_message_direction=conv.last_message_direction,
        created_at=conv.created_at.isoformat(),
        assigned_agent_id=str(conv.assigned_agent_id) if conv.assigned_agent_id else None,
        assigned_agent_name=conv.assigned_agent.name if conv.assigned_agent else None,
        ai_enabled=conv.ai_enabled,
        ai_paused=conv.ai_paused,
    )


@router.get("/text-agents", response_model=list[dict[str, str]])
async def list_text_agents(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Query(..., description="Workspace ID"),
) -> list[dict[str, str]]:
    """List agents that support text channel for assignment."""
    from app.models.agent import Agent
    from app.models.workspace import AgentWorkspace

    workspace_uuid = uuid.UUID(workspace_id)

    # Get agents that support text and are assigned to this workspace
    result = await db.execute(
        select(Agent)
        .join(AgentWorkspace, Agent.id == AgentWorkspace.agent_id)
        .where(
            AgentWorkspace.workspace_id == workspace_uuid,
            Agent.channel_mode.in_(["text", "both"]),
            Agent.is_active == True,  # noqa: E712
        )
        .order_by(Agent.name)
    )
    agents = result.scalars().all()

    return [
        {
            "id": str(agent.id),
            "name": agent.name,
            "channel_mode": agent.channel_mode,
        }
        for agent in agents
    ]


# =============================================================================
# Message Endpoints
# =============================================================================


@router.post("/messages", response_model=MessageResponse)
@limiter.limit("30/minute")
async def send_message(
    send_request: SendMessageRequest,
    request: Request,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Query(..., description="Workspace ID"),
) -> MessageResponse:
    """Send an SMS message."""
    workspace_uuid = uuid.UUID(workspace_id)
    user_uuid = user_id_to_uuid(current_user.id)

    logger.info(
        "sms_send_request",
        provider=send_request.provider,
        from_number=send_request.from_number,
        to_number=send_request.to_number,
    )

    # Route to SlickText if provider is slicktext
    if send_request.provider == "slicktext":
        slicktext_service = await get_slicktext_service(current_user.id, db, workspace_uuid)
        if not slicktext_service:
            raise HTTPException(
                status_code=400,
                detail="SlickText SMS not configured. Please add credentials in Settings.",
            )

        try:
            result = await slicktext_service.send_sms(
                to=send_request.to_number,
                body=send_request.body,
            )
        finally:
            await slicktext_service.close()

        if not result.get("success"):
            raise HTTPException(
                status_code=502,
                detail=result.get("error", "Failed to send SMS via SlickText"),
            )

        # Create SMSMessage record for SlickText
        # First, get or create conversation (like Telnyx does)
        conv_result = await db.execute(
            select(SMSConversation).where(
                SMSConversation.workspace_id == workspace_uuid,
                SMSConversation.from_number == send_request.from_number,
                SMSConversation.to_number == send_request.to_number,
            )
        )
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            # Try to find contact by phone number
            contact_result = await db.execute(
                select(Contact).where(
                    Contact.workspace_id == workspace_uuid,
                    Contact.phone_number == send_request.to_number,
                )
            )
            contact = contact_result.scalar_one_or_none()

            # Look up default text agent from the phone number configuration
            from app.models.phone_number import PhoneNumber

            phone_result = await db.execute(
                select(PhoneNumber).where(
                    PhoneNumber.workspace_id == workspace_uuid,
                    PhoneNumber.phone_number == send_request.from_number,
                )
            )
            phone_number = phone_result.scalar_one_or_none()
            default_agent_id = phone_number.default_text_agent_id if phone_number else None

            # Platform-initiated conversation - AI can auto-respond to replies
            conversation = SMSConversation(
                user_id=user_uuid,
                workspace_id=workspace_uuid,
                contact_id=contact.id if contact else None,
                from_number=send_request.from_number,
                to_number=send_request.to_number,
                initiated_by="platform",  # WE initiated this conversation
                assigned_agent_id=default_agent_id,  # Auto-assign default text agent
                ai_enabled=default_agent_id is not None,  # Enable AI if agent assigned
            )
            db.add(conversation)
            await db.flush()
            logger.info(
                "created_platform_conversation_slicktext",
                conversation_id=str(conversation.id),
                assigned_agent_id=str(default_agent_id) if default_agent_id else None,
            )

        # message_id is from inbox API, campaign_id is from campaigns API
        provider_msg_id = result.get("message_id") or result.get("campaign_id")
        message = SMSMessage(
            conversation_id=conversation.id,
            provider="slicktext",
            provider_message_id=provider_msg_id,
            direction=MessageDirection.OUTBOUND.value,
            from_number=send_request.from_number,
            to_number=send_request.to_number,
            body=send_request.body,
            status="sent",
            sent_at=datetime.now(UTC),
        )
        db.add(message)

        # Update conversation with last message info
        conversation.last_message_preview = send_request.body[:255] if send_request.body else None
        conversation.last_message_at = datetime.now(UTC)
        conversation.last_message_direction = MessageDirection.OUTBOUND.value

        await db.commit()
        await db.refresh(message)

        return MessageResponse(
            id=str(message.id),
            direction=message.direction,
            from_number=message.from_number,
            to_number=message.to_number,
            body=message.body,
            status=message.status,
            is_read=message.is_read,
            sent_at=message.sent_at.isoformat() if message.sent_at else None,
            delivered_at=message.delivered_at.isoformat() if message.delivered_at else None,
            created_at=message.created_at.isoformat(),
            agent_id=str(message.agent_id) if message.agent_id else None,
            error_message=message.error_message,
        )

    # Default: Use Telnyx
    sms_service = await get_sms_service(current_user.id, db, workspace_uuid)
    if not sms_service:
        raise HTTPException(
            status_code=400,
            detail="Telnyx SMS not configured. Please add credentials in Settings.",
        )

    message = await sms_service.send_message(
        to_number=send_request.to_number,
        from_number=send_request.from_number,
        body=send_request.body,
        db=db,
        workspace_id=workspace_uuid,
        user_id=user_uuid,
    )

    # Check if message failed to send
    if message.status == "failed":
        error_detail = message.error_message or "Failed to send SMS"
        # Check for common Telnyx errors
        if "No key found" in error_detail or "API key" in error_detail.lower():
            error_detail = "Invalid Telnyx API key. Please update your credentials in Settings."
        raise HTTPException(status_code=502, detail=error_detail)

    return MessageResponse(
        id=str(message.id),
        direction=message.direction,
        from_number=message.from_number,
        to_number=message.to_number,
        body=message.body,
        status=message.status,
        is_read=message.is_read,
        sent_at=message.sent_at.isoformat() if message.sent_at else None,
        delivered_at=message.delivered_at.isoformat() if message.delivered_at else None,
        created_at=message.created_at.isoformat(),
        agent_id=str(message.agent_id) if message.agent_id else None,
        error_message=message.error_message,
    )


# =============================================================================
# Campaign Endpoints
# =============================================================================


@router.get("/campaigns", response_model=list[CampaignResponse])
async def list_campaigns(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Query(..., description="Workspace ID"),
    status: str | None = Query(None, description="Filter by status"),
) -> list[CampaignResponse]:
    """List SMS campaigns."""
    workspace_uuid = uuid.UUID(workspace_id)

    query = (
        select(SMSCampaign)
        .options(selectinload(SMSCampaign.agent))
        .where(SMSCampaign.workspace_id == workspace_uuid)
        .order_by(SMSCampaign.created_at.desc())
    )

    if status:
        query = query.where(SMSCampaign.status == status)

    result = await db.execute(query)
    campaigns = result.scalars().all()

    return [
        CampaignResponse(
            id=str(c.id),
            name=c.name,
            description=c.description,
            status=c.status,
            from_phone_number=c.from_phone_number,
            initial_message=c.initial_message,
            ai_enabled=c.ai_enabled,
            agent_id=str(c.agent_id) if c.agent_id else None,
            agent_name=c.agent.name if c.agent else None,
            total_contacts=c.total_contacts,
            messages_sent=c.messages_sent,
            messages_delivered=c.messages_delivered,
            replies_received=c.replies_received,
            contacts_qualified=c.contacts_qualified,
            contacts_opted_out=c.contacts_opted_out,
            created_at=c.created_at.isoformat(),
            started_at=c.started_at.isoformat() if c.started_at else None,
            completed_at=c.completed_at.isoformat() if c.completed_at else None,
        )
        for c in campaigns
    ]


@router.post("/campaigns", response_model=CampaignResponse)
async def create_campaign(
    campaign_request: CreateCampaignRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Query(..., description="Workspace ID"),
) -> CampaignResponse:
    """Create an SMS campaign."""
    from app.models.agent import Agent

    workspace_uuid = uuid.UUID(workspace_id)
    user_uuid = user_id_to_uuid(current_user.id)

    # Validate agent if provided
    agent = None
    if campaign_request.agent_id:
        agent_result = await db.execute(
            select(Agent).where(Agent.id == uuid.UUID(campaign_request.agent_id))
        )
        agent = agent_result.scalar_one_or_none()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        if agent.channel_mode not in ("text", "both"):
            raise HTTPException(
                status_code=400,
                detail="Agent does not support text channel. Update agent's channel mode first.",
            )

    campaign = SMSCampaign(
        user_id=user_uuid,
        workspace_id=workspace_uuid,
        agent_id=uuid.UUID(campaign_request.agent_id) if campaign_request.agent_id else None,
        name=campaign_request.name,
        description=campaign_request.description,
        from_phone_number=campaign_request.from_phone_number,
        initial_message=campaign_request.initial_message,
        ai_enabled=campaign_request.ai_enabled,
        ai_system_prompt=campaign_request.ai_system_prompt,
        qualification_criteria=campaign_request.qualification_criteria,
        sending_hours_start=campaign_request.sending_hours_start,
        sending_hours_end=campaign_request.sending_hours_end,
        sending_days=campaign_request.sending_days,
        timezone=campaign_request.timezone,
        messages_per_minute=campaign_request.messages_per_minute,
        follow_up_enabled=campaign_request.follow_up_enabled,
        follow_up_delay_hours=campaign_request.follow_up_delay_hours,
        follow_up_message=campaign_request.follow_up_message,
        max_follow_ups=campaign_request.max_follow_ups,
    )
    db.add(campaign)
    await db.flush()

    # Add contacts to campaign
    if campaign_request.contact_ids:
        for contact_id in campaign_request.contact_ids:
            campaign_contact = SMSCampaignContact(
                campaign_id=campaign.id,
                contact_id=contact_id,
            )
            db.add(campaign_contact)

        campaign.total_contacts = len(campaign_request.contact_ids)

    await db.commit()
    await db.refresh(campaign)

    return CampaignResponse(
        id=str(campaign.id),
        name=campaign.name,
        description=campaign.description,
        status=campaign.status,
        from_phone_number=campaign.from_phone_number,
        initial_message=campaign.initial_message,
        ai_enabled=campaign.ai_enabled,
        agent_id=str(campaign.agent_id) if campaign.agent_id else None,
        agent_name=agent.name if agent else None,
        total_contacts=campaign.total_contacts,
        messages_sent=campaign.messages_sent,
        messages_delivered=campaign.messages_delivered,
        replies_received=campaign.replies_received,
        contacts_qualified=campaign.contacts_qualified,
        contacts_opted_out=campaign.contacts_opted_out,
        created_at=campaign.created_at.isoformat(),
        started_at=campaign.started_at.isoformat() if campaign.started_at else None,
        completed_at=campaign.completed_at.isoformat() if campaign.completed_at else None,
    )


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> CampaignResponse:
    """Get a campaign."""
    result = await db.execute(
        select(SMSCampaign)
        .options(selectinload(SMSCampaign.agent))
        .where(SMSCampaign.id == uuid.UUID(campaign_id))
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return CampaignResponse(
        id=str(campaign.id),
        name=campaign.name,
        description=campaign.description,
        status=campaign.status,
        from_phone_number=campaign.from_phone_number,
        initial_message=campaign.initial_message,
        ai_enabled=campaign.ai_enabled,
        agent_id=str(campaign.agent_id) if campaign.agent_id else None,
        agent_name=campaign.agent.name if campaign.agent else None,
        total_contacts=campaign.total_contacts,
        messages_sent=campaign.messages_sent,
        messages_delivered=campaign.messages_delivered,
        replies_received=campaign.replies_received,
        contacts_qualified=campaign.contacts_qualified,
        contacts_opted_out=campaign.contacts_opted_out,
        created_at=campaign.created_at.isoformat(),
        started_at=campaign.started_at.isoformat() if campaign.started_at else None,
        completed_at=campaign.completed_at.isoformat() if campaign.completed_at else None,
    )


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Query(..., description="Workspace ID"),
) -> dict[str, str]:
    """Delete an SMS campaign and all its contacts."""
    workspace_uuid = uuid.UUID(workspace_id)
    campaign_uuid = uuid.UUID(campaign_id)

    # Verify campaign exists and belongs to workspace
    result = await db.execute(
        select(SMSCampaign).where(
            SMSCampaign.id == campaign_uuid,
            SMSCampaign.workspace_id == workspace_uuid,
        )
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Prevent deletion of running campaigns
    if campaign.status == SMSCampaignStatus.RUNNING.value:
        raise HTTPException(
            status_code=400, detail="Cannot delete a running campaign. Pause it first."
        )

    # Delete all campaign contacts first
    from sqlalchemy import delete as sql_delete

    await db.execute(
        sql_delete(SMSCampaignContact).where(SMSCampaignContact.campaign_id == campaign_uuid)
    )

    # Delete the campaign
    await db.delete(campaign)
    await db.commit()

    return {"status": "deleted"}


@router.post("/campaigns/{campaign_id}/start")
async def start_campaign(
    campaign_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Start an SMS campaign."""
    result = await db.execute(select(SMSCampaign).where(SMSCampaign.id == uuid.UUID(campaign_id)))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status not in [SMSCampaignStatus.DRAFT.value, SMSCampaignStatus.PAUSED.value]:
        raise HTTPException(status_code=400, detail="Campaign cannot be started")

    campaign.status = SMSCampaignStatus.RUNNING.value
    if not campaign.started_at:
        campaign.started_at = datetime.now(UTC)

    await db.commit()

    return {"status": "started"}


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Pause an SMS campaign."""
    result = await db.execute(select(SMSCampaign).where(SMSCampaign.id == uuid.UUID(campaign_id)))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status != SMSCampaignStatus.RUNNING.value:
        raise HTTPException(status_code=400, detail="Campaign is not running")

    campaign.status = SMSCampaignStatus.PAUSED.value
    await db.commit()

    return {"status": "paused"}


@router.get("/campaigns/{campaign_id}/contacts", response_model=list[CampaignContactResponse])
async def get_campaign_contacts(
    campaign_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[CampaignContactResponse]:
    """Get contacts in a campaign."""
    query = (
        select(SMSCampaignContact)
        .options(selectinload(SMSCampaignContact.contact))
        .where(SMSCampaignContact.campaign_id == uuid.UUID(campaign_id))
        .offset(offset)
        .limit(limit)
    )

    if status:
        query = query.where(SMSCampaignContact.status == status)

    result = await db.execute(query)
    contacts = result.scalars().all()

    return [
        CampaignContactResponse(
            id=str(cc.id),
            contact_id=cc.contact_id,
            contact_name=(
                f"{cc.contact.first_name} {cc.contact.last_name or ''}".strip()
                if cc.contact
                else None
            ),
            contact_phone=cc.contact.phone_number if cc.contact else "",
            status=cc.status,
            messages_sent=cc.messages_sent,
            messages_received=cc.messages_received,
            is_qualified=cc.is_qualified,
            opted_out=cc.opted_out,
            first_sent_at=cc.first_sent_at.isoformat() if cc.first_sent_at else None,
            last_reply_at=cc.last_reply_at.isoformat() if cc.last_reply_at else None,
        )
        for cc in contacts
    ]


@router.post("/campaigns/{campaign_id}/contacts")
async def add_contacts_to_campaign(
    campaign_id: str,
    contact_ids: list[int],
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Add contacts to a campaign."""
    result = await db.execute(select(SMSCampaign).where(SMSCampaign.id == uuid.UUID(campaign_id)))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status not in [SMSCampaignStatus.DRAFT.value, SMSCampaignStatus.PAUSED.value]:
        raise HTTPException(status_code=400, detail="Cannot add contacts to active campaign")

    # Get existing contact IDs
    existing_result = await db.execute(
        select(SMSCampaignContact.contact_id).where(
            SMSCampaignContact.campaign_id == uuid.UUID(campaign_id)
        )
    )
    existing_ids = {row[0] for row in existing_result.fetchall()}

    added = 0
    for contact_id in contact_ids:
        if contact_id not in existing_ids:
            campaign_contact = SMSCampaignContact(
                campaign_id=campaign.id,
                contact_id=contact_id,
            )
            db.add(campaign_contact)
            added += 1

    campaign.total_contacts += added
    await db.commit()

    return {"added": added}


# =============================================================================
# Telnyx Webhook Helpers
# =============================================================================


async def _handle_inbound_message(
    db: AsyncSession,
    payload: dict,  # type: ignore[type-arg]
) -> str | None:
    """Handle inbound SMS message from Telnyx webhook."""
    from app.models.agent import Agent
    from app.models.phone_number import PhoneNumber
    from app.services.text_agent_service import schedule_ai_response

    from_number = payload.get("from", {}).get("phone_number", "")
    to_number = payload.get("to", [{}])[0].get("phone_number", "")
    message_text = payload.get("text", "")
    message_id = payload.get("id", "")

    phone_result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.phone_number == to_number)
    )
    phone = phone_result.scalar_one_or_none()

    if not phone:
        return None

    # Find or create conversation
    conv_result = await db.execute(
        select(SMSConversation).where(
            SMSConversation.workspace_id == phone.workspace_id,
            SMSConversation.from_number == to_number,
            SMSConversation.to_number == from_number,
        )
    )
    conversation = conv_result.scalar_one_or_none()
    is_new_conversation = conversation is None

    if not conversation:
        contact_result = await db.execute(
            select(Contact).where(
                Contact.workspace_id == phone.workspace_id,
                Contact.phone_number == from_number,
            )
        )
        contact = contact_result.scalar_one_or_none()

        # NEW CONVERSATION from external party - do NOT enable AI auto-response
        # AI should only auto-respond to conversations WE initiated (platform-initiated)
        conversation = SMSConversation(
            user_id=phone.user_id,
            workspace_id=phone.workspace_id,
            contact_id=contact.id if contact else None,
            from_number=to_number,
            to_number=from_number,
            # Mark as externally initiated - AI will NOT auto-respond
            initiated_by="external",
            # Do NOT auto-assign agent for external conversations
            assigned_agent_id=None,
            ai_enabled=False,  # Disable AI for external conversations
        )
        db.add(conversation)
        await db.flush()
        logger.info(
            "created_external_conversation_telnyx",
            conversation_id=str(conversation.id),
            ai_enabled=False,
        )
    # EXISTING conversation - auto-assign agent if it's platform-initiated
    # but doesn't have an agent yet
    elif conversation.initiated_by == "platform" and not conversation.assigned_agent_id:
        # First, check if conversation is part of a campaign and use campaign's agent
        campaign_agent_id = None
        campaign_contact_result = await db.execute(
            select(SMSCampaignContact)
            .options(selectinload(SMSCampaignContact.campaign))
            .where(SMSCampaignContact.conversation_id == conversation.id)
        )
        campaign_contact = campaign_contact_result.scalar_one_or_none()

        if campaign_contact and campaign_contact.campaign and campaign_contact.campaign.agent_id:
            campaign_agent_id = campaign_contact.campaign.agent_id
            logger.info(
                "found_campaign_agent_for_conversation",
                conversation_id=str(conversation.id),
                campaign_id=str(campaign_contact.campaign_id),
                agent_id=str(campaign_agent_id),
            )

        # Use campaign agent first, then fall back to phone default agent
        agent_to_assign = campaign_agent_id or phone.default_text_agent_id

        if agent_to_assign:
            conversation.assigned_agent_id = agent_to_assign
            conversation.ai_enabled = True
            logger.info(
                "auto_assigned_agent_to_existing_conversation",
                conversation_id=str(conversation.id),
                agent_id=str(agent_to_assign),
                source="campaign" if campaign_agent_id else "phone_default",
            )

    # Create message
    message = SMSMessage(
        conversation_id=conversation.id,
        provider="telnyx",
        provider_message_id=message_id,
        direction=MessageDirection.INBOUND.value,
        from_number=from_number,
        to_number=to_number,
        body=message_text,
        status="received",
    )
    db.add(message)

    # Update conversation
    preview_length = 255
    conversation.last_message_preview = (
        message_text[:preview_length] if len(message_text) > preview_length else message_text
    )
    conversation.last_message_at = datetime.now(UTC)
    conversation.last_message_direction = MessageDirection.INBOUND.value
    conversation.unread_count += 1

    await db.commit()

    # Schedule AI response if agent is assigned and workspace exists
    if (
        conversation.assigned_agent_id
        and conversation.ai_enabled
        and not conversation.ai_paused
        and phone.workspace_id  # Must have workspace for AI response
    ):
        # Get agent to determine delay
        agent_result = await db.execute(
            select(Agent).where(Agent.id == conversation.assigned_agent_id)
        )
        agent = agent_result.scalar_one_or_none()
        delay_ms = agent.text_response_delay_ms if agent else 3000

        # Schedule response with debounce
        await schedule_ai_response(
            conversation_id=conversation.id,
            workspace_id=phone.workspace_id,
            delay_ms=delay_ms,
        )
        logger.info(
            "scheduled_ai_response",
            conversation_id=str(conversation.id),
            agent_id=str(conversation.assigned_agent_id),
            delay_ms=delay_ms,
            is_new=is_new_conversation,
        )

    return str(conversation.id)


async def _handle_delivery_status(
    db: AsyncSession,
    payload: dict,  # type: ignore[type-arg]
) -> None:
    """Handle delivery status update from Telnyx webhook."""
    message_id = payload.get("id", "")
    to_info = payload.get("to", [{}])[0] if payload.get("to") else {}
    status = to_info.get("status", "")
    errors = payload.get("errors", [])

    result = await db.execute(
        select(SMSMessage).where(SMSMessage.provider_message_id == message_id)
    )
    message = result.scalar_one_or_none()

    if not message:
        return

    status_map = {
        "queued": "queued",
        "sending": "sending",
        "sent": "sent",
        "delivered": "delivered",
        "delivery_failed": "failed",
        "sending_failed": "failed",
    }
    message.status = status_map.get(status, status)

    if status == "delivered":
        message.delivered_at = datetime.now(UTC)

    if errors:
        error = errors[0] if errors else {}
        message.error_code = error.get("code")
        message.error_message = error.get("detail")

    await db.commit()


# =============================================================================
# Telnyx Webhook Endpoints
# =============================================================================


@webhook_router.post("/sms")
async def telnyx_sms_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle Telnyx SMS webhooks (inbound messages and delivery receipts)."""
    await verify_telnyx_webhook(request)

    body = await request.json()
    data = body.get("data", {})
    event_type = data.get("event_type", "")
    payload = data.get("payload", {})

    log = logger.bind(webhook="telnyx_sms", event_type=event_type)
    log.info("telnyx_sms_webhook_received")

    if event_type == "message.received":
        conv_id = await _handle_inbound_message(db, payload)
        if conv_id:
            log.info("inbound_message_saved", conversation_id=conv_id)
        else:
            log.warning("phone_number_not_found")

    elif event_type in ["message.sent", "message.delivered", "message.finalized"]:
        message_id = payload.get("id", "")
        log.info("delivery_status", message_id=message_id)
        await _handle_delivery_status(db, payload)

    return {"status": "received"}


# =============================================================================
# SlickText Webhook Helpers
# =============================================================================


async def _handle_slicktext_inbound_message(  # noqa: PLR0912, PLR0915
    db: AsyncSession,
    payload: dict,  # type: ignore[type-arg]
) -> str | None:
    """Handle inbound SMS message from SlickText webhook.

    SlickText Inbox Chat Message Received webhook payload structure:
    {
        "Event": "ChatMessageRecieved",  # Note: SlickText has typo in API
        "Timestamp": "2018-05-31 12:57:40",
        "attemptNumber": 1,
        "ChatThread": {
            "ChatThreadId": "string",
            "WithNumber": "+15554449998",  # Our phone number (receiver)
            "DateCreated": "string"
        },
        "ChatMessage": {
            "ChatMessageId": "string",
            "FromNumber": "+15554441234",  # Sender's phone number
            "Body": "message text",
            "MediaUrl": "string",
            "MessageRead": false,
            "Received": "string"
        },
        "Textwords": [...]
    }
    """
    from app.models.agent import Agent
    from app.models.phone_number import PhoneNumber
    from app.models.user_settings import UserSettings
    from app.services.text_agent_service import schedule_ai_response

    # SlickText "Inbox Chat Message Received" webhook payload structure
    chat_thread = payload.get("ChatThread", {})
    chat_message = payload.get("ChatMessage", {})

    # Extract fields from SlickText payload
    from_number = chat_message.get("FromNumber", "")
    to_number = chat_thread.get("WithNumber", "")
    message_text = chat_message.get("Body", "")
    message_id = chat_message.get("ChatMessageId", "")

    # Normalize phone numbers to E.164
    if from_number and not from_number.startswith("+"):
        from_number = f"+{from_number}"
    if to_number and not to_number.startswith("+"):
        to_number = f"+{to_number}"

    log = logger.bind(
        from_number=from_number,
        to_number=to_number,
        message_id=message_id,
    )
    log.info("processing_slicktext_inbound")

    # First, try to find phone number in PhoneNumber table (for consistency with Telnyx)
    phone_result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.phone_number == to_number)
    )
    phone = phone_result.scalar_one_or_none()

    # If not found in PhoneNumber table, look up in UserSettings (SlickText-specific)
    user_settings = None
    workspace_id = None
    user_id = None
    if phone:
        # Found in PhoneNumber table
        workspace_id = phone.workspace_id
        user_id = phone.user_id
        log.info("found_phone_in_phone_number_table", workspace_id=str(workspace_id))
    else:
        # Look up SlickText phone number in UserSettings
        settings_result = await db.execute(
            select(UserSettings).where(UserSettings.slicktext_phone_number == to_number)
        )
        user_settings = settings_result.scalar_one_or_none()

        if not user_settings:
            # Try without + prefix
            to_number_no_plus = to_number.lstrip("+")
            settings_result = await db.execute(
                select(UserSettings).where(
                    UserSettings.slicktext_phone_number.in_(
                        [to_number, to_number_no_plus, f"+{to_number_no_plus}"]
                    )
                )
            )
            user_settings = settings_result.scalar_one_or_none()

        if user_settings:
            workspace_id = user_settings.workspace_id
            user_id = user_settings.user_id
            log.info("found_phone_in_user_settings", workspace_id=str(workspace_id))
        else:
            log.warning("phone_number_not_found_anywhere", to_number=to_number)
            return None

    if not workspace_id or not user_id:
        log.warning("missing_workspace_or_user")
        return None

    # Find or create conversation
    conv_result = await db.execute(
        select(SMSConversation).where(
            SMSConversation.workspace_id == workspace_id,
            SMSConversation.from_number == to_number,
            SMSConversation.to_number == from_number,
        )
    )
    conversation = conv_result.scalar_one_or_none()
    is_new_conversation = conversation is None

    if not conversation:
        contact_result = await db.execute(
            select(Contact).where(
                Contact.workspace_id == workspace_id,
                Contact.phone_number == from_number,
            )
        )
        contact = contact_result.scalar_one_or_none()

        # NEW CONVERSATION from external party - do NOT enable AI auto-response
        # AI should only auto-respond to conversations WE initiated (platform-initiated)
        conversation = SMSConversation(
            user_id=user_id,
            workspace_id=workspace_id,
            contact_id=contact.id if contact else None,
            from_number=to_number,
            to_number=from_number,
            # Mark as externally initiated - AI will NOT auto-respond
            initiated_by="external",
            # Do NOT auto-assign agent for external conversations
            assigned_agent_id=None,
            ai_enabled=False,  # Disable AI for external conversations
        )
        db.add(conversation)
        await db.flush()
        log.info(
            "created_external_conversation",
            conversation_id=str(conversation.id),
            ai_enabled=False,
        )
    # EXISTING conversation - auto-assign agent if it's platform-initiated
    # but doesn't have an agent yet
    elif conversation.initiated_by == "platform" and not conversation.assigned_agent_id:
        # First, check if conversation is part of a campaign and use campaign's agent
        campaign_agent_id = None
        campaign_contact_result = await db.execute(
            select(SMSCampaignContact)
            .options(selectinload(SMSCampaignContact.campaign))
            .where(SMSCampaignContact.conversation_id == conversation.id)
        )
        campaign_contact = campaign_contact_result.scalar_one_or_none()

        if campaign_contact and campaign_contact.campaign and campaign_contact.campaign.agent_id:
            campaign_agent_id = campaign_contact.campaign.agent_id
            log.info(
                "found_campaign_agent_for_conversation",
                conversation_id=str(conversation.id),
                campaign_id=str(campaign_contact.campaign_id),
                agent_id=str(campaign_agent_id),
            )

        # Get default agent from phone number or user settings (as fallback)
        default_agent_id = None
        if phone and phone.default_text_agent_id:
            default_agent_id = phone.default_text_agent_id
        elif user_settings and user_settings.slicktext_default_text_agent_id:
            default_agent_id = user_settings.slicktext_default_text_agent_id

        # Use campaign agent first, then fall back to phone/settings default agent
        agent_to_assign = campaign_agent_id or default_agent_id

        if agent_to_assign:
            conversation.assigned_agent_id = agent_to_assign
            conversation.ai_enabled = True
            log.info(
                "auto_assigned_agent_to_existing_conversation",
                conversation_id=str(conversation.id),
                agent_id=str(agent_to_assign),
                source="campaign" if campaign_agent_id else "phone_default",
            )

    # Create message record
    message = SMSMessage(
        conversation_id=conversation.id,
        provider="slicktext",
        provider_message_id=str(message_id),
        direction=MessageDirection.INBOUND.value,
        from_number=from_number,
        to_number=to_number,
        body=message_text,
        status="received",
    )
    db.add(message)

    # Update conversation metadata
    preview_length = 255
    conversation.last_message_preview = (
        message_text[:preview_length] if len(message_text) > preview_length else message_text
    )
    conversation.last_message_at = datetime.now(UTC)
    conversation.last_message_direction = MessageDirection.INBOUND.value
    conversation.unread_count += 1

    await db.commit()

    # Schedule AI response if agent is assigned and workspace exists
    if (
        conversation.assigned_agent_id
        and conversation.ai_enabled
        and not conversation.ai_paused
        and workspace_id  # Must have workspace for AI response
    ):
        # Get agent to determine delay
        agent_result = await db.execute(
            select(Agent).where(Agent.id == conversation.assigned_agent_id)
        )
        agent = agent_result.scalar_one_or_none()
        delay_ms = agent.text_response_delay_ms if agent else 3000

        # Schedule response with debounce
        await schedule_ai_response(
            conversation_id=conversation.id,
            workspace_id=workspace_id,
            delay_ms=delay_ms,
            provider="slicktext",  # Pass provider for response routing
        )
        log.info(
            "scheduled_ai_response_slicktext",
            agent_id=str(conversation.assigned_agent_id),
            delay_ms=delay_ms,
            is_new=is_new_conversation,
        )

    return str(conversation.id)


# =============================================================================
# SlickText Webhook Endpoints
# =============================================================================


@slicktext_webhook_router.post("/sms")
async def slicktext_sms_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle SlickText SMS webhooks (inbound messages).

    SlickText sends webhooks for:
    - ChatMessageRecieved: Inbound SMS received (note: SlickText has typo in API)
    - MessageSent: Outbound message sent
    - campaign.sent: Campaign message sent
    - campaign.failed: Campaign message failed

    SlickText webhook payload uses "Event" field (not "name").
    """
    # Note: In production, you'd want to look up the webhook secret
    # from user settings based on the phone number or other identifier
    # For now, we'll verify in debug mode or skip if no secret
    await verify_slicktext_webhook(request, webhook_secret=None)

    body = await request.json()
    # SlickText uses "Event" field, not "name"
    event_name = body.get("Event", "") or body.get("name", "")
    payload = body

    log = logger.bind(webhook="slicktext_sms", event_name=event_name)
    log.info("slicktext_sms_webhook_received", payload_keys=list(body.keys()))

    # Handle inbound messages - SlickText uses "ChatMessageRecieved" (their typo)
    if event_name in ("ChatMessageRecieved", "ChatMessageReceived", "inbox.message.received"):
        conv_id = await _handle_slicktext_inbound_message(db, payload)
        if conv_id:
            log.info("inbound_message_saved", conversation_id=conv_id)
        else:
            log.warning("phone_number_not_found")

    return {"status": "received"}
