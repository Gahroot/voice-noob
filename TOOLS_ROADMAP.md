# Tools & Integrations Roadmap

## Current Status (What We Have)

### ✅ Built - Frontend UI
- Integrations management page with 15 integrations
- OAuth & API key configuration UI
- Connection status tracking
- Tools selector in agent creation form
- Category filtering and search

### ❌ Not Built Yet - Actual Tool Functions

**Important**: We currently have the **UI and configuration system** for integrations, but we haven't built the actual **tool functions** that voice agents can call.

## What Needs to Be Built

### Backend - Tool Functions (Python)

Each integration needs actual Python functions that Pipecat can call during conversations:

#### Example: Google Calendar Tools

```python
# backend/app/services/tools/google_calendar.py

async def check_availability(
    date: str,
    time_range: str,
    user_credentials: dict
) -> dict:
    """Check if user is available at given time"""
    # 1. Use OAuth credentials from database
    # 2. Call Google Calendar API
    # 3. Return availability
    pass

async def schedule_meeting(
    title: str,
    datetime: str,
    duration_minutes: int,
    attendees: list[str],
    user_credentials: dict
) -> dict:
    """Schedule a new meeting"""
    # 1. Create calendar event
    # 2. Send invites
    # 3. Return confirmation
    pass
```

#### Example: Salesforce Tools

```python
# backend/app/services/tools/salesforce.py

async def lookup_customer(
    email: str,
    user_credentials: dict
) -> dict:
    """Look up customer by email"""
    # Query Salesforce API
    pass

async def create_lead(
    name: str,
    email: str,
    phone: str,
    company: str,
    user_credentials: dict
) -> dict:
    """Create new lead in Salesforce"""
    pass
```

### Pipecat Integration

Each tool needs to be registered as a function that Pipecat can call:

```python
from pipecat.services.openai import OpenAILLMService

# Register tools with the LLM
llm_service = OpenAILLMService(
    api_key=openai_key,
    model="gpt-4o",
    functions=[
        {
            "name": "check_calendar_availability",
            "description": "Check if the user is available at a specific time",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "time": {"type": "string", "description": "Time in HH:MM format"},
                },
                "required": ["date", "time"]
            }
        },
        # ... more tools
    ]
)
```

## Implementation Priority

### Phase 1: Core Tools (Week 1)
1. **Google Calendar** - Most requested
   - check_availability
   - schedule_meeting
   - cancel_meeting

2. **Salesforce** - CRM essential
   - lookup_contact
   - create_lead
   - update_opportunity

3. **HubSpot** - CRM alternative
   - get_contact
   - create_ticket
   - log_call

### Phase 2: Communication (Week 2)
4. **Slack**
   - send_message
   - create_channel

5. **Gmail**
   - send_email
   - search_emails

### Phase 3: Database & Productivity (Week 3)
6. **Notion**
   - query_database
   - create_page

7. **Google Sheets**
   - read_data
   - append_row

8. **Airtable**
   - get_records
   - create_record

### Phase 4: Additional Tools (Week 4+)
- Stripe, Zendesk, Jira, GitHub, etc.

## Technical Architecture

### 1. Database Schema

```sql
-- Store user integration credentials
CREATE TABLE user_integrations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    integration_id VARCHAR(50),  -- e.g., "salesforce"
    auth_type VARCHAR(20),        -- "oauth" or "api_key"

    -- For OAuth
    access_token TEXT,
    refresh_token TEXT,
    expires_at TIMESTAMP,

    -- For API Keys
    api_key TEXT,
    api_secret TEXT,

    -- Metadata
    scopes JSON,
    metadata JSON,
    is_active BOOLEAN DEFAULT TRUE,
    connected_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Link integrations to agents
CREATE TABLE agent_tools (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER REFERENCES voice_agents(id),
    integration_id VARCHAR(50),
    enabled BOOLEAN DEFAULT TRUE,
    config JSON  -- Tool-specific config
);
```

### 2. Backend API Endpoints

```
POST   /api/v1/integrations/oauth/start
GET    /api/v1/integrations/oauth/callback
POST   /api/v1/integrations/{id}/connect     # For API keys
DELETE /api/v1/integrations/{id}/disconnect
GET    /api/v1/integrations                  # List user's connections
POST   /api/v1/integrations/{id}/test        # Test connection
```

### 3. Pipecat Tool Registry

```python
# backend/app/services/tools/registry.py

class ToolRegistry:
    """Central registry of all available tools"""

    def __init__(self):
        self.tools = {}

    def register_tool(self, integration_id: str, tool_name: str, func: callable):
        """Register a tool function"""
        pass

    def get_tools_for_agent(self, agent_id: int) -> list:
        """Get all enabled tools for an agent"""
        # 1. Query agent_tools table
        # 2. Get user credentials from user_integrations
        # 3. Return callable functions with credentials injected
        pass
```

### 4. Example: Full Google Calendar Implementation

```python
# backend/app/services/tools/google_calendar.py

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

class GoogleCalendarTools:
    def __init__(self, access_token: str, refresh_token: str):
        self.creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            # ... other OAuth params
        )
        self.service = build('calendar', 'v3', credentials=self.creds)

    async def check_availability(self, date: str, start_time: str, end_time: str) -> dict:
        """Check if time slot is available"""
        time_min = f"{date}T{start_time}:00Z"
        time_max = f"{date}T{end_time}:00Z"

        events_result = self.service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        is_available = len(events) == 0

        return {
            "available": is_available,
            "conflicting_events": len(events),
            "suggestion": "Available" if is_available else "Busy"
        }

    async def schedule_meeting(
        self,
        title: str,
        date: str,
        start_time: str,
        duration_minutes: int,
        attendees: list[str] = None
    ) -> dict:
        """Schedule a new meeting"""
        start = f"{date}T{start_time}:00Z"
        end_dt = datetime.fromisoformat(start) + timedelta(minutes=duration_minutes)

        event = {
            'summary': title,
            'start': {'dateTime': start, 'timeZone': 'UTC'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'UTC'},
            'attendees': [{'email': email} for email in (attendees or [])]
        }

        created_event = self.service.events().insert(
            calendarId='primary',
            body=event
        ).execute()

        return {
            "success": True,
            "event_id": created_event['id'],
            "link": created_event.get('htmlLink'),
            "message": f"Meeting '{title}' scheduled for {date} at {start_time}"
        }
```

### 5. Register Tools with Pipecat

```python
# When creating a voice agent session

from app.services.tools.registry import ToolRegistry
from app.services.tools.google_calendar import GoogleCalendarTools

# Get user's integrations
user_integrations = await get_user_integrations(user_id)

# Build tool list for this agent
tools = []
if agent.has_tool_enabled("google-calendar"):
    calendar_creds = user_integrations["google-calendar"]
    calendar_tools = GoogleCalendarTools(
        access_token=calendar_creds.access_token,
        refresh_token=calendar_creds.refresh_token
    )

    tools.extend([
        {
            "name": "check_calendar_availability",
            "description": "Check if user is available at specific time",
            "parameters": { ... },
            "function": calendar_tools.check_availability
        },
        {
            "name": "schedule_meeting",
            "description": "Schedule a meeting on user's calendar",
            "parameters": { ... },
            "function": calendar_tools.schedule_meeting
        }
    ])

# Initialize Pipecat with tools
llm = OpenAILLMService(functions=tools)
```

## What We Have vs What We Need

### ✅ What We Have (UI Layer)
- Integration configuration UI
- OAuth flow UI
- API key management UI
- Connection status display
- Tool selector in agent form

### ❌ What We Need to Build (Functionality Layer)
1. **Backend OAuth Implementation**
   - OAuth redirect handlers
   - Token storage & refresh
   - Credential encryption

2. **Tool Function Implementations**
   - Python functions for each tool
   - API client wrappers (Google, Salesforce, etc.)
   - Error handling & retries

3. **Pipecat Integration**
   - Tool registration system
   - Function calling during conversations
   - Result handling & formatting

4. **Database Models**
   - user_integrations table
   - agent_tools table
   - credential storage

5. **API Endpoints**
   - Integration CRUD
   - OAuth callbacks
   - Test connections

## Next Steps

1. **Choose 2-3 integrations to implement first** (e.g., Google Calendar + Salesforce)
2. **Build backend OAuth handlers**
3. **Implement tool functions**
4. **Register with Pipecat**
5. **Test end-to-end in voice calls**
6. **Add remaining integrations incrementally**

## Estimated Effort

- **Per integration**: 4-8 hours
  - OAuth setup: 2-3 hours
  - Tool functions: 2-3 hours
  - Testing: 1-2 hours

- **Core 3 integrations**: ~20 hours
- **All 15 integrations**: ~80 hours

Should we start with Google Calendar and Salesforce as the first two?
