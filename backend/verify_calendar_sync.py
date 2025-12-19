#!/usr/bin/env python3
"""Manual verification script for Cal.com calendar sync.

This script checks if the calendar sync service is working correctly.
Run this script to verify that:
1. Calendar sync service is configured
2. Cal.com integration is connected
3. Sync queue is being processed
4. Appointments are syncing to Cal.com
"""

import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.api.integrations import get_workspace_integrations
from app.core.auth import user_id_to_uuid
from app.db.session import AsyncSessionLocal
from app.models.appointment import Appointment
from app.models.calendar_sync import CalendarSyncQueue
from app.models.user_integration import UserIntegration
from app.models.workspace import Workspace


async def main() -> None:
    """Run verification checks."""
    print("=" * 80)
    print("CAL.COM CALENDAR SYNC VERIFICATION")
    print("=" * 80)
    print()

    async with AsyncSessionLocal() as db:
        # Check 1: Find workspaces with Cal.com integration
        print("[1] Checking for Cal.com integrations...")
        stmt = select(UserIntegration).where(
            UserIntegration.integration_id == "cal-com",
            UserIntegration.is_active == True,  # noqa: E712
        )
        result = await db.execute(stmt)
        calcom_integrations = result.scalars().all()

        if not calcom_integrations:
            print("   ❌ NO Cal.com integrations found!")
            print("   → Connect Cal.com in the integrations UI")
            print()
            print("Exiting...")
            sys.exit(1)

        print(f"   ✅ Found {len(calcom_integrations)} Cal.com integration(s)")
        for integration in calcom_integrations:
            workspace_stmt = select(Workspace).where(
                Workspace.id == integration.workspace_id
            )
            workspace_result = await db.execute(workspace_stmt)
            workspace = workspace_result.scalar_one_or_none()
            print(
                f"      - Workspace: {workspace.name if workspace else 'User-level'}"
            )
            print(f"        API Key: {'*' * 20}{integration.credentials.get('api_key', '')[-4:]}")
            print(
                f"        Event Type ID: {integration.credentials.get('event_type_id', 'Not set')}"
            )
        print()

        # Check 2: Check sync queue status
        print("[2] Checking calendar sync queue...")
        queue_stmt = select(CalendarSyncQueue).where(
            CalendarSyncQueue.calendar_provider == "cal-com"
        )
        queue_result = await db.execute(queue_stmt)
        all_entries = queue_result.scalars().all()

        if not all_entries:
            print("   ⚠️  No sync queue entries found")
            print("   → This is normal if no appointments have been created yet")
        else:
            print(f"   📊 Found {len(all_entries)} sync queue entries")

            # Group by status
            by_status = {}
            for entry in all_entries:
                by_status.setdefault(entry.status, []).append(entry)

            for status, entries in sorted(by_status.items()):
                print(f"      - {status.upper()}: {len(entries)}")

            # Show recent entries
            print()
            print("   Recent sync queue entries:")
            recent = sorted(all_entries, key=lambda e: e.created_at, reverse=True)[:5]
            for entry in recent:
                print(f"      - ID: {entry.id}")
                print(f"        Operation: {entry.operation}")
                print(f"        Status: {entry.status}")
                print(f"        Retries: {entry.retry_count}/{entry.max_retries}")
                if entry.error_message:
                    print(f"        Error: {entry.error_message}")
                print(f"        Created: {entry.created_at}")
                print()
        print()

        # Check 3: Check appointments with sync status
        print("[3] Checking appointments with Cal.com sync status...")
        appt_stmt = (
            select(Appointment)
            .where(Appointment.external_calendar_id == "cal-com")
            .order_by(Appointment.created_at.desc())
            .limit(10)
        )
        appt_result = await db.execute(appt_stmt)
        synced_appointments = appt_result.scalars().all()

        if not synced_appointments:
            print("   ⚠️  No appointments synced to Cal.com yet")
            print("   → Create an appointment via voice agent to test sync")
        else:
            print(f"   ✅ Found {len(synced_appointments)} synced appointment(s)")
            for appt in synced_appointments[:5]:
                print(f"      - ID: {appt.id}")
                print(f"        Scheduled: {appt.scheduled_at}")
                print(f"        Sync Status: {appt.sync_status}")
                print(f"        External Event ID: {appt.external_event_id}")
                print(f"        Last Synced: {appt.last_synced_at}")
                if appt.sync_error:
                    print(f"        Sync Error: {appt.sync_error}")
                print()
        print()

        # Check 4: Check for pending/failed syncs
        print("[4] Checking for pending or failed syncs...")
        problem_stmt = select(CalendarSyncQueue).where(
            CalendarSyncQueue.calendar_provider == "cal-com",
            CalendarSyncQueue.status.in_(["pending", "failed"]),
        )
        problem_result = await db.execute(problem_stmt)
        problem_entries = problem_result.scalars().all()

        if not problem_entries:
            print("   ✅ No pending or failed syncs")
        else:
            print(f"   ⚠️  Found {len(problem_entries)} pending/failed sync(s)")
            for entry in problem_entries[:10]:
                print(f"      - ID: {entry.id}")
                print(f"        Status: {entry.status}")
                print(f"        Operation: {entry.operation}")
                print(f"        Appointment ID: {entry.appointment_id}")
                print(f"        Retries: {entry.retry_count}/{entry.max_retries}")
                if entry.error_message:
                    print(f"        Error: {entry.error_message[:200]}")
                if entry.scheduled_at:
                    print(f"        Next Retry: {entry.scheduled_at}")
                print()
        print()

        # Check 5: Service configuration
        print("[5] Checking service configuration...")
        from app.core.config import settings

        print(f"   CALENDAR_SYNC_ENABLED: {settings.CALENDAR_SYNC_ENABLED}")
        print(f"   CALENDAR_SYNC_POLL_INTERVAL: {settings.CALENDAR_SYNC_POLL_INTERVAL}s")
        print(f"   CALENDAR_SYNC_MAX_RETRIES: {settings.CALENDAR_SYNC_MAX_RETRIES}")
        print()

        # Summary
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)

        issues = []
        if not calcom_integrations:
            issues.append("No Cal.com integrations connected")
        if problem_entries:
            issues.append(f"{len(problem_entries)} sync(s) pending or failed")

        if issues:
            print("⚠️  Issues found:")
            for issue in issues:
                print(f"   - {issue}")
        else:
            print("✅ Calendar sync appears to be configured correctly!")

        print()
        print("Next steps:")
        print("1. Create an appointment via voice agent")
        print("2. Check sync queue: SELECT * FROM calendar_sync_queue;")
        print("3. Check appointments: SELECT id, sync_status, external_event_id FROM appointments;")
        print("4. Check Cal.com dashboard for new bookings")
        print()


if __name__ == "__main__":
    asyncio.run(main())
