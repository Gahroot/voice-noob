#!/usr/bin/env python3
"""Script to create the Voice Noob appointment setter agent for Nolan Grout.

This script creates a voice agent optimized for:
- Instant callback to leads from Facebook/website forms
- Booking 30-minute video calls via Cal.com
- Professional, friendly appointment setting

Usage:
    cd backend
    uv run python scripts/create_appointment_setter_agent.py

Requirements:
    - Admin user must exist in database
    - Workspace must exist
    - Cal.com integration must be configured with your API key
    - Telnyx phone number must be assigned
"""

import asyncio

# Add backend directory to path for imports
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal
from app.models.agent import Agent
from app.models.user import User
from app.models.workspace import AgentWorkspace, Workspace

# =============================================================================
# Agent Configuration
# =============================================================================

AGENT_NAME = "Voice Noob Appointment Setter"
AGENT_DESCRIPTION = """
Instant callback agent for Voice Noob leads. Calls prospects who submit forms on
Facebook or the website, qualifies them, and books 30-minute video discovery calls
with Nolan Grout via Cal.com.
"""

# The system prompt is critical for agent behavior
SYSTEM_PROMPT = """You are Sarah, a friendly and professional AI assistant for Voice Noob, an AI-powered voice agent platform. Your primary goal is to book a 30-minute video discovery call with Nolan Grout, the founder.

## Your Personality
- Warm, professional, and conversational (not robotic or scripted)
- Confident but not pushy
- Patient and helpful
- Speak naturally with appropriate pauses

## About Voice Noob (use this to answer questions)
Voice Noob helps businesses automate phone calls with AI voice agents that can:
- Handle inbound customer calls 24/7
- Make outbound calls for appointment setting, follow-ups, and lead qualification
- Integrate with CRM systems, calendars (Cal.com, Calendly), and tools
- Support multiple languages and natural conversations
- Offer transparent pricing starting at $29/month

Nolan Grout is the founder and will personally help set up your voice agent solution during the discovery call.

## Call Flow

### 1. Opening (first 15 seconds are critical)
Start with: "Hi, this is Sarah from Voice Noob! I'm calling because you just submitted your information about AI voice agents. Is now a good time for a quick 2-minute chat?"

If they say no or ask who's calling:
- Briefly explain you're following up on their form submission
- Offer to call back at a better time if needed

### 2. Quick Qualification (30-60 seconds)
Ask ONE of these questions based on context:
- "What kind of calls are you looking to automate - inbound customer calls, outbound sales calls, or both?"
- "Roughly how many calls does your business handle per day or week?"
- "What's the biggest phone-related challenge you're facing right now?"

Listen actively and acknowledge their response. If they have questions, answer briefly using the Voice Noob info above.

### 3. Book the Call (this is your main goal)
Transition with: "It sounds like Voice Noob could really help with that! Nolan would love to show you exactly how it works in a quick 30-minute video call. He'll walk you through setting up an agent for your specific use case."

Then use the calendar tools:
1. First, use `calcom_get_availability` to check available slots for the next 5-7 business days
2. Offer 2-3 specific time options: "I have [time 1], [time 2], or [time 3] available. Which works best for you?"
3. Once they choose, confirm their details and use `calcom_create_booking` to book it

### 4. Confirmation & Close
After booking: "Perfect! You're all set for [date and time]. You'll get a calendar invite with the video link to your email. Nolan's really looking forward to chatting with you. Is there anything specific you'd like him to prepare for?"

Then: "Great! Thanks so much for your time, [name]. Have a wonderful day!"

## Handling Objections

"I'm busy right now"
→ "No problem at all! When would be a better time for me to call back?"

"I'm not interested"
→ "I understand. Just so I know, was there something specific that didn't seem like a fit? Sometimes I can point you to better resources."

"How much does it cost?"
→ "Plans start at $29/month, but pricing depends on your call volume and needs. That's exactly what Nolan will help figure out in the discovery call - no pressure, just information."

"Is this a sales call?"
→ "I'm actually an AI assistant! I help coordinate discovery calls. Nolan will give you a personalized demo - it's more educational than salesy. Many people actually enjoy seeing the tech in action."

"Can you just send me information?"
→ "Absolutely! I can have Nolan send you some details. To make sure he sends the right info, let me ask - what's your main interest: handling customer support calls, appointment booking, or something else?"

## Important Rules
1. NEVER be pushy. If they're clearly not interested, thank them and end politely
2. ALWAYS confirm email and phone before booking
3. If they ask technical questions you can't answer: "That's a great question for Nolan - he can give you the full technical breakdown in the call"
4. Speak concisely - this is a phone call, not an email
5. Use their name occasionally to build rapport
6. If the call goes over 3 minutes without booking, offer to send info and follow up later

## Tools Available
- `calcom_get_availability` - Check available time slots
- `calcom_create_booking` - Create a booking with attendee details
- `calcom_get_event_types` - Get available meeting types (use if needed)

## Time Zone Handling
- Ask the prospect what time zone they're in before offering times
- Convert times appropriately when presenting options
- Always confirm the time and time zone before booking
"""

INITIAL_GREETING = "Hi, this is Sarah from Voice Noob! I'm calling because you just submitted your information about AI voice agents. Is now a good time for a quick 2-minute chat?"

# Agent settings
PRICING_TIER = "premium"  # Best quality for sales calls
VOICE = "shimmer"  # Professional female voice
LANGUAGE = "en-US"
TEMPERATURE = 0.7  # Balanced between creative and consistent
MAX_TOKENS = 500  # Keep responses concise for phone

# Turn detection - optimized for natural conversation
TURN_DETECTION_MODE = "semantic"  # Better for back-and-forth dialogue
TURN_DETECTION_THRESHOLD = 0.5
TURN_DETECTION_PREFIX_PADDING_MS = 300
TURN_DETECTION_SILENCE_DURATION_MS = 700  # Slightly longer for thinking

# Tools to enable
ENABLED_TOOLS = ["cal-com"]
ENABLED_TOOL_IDS = {
    "cal-com": [
        "calcom_get_event_types",
        "calcom_get_availability",
        "calcom_create_booking",
    ]
}


async def main() -> None:
    """Create the appointment setter agent."""
    async with AsyncSessionLocal() as db:
        # Find the admin user (Nolan)
        result = await db.execute(
            select(User).where(User.is_superuser == True).limit(1)  # noqa: E712
        )
        admin_user = result.scalar_one_or_none()

        if not admin_user:
            print("ERROR: No admin user found. Please create an admin user first.")  # noqa: T201
            return

        print(f"Found admin user: {admin_user.email} (ID: {admin_user.id})")  # noqa: T201

        # Get or create workspace
        workspace_result = await db.execute(
            select(Workspace).where(Workspace.owner_id == admin_user.uuid).limit(1)
        )
        workspace = workspace_result.scalar_one_or_none()

        if not workspace:
            print("Creating default workspace...")  # noqa: T201
            workspace = Workspace(
                name="Voice Noob",
                owner_id=admin_user.uuid,
                description="Voice Noob main workspace",
            )
            db.add(workspace)
            await db.commit()
            await db.refresh(workspace)
            print(f"Created workspace: {workspace.name} (ID: {workspace.id})")  # noqa: T201
        else:
            print(f"Using existing workspace: {workspace.name} (ID: {workspace.id})")  # noqa: T201

        # Check if agent already exists
        existing_result = await db.execute(
            select(Agent).where(
                Agent.user_id == admin_user.uuid,
                Agent.name == AGENT_NAME,
            )
        )
        existing_agent = existing_result.scalar_one_or_none()

        if existing_agent:
            print(f"\nAgent already exists: {existing_agent.name}")  # noqa: T201
            print(f"Agent ID: {existing_agent.id}")  # noqa: T201
            print("\nTo update, delete the existing agent first or modify this script.")  # noqa: T201
            return

        # Create the agent
        agent = Agent(
            user_id=admin_user.uuid,
            name=AGENT_NAME,
            description=AGENT_DESCRIPTION.strip(),
            pricing_tier=PRICING_TIER,
            system_prompt=SYSTEM_PROMPT.strip(),
            language=LANGUAGE,
            voice=VOICE,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            initial_greeting=INITIAL_GREETING,
            turn_detection_mode=TURN_DETECTION_MODE,
            turn_detection_threshold=TURN_DETECTION_THRESHOLD,
            turn_detection_prefix_padding_ms=TURN_DETECTION_PREFIX_PADDING_MS,
            turn_detection_silence_duration_ms=TURN_DETECTION_SILENCE_DURATION_MS,
            enabled_tools=ENABLED_TOOLS,
            enabled_tool_ids=ENABLED_TOOL_IDS,
            integration_settings={},  # Will need to set Cal.com event_type_id
            is_active=True,
            is_published=False,
            enable_recording=True,  # Record calls for review
            enable_transcript=True,  # Transcribe for analysis
        )

        db.add(agent)
        await db.commit()
        await db.refresh(agent)

        print(f"\n✅ Created agent: {agent.name}")  # noqa: T201
        print(f"   Agent ID: {agent.id}")  # noqa: T201

        # Associate agent with workspace
        agent_workspace = AgentWorkspace(
            agent_id=agent.id,
            workspace_id=workspace.id,
        )
        db.add(agent_workspace)
        await db.commit()

        print(f"   Workspace: {workspace.name}")  # noqa: T201

        # Print next steps
        print("\n" + "=" * 60)  # noqa: T201
        print("NEXT STEPS:")  # noqa: T201
        print("=" * 60)  # noqa: T201
        print(  # noqa: T201
            """
1. CONFIGURE CAL.COM INTEGRATION:
   - Go to Settings > Integrations > Cal.com
   - Add your Cal.com API key
   - Note your 30-min event type ID

2. UPDATE AGENT INTEGRATION SETTINGS:
   Update the agent's integration_settings with your Cal.com event type ID:

   curl -X PATCH http://localhost:8000/api/v1/agents/{agent_id} \\
     -H "Authorization: Bearer YOUR_TOKEN" \\
     -H "Content-Type: application/json" \\
     -d '{
       "integration_settings": {
         "cal-com": {
           "default_event_type_id": YOUR_EVENT_TYPE_ID
         }
       }
     }'

3. ASSIGN A PHONE NUMBER:
   - Go to Phone Numbers > Buy a new number
   - Assign it to this agent

4. SET UP LEAD WEBHOOKS:
   - Generate an API key and set LEAD_WEBHOOK_API_KEY in .env
   - Configure your Facebook Lead Ads webhook:
     POST https://your-domain.com/webhooks/leads/facebook?agent_id={agent_id}

   - Configure your website form to POST to:
     POST https://your-domain.com/webhooks/leads/website?api_key=YOUR_KEY
     Body: {
       "first_name": "...",
       "phone_number": "+1...",
       "agent_id": "{agent_id}"
     }

5. TEST THE AGENT:
   - Use the dashboard to test the agent
   - Make a test call to verify audio quality
   - Submit a test lead to verify the callback flow
"""
        )
        print(f"\nAgent ID: {agent.id}")  # noqa: T201
        print("=" * 60)  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
