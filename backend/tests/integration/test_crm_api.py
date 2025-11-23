"""Integration tests for CRM API endpoints."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contact import Contact

# API prefix for all endpoints
API_PREFIX = settings.API_V1_PREFIX


class TestContactsAPI:
    """Test contact management endpoints."""

    @pytest.mark.asyncio
    async def test_list_contacts_empty(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test listing contacts returns empty list when no contacts exist."""
        response = await test_client.get(f"{API_PREFIX}/crm/contacts")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_create_contact_success(
        self,
        test_client: AsyncClient,
        sample_contact_data: dict[str, Any],
    ) -> None:
        """Test creating a contact with valid data."""
        response = await test_client.post(f"{API_PREFIX}/crm/contacts", json=sample_contact_data)

        assert response.status_code == 201

        data = response.json()
        assert data["first_name"] == sample_contact_data["first_name"]
        assert data["last_name"] == sample_contact_data["last_name"]
        assert data["email"] == sample_contact_data["email"]
        assert data["phone_number"] == sample_contact_data["phone_number"]
        assert data["company_name"] == sample_contact_data["company_name"]
        assert data["status"] == sample_contact_data["status"]
        assert "id" in data
        assert data["id"] > 0

    @pytest.mark.asyncio
    async def test_create_contact_minimal_data(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test creating contact with only required fields."""
        minimal_data = {
            "first_name": "John",
            "phone_number": "+15551234567",
        }

        response = await test_client.post(f"{API_PREFIX}/crm/contacts", json=minimal_data)

        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "John"
        assert data["phone_number"] == "+15551234567"
        assert data["last_name"] is None
        assert data["email"] is None

    @pytest.mark.asyncio
    async def test_create_contact_validation_error(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test creating contact with missing required fields."""
        invalid_data = {
            "first_name": "John",
            # Missing phone_number
        }

        response = await test_client.post(f"{API_PREFIX}/crm/contacts", json=invalid_data)

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_list_contacts_with_data(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
    ) -> None:
        """Test listing contacts returns created contacts."""
        # Create test contacts directly in database
        contacts = [
            Contact(
                user_id=1,
                first_name="Alice",
                phone_number="+15551111111",
                status="new",
            ),
            Contact(
                user_id=1,
                first_name="Bob",
                phone_number="+15552222222",
                status="qualified",
            ),
        ]

        for contact in contacts:
            test_session.add(contact)

        await test_session.commit()

        # List contacts via API
        response = await test_client.get(f"{API_PREFIX}/crm/contacts")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Check ordering (newest first)
        assert data[0]["first_name"] == "Bob"  # Created second
        assert data[1]["first_name"] == "Alice"  # Created first

    @pytest.mark.asyncio
    async def test_list_contacts_pagination(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
    ) -> None:
        """Test contact listing pagination."""
        # Create 5 test contacts
        for i in range(5):
            contact = Contact(
                user_id=1,
                first_name=f"Contact{i}",
                phone_number=f"+155512345{i}0",
                status="new",
            )
            test_session.add(contact)

        await test_session.commit()

        # Test pagination with limit
        response = await test_client.get(f"{API_PREFIX}/crm/contacts?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Test pagination with skip
        response = await test_client.get(f"{API_PREFIX}/crm/contacts?skip=2&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_get_contact_success(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
    ) -> None:
        """Test getting a single contact by ID."""
        # Create test contact
        contact = Contact(
            user_id=1,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone_number="+15551234567",
            status="qualified",
        )
        test_session.add(contact)
        await test_session.commit()
        await test_session.refresh(contact)

        # Get contact by ID
        response = await test_client.get(f"/crm/contacts/{contact.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == contact.id
        assert data["first_name"] == "John"
        assert data["last_name"] == "Doe"
        assert data["email"] == "john@example.com"

    @pytest.mark.asyncio
    async def test_get_contact_not_found(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test getting non-existent contact returns 404."""
        response = await test_client.get(f"{API_PREFIX}/crm/contacts/99999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestCRMStatsAPI:
    """Test CRM statistics endpoints."""

    @pytest.mark.asyncio
    async def test_get_crm_stats_empty(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test CRM stats with no data returns zero counts."""
        response = await test_client.get(f"{API_PREFIX}/crm/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_contacts"] == 0
        assert data["total_appointments"] == 0
        assert data["total_calls"] == 0

    @pytest.mark.asyncio
    async def test_get_crm_stats_with_contacts(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
    ) -> None:
        """Test CRM stats reflects created contacts."""
        # Create test contacts
        for i in range(3):
            contact = Contact(
                user_id=1,
                first_name=f"Contact{i}",
                phone_number=f"+155512345{i}0",
                status="new",
            )
            test_session.add(contact)

        await test_session.commit()

        # Get stats
        response = await test_client.get(f"{API_PREFIX}/crm/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_contacts"] == 3
        assert data["total_appointments"] == 0
        assert data["total_calls"] == 0
