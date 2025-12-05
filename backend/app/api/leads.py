"""Lead webhook API for receiving leads from Facebook and website forms.

This module provides webhook endpoints to:
- Receive leads from Facebook Lead Ads via webhook
- Receive leads from website forms
- Automatically create contacts in CRM
- Trigger instant outbound calls to leads via the appointment setter agent
"""

import hashlib
import hmac
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.agent import Agent
from app.models.contact import Contact
from app.models.workspace import AgentWorkspace

router = APIRouter(prefix="/webhooks/leads", tags=["leads"])

logger = structlog.get_logger()


# =============================================================================
# Pydantic Models
# =============================================================================


class WebsiteLeadRequest(BaseModel):
    """Request model for website lead form submissions."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    phone_number: str = Field(..., min_length=10, max_length=20)
    company_name: str | None = Field(None, max_length=255)
    notes: str | None = Field(None, max_length=1000)
    source: str = Field(default="website", max_length=50)
    # Agent to use for the callback (required)
    agent_id: str = Field(..., description="Agent ID to use for instant callback")


class FacebookLeadData(BaseModel):
    """Facebook lead data from webhook payload."""

    leadgen_id: str
    page_id: str
    form_id: str
    field_data: list[dict[str, Any]]


class LeadResponse(BaseModel):
    """Response after processing a lead."""

    success: bool
    message: str
    contact_id: int | None = None
    call_initiated: bool = False
    call_id: str | None = None


# =============================================================================
# Helper Functions
# =============================================================================


def verify_facebook_signature(request: Request, body: bytes) -> bool:
    """Verify Facebook webhook signature.

    Facebook sends X-Hub-Signature-256 header with HMAC-SHA256 signature.
    """
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature or not settings.FACEBOOK_APP_SECRET:
        return False

    expected = (
        "sha256="
        + hmac.new(
            settings.FACEBOOK_APP_SECRET.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
    )

    return hmac.compare_digest(signature, expected)


def parse_facebook_field_data(field_data: list[dict[str, Any]]) -> dict[str, str]:
    """Parse Facebook lead form field data into a dict."""
    result = {}
    for field in field_data:
        name = field.get("name", "").lower()
        values = field.get("values", [])
        if values:
            result[name] = values[0]
    return result


async def get_agent_with_workspace(
    agent_id: str, db: AsyncSession
) -> tuple[Agent | None, uuid.UUID | None]:
    """Get agent and its workspace ID."""
    try:
        agent_uuid = uuid.UUID(agent_id)
    except ValueError:
        return None, None

    result = await db.execute(select(Agent).where(Agent.id == agent_uuid))
    agent = result.scalar_one_or_none()

    if not agent:
        return None, None

    # Get workspace ID
    ws_result = await db.execute(
        select(AgentWorkspace.workspace_id).where(AgentWorkspace.agent_id == agent_uuid).limit(1)
    )
    workspace_id = ws_result.scalar_one_or_none()

    return agent, workspace_id


async def create_or_update_contact(
    db: AsyncSession,
    user_id: int,
    workspace_id: uuid.UUID | None,
    first_name: str,
    last_name: str | None,
    email: str | None,
    phone_number: str,
    company_name: str | None = None,
    notes: str | None = None,
    source: str = "website",
) -> Contact:
    """Create a new contact or update existing one by phone number."""
    # Normalize phone number (remove spaces, dashes)
    normalized_phone = "".join(c for c in phone_number if c.isdigit() or c == "+")

    # Check for existing contact
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.phone_number == normalized_phone,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing contact
        existing.first_name = first_name
        if last_name:
            existing.last_name = last_name
        if email:
            existing.email = email
        if company_name:
            existing.company_name = company_name
        if notes:
            existing.notes = (existing.notes or "") + f"\n[{source}] {notes}"
        existing.status = "new"  # Reset status for re-engagement
        await db.commit()
        await db.refresh(existing)
        return existing

    # Create new contact
    contact = Contact(
        user_id=user_id,
        workspace_id=workspace_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone_number=normalized_phone,
        company_name=company_name,
        status="new",
        tags=source,
        notes=notes,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


async def initiate_lead_call(
    db: AsyncSession,
    agent: Agent,
    workspace_id: uuid.UUID | None,
    contact: Contact,
) -> tuple[bool, str | None]:
    """Initiate an outbound call to a lead.

    Returns (success, call_id).
    """
    from app.api.telephony import get_telnyx_service
    from app.core.auth import get_user_id_from_uuid
    from app.models.call_record import CallDirection, CallRecord, CallStatus

    log = logger.bind(
        agent_id=str(agent.id),
        contact_id=contact.id,
        phone_number=contact.phone_number,
    )

    # Check if agent has a phone number assigned
    if not agent.phone_number_id:
        log.warning("agent_has_no_phone_number")
        return False, None

    # agent.user_id is already the integer user ID
    user_id_int = agent.user_id

    # Get Telnyx service
    telnyx_service = await get_telnyx_service(user_id_int, db, workspace_id=workspace_id)
    if not telnyx_service:
        log.error("telnyx_service_not_available")
        return False, None

    # Get the phone number for the agent
    from app.models.phone_number import PhoneNumber

    phone_result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.id == uuid.UUID(agent.phone_number_id))
    )
    phone_number_record = phone_result.scalar_one_or_none()

    if not phone_number_record:
        log.error("phone_number_not_found", phone_number_id=agent.phone_number_id)
        return False, None

    from_number = phone_number_record.phone_number

    # Build webhook URL for call answer
    if settings.PUBLIC_WEBHOOK_URL:
        base_url = settings.PUBLIC_WEBHOOK_URL.rstrip("/")
    else:
        log.warning("PUBLIC_WEBHOOK_URL_not_set_using_default")
        base_url = f"https://{settings.HOST}:{settings.PORT}"

    webhook_url = f"{base_url}/webhooks/telnyx/answer"

    try:
        # Initiate the call
        call_info = await telnyx_service.initiate_call(
            to_number=contact.phone_number,
            from_number=from_number,
            webhook_url=webhook_url,
            agent_id=str(agent.id),
        )

        # Create call record
        call_record = CallRecord(
            user_id=agent.user_id,
            workspace_id=workspace_id,
            provider="telnyx",
            provider_call_id=call_info.call_id,
            agent_id=agent.id,
            contact_id=contact.id,
            direction=CallDirection.OUTBOUND.value,
            status=CallStatus.INITIATED.value,
            from_number=from_number,
            to_number=contact.phone_number,
        )
        db.add(call_record)
        await db.commit()

        log.info(
            "lead_call_initiated",
            call_id=call_info.call_id,
            from_number=from_number,
            to_number=contact.phone_number,
        )
        return True, call_info.call_id

    except Exception as e:
        log.exception("failed_to_initiate_lead_call", error=str(e))
        return False, None


# =============================================================================
# Webhook Endpoints
# =============================================================================


@router.post("/website", response_model=LeadResponse)
async def website_lead_webhook(
    lead: WebsiteLeadRequest,
    db: AsyncSession = Depends(get_db),
    api_key: str = Query(..., description="API key for authentication"),
) -> LeadResponse:
    """Receive a lead from a website form and initiate instant callback.

    This endpoint:
    1. Validates the API key
    2. Creates/updates contact in CRM
    3. Initiates an outbound call using the specified agent

    Query Parameters:
        api_key: Your Voice Noob API key for authentication

    Example webhook URL for your website form:
        POST https://your-domain.com/webhooks/leads/website?api_key=YOUR_API_KEY

    Example payload:
        {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone_number": "+15551234567",
            "company_name": "Acme Inc",
            "notes": "Interested in voice agents",
            "source": "website",
            "agent_id": "uuid-of-your-appointment-setter-agent"
        }
    """
    log = logger.bind(
        webhook="website_lead",
        phone=lead.phone_number,
        agent_id=lead.agent_id,
    )
    log.info("website_lead_received")

    # Validate API key (simple check - in production use proper API key management)
    # For now, we check against LEAD_WEBHOOK_API_KEY environment variable
    if not settings.LEAD_WEBHOOK_API_KEY or api_key != settings.LEAD_WEBHOOK_API_KEY:
        log.warning("invalid_api_key")
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Get agent and workspace
    agent, workspace_id = await get_agent_with_workspace(lead.agent_id, db)
    if not agent:
        log.error("agent_not_found")
        raise HTTPException(status_code=404, detail="Agent not found")

    if not agent.is_active:
        log.error("agent_not_active")
        raise HTTPException(status_code=400, detail="Agent is not active")

    # agent.user_id is already the integer user ID
    user_id_int = agent.user_id

    # Create or update contact
    contact = await create_or_update_contact(
        db=db,
        user_id=user_id_int,
        workspace_id=workspace_id,
        first_name=lead.first_name,
        last_name=lead.last_name,
        email=lead.email,
        phone_number=lead.phone_number,
        company_name=lead.company_name,
        notes=lead.notes,
        source=lead.source,
    )
    log.info("contact_created_or_updated", contact_id=contact.id)

    # Initiate callback
    call_success, call_id = await initiate_lead_call(db, agent, workspace_id, contact)

    if call_success:
        # Update contact status
        contact.status = "contacted"
        await db.commit()

        return LeadResponse(
            success=True,
            message="Lead received and call initiated",
            contact_id=contact.id,
            call_initiated=True,
            call_id=call_id,
        )
    return LeadResponse(
        success=True,
        message="Lead received but call could not be initiated. Contact saved for manual follow-up.",
        contact_id=contact.id,
        call_initiated=False,
    )


@router.get("/facebook")
async def facebook_webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
) -> str | dict[str, str]:
    """Facebook webhook verification endpoint.

    Facebook sends a GET request with a verify_token to confirm webhook ownership.
    """
    logger.info(
        "facebook_webhook_verification",
        mode=hub_mode,
        has_token=bool(hub_verify_token),
    )

    if hub_mode == "subscribe":
        if hub_verify_token == settings.FACEBOOK_VERIFY_TOKEN:
            logger.info("facebook_webhook_verified")
            return hub_challenge or ""
        logger.warning("facebook_webhook_invalid_token")
        raise HTTPException(status_code=403, detail="Invalid verify token")

    return {"status": "ok"}


@router.post("/facebook", response_model=LeadResponse)
async def facebook_lead_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Query(..., description="Agent ID for instant callback"),
) -> LeadResponse:
    """Receive a lead from Facebook Lead Ads webhook.

    Facebook Lead Ads sends lead data via webhook when someone fills out a lead form.
    This endpoint:
    1. Verifies the Facebook signature
    2. Parses lead data
    3. Creates/updates contact in CRM
    4. Initiates an outbound call

    Setup in Facebook:
    1. Go to your Facebook App > Webhooks
    2. Subscribe to "leadgen" events
    3. Set webhook URL: https://your-domain.com/webhooks/leads/facebook?agent_id=YOUR_AGENT_ID

    Required environment variables:
        FACEBOOK_APP_SECRET: Your Facebook app secret for signature verification
        FACEBOOK_VERIFY_TOKEN: Token you set in Facebook webhook config
    """
    body = await request.body()
    log = logger.bind(webhook="facebook_lead", body_length=len(body))

    # Verify Facebook signature (skip if no secret configured - for testing)
    if settings.FACEBOOK_APP_SECRET and not verify_facebook_signature(request, body):
        log.warning("invalid_facebook_signature")
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        log.exception("invalid_json_payload")
        raise HTTPException(status_code=400, detail="Invalid JSON") from None

    log.info("facebook_lead_payload_received", payload_keys=list(payload.keys()))

    # Facebook sends lead data in a specific format
    # See: https://developers.facebook.com/docs/marketing-api/guides/lead-ads/
    entry = payload.get("entry", [{}])[0]
    changes = entry.get("changes", [{}])[0]
    value = changes.get("value", {})

    # Extract lead data
    field_data = value.get("field_data", [])
    if not field_data:
        log.warning("no_field_data_in_payload")
        return LeadResponse(
            success=False,
            message="No lead data found in webhook payload",
        )

    # Parse field data
    fields = parse_facebook_field_data(field_data)
    log.info("parsed_facebook_fields", fields=list(fields.keys()))

    # Extract common field names (Facebook forms can have custom names)
    first_name = fields.get("first_name") or fields.get("full_name", "").split()[0] or "Unknown"
    last_name = fields.get("last_name")
    if not last_name and " " in fields.get("full_name", ""):
        last_name = " ".join(fields.get("full_name", "").split()[1:])

    email = fields.get("email")
    phone = fields.get("phone_number") or fields.get("phone")
    company = fields.get("company_name") or fields.get("company")

    if not phone:
        log.warning("no_phone_in_facebook_lead")
        return LeadResponse(
            success=False,
            message="No phone number found in lead data",
        )

    # Get agent and workspace
    agent, workspace_id = await get_agent_with_workspace(agent_id, db)
    if not agent:
        log.error("agent_not_found")
        raise HTTPException(status_code=404, detail="Agent not found")

    if not agent.is_active:
        log.error("agent_not_active")
        raise HTTPException(status_code=400, detail="Agent is not active")

    # agent.user_id is already the integer user ID
    user_id_int = agent.user_id

    # Create or update contact
    contact = await create_or_update_contact(
        db=db,
        user_id=user_id_int,
        workspace_id=workspace_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone_number=phone,
        company_name=company,
        notes=f"Facebook Lead ID: {value.get('leadgen_id', 'unknown')}",
        source="facebook",
    )
    log.info("contact_created_from_facebook", contact_id=contact.id)

    # Initiate callback
    call_success, call_id = await initiate_lead_call(db, agent, workspace_id, contact)

    if call_success:
        contact.status = "contacted"
        await db.commit()

        return LeadResponse(
            success=True,
            message="Facebook lead received and call initiated",
            contact_id=contact.id,
            call_initiated=True,
            call_id=call_id,
        )
    return LeadResponse(
        success=True,
        message="Facebook lead received but call could not be initiated",
        contact_id=contact.id,
        call_initiated=False,
    )


@router.post("/zapier", response_model=LeadResponse)
async def zapier_lead_webhook(
    lead: WebsiteLeadRequest,
    db: AsyncSession = Depends(get_db),
    api_key: str = Query(..., description="API key for authentication"),
) -> LeadResponse:
    """Receive a lead from Zapier or any other automation tool.

    This is a generic webhook that can be used with:
    - Zapier
    - Make (Integromat)
    - n8n
    - Any custom automation

    Uses the same format as the website webhook.

    Example Zapier setup:
    1. Create a Zap with your trigger (e.g., new row in Google Sheets)
    2. Add a "Webhooks by Zapier" action
    3. Set URL: https://your-domain.com/webhooks/leads/zapier?api_key=YOUR_KEY&agent_id=YOUR_AGENT
    4. Map fields to the required format
    """
    log = logger.bind(
        webhook="zapier_lead",
        phone=lead.phone_number,
        agent_id=lead.agent_id,
        source=lead.source,
    )
    log.info("zapier_lead_received")

    # Reuse website webhook logic with source override
    if lead.source == "website":
        lead.source = "zapier"

    # Call the website webhook handler
    return await website_lead_webhook(lead, db, api_key)
