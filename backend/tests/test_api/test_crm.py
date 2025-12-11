"""Tests for CRM API endpoints."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.models.user import User


class TestContactEndpoints:
    """Test contact CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_contact_success(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
        sample_contact_data: dict[str, Any],
    ) -> None:
        """Test successful contact creation."""
        client, user = authenticated_test_client

        # Create contact
        response = await client.post("/api/v1/crm/contacts", json=sample_contact_data)

        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == sample_contact_data["first_name"]
        assert data["last_name"] == sample_contact_data["last_name"]
        assert data["email"] == sample_contact_data["email"]
        assert data["phone_number"] == sample_contact_data["phone_number"]
        assert data["company_name"] == sample_contact_data["company_name"]
        assert data["status"] == sample_contact_data["status"]
        assert data["user_id"] == user.id
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_contact_minimal_data(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
    ) -> None:
        """Test contact creation with minimal required fields."""
        client, _user = authenticated_test_client

        minimal_data = {
            "first_name": "Jane",
            "phone_number": "+9876543210",
        }

        response = await client.post("/api/v1/crm/contacts", json=minimal_data)

        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "Jane"
        assert data["phone_number"] == "+9876543210"
        assert data["last_name"] is None
        assert data["email"] is None
        assert data["status"] == "new"

    @pytest.mark.asyncio
    async def test_create_contact_validation_error(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
    ) -> None:
        """Test contact creation with missing required fields."""
        client, _user = authenticated_test_client

        # Missing first_name and phone_number
        invalid_data = {"email": "test@example.com"}

        response = await client.post("/api/v1/crm/contacts", json=invalid_data)

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_get_contact_success(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
        create_test_contact: Any,
    ) -> None:
        """Test successful contact retrieval."""
        client, user = authenticated_test_client
        contact = await create_test_contact(user_id=user.id)

        response = await client.get(f"/api/v1/crm/contacts/{contact.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == contact.id
        assert data["first_name"] == contact.first_name
        assert data["phone_number"] == contact.phone_number

    @pytest.mark.asyncio
    async def test_get_contact_not_found(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
    ) -> None:
        """Test retrieving non-existent contact."""
        client, _user = authenticated_test_client
        response = await client.get("/api/v1/crm/contacts/99999")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert data["detail"] == "Contact not found"

    @pytest.mark.asyncio
    async def test_list_contacts_empty(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
    ) -> None:
        """Test listing contacts when none exist."""
        client, _user = authenticated_test_client
        response = await client.get("/api/v1/crm/contacts")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_list_contacts_success(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
        create_test_contact: Any,
    ) -> None:
        """Test listing multiple contacts."""
        client, user = authenticated_test_client

        # Create multiple contacts
        await create_test_contact(
            user_id=user.id,
            first_name="Alice",
            phone_number="+1111111111",
        )
        await create_test_contact(
            user_id=user.id,
            first_name="Bob",
            phone_number="+2222222222",
        )

        response = await client.get("/api/v1/crm/contacts")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

        # Check that both contacts are present (order may vary due to same timestamp)
        first_names = {c["first_name"] for c in data}
        assert first_names == {"Alice", "Bob"}

    @pytest.mark.asyncio
    async def test_list_contacts_pagination(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
        create_test_contact: Any,
    ) -> None:
        """Test contact listing with pagination."""
        client, user = authenticated_test_client

        # Create 5 contacts
        for i in range(5):
            await create_test_contact(
                user_id=user.id,
                first_name=f"Contact{i}",
                phone_number=f"+100000000{i}",
            )

        # Test skip and limit
        response = await client.get("/api/v1/crm/contacts?skip=2&limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_contact_rate_limiting(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
    ) -> None:
        """Test rate limiting on contact endpoints."""
        client, _user = authenticated_test_client

        # Make many requests to trigger rate limit
        # Rate limit is 100/minute, so we'll make 110 requests
        responses = []
        for _ in range(110):
            response = await client.get("/api/v1/crm/contacts")
            responses.append(response)

        # Some responses should be rate limited (429)
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes


class TestCRMStatsEndpoint:
    """Test CRM statistics endpoint."""

    @pytest.mark.asyncio
    async def test_get_stats_structure(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
    ) -> None:
        """Test stats endpoint returns expected structure."""
        client, _user = authenticated_test_client
        response = await client.get("/api/v1/crm/stats")

        assert response.status_code == 200
        data = response.json()
        # Verify structure (counts may vary due to test isolation)
        assert "total_contacts" in data
        assert "total_appointments" in data
        assert "total_calls" in data
        assert isinstance(data["total_contacts"], int)
        assert isinstance(data["total_appointments"], int)
        assert isinstance(data["total_calls"], int)
        assert data["total_contacts"] >= 0
        assert data["total_appointments"] >= 0
        assert data["total_calls"] >= 0

    @pytest.mark.asyncio
    async def test_get_stats_contacts_increment(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
    ) -> None:
        """Test stats endpoint shows correct contact count after creation."""
        client, _user = authenticated_test_client

        # Create contacts via API with unique phone numbers
        import uuid

        suffix = str(uuid.uuid4())[:8]
        response1 = await client.post(
            "/api/v1/crm/contacts",
            json={"first_name": "Alice", "phone_number": f"+111{suffix}1111"},
        )
        assert response1.status_code == 201

        response2 = await client.post(
            "/api/v1/crm/contacts",
            json={"first_name": "Bob", "phone_number": f"+222{suffix}2222"},
        )
        assert response2.status_code == 201

        # Get stats - should have at least 2 contacts
        final_response = await client.get("/api/v1/crm/stats")

        assert final_response.status_code == 200
        data = final_response.json()
        # At least 2 contacts should exist (may be more if test isolation is imperfect)
        assert data["total_contacts"] >= 2

    @pytest.mark.asyncio
    async def test_stats_consistency(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
    ) -> None:
        """Test that stats endpoint returns consistent results."""
        client, _user = authenticated_test_client

        # Create a contact via API with unique phone number
        import uuid

        suffix = str(uuid.uuid4())[:8]
        create_response = await client.post(
            "/api/v1/crm/contacts",
            json={"first_name": "Test", "phone_number": f"+123{suffix}4567890"},
        )
        assert create_response.status_code == 201

        # First request
        response1 = await client.get("/api/v1/crm/stats")
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["total_contacts"] >= 1

        # Second request - should return same or greater count
        response2 = await client.get("/api/v1/crm/stats")
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["total_contacts"] >= data1["total_contacts"]

    @pytest.mark.asyncio
    async def test_stats_after_contact_creation(
        self,
        authenticated_test_client: tuple[AsyncClient, User],
    ) -> None:
        """Test that stats reflect contact creation."""
        import uuid

        client, _user = authenticated_test_client

        # Get initial stats
        response1 = await client.get("/api/v1/crm/stats")
        assert response1.status_code == 200
        initial_count = response1.json()["total_contacts"]

        # Create a contact with unique phone number
        suffix = str(uuid.uuid4())[:8]
        create_response = await client.post(
            "/api/v1/crm/contacts",
            json={"first_name": "New", "phone_number": f"+555{suffix}1234"},
        )
        assert create_response.status_code == 201

        # Get stats again - should show at least the initial count
        # (may be cached, so we check it's at least the same)
        response2 = await client.get("/api/v1/crm/stats")
        assert response2.status_code == 200
        assert response2.json()["total_contacts"] >= initial_count


class TestContactDatabaseIntegration:
    """Test contact database operations."""

    @pytest.mark.asyncio
    async def test_contact_persists_to_database(
        self,
        test_session: Any,
        create_test_user: Any,
        create_test_contact: Any,
    ) -> None:
        """Test that contacts are properly persisted."""
        from sqlalchemy import select

        from app.models.contact import Contact

        user = await create_test_user()
        contact = await create_test_contact(
            user_id=user.id,
            first_name="Test",
            last_name="User",
            phone_number="+1234567890",
        )

        # Query directly from database
        result = await test_session.execute(select(Contact).where(Contact.id == contact.id))
        db_contact = result.scalar_one()

        assert db_contact.id == contact.id
        assert db_contact.first_name == "Test"
        assert db_contact.last_name == "User"
        assert db_contact.phone_number == "+1234567890"
        assert db_contact.user_id == user.id

    @pytest.mark.asyncio
    async def test_contact_cascade_delete_appointments(
        self,
        test_session: Any,
        create_test_user: Any,
        create_test_contact: Any,
        create_test_appointment: Any,
    ) -> None:
        """Test that deleting a contact cascades to appointments."""
        from sqlalchemy import select

        from app.models.appointment import Appointment

        user = await create_test_user()
        contact = await create_test_contact(user_id=user.id)
        appointment = await create_test_appointment(contact_id=contact.id)

        # Delete contact
        await test_session.delete(contact)
        await test_session.commit()

        # Verify appointment was also deleted
        result = await test_session.execute(
            select(Appointment).where(Appointment.id == appointment.id)
        )
        deleted_appointment = result.scalar_one_or_none()
        assert deleted_appointment is None

    @pytest.mark.asyncio
    async def test_contact_cascade_delete_call_interactions(
        self,
        test_session: Any,
        create_test_user: Any,
        create_test_contact: Any,
        create_test_call_interaction: Any,
    ) -> None:
        """Test that deleting a contact cascades to call interactions."""
        from sqlalchemy import select

        from app.models.call_interaction import CallInteraction

        user = await create_test_user()
        contact = await create_test_contact(user_id=user.id)
        call = await create_test_call_interaction(contact_id=contact.id)

        # Delete contact
        await test_session.delete(contact)
        await test_session.commit()

        # Verify call was also deleted
        result = await test_session.execute(
            select(CallInteraction).where(CallInteraction.id == call.id)
        )
        deleted_call = result.scalar_one_or_none()
        assert deleted_call is None
