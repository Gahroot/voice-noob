"""API endpoints for user integrations (per workspace)."""

import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, user_id_to_uuid
from app.db.session import get_db
from app.models.user_integration import UserIntegration
from app.models.workspace import Workspace

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


class IntegrationCredentials(BaseModel):
    """Credentials for connecting an integration."""

    credentials: dict[str, Any] = Field(
        ..., description="Integration credentials (api_key, access_token, etc.)"
    )
    metadata: dict[str, Any] | None = Field(
        None, description="Additional integration-specific metadata"
    )


class ConnectIntegrationRequest(BaseModel):
    """Request to connect an integration."""

    integration_id: str = Field(..., description="Integration slug (e.g., 'hubspot', 'slack')")
    integration_name: str = Field(..., description="Display name (e.g., 'HubSpot', 'Slack')")
    workspace_id: str | None = Field(
        None, description="Workspace ID (null for user-level integration)"
    )
    credentials: dict[str, Any] = Field(
        ..., description="Integration credentials (api_key, access_token, etc.)"
    )
    metadata: dict[str, Any] | None = Field(
        None, description="Additional integration-specific metadata"
    )


class UpdateIntegrationRequest(BaseModel):
    """Request to update integration credentials."""

    credentials: dict[str, Any] | None = Field(
        None, description="Updated credentials (partial update supported)"
    )
    metadata: dict[str, Any] | None = Field(None, description="Updated metadata")
    is_active: bool | None = Field(None, description="Enable/disable integration")


class IntegrationResponse(BaseModel):
    """Integration response (credentials masked)."""

    model_config = {"from_attributes": True}

    id: str
    integration_id: str
    integration_name: str
    workspace_id: str | None
    is_active: bool
    is_connected: bool
    connected_at: datetime | None
    last_used_at: datetime | None
    has_credentials: bool
    credential_fields: list[str]  # List of field names that are set


class IntegrationListResponse(BaseModel):
    """List of integrations."""

    integrations: list[IntegrationResponse]
    total: int


def mask_credentials(credentials: dict[str, Any]) -> list[str]:
    """Return list of credential field names that are set (without values)."""
    return [key for key, value in credentials.items() if value]


@router.get("", response_model=IntegrationListResponse)
async def list_integrations(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str | None = None,
) -> IntegrationListResponse:
    """List user's connected integrations.

    Args:
        workspace_id: Filter by workspace (optional, null returns user-level integrations)
        current_user: Authenticated user
        db: Database session

    Returns:
        List of connected integrations with masked credentials
    """
    user_uuid = user_id_to_uuid(current_user.id)

    # Build query
    query = select(UserIntegration).where(UserIntegration.user_id == user_uuid)

    if workspace_id:
        try:
            ws_uuid = uuid.UUID(workspace_id)
            query = query.where(UserIntegration.workspace_id == ws_uuid)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid workspace_id format",
            ) from err
    # If workspace_id is None, we return ALL integrations for the user (both workspace-level and user-level)

    result = await db.execute(query.order_by(UserIntegration.created_at.desc()))
    integrations = result.scalars().all()

    responses = [
        IntegrationResponse(
            id=str(integration.id),
            integration_id=integration.integration_id,
            integration_name=integration.integration_name,
            workspace_id=str(integration.workspace_id) if integration.workspace_id else None,
            is_active=integration.is_active,
            is_connected=True,
            connected_at=integration.created_at,
            last_used_at=integration.last_used_at,
            has_credentials=bool(integration.credentials),
            credential_fields=mask_credentials(integration.credentials or {}),
        )
        for integration in integrations
    ]

    return IntegrationListResponse(integrations=responses, total=len(responses))


@router.get("/{integration_id}", response_model=IntegrationResponse)
async def get_integration(
    integration_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str | None = None,
) -> IntegrationResponse:
    """Get a specific integration's connection status.

    Args:
        integration_id: Integration slug (e.g., 'hubspot')
        workspace_id: Workspace ID (optional)
        current_user: Authenticated user
        db: Database session

    Returns:
        Integration details with masked credentials
    """
    user_uuid = user_id_to_uuid(current_user.id)

    # Build query conditions
    conditions = [
        UserIntegration.user_id == user_uuid,
        UserIntegration.integration_id == integration_id,
    ]

    if workspace_id:
        try:
            ws_uuid = uuid.UUID(workspace_id)
            conditions.append(UserIntegration.workspace_id == ws_uuid)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid workspace_id format",
            ) from err
    else:
        conditions.append(UserIntegration.workspace_id.is_(None))

    result = await db.execute(select(UserIntegration).where(and_(*conditions)))
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not connected",
        )

    return IntegrationResponse(
        id=str(integration.id),
        integration_id=integration.integration_id,
        integration_name=integration.integration_name,
        workspace_id=str(integration.workspace_id) if integration.workspace_id else None,
        is_active=integration.is_active,
        is_connected=True,
        connected_at=integration.created_at,
        last_used_at=integration.last_used_at,
        has_credentials=bool(integration.credentials),
        credential_fields=mask_credentials(integration.credentials or {}),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=IntegrationResponse)
async def connect_integration(
    request: ConnectIntegrationRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> IntegrationResponse:
    """Connect a new integration.

    Args:
        request: Integration connection request
        current_user: Authenticated user
        db: Database session

    Returns:
        Connected integration details
    """
    user_uuid = user_id_to_uuid(current_user.id)
    workspace_uuid: uuid.UUID | None = None

    # CRITICAL: FollowUpBoss integration requires workspace_id (workspace-only)
    if request.integration_id == "followupboss" and not request.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="FollowUpBoss integration requires a workspace_id. It cannot be user-level.",
        )

    # Validate workspace if provided
    if request.workspace_id:
        try:
            workspace_uuid = uuid.UUID(request.workspace_id)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid workspace_id format",
            ) from err

        # Verify workspace belongs to user
        ws_result = await db.execute(
            select(Workspace).where(
                and_(Workspace.id == workspace_uuid, Workspace.user_id == user_uuid)
            )
        )
        workspace = ws_result.scalar_one_or_none()
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )

    # Check if integration already exists for this user/workspace combo
    conditions = [
        UserIntegration.user_id == user_uuid,
        UserIntegration.integration_id == request.integration_id,
    ]
    if workspace_uuid:
        conditions.append(UserIntegration.workspace_id == workspace_uuid)
    else:
        conditions.append(UserIntegration.workspace_id.is_(None))

    existing = await db.execute(select(UserIntegration).where(and_(*conditions)))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Integration '{request.integration_id}' already connected for this workspace",
        )

    # Create new integration
    integration = UserIntegration(
        user_id=user_uuid,
        workspace_id=workspace_uuid,
        integration_id=request.integration_id,
        integration_name=request.integration_name,
        credentials=request.credentials,
        integration_metadata=request.metadata,
        is_active=True,
    )

    db.add(integration)
    await db.commit()
    await db.refresh(integration)

    # Start FUB sync worker if this is the first FUB integration (conditional worker)
    if request.integration_id == "followupboss":
        from app.services.fub_inbox_sync_service import start_fub_inbox_sync_if_needed

        await start_fub_inbox_sync_if_needed(db)

    return IntegrationResponse(
        id=str(integration.id),
        integration_id=integration.integration_id,
        integration_name=integration.integration_name,
        workspace_id=str(integration.workspace_id) if integration.workspace_id else None,
        is_active=integration.is_active,
        is_connected=True,
        connected_at=integration.created_at,
        last_used_at=integration.last_used_at,
        has_credentials=bool(integration.credentials),
        credential_fields=mask_credentials(integration.credentials or {}),
    )


@router.put("/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    integration_id: str,
    request: UpdateIntegrationRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str | None = None,
) -> IntegrationResponse:
    """Update an integration's credentials or settings.

    Args:
        integration_id: Integration slug (e.g., 'hubspot')
        request: Update request
        workspace_id: Workspace ID (optional)
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated integration details
    """
    user_uuid = user_id_to_uuid(current_user.id)

    # Build query conditions
    conditions = [
        UserIntegration.user_id == user_uuid,
        UserIntegration.integration_id == integration_id,
    ]

    if workspace_id:
        try:
            ws_uuid = uuid.UUID(workspace_id)
            conditions.append(UserIntegration.workspace_id == ws_uuid)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid workspace_id format",
            ) from err
    else:
        conditions.append(UserIntegration.workspace_id.is_(None))

    result = await db.execute(select(UserIntegration).where(and_(*conditions)))
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not connected",
        )

    # Update fields
    if request.credentials is not None:
        # Merge with existing credentials (partial update)
        existing_creds = integration.credentials or {}
        existing_creds.update(request.credentials)
        integration.credentials = existing_creds

    if request.metadata is not None:
        existing_meta = integration.integration_metadata or {}
        existing_meta.update(request.metadata)
        integration.integration_metadata = existing_meta

    if request.is_active is not None:
        integration.is_active = request.is_active

    integration.updated_at = datetime.now(UTC)

    db.add(integration)
    await db.commit()
    await db.refresh(integration)

    return IntegrationResponse(
        id=str(integration.id),
        integration_id=integration.integration_id,
        integration_name=integration.integration_name,
        workspace_id=str(integration.workspace_id) if integration.workspace_id else None,
        is_active=integration.is_active,
        is_connected=True,
        connected_at=integration.created_at,
        last_used_at=integration.last_used_at,
        has_credentials=bool(integration.credentials),
        credential_fields=mask_credentials(integration.credentials or {}),
    )


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_integration(
    integration_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str | None = None,
) -> None:
    """Disconnect an integration.

    Args:
        integration_id: Integration slug (e.g., 'hubspot')
        workspace_id: Workspace ID (optional)
        current_user: Authenticated user
        db: Database session
    """
    user_uuid = user_id_to_uuid(current_user.id)

    # Build query conditions
    conditions = [
        UserIntegration.user_id == user_uuid,
        UserIntegration.integration_id == integration_id,
    ]

    if workspace_id:
        try:
            ws_uuid = uuid.UUID(workspace_id)
            conditions.append(UserIntegration.workspace_id == ws_uuid)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid workspace_id format",
            ) from err
    else:
        conditions.append(UserIntegration.workspace_id.is_(None))

    result = await db.execute(select(UserIntegration).where(and_(*conditions)))
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not connected",
        )

    await db.delete(integration)
    await db.commit()


async def get_integration_credentials(
    user_id: uuid.UUID,
    integration_id: str,
    db: AsyncSession,
    workspace_id: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    """Get integration credentials for internal use.

    Args:
        user_id: User ID (UUID)
        integration_id: Integration slug
        db: Database session
        workspace_id: Workspace ID (optional)

    Returns:
        Credentials dict or None if not connected
    """
    conditions = [
        UserIntegration.user_id == user_id,
        UserIntegration.integration_id == integration_id,
        UserIntegration.is_active.is_(True),
    ]

    if workspace_id:
        conditions.append(UserIntegration.workspace_id == workspace_id)
    else:
        conditions.append(UserIntegration.workspace_id.is_(None))

    result = await db.execute(select(UserIntegration).where(and_(*conditions)))
    integration = result.scalar_one_or_none()

    if integration:
        # Update last_used_at
        integration.last_used_at = datetime.now(UTC)
        db.add(integration)
        await db.commit()
        return integration.credentials

    return None


async def get_workspace_integrations(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    db: AsyncSession,
) -> dict[str, dict[str, Any]]:
    """Get all active integration credentials for a workspace.

    Falls back to user-level integrations (workspace_id=NULL) if no
    workspace-specific integrations are found.

    Args:
        user_id: User ID
        workspace_id: Workspace ID
        db: Database session

    Returns:
        Dict mapping integration_id to credentials
    """
    result = await db.execute(
        select(UserIntegration).where(
            and_(
                UserIntegration.user_id == user_id,
                or_(
                    UserIntegration.workspace_id == workspace_id,
                    UserIntegration.workspace_id.is_(None),
                ),
                UserIntegration.is_active.is_(True),
            )
        )
    )
    integrations = result.scalars().all()

    # Build credentials dict with FUB filtering
    # FUB is workspace-only: ONLY workspace-specific (no user-level fallback)
    credentials_dict: dict[str, dict[str, Any]] = {}
    for integration in integrations:
        if not integration.credentials:
            continue

        # For FollowUpBoss: ONLY workspace-level (workspace_id must match)
        if integration.integration_id == "followupboss":
            if integration.workspace_id == workspace_id:
                credentials_dict[integration.integration_id] = integration.credentials
        # Other integrations: workspace-specific takes precedence over user-level
        elif (
            integration.integration_id not in credentials_dict
            or integration.workspace_id == workspace_id
        ):
            credentials_dict[integration.integration_id] = integration.credentials

    return credentials_dict


class CalComEventType(BaseModel):
    """Cal.com event type."""

    id: int
    title: str
    slug: str
    length: int | None = None


class CalComEventTypesResponse(BaseModel):
    """Response for Cal.com event types."""

    event_types: list[CalComEventType]
    total: int


@router.get("/cal-com/event-types", response_model=CalComEventTypesResponse)
async def get_calcom_event_types(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str | None = None,
) -> CalComEventTypesResponse:
    """Fetch Cal.com event types using stored credentials.

    Args:
        workspace_id: Workspace ID (optional)
        current_user: Authenticated user
        db: Database session

    Returns:
        List of Cal.com event types
    """
    import httpx

    user_uuid = user_id_to_uuid(current_user.id)

    # Get Cal.com credentials
    workspace_uuid: uuid.UUID | None = None
    if workspace_id:
        try:
            workspace_uuid = uuid.UUID(workspace_id)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid workspace_id format",
            ) from err

    credentials = await get_integration_credentials(user_uuid, "cal-com", db, workspace_uuid)

    if not credentials or "api_key" not in credentials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cal.com integration not connected or missing API key",
        )

    # Fetch event types from Cal.com API
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.cal.com/v2/event-types",
                headers={
                    "Authorization": f"Bearer {credentials['api_key']}",
                    "cal-api-version": "2024-06-14",
                },
            )

            if response.status_code != HTTPStatus.OK:
                raise HTTPException(  # noqa: TRY301
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Cal.com API returned status {response.status_code}: {response.text[:200]}",
                )

            data = response.json()
            event_types = []

            for et in data.get("data", []):
                event_types.append(
                    CalComEventType(
                        id=et["id"],
                        title=et.get("title") or et.get("slug", "Unnamed"),
                        slug=et["slug"],
                        length=et.get("lengthInMinutes") or et.get("length"),
                    )
                )

            return CalComEventTypesResponse(event_types=event_types, total=len(event_types))

    except HTTPException:
        # Re-raise FastAPI HTTPExceptions without wrapping them
        raise
    except httpx.TimeoutException as err:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Cal.com API request timed out",
        ) from err
    except httpx.HTTPError as err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cal.com API error: {err!s}",
        ) from err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error fetching event types: {err!s}",
        ) from err


@router.get("/google-calendar/calendars")
async def list_google_calendars(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """List available Google Calendars for the user.

    Args:
        workspace_id: Workspace ID (optional)
        current_user: Authenticated user
        db: Database session

    Returns:
        List of calendars with id, summary, primary flag
    """
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build  # type: ignore[import-untyped]

    user_uuid = user_id_to_uuid(current_user.id)
    workspace_uuid: uuid.UUID | None = None

    if workspace_id:
        try:
            workspace_uuid = uuid.UUID(workspace_id)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid workspace_id format",
            ) from err

    credentials = await get_integration_credentials(
        user_uuid, "google-calendar", db, workspace_uuid
    )

    if not credentials or "access_token" not in credentials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google Calendar not connected",
        )

    try:
        creds = Credentials(  # type: ignore[no-untyped-call]
            token=credentials["access_token"],
            refresh_token=credentials.get("refresh_token"),
        )

        service = build("calendar", "v3", credentials=creds)
        calendar_list = service.calendarList().list().execute()

        calendars = [
            {
                "id": cal["id"],
                "summary": cal["summary"],
                "primary": cal.get("primary", False),
                "backgroundColor": cal.get("backgroundColor"),
            }
            for cal in calendar_list.get("items", [])
        ]

        return {"calendars": calendars, "total": len(calendars)}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch calendars: {e!s}",
        ) from e
