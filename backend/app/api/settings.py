"""API endpoints for user settings."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, user_id_to_uuid
from app.db.session import get_db
from app.models.user_settings import UserSettings
from app.models.workspace import Workspace
from app.services.hume_tts import HUME_VOICES, HumeOctaveTTS

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
logger = structlog.get_logger()


class UpdateSettingsRequest(BaseModel):
    """Request to update user settings."""

    openai_api_key: str | None = None
    deepgram_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    # Hume AI (EVI voice-to-voice and Octave TTS)
    hume_api_key: str | None = None
    hume_secret_key: str | None = None
    # Telephony
    telnyx_api_key: str | None = None
    telnyx_public_key: str | None = None
    telnyx_messaging_profile_id: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    # SlickText V2 API (Bearer token)
    slicktext_api_key: str | None = None
    # SlickText V1 API (Basic auth)
    slicktext_public_key: str | None = None
    slicktext_private_key: str | None = None
    slicktext_textword_id: str | None = None
    slicktext_webhook_secret: str | None = None
    slicktext_phone_number: str | None = None
    slicktext_default_text_agent_id: str | None = None


class SettingsResponse(BaseModel):
    """Settings response (API keys masked for security)."""

    openai_api_key_set: bool
    deepgram_api_key_set: bool
    elevenlabs_api_key_set: bool
    # Hume AI
    hume_api_key_set: bool = False
    hume_secret_key_set: bool = False
    # Telephony
    telnyx_api_key_set: bool
    telnyx_messaging_profile_id_set: bool
    twilio_account_sid_set: bool
    # SlickText V2 API
    slicktext_api_key_set: bool
    # SlickText V1 API
    slicktext_public_key_set: bool = False
    slicktext_private_key_set: bool = False
    slicktext_textword_id: str | None = None
    slicktext_phone_number: str | None = None
    slicktext_default_text_agent_id: str | None = None
    workspace_id: str | None = None


async def _validate_workspace_ownership(
    workspace_id_str: str,
    user_id: int,
    db: AsyncSession,
) -> uuid.UUID:
    """Validate workspace_id and verify ownership."""
    try:
        workspace_uuid = uuid.UUID(workspace_id_str)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid workspace_id format") from e

    ws_result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_uuid,
            Workspace.user_id == user_id,
        )
    )
    if not ws_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Workspace not found")

    return workspace_uuid


@router.get("", response_model=SettingsResponse)
async def get_settings(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str | None = None,
) -> SettingsResponse:
    """Get user settings (API keys masked).

    Args:
        current_user: Authenticated user
        db: Database session
        workspace_id: Optional workspace ID for workspace-specific settings

    Returns:
        Settings with masked API keys
    """
    user_uuid = user_id_to_uuid(current_user.id)

    # Build query conditions
    conditions = [UserSettings.user_id == user_uuid]

    if workspace_id:
        workspace_uuid = await _validate_workspace_ownership(workspace_id, current_user.id, db)
        conditions.append(UserSettings.workspace_id == workspace_uuid)
    else:
        conditions.append(UserSettings.workspace_id.is_(None))

    result = await db.execute(select(UserSettings).where(and_(*conditions)))
    settings = result.scalar_one_or_none()

    if not settings:
        return SettingsResponse(
            openai_api_key_set=False,
            deepgram_api_key_set=False,
            elevenlabs_api_key_set=False,
            hume_api_key_set=False,
            hume_secret_key_set=False,
            telnyx_api_key_set=False,
            telnyx_messaging_profile_id_set=False,
            twilio_account_sid_set=False,
            slicktext_api_key_set=False,
            slicktext_public_key_set=False,
            slicktext_private_key_set=False,
            slicktext_textword_id=None,
            slicktext_phone_number=None,
            slicktext_default_text_agent_id=None,
            workspace_id=workspace_id,
        )

    return SettingsResponse(
        openai_api_key_set=bool(settings.openai_api_key),
        deepgram_api_key_set=bool(settings.deepgram_api_key),
        elevenlabs_api_key_set=bool(settings.elevenlabs_api_key),
        hume_api_key_set=bool(settings.hume_api_key),
        hume_secret_key_set=bool(settings.hume_secret_key),
        telnyx_api_key_set=bool(settings.telnyx_api_key),
        telnyx_messaging_profile_id_set=bool(settings.telnyx_messaging_profile_id),
        twilio_account_sid_set=bool(settings.twilio_account_sid),
        slicktext_api_key_set=bool(settings.slicktext_api_key),
        slicktext_public_key_set=bool(settings.slicktext_public_key),
        slicktext_private_key_set=bool(settings.slicktext_private_key),
        slicktext_textword_id=settings.slicktext_textword_id,
        slicktext_phone_number=settings.slicktext_phone_number,
        slicktext_default_text_agent_id=(
            str(settings.slicktext_default_text_agent_id)
            if settings.slicktext_default_text_agent_id
            else None
        ),
        workspace_id=str(settings.workspace_id) if settings.workspace_id else None,
    )


@router.post("", status_code=status.HTTP_200_OK)
async def update_settings(  # noqa: PLR0912, PLR0915
    request: UpdateSettingsRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str | None = None,
) -> dict[str, str]:
    """Update user settings.

    Args:
        request: Settings update request
        current_user: Authenticated user
        db: Database session
        workspace_id: Optional workspace ID for workspace-specific settings

    Returns:
        Success message
    """
    user_uuid = user_id_to_uuid(current_user.id)

    # Build query conditions
    conditions = [UserSettings.user_id == user_uuid]
    workspace_uuid: uuid.UUID | None = None

    if workspace_id:
        workspace_uuid = await _validate_workspace_ownership(workspace_id, current_user.id, db)
        conditions.append(UserSettings.workspace_id == workspace_uuid)
    else:
        conditions.append(UserSettings.workspace_id.is_(None))

    result = await db.execute(select(UserSettings).where(and_(*conditions)))
    settings = result.scalar_one_or_none()

    if settings:
        # Update existing
        if request.openai_api_key is not None:
            settings.openai_api_key = request.openai_api_key or None
        if request.deepgram_api_key is not None:
            settings.deepgram_api_key = request.deepgram_api_key or None
        if request.elevenlabs_api_key is not None:
            settings.elevenlabs_api_key = request.elevenlabs_api_key or None
        if request.hume_api_key is not None:
            settings.hume_api_key = request.hume_api_key or None
        if request.hume_secret_key is not None:
            settings.hume_secret_key = request.hume_secret_key or None
        if request.telnyx_api_key is not None:
            settings.telnyx_api_key = request.telnyx_api_key or None
        if request.telnyx_public_key is not None:
            settings.telnyx_public_key = request.telnyx_public_key or None
        if request.telnyx_messaging_profile_id is not None:
            settings.telnyx_messaging_profile_id = request.telnyx_messaging_profile_id or None
        if request.twilio_account_sid is not None:
            settings.twilio_account_sid = request.twilio_account_sid or None
        if request.twilio_auth_token is not None:
            settings.twilio_auth_token = request.twilio_auth_token or None
        if request.slicktext_api_key is not None:
            settings.slicktext_api_key = request.slicktext_api_key or None
        if request.slicktext_public_key is not None:
            settings.slicktext_public_key = request.slicktext_public_key or None
        if request.slicktext_private_key is not None:
            settings.slicktext_private_key = request.slicktext_private_key or None
        if request.slicktext_textword_id is not None:
            settings.slicktext_textword_id = request.slicktext_textword_id or None
        if request.slicktext_webhook_secret is not None:
            settings.slicktext_webhook_secret = request.slicktext_webhook_secret or None
        if request.slicktext_phone_number is not None:
            settings.slicktext_phone_number = request.slicktext_phone_number or None
        if request.slicktext_default_text_agent_id is not None:
            settings.slicktext_default_text_agent_id = (
                uuid.UUID(request.slicktext_default_text_agent_id)
                if request.slicktext_default_text_agent_id
                else None
            )

        db.add(settings)
    else:
        # Create new
        settings = UserSettings(
            user_id=user_uuid,
            workspace_id=workspace_uuid,
            openai_api_key=request.openai_api_key,
            deepgram_api_key=request.deepgram_api_key,
            elevenlabs_api_key=request.elevenlabs_api_key,
            hume_api_key=request.hume_api_key,
            hume_secret_key=request.hume_secret_key,
            telnyx_api_key=request.telnyx_api_key,
            telnyx_public_key=request.telnyx_public_key,
            telnyx_messaging_profile_id=request.telnyx_messaging_profile_id,
            twilio_account_sid=request.twilio_account_sid,
            twilio_auth_token=request.twilio_auth_token,
            slicktext_api_key=request.slicktext_api_key,
            slicktext_public_key=request.slicktext_public_key,
            slicktext_private_key=request.slicktext_private_key,
            slicktext_textword_id=request.slicktext_textword_id,
            slicktext_webhook_secret=request.slicktext_webhook_secret,
            slicktext_phone_number=request.slicktext_phone_number,
            slicktext_default_text_agent_id=(
                uuid.UUID(request.slicktext_default_text_agent_id)
                if request.slicktext_default_text_agent_id
                else None
            ),
        )
        db.add(settings)

    await db.commit()

    return {"message": "Settings updated successfully"}


class HumeVoiceResponse(BaseModel):
    """Response for a single Hume voice."""

    id: str
    name: str
    description: str | None = None
    is_custom: bool = False


class HumeVoicesResponse(BaseModel):
    """Response for listing Hume voices."""

    voices: list[HumeVoiceResponse]
    total: int


@router.get("/hume/voices", response_model=HumeVoicesResponse)
async def list_hume_voices(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str | None = None,
) -> HumeVoicesResponse:
    """List available Hume AI voices.

    Returns pre-built voices and user's custom voices from Hume.

    Args:
        current_user: Authenticated user
        db: Database session
        workspace_id: Optional workspace ID for workspace-specific API keys

    Returns:
        List of available Hume voices
    """
    user_uuid = user_id_to_uuid(current_user.id)
    workspace_uuid: uuid.UUID | None = None

    if workspace_id:
        workspace_uuid = await _validate_workspace_ownership(workspace_id, current_user.id, db)

    # Get user's Hume API key
    settings = await get_user_api_keys(user_uuid, db, workspace_uuid)

    # Start with pre-built voices
    voices: list[HumeVoiceResponse] = [
        HumeVoiceResponse(
            id=voice_id,
            name=voice_info["name"],
            description=voice_info["description"],
            is_custom=False,
        )
        for voice_id, voice_info in HUME_VOICES.items()
    ]

    # If user has Hume API key, fetch their custom voices
    if settings and settings.hume_api_key:
        try:
            tts = HumeOctaveTTS(api_key=settings.hume_api_key)
            custom_voices = await tts.list_voices()

            for voice in custom_voices:
                # Skip pre-built voices we already have
                if voice["id"] not in HUME_VOICES:
                    voices.append(
                        HumeVoiceResponse(
                            id=voice["id"],
                            name=voice["name"],
                            description=voice.get("description"),
                            is_custom=True,
                        )
                    )
        except Exception as e:
            # Log but don't fail - user can still use pre-built voices
            logger.warning(
                "failed_to_fetch_hume_custom_voices",
                error=str(e),
                user_id=str(user_uuid),
            )

    return HumeVoicesResponse(voices=voices, total=len(voices))


async def get_user_api_keys(
    user_id: uuid.UUID,
    db: AsyncSession,
    workspace_id: uuid.UUID | None = None,
) -> UserSettings | None:
    """Get user API keys for internal use.

    Settings lookup order:
    1. Workspace-specific settings (if workspace_id provided)
    2. User-level settings (fallback)

    Args:
        user_id: User ID (UUID)
        db: Database session
        workspace_id: Optional workspace ID for workspace-specific settings

    Returns:
        UserSettings or None
    """
    if workspace_id:
        # First try workspace-specific settings
        result = await db.execute(
            select(UserSettings).where(
                and_(
                    UserSettings.user_id == user_id,
                    UserSettings.workspace_id == workspace_id,
                )
            )
        )
        settings = result.scalar_one_or_none()
        if settings:
            return settings

        # Fallback to user-level settings
        result = await db.execute(
            select(UserSettings).where(
                and_(
                    UserSettings.user_id == user_id,
                    UserSettings.workspace_id.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    # Get user-level settings only (no workspace specified)
    result = await db.execute(
        select(UserSettings).where(
            and_(
                UserSettings.user_id == user_id,
                UserSettings.workspace_id.is_(None),
            )
        )
    )
    return result.scalar_one_or_none()
