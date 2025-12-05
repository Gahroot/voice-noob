# Cal.com Integration Fix

## Issue Summary

The Cal.com event types endpoint was returning a 404 error because the backend was using an incorrect API version header.

**Error Messages:**
- Frontend: `Failed to load event types. Cal.com API returned status 404: {"status":"error","timestamp":"2025-12-03T16:00:26.376Z","path":"/v2/event-types","error":{"code":"NotFoundException","message":"Cannot GET /v2/event-types"`
- Frontend: `Request failed with status code 502` (502 Bad Gateway from backend after Cal.com API returned 404)

## Root Cause

The Cal.com API v2 endpoint requires a specific API version header (`cal-api-version`). The backend was using version `2024-08-13`, which is not supported. The correct version is `2024-06-14`.

## Fix Applied

**File:** `backend/app/api/integrations.py:558`

**Changed:**
```python
"cal-api-version": "2024-08-13",  # ❌ Not supported
```

**To:**
```python
"cal-api-version": "2024-06-14",  # ✅ Supported
```

## Verification

### 1. Test Script Output

The test script (`backend/test_calcom_api.py`) confirmed:
- ✅ Cal.com V1 API works: `/v1/event-types` with `?apiKey=<key>` parameter
- ❌ Cal.com V2 API with version `2024-08-13`: Returns 404
- ✅ Cal.com V2 API with version `2024-06-14`: Works correctly, returns 3 event types

### 2. Event Types Found

Your Cal.com account has 3 event types:
1. **15 Min Meeting** (ID: 3928133)
2. **30 Min Video Call** (ID: 3928135)
3. **Secret Meeting** (ID: 3928134)

## How to Test in Your Dashboard

1. **Navigate to Agent Settings:**
   - Go to your dashboard at `http://localhost:3000/dashboard`
   - Click on an agent (or create a new one)
   - Scroll to the "Integrations" section
   - Find the "Cal.com" integration

2. **Load Event Types:**
   - Click the "Load Event Types" button
   - You should see: "Loaded 3 event type(s) from Cal.com" (toast notification)
   - The dropdown should populate with your 3 event types

3. **Select Default Event Type:**
   - Choose one of the event types from the dropdown
   - Save the agent settings
   - The agent will now use this event type for scheduling calls

## Technical Details

### API Version History

According to GitHub research:
- Cal.com uses versioned API endpoints with a `cal-api-version` header
- Supported versions found: `2024-06-14`, `2024-04-15`
- Newer version `2024-08-13` appears unsupported or in beta

### API Endpoints

**V1 Endpoint (Legacy):**
```bash
GET https://api.cal.com/v1/event-types?apiKey=<key>
```

**V2 Endpoint (Current):**
```bash
GET https://api.cal.com/v2/event-types
Headers:
  Authorization: Bearer <api_key>
  cal-api-version: 2024-06-14
```

### Response Format

```json
{
  "data": [
    {
      "id": 3928133,
      "title": "15 Min Meeting",
      "slug": "15min",
      "lengthInMinutes": 15
    }
  ]
}
```

## Files Modified

1. ✅ `backend/app/api/integrations.py` - Fixed API version header
2. ✅ `backend/test_calcom_api.py` - Created diagnostic test script

## Backend Auto-Reload

The backend is running with `--reload`, so the changes were automatically picked up without needing a restart.

## Next Steps

1. Test the integration in your dashboard (see "How to Test" above)
2. Select a default event type for your agent
3. Test the agent's ability to book appointments using the selected event type

## If Issues Persist

Run the diagnostic script:
```bash
cd backend
uv run python test_calcom_api.py
```

This will:
- Check if Cal.com integration is connected
- Test both V1 and V2 API endpoints
- Try multiple API versions
- Display your available event types
