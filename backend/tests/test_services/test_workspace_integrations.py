"""Tests for workspace integration fallback logic."""

# ruff: noqa: S106

import uuid

import pytest
import pytest_asyncio

from app.api.integrations import get_workspace_integrations
from app.core.auth import user_id_to_uuid
from app.models.user_integration import UserIntegration
from app.models.workspace import Workspace


@pytest_asyncio.fixture
async def test_user(test_session):
    """Create a test user."""
    from app.models.user import User

    user = User(
        email="testuser@example.com",
        hashed_password="test_hashed_pw",
        full_name="Test User",
        is_active=True,
        is_superuser=False,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def workspace(test_session, test_user):
    """Create a test workspace."""
    workspace = Workspace(
        id=uuid.uuid4(),
        name="Test Workspace",
        user_id=test_user.id,  # user_id is INTEGER in Workspace model
        is_default=True,
        settings={"timezone": "America/New_York"},
    )
    test_session.add(workspace)
    await test_session.commit()
    await test_session.refresh(workspace)
    return workspace


@pytest_asyncio.fixture
async def user_level_integration(test_session, test_user):
    """Create a user-level integration (workspace_id=NULL)."""
    integration = UserIntegration(
        id=uuid.uuid4(),
        user_id=user_id_to_uuid(test_user.id),
        workspace_id=None,  # User-level integration
        integration_id="cal-com",
        integration_name="Cal.com",
        credentials={
            "api_key": "cal_test_1234567890abcdef",
            "event_type_id": 12345,
        },
        is_active=True,
    )
    test_session.add(integration)
    await test_session.commit()
    await test_session.refresh(integration)
    return integration


@pytest_asyncio.fixture
async def workspace_level_integration(test_session, test_user, workspace):
    """Create a workspace-specific integration."""
    integration = UserIntegration(
        id=uuid.uuid4(),
        user_id=user_id_to_uuid(test_user.id),
        workspace_id=workspace.id,  # Workspace-specific integration
        integration_id="google-calendar",
        integration_name="Google Calendar",
        credentials={
            "access_token": "google_token_xyz",
            "refresh_token": "google_refresh_xyz",
        },
        is_active=True,
    )
    test_session.add(integration)
    await test_session.commit()
    await test_session.refresh(integration)
    return integration


@pytest.mark.asyncio
async def test_get_workspace_integrations_fallback_to_user_level(
    test_session, test_user, workspace, user_level_integration
):
    """Test that get_workspace_integrations falls back to user-level integrations."""
    # Query for workspace integrations
    integrations = await get_workspace_integrations(
        user_id=user_id_to_uuid(test_user.id),
        workspace_id=workspace.id,
        db=test_session,
    )

    # Should find user-level integration even though workspace_id doesn't match
    assert "cal-com" in integrations
    assert integrations["cal-com"]["api_key"] == "cal_test_1234567890abcdef"


@pytest.mark.asyncio
async def test_get_workspace_integrations_prefers_workspace_specific(
    test_session, test_user, workspace, user_level_integration, workspace_level_integration
):
    """Test that workspace-specific integrations are included alongside user-level ones."""
    # Query for workspace integrations
    integrations = await get_workspace_integrations(
        user_id=user_id_to_uuid(test_user.id),
        workspace_id=workspace.id,
        db=test_session,
    )

    # Should find both workspace-specific and user-level integrations
    assert "cal-com" in integrations  # User-level
    assert "google-calendar" in integrations  # Workspace-specific
    assert len(integrations) == 2


@pytest.mark.asyncio
async def test_get_workspace_integrations_only_active(test_session, test_user, workspace):
    """Test that only active integrations are returned."""
    # Create active integration
    active_integration = UserIntegration(
        id=uuid.uuid4(),
        user_id=user_id_to_uuid(test_user.id),
        workspace_id=None,
        integration_id="cal-com",
        integration_name="Cal.com",
        credentials={"api_key": "active_key"},
        is_active=True,
    )
    test_session.add(active_integration)

    # Create inactive integration
    inactive_integration = UserIntegration(
        id=uuid.uuid4(),
        user_id=user_id_to_uuid(test_user.id),
        workspace_id=None,
        integration_id="calendly",
        integration_name="Calendly",
        credentials={"access_token": "inactive_token"},
        is_active=False,
    )
    test_session.add(inactive_integration)
    await test_session.commit()

    # Query for workspace integrations
    integrations = await get_workspace_integrations(
        user_id=user_id_to_uuid(test_user.id),
        workspace_id=workspace.id,
        db=test_session,
    )

    # Should only find active integration
    assert "cal-com" in integrations
    assert "calendly" not in integrations


@pytest.mark.asyncio
async def test_get_workspace_integrations_user_isolation(test_session, test_user, workspace):
    """Test that integrations from other users are not returned."""
    from app.models.user import User

    # Create another user
    other_user = User(
        email="otheruser@example.com",
        hashed_password="other_hashed_pw",
        full_name="Other User",
        is_active=True,
        is_superuser=False,
    )
    test_session.add(other_user)
    await test_session.commit()
    await test_session.refresh(other_user)

    # Create integration for other user
    other_integration = UserIntegration(
        id=uuid.uuid4(),
        user_id=user_id_to_uuid(other_user.id),
        workspace_id=None,
        integration_id="cal-com",
        integration_name="Cal.com",
        credentials={"api_key": "other_user_key"},
        is_active=True,
    )
    test_session.add(other_integration)
    await test_session.commit()

    # Query for test_user's workspace integrations
    integrations = await get_workspace_integrations(
        user_id=user_id_to_uuid(test_user.id),
        workspace_id=workspace.id,
        db=test_session,
    )

    # Should not find other user's integration
    assert "cal-com" not in integrations
    assert len(integrations) == 0
