#!/usr/bin/env python3
"""Helper script to list Cal.com event types and update integration credentials.

This script helps you:
1. List available event types from your Cal.com account
2. Update your Cal.com integration with the event_type_id

This is required for calendar sync to work!
"""

import asyncio
import sys
from typing import Any

import httpx
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.user_integration import UserIntegration


async def list_calcom_event_types(api_key: str) -> list[dict[str, Any]]:
    """Fetch event types from Cal.com API."""
    base_url = "https://api.cal.com/v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-08-13",
    }

    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30.0) as client:
        try:
            response = await client.get("/event-types")
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except httpx.HTTPError as e:
            print(f"❌ Error fetching event types: {e}")
            return []


async def main() -> None:
    """Run the setup script."""
    print("=" * 80)
    print("CAL.COM EVENT TYPE SETUP")
    print("=" * 80)
    print()

    async with AsyncSessionLocal() as db:
        # Find Cal.com integrations
        stmt = select(UserIntegration).where(
            UserIntegration.integration_id == "cal-com",
            UserIntegration.is_active == True,  # noqa: E712
        )
        result = await db.execute(stmt)
        integrations = result.scalars().all()

        if not integrations:
            print("❌ No Cal.com integrations found!")
            print("   Please connect Cal.com in the integrations UI first.")
            sys.exit(1)

        if len(integrations) > 1:
            print(f"Found {len(integrations)} Cal.com integrations.")
            print("Please select which one to configure:")
            for i, integration in enumerate(integrations, 1):
                print(f"  {i}. Integration ID: {integration.id}")
            choice = int(input("Enter number: ")) - 1
            integration = integrations[choice]
        else:
            integration = integrations[0]

        print(f"Using integration: {integration.id}")
        print()

        # Get API key
        api_key = integration.credentials.get("api_key")
        if not api_key:
            print("❌ No API key found in integration credentials!")
            sys.exit(1)

        print("Fetching event types from Cal.com...")
        event_types = await list_calcom_event_types(api_key)

        if not event_types:
            print("❌ No event types found or API error!")
            print("   Please check:")
            print("   1. Your Cal.com API key is valid")
            print("   2. You have created at least one event type in Cal.com")
            sys.exit(1)

        print(f"✅ Found {len(event_types)} event type(s):")
        print()

        for i, et in enumerate(event_types, 1):
            print(f"{i}. {et.get('title', et.get('slug'))}")
            print(f"   ID: {et['id']}")
            print(f"   Slug: {et['slug']}")
            print(f"   Duration: {et.get('lengthInMinutes', et.get('length'))} minutes")
            if et.get('description'):
                print(f"   Description: {et['description']}")
            print()

        # Prompt user to select
        print("Which event type should be used for appointments?")
        choice = int(input(f"Enter number (1-{len(event_types)}): ")) - 1
        selected_event_type = event_types[choice]

        event_type_id = selected_event_type["id"]
        print()
        print(f"Selected: {selected_event_type.get('title')} (ID: {event_type_id})")
        print()

        # Update integration credentials
        integration.credentials["event_type_id"] = event_type_id
        await db.commit()

        print("✅ Integration updated successfully!")
        print()
        print("=" * 80)
        print("NEXT STEPS")
        print("=" * 80)
        print("1. Create a test appointment via voice agent")
        print("2. Check the sync queue:")
        print("   SELECT * FROM calendar_sync_queue WHERE calendar_provider = 'cal-com';")
        print()
        print("3. Check the appointment sync status:")
        print("   SELECT id, scheduled_at, sync_status, external_event_id FROM appointments;")
        print()
        print("4. Verify the booking appears in your Cal.com dashboard")
        print()


if __name__ == "__main__":
    asyncio.run(main())
