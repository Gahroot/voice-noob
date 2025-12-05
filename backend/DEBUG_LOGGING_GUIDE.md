# Voice Agent Audio Pipeline Debug Logging Guide

This guide explains all the logging added to diagnose audio flow in voice calls.

## Expected Log Flow for a Successful Call

### Phase 1: WebSocket Connection & Realtime Session Init
```
telnyx_websocket_connected          # WebSocket accepted
gpt_realtime_session_initializing   # Starting to initialize session
fetching_user_api_keys              # Looking up OpenAI API key
user_settings_retrieved             # Found API key config
using_workspace_openai_key          # Using workspace-isolated key
initializing_openai_client          # Creating OpenAI client
openai_client_created               # Client created successfully
fetching_workspace_integrations     # Getting tool credentials
workspace_integrations_fetched      # Integrations loaded
initializing_tool_registry          # Setting up tool registry
tool_registry_initialized           # Tool registry ready
connecting_to_realtime_api          # Connecting to OpenAI
realtime_connection_established     # Connected to OpenAI
session_configured                  # Session config sent to OpenAI
gpt_realtime_session_initialized    # Ready to handle audio
realtime_to_telnyx_starting         # Starting to listen for OpenAI events
telnyx_to_realtime_loop_started     # Starting to listen for Telnyx audio
```

### Phase 2: Call Answer (User Says "Hello")
```
telnyx_message_received event=start         # Telnyx sends stream start
telnyx_stream_started                       # Stream ID and call ID extracted
telnyx_message_received event=media         # Audio from user arriving
pcmu_decoded pcmu_bytes_length=160          # PCMU audio decoded (8000 Hz = 160 bytes)
audio_converted pcm16_bytes_length=320      # Converted to PCM16 (double size)
sending_audio_to_realtime size_bytes=320    # Sending to OpenAI buffer
audio_sent_successfully                     # Audio added to buffer
audio_chunk_count count=1                   # Tracking chunks
```

### Phase 3: Audio Buffer Commits (Every 10 Chunks)
```
telnyx_message_received event=media
pcmu_decoded pcmu_bytes_length=160
audio_converted pcm16_bytes_length=320
sending_audio_to_realtime size_bytes=320
audio_sent_successfully
audio_chunk_count count=10                  # At 10 chunks...
committing_audio_buffer chunk_count=10      # ...trigger OpenAI processing
committing_audio_buffer_to_openai           # Calling commit()
audio_buffer_committed_successfully         # Commit successful
audio_buffer_committed chunk_count=10       # Logged
```

### Phase 4: OpenAI Generating Response
```
realtime_event_received event_type=input_audio_buffer.speech_started  # User detected
realtime_event_received event_type=response.audio.delta               # OpenAI CRITICAL!
audio_delta_event_received delta_length=XXX                           # Audio chunk received
pcm16_decoded pcm16_bytes_length=320                                  # Decoded from base64
audio_converted_to_pcmu pcmu_bytes_length=160                         # Converted to PCMU
payload_encoded payload_length=XXX                                    # Base64 encoded
sending_media_to_telnyx stream_id=XYZ                                 # Sending to phone
media_sent_to_telnyx                                                  # Sent successfully
first_audio_delta_received pcm16_bytes=320                            # FIRST audio received
```

### Phase 5: Conversation Continues
```
telnyx_message_received event=media
# ... audio from user ...
realtime_event_received event_type=response.audio.delta               # OpenAI continues
audio_delta_event_received delta_length=XXX
audio_delta_batch audio_events=20                                     # Batches logged
# ... audio sent to phone ...
```

### Phase 6: Call End
```
telnyx_message_received event=stop
telnyx_stream_stopped total_chunks=45
final_audio_commit chunk_count=45
committing_audio_buffer_to_openai
audio_buffer_committed_successfully
final_commit_complete
telnyx_websocket_closed
realtime_to_telnyx_error ConnectionClosedOK                           # Normal closure
gpt_realtime_session_cleanup_started
gpt_realtime_session_cleanup_completed
```

## Critical Log Points to Watch

### If You See Complete Silence:

1. **No `telnyx_stream_started`**
   - WebSocket isn't connecting from Telnyx
   - Check: Telnyx webhook URL is correct and reachable
   - Check: No errors before this log

2. **`telnyx_stream_started` but no `telnyx_message_received event=media`**
   - Stream connected but no audio from user
   - User hasn't spoken into phone
   - Check: Phone call is active and audio is working

3. **Audio received but no `first_audio_delta_received`**
   - This is the biggest clue - OpenAI isn't generating audio
   - Check: `audio_buffer_committed_successfully` logs appear
   - Check: No errors in `realtime_to_telnyx`
   - Possible causes:
     - OpenAI API key is invalid or expired
     - Audio buffer not being committed properly
     - OpenAI session misconfigured
     - OpenAI API response errors (check for `realtime_to_telnyx_error`)

4. **`first_audio_delta_received` but no audio on phone**
   - OpenAI is working but Telnyx audio isn't reaching phone
   - Check: `audio_delta_error` logs (conversion errors)
   - Check: `media_sent_to_telnyx` logs appear
   - Check: WebSocket still connected to Telnyx
   - Possible causes:
     - Audio conversion error (audioop exception)
     - WebSocket disconnected during response
     - Telnyx not accepting media messages

## How to Debug Specific Issues

### Silence During User Speech
Look for these sequences:
1. `audio_chunk_count` increasing every media event
2. `audio_buffer_committed_successfully` every 10 chunks
3. `realtime_event_received` events from OpenAI

If counts don't increase → no audio from user
If commits succeed but no realtime events → OpenAI not processing

### Audio Conversion Errors
Search logs for: `audio_conversion_error` or `audio_delta_error`
- Most common: Exception details should show the audioop error
- Usually means invalid audio size or format mismatch

### Workspace/API Key Issues
Search logs for: `workspace_missing_openai_key` or `no_user_settings_found`
- Agent's workspace doesn't have OpenAI key configured
- User needs to add key in Settings > Workspace API Keys

### OpenAI Connection Issues
Search logs for: `realtime_connection_failed` or `session_config_failed`
- OpenAI SDK connection failed
- Session configuration rejected by OpenAI
- Check OpenAI API status and key validity

## Log Filtering Commands

Show only audio pipeline critical events:
```bash
grep -E "stream_started|first_audio_delta|audio_buffer_committed" logs.txt
```

Show audio counts:
```bash
grep -E "audio_chunk_count|audio_delta_batch" logs.txt
```

Show all errors in audio pipeline:
```bash
grep -E "error|exception|failed" logs.txt | grep -i audio
```

Show complete timeline for a call:
```bash
grep SESSION_ID logs.txt  # where SESSION_ID is from initial log
```

## Testing Checklist

- [ ] See `gpt_realtime_session_initialized` (connection successful)
- [ ] See `telnyx_stream_started` (call answered)
- [ ] See `audio_chunk_count` increasing (user audio arriving)
- [ ] See `audio_buffer_committed_successfully` (audio processing triggered)
- [ ] See `first_audio_delta_received` (OpenAI generating response)
- [ ] See `media_sent_to_telnyx` (audio sent back to phone)
- [ ] Hear AI voice on phone speaker
