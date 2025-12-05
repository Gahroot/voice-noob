# Voice Call Audio Streaming - Debugging Guide

## Issue
Phone rings, user speaks ("hello this is nolan"), but no AI response. Call duration 0 seconds. Audio never streams.

## Root Causes Fixed (Commit)
1. ✅ `call_control_id` extraction now handles JSON webhook format
2. ✅ Removed manual `response.create()` that was blocking audio
3. ✅ Added fallback agent lookup from query parameters

## Debug Checklist

### Step 1: Verify Telnyx Webhook Configuration
Check that Telnyx knows where to send webhooks:

```bash
# See what webhook URL Telnyx has registered
cd backend
python check_telnyx_apps.py
# Look for: "Webhook Event URL: {your-url}/webhooks/telnyx/answer"
```

**Expected:** URL should be `https://your-domain/webhooks/telnyx/answer`
**Problem if:** Shows "NOT SET (INVALID)" or different URL

**Fix if needed:**
```python
# Set in your .env or environment:
PUBLIC_WEBHOOK_URL=https://your-actual-domain.com
```

---

### Step 2: Check Logs When Call Comes In

**Sequence that should appear:**

1. **Webhook received:**
   ```
   "event": "telnyx_outbound_answered"
   "call_control_id": "v3:..." (should NOT be empty!)
   ```

2. **Agent found:**
   ```
   "agent_id_found_from_call_record"
   "agent_name": "Your Agent Name"
   ```

3. **WebSocket established:**
   ```
   "initializing_gpt_realtime_session"
   "agent_name": "..."
   "enabled_tools": [...]
   ```

4. **Audio streaming started:**
   ```
   "telnyx_stream_started"
   "stream_id": "..." (should NOT be empty!)
   ```

5. **Audio received:**
   ```
   "audio_chunk_count": 1
   "audio_chunk_count": 10
   "committing_audio_buffer"
   ```

6. **AI response starting:**
   ```
   "realtime_to_telnyx_starting"
   "first_audio_delta_received"
   ```

7. **Audio sent back:**
   ```
   "media_sent_to_telnyx"
   "audio_delta_batch"
   ```

---

### Step 3: If Logs Show Empty `call_control_id`

**Problem:** Webhook body not being parsed correctly
**Debug:** Check what Telnyx actually sends:

Add temporary logging to `telephony.py` line 920:
```python
log.warning("webhook_raw_body", body_preview=str(body[:500]))
```

Restart server, make a call, check logs for actual webhook format.

Common formats Telnyx uses:
- JSON: `{"data": {"payload": {"call_control_id": "..."}}}`
- Form: `CallControlId=xxx&...`

---

### Step 4: If Logs Show Empty `stream_id`

**Problem:** WebSocket message from Telnyx not arriving or malformed
**Symptom:** Phone rings but WebSocket never connects

**Check:**
1. Is the TeXML response valid? Test with:
```bash
curl -X POST https://api.telnyx.com/v2/calls/test \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d @- << 'EOF'
{"to": "+1234567890", "from": "+9876543210", "webhook_event_url": "https://your-domain/webhooks/telnyx/answer", "webhook_event_method": "POST"}
EOF
```

2. Check WebSocket URL format in logs:
   - Should be: `wss://your-domain/ws/telephony/telnyx/{agent-id}?workspace_id={workspace-id}`
   - Check that `wss://` (not `ws://`) for production

---

### Step 5: OpenAI API Key Issue

If logs show:
```
"workspace_missing_openai_key"
"OpenAI API key not configured for this workspace"
```

**Fix:**
1. Go to Dashboard → Settings → Workspace API Keys
2. Add your OpenAI API key
3. Make sure it's for the workspace you're testing in

---

### Step 6: Run Backend Diagnostics

```bash
cd backend

# Check all imports work
python -c "from app.services.gpt_realtime import GPTRealtimeSession; print('✓ GPT Realtime imports OK')"

# Verify database migrations
alembic current
alembic upgrade head

# Check Telnyx config
python -c "from app.services.telephony.telnyx_service import TelnyxService; print('✓ Telnyx service imports OK')"
```

---

## Key Files to Monitor

| File | What to check |
|------|---|
| `app/api/telephony.py` | Line 945-946: "telnyx_outbound_answered" log |
| `app/api/telephony.py` | Line 960: "agent_id_found_from_call_record" log |
| `app/api/telephony_ws.py` | Line 305-311: "initializing_gpt_realtime_session" log |
| `app/api/telephony_ws.py` | Line 360-364: "telnyx_stream_started" log |
| `app/services/gpt_realtime.py` | Line 149: "gpt_realtime_session_initializing" log |

---

## Still No Audio?

If all logs appear correctly but no audio plays:

1. **Check Telnyx Media Streams support:**
   - Is Media Streams enabled on your Telnyx account?
   - Do you have call control permissions?

2. **Check OpenAI Realtime API:**
   - Is your API key valid?
   - Do you have realtime API access?
   - Check: `curl -H "Authorization: Bearer YOUR_KEY" https://api.openai.com/v1/models | grep gpt-realtime`

3. **Check audio codec:**
   - Telnyx sends: **PCMU (mulaw)** at 8kHz
   - We convert to: **PCM16** at 16kHz for OpenAI
   - Check logs for "audio_converted" without errors

4. **Check firewall/networking:**
   - Can your server reach `api.openai.com`?
   - Can your server reach `api.telnyx.com`?
   - Can Telnyx reach your webhook URL?

---

## One-Liner Diagnostics

```bash
# All in one - check everything
cd backend && \
echo "=== Telnyx Apps ===" && python check_telnyx_apps.py && \
echo "=== Imports ===" && python -c "from app.services.gpt_realtime import GPTRealtimeSession; print('OK')" && \
echo "=== WebSocket Test ===" && python -c "from app.api.telephony_ws import telnyx_media_stream; print('OK')"
```

---

## Next Steps Tomorrow

1. **Check webhook URL** in Telnyx (most common issue)
2. **Look at actual logs** during test call
3. **Verify call_control_id** is being extracted
4. **Check stream_id** appears in WebSocket
5. **Confirm audio chunks** are flowing both directions

---

## Questions?

When debugging, capture:
```bash
# Full logs from one test call
grep "correlation_id: {YOUR_CALL_ID}" logs.json | jq . | head -50
```

This will show complete call flow for diagnostics.
