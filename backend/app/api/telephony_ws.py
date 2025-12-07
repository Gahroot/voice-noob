"""Telephony WebSocket endpoints for Twilio and Telnyx media streaming.

These WebSocket endpoints handle the audio streams from Twilio and Telnyx,
connecting them to our AI voice agent pipeline.
"""

import asyncio
import base64
import contextlib
import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.agent import Agent
from app.models.call_record import CallRecord
from app.models.workspace import AgentWorkspace
from app.services.gpt_realtime import GPTRealtimeSession

router = APIRouter(prefix="/ws/telephony", tags=["telephony-ws"])
logger = structlog.get_logger()

# Constants for event logging
EVENT_LOG_THRESHOLD = 20  # Log first N events, then every 100th
INITIAL_EVENT_LOGS = 5  # Number of initial events to log before switching to periodic logging
EVENT_LOG_INTERVAL = 20  # Log every Nth event after initial logs


async def get_agent_workspace_id(agent_id: uuid.UUID, db: AsyncSession) -> uuid.UUID | None:
    """Get workspace ID for an agent."""
    result = await db.execute(
        select(AgentWorkspace.workspace_id).where(AgentWorkspace.agent_id == agent_id).limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def save_transcript_to_call_record(
    call_sid: str,
    transcript: str,
    db: AsyncSession,
    log: Any,
) -> None:
    """Save transcript to the call record.

    Args:
        call_sid: Provider call ID (CallSid for Twilio, call_control_id for Telnyx)
        transcript: Formatted transcript text
        db: Database session
        log: Logger instance
    """
    if not transcript.strip():
        log.debug("empty_transcript_skipped")
        return

    result = await db.execute(select(CallRecord).where(CallRecord.provider_call_id == call_sid))
    call_record = result.scalar_one_or_none()

    if call_record:
        call_record.transcript = transcript
        await db.commit()
        log.info("transcript_saved", record_id=str(call_record.id), length=len(transcript))
    else:
        log.warning("call_record_not_found_for_transcript", call_sid=call_sid)


@router.websocket("/twilio/{agent_id}")
async def twilio_media_stream(
    websocket: WebSocket,
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """WebSocket endpoint for Twilio Media Streams.

    Twilio sends audio via Media Streams in mulaw format at 8kHz.
    This endpoint bridges that audio to our GPT Realtime session.

    Message format from Twilio:
    - {"event": "connected", "protocol": "Call", "version": "1.0.0"}
    - {"event": "start", "start": {"streamSid": "...", "callSid": "..."}}
    - {"event": "media", "media": {"payload": "base64_audio"}}
    - {"event": "stop"}
    """
    session_id = str(uuid.uuid4())
    log = logger.bind(
        endpoint="twilio_media_stream",
        agent_id=agent_id,
        session_id=session_id,
    )

    await websocket.accept()
    log.info("twilio_websocket_connected")

    stream_sid: str = ""
    call_sid: str = ""

    try:
        # Load agent configuration
        result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
        agent = result.scalar_one_or_none()

        if not agent:
            log.error("agent_not_found")
            await websocket.close(code=4004, reason="Agent not found")
            return

        if not agent.is_active:
            log.error("agent_not_active")
            await websocket.close(code=4003, reason="Agent is not active")
            return

        log.info("agent_loaded", agent_name=agent.name)

        # agent.user_id is now directly the integer user ID
        user_id_int = agent.user_id

        # Get workspace for the agent
        workspace_id = await get_agent_workspace_id(agent.id, db)

        # Build agent config
        agent_config = {
            "system_prompt": agent.system_prompt,
            "enabled_tools": agent.enabled_tools,
            "language": agent.language,
            "voice": agent.voice or "shimmer",
            "enable_transcript": agent.enable_transcript,
            "initial_greeting": agent.initial_greeting,
        }

        # Initialize GPT Realtime session
        async with GPTRealtimeSession(
            db=db,
            user_id=user_id_int,
            agent_config=agent_config,
            session_id=session_id,
            workspace_id=workspace_id,
        ) as realtime_session:
            # Handle Twilio media stream and capture call_sid
            call_sid = await _handle_twilio_stream(
                websocket=websocket,
                realtime_session=realtime_session,
                log=log,
                enable_transcript=agent.enable_transcript,
            )

            # Save transcript to call record if enabled
            if agent.enable_transcript and call_sid:
                transcript = realtime_session.get_transcript()
                await save_transcript_to_call_record(call_sid, transcript, db, log)

    except WebSocketDisconnect:
        log.info("twilio_websocket_disconnected")
    except Exception as e:
        log.exception("twilio_websocket_error", error=str(e))
    finally:
        log.info("twilio_websocket_closed", stream_sid=stream_sid, call_sid=call_sid)


async def _handle_twilio_stream(  # noqa: PLR0915
    websocket: WebSocket,
    realtime_session: GPTRealtimeSession,
    log: Any,
    enable_transcript: bool = False,
) -> str:
    """Handle Twilio Media Stream messages.

    Args:
        websocket: WebSocket connection from Twilio
        realtime_session: GPT Realtime session
        log: Logger instance
        enable_transcript: Whether to capture transcript

    Returns:
        The call_sid for transcript saving
    """
    stream_sid = ""
    call_sid = ""
    should_end_call = False  # Flag to signal call should end

    async def twilio_to_realtime() -> None:
        """Forward audio from Twilio to GPT Realtime."""
        nonlocal stream_sid, call_sid, should_end_call

        try:
            while not should_end_call:
                message = await websocket.receive_text()
                data = json.loads(message)
                event = data.get("event", "")

                if event == "connected":
                    log.info("twilio_stream_connected")

                elif event == "start":
                    start_data = data.get("start", {})
                    stream_sid = start_data.get("streamSid", "")
                    call_sid = start_data.get("callSid", "")
                    log.info(
                        "twilio_stream_started",
                        stream_sid=stream_sid,
                        call_sid=call_sid,
                    )

                elif event == "media":
                    # Decode base64 mulaw audio and forward to Realtime
                    media = data.get("media", {})
                    payload = media.get("payload", "")
                    if payload:
                        audio_bytes = base64.b64decode(payload)
                        await realtime_session.send_audio(audio_bytes)

                elif event == "stop":
                    log.info("twilio_stream_stopped")
                    break

                elif event == "mark":
                    # Mark events indicate playback position
                    log.debug("twilio_mark_event", name=data.get("mark", {}).get("name"))

        except WebSocketDisconnect:
            log.info("twilio_to_realtime_disconnected")
        except Exception as e:
            log.exception("twilio_to_realtime_error", error=str(e))

    async def realtime_to_twilio() -> None:  # noqa: PLR0912, PLR0915
        """Forward audio from GPT Realtime to Twilio."""
        nonlocal should_end_call
        # Track if end_call was requested
        end_call_requested = False

        try:
            if not realtime_session.connection:
                log.error("no_realtime_connection")
                return

            log.info("realtime_to_twilio_started", waiting_for_events=True)
            event_count = 0
            greeting_triggered = False  # Track if we've triggered the greeting

            async for event in realtime_session.connection:
                event_type = event.type
                event_count += 1

                # Log all events for debugging
                if event_count <= EVENT_LOG_THRESHOLD or event_count % 100 == 0:
                    log.info("realtime_event_received", event_type=event_type, count=event_count)

                # Trigger initial greeting after session is configured
                # This avoids race condition where audio events arrive before listener is ready
                if event_type == "session.updated" and not greeting_triggered:
                    greeting_triggered = True
                    triggered = await realtime_session.trigger_initial_greeting()
                    if triggered:
                        log.info("initial_greeting_triggered_after_session_update")

                # Handle audio output
                elif event_type == "response.audio.delta":
                    # Get audio delta and send to Twilio
                    # Check various possible attribute names for the audio data
                    delta_data = getattr(event, "delta", None)
                    if not delta_data:
                        # Log event attributes for debugging
                        log.warning(
                            "audio_delta_missing",
                            event_attrs=dir(event),
                            has_delta=hasattr(event, "delta"),
                        )
                        continue

                    try:
                        audio_bytes = base64.b64decode(delta_data)
                        # Encode for Twilio (already in g711_ulaw format now)
                        payload = base64.b64encode(audio_bytes).decode("utf-8")
                        log.info(
                            "sending_audio_to_twilio",
                            audio_size=len(audio_bytes),
                            stream_sid=stream_sid,
                        )
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {"payload": payload},
                                }
                            )
                        )
                    except Exception as audio_err:
                        log.exception("audio_send_error", error=str(audio_err))

                # Handle tool calls
                elif event_type == "response.function_call_arguments.done":
                    log.info(
                        "handling_function_call",
                        call_id=event.call_id,
                        name=event.name,
                    )
                    result = await realtime_session.handle_function_call_event(event)
                    # Check if end_call was requested
                    if result.get("action") == "end_call":
                        log.info("end_call_action_detected", reason=result.get("reason"))
                        end_call_requested = True
                        # Continue processing to let the AI finish its response

                # Capture transcript events
                elif (
                    enable_transcript
                    and event_type == "conversation.item.input_audio_transcription.completed"
                ):
                    # User speech transcription
                    if hasattr(event, "transcript") and event.transcript:
                        realtime_session.add_user_transcript(event.transcript)
                        log.debug("user_transcript_captured", length=len(event.transcript))

                elif enable_transcript and event_type == "response.audio_transcript.delta":
                    # Assistant speech transcript delta
                    if hasattr(event, "delta") and event.delta:
                        realtime_session.accumulate_assistant_text(event.delta)

                elif enable_transcript and event_type == "response.audio_transcript.done":
                    # Assistant speech transcript complete
                    realtime_session.flush_assistant_text()

                # Handle response completion - check if we should end the call
                elif event_type == "response.done":
                    log.debug("realtime_event", event_type=event_type)
                    if end_call_requested:
                        log.info("ending_call_after_response_complete")
                        should_end_call = True
                        break

                # Log other events
                elif event_type in [
                    "response.audio.done",
                    "input_audio_buffer.speech_started",
                    "input_audio_buffer.speech_stopped",
                ]:
                    log.debug("realtime_event", event_type=event_type)

        except Exception as e:
            log.exception("realtime_to_twilio_error", error=str(e))

    # Run both directions concurrently with timeout to prevent hung tasks
    try:
        await asyncio.wait_for(
            asyncio.gather(
                twilio_to_realtime(),
                realtime_to_twilio(),
                return_exceptions=True,
            ),
            timeout=300.0,  # 5 minute max call duration before forced cleanup
        )
    except TimeoutError:
        log.warning("twilio_bridge_timeout", message="Call exceeded max duration, forcing cleanup")

    # Close WebSocket to hang up the call if end_call was triggered
    if should_end_call:
        log.info("closing_websocket_for_end_call")
        with contextlib.suppress(Exception):
            await websocket.close(code=1000, reason="Call ended by agent")

    return call_sid


@router.websocket("/telnyx/{agent_id}")
async def telnyx_media_stream(
    websocket: WebSocket,
    agent_id: str,
    workspace_id: str = "",
    db: AsyncSession = Depends(get_db),
) -> None:
    """WebSocket endpoint for Telnyx Media Streams.

    Telnyx sends audio via Media Streams in PCMU format at 8kHz.
    This endpoint bridges that audio to our GPT Realtime session.

    Message format from Telnyx:
    - {"event": "start", "stream_id": "...", "call_control_id": "..."}
    - {"event": "media", "media": {"payload": "base64_audio"}}
    - {"event": "stop"}

    Args:
        websocket: WebSocket connection from Telnyx
        agent_id: Agent UUID
        workspace_id: Workspace UUID (required for API key isolation)
        db: Database session
    """
    session_id = str(uuid.uuid4())
    log = logger.bind(
        endpoint="telnyx_media_stream",
        agent_id=agent_id,
        workspace_id=workspace_id,
        session_id=session_id,
    )

    await websocket.accept()
    log.info("telnyx_websocket_connected")

    stream_id: str = ""
    call_control_id: str = ""

    try:
        # Parse and validate workspace_id
        workspace_uuid: uuid.UUID | None = None
        if workspace_id:
            try:
                workspace_uuid = uuid.UUID(workspace_id)
            except ValueError:
                log.exception("invalid_workspace_id_format")
                await websocket.close(code=4000, reason="Invalid workspace ID format")
                return

        # Load agent configuration
        result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
        agent = result.scalar_one_or_none()

        if not agent:
            log.error("agent_not_found")
            await websocket.close(code=4004, reason="Agent not found")
            return

        if not agent.is_active:
            log.error("agent_not_active")
            await websocket.close(code=4003, reason="Agent is not active")
            return

        log.info("agent_loaded", agent_name=agent.name)

        # agent.user_id is now directly the integer user ID
        user_id_int = agent.user_id

        # Get workspace for the agent (use parsed workspace_uuid or query from agent)
        if not workspace_uuid:
            workspace_uuid = await get_agent_workspace_id(agent.id, db)
        workspace_id_str = str(workspace_uuid) if workspace_uuid else None

        # Build agent config
        agent_config = {
            "system_prompt": agent.system_prompt,
            "enabled_tools": agent.enabled_tools,
            "language": agent.language,
            "voice": agent.voice or "shimmer",
            "enable_transcript": agent.enable_transcript,
            "initial_greeting": agent.initial_greeting,
        }

        log.info(
            "initializing_gpt_realtime_session",
            agent_name=agent.name,
            language=agent.language,
            voice=agent.voice or "shimmer",
            enabled_tools=agent.enabled_tools,
        )

        # Initialize GPT Realtime session with workspace context for API key isolation
        async with GPTRealtimeSession(
            db=db,
            user_id=user_id_int,
            agent_config=agent_config,
            session_id=session_id,
            workspace_id=workspace_uuid,
        ) as realtime_session:
            # Handle Telnyx media stream with initial greeting for outbound calls
            call_control_id = await _handle_telnyx_stream(
                websocket=websocket,
                realtime_session=realtime_session,
                log=log,
                initial_greeting=agent.initial_greeting,
                agent_id=agent_id,
                workspace_id=workspace_id_str,
                db=db,
                enable_transcript=agent.enable_transcript,
            )

            # Save transcript to call record if enabled
            if agent.enable_transcript and call_control_id:
                transcript = realtime_session.get_transcript()
                await save_transcript_to_call_record(call_control_id, transcript, db, log)

    except WebSocketDisconnect:
        log.info("telnyx_websocket_disconnected")
    except Exception as e:
        log.exception("telnyx_websocket_error", error=str(e))
    finally:
        log.info("telnyx_websocket_closed", stream_id=stream_id, call_control_id=call_control_id)


async def _handle_telnyx_stream(  # noqa: PLR0915
    websocket: WebSocket,
    realtime_session: GPTRealtimeSession,
    log: Any,
    initial_greeting: str | None = None,
    agent_id: str | None = None,
    workspace_id: str | None = None,
    db: AsyncSession | None = None,
    enable_transcript: bool = False,
) -> str:
    """Handle Telnyx Media Stream messages.

    Args:
        websocket: WebSocket connection from Telnyx
        realtime_session: GPT Realtime session
        log: Logger instance
        initial_greeting: Optional greeting for outbound calls
        agent_id: Agent UUID (for hangup)
        workspace_id: Workspace ID (for hangup)
        db: Database session (for hangup)
        enable_transcript: Whether to capture transcript

    Returns:
        The call_control_id for transcript saving
    """
    stream_id = ""
    call_control_id = ""
    should_end_call = False  # Flag to signal call should end
    # Events for synchronization
    stream_ready = asyncio.Event()
    events_listener_ready = asyncio.Event()

    async def telnyx_to_realtime() -> None:  # noqa: PLR0915
        """Forward audio from Telnyx to GPT Realtime."""
        nonlocal stream_id, call_control_id, should_end_call

        try:
            audio_chunk_count = 0
            log.info("telnyx_to_realtime_loop_started")
            while not should_end_call:
                message = await websocket.receive_text()
                data = json.loads(message)
                msg_event = data.get("event", "")
                log.debug("telnyx_message_received", msg_event=msg_event)

                if msg_event == "start":
                    stream_id = data.get("stream_id", "")
                    start_data = data.get("start", {})
                    call_control_id = start_data.get("call_control_id", "")
                    log.info(
                        "telnyx_stream_started",
                        stream_id=stream_id,
                        call_control_id=call_control_id,
                    )
                    # Signal that stream is ready for sending audio
                    stream_ready.set()

                    # Wait for the event listener to be ready before triggering the AI response
                    # This prevents the race condition where events are generated before listener is active
                    log.info("waiting_for_events_listener_ready")
                    try:
                        await asyncio.wait_for(events_listener_ready.wait(), timeout=10.0)
                        log.info("events_listener_ready_confirmed")
                    except TimeoutError:
                        log.warning("events_listener_ready_timeout", timeout_seconds=10)

                    # Brief delay to let initial audio come in before AI speaks
                    # This allows the AI to hear if the user says something first
                    log.info("waiting_for_initial_audio")
                    await asyncio.sleep(0.8)  # 800ms - enough for "Hello?" but not too long

                    # Trigger initial AI response for outbound calls
                    log.info("triggering_initial_ai_greeting")
                    await realtime_session.trigger_initial_response(initial_greeting)

                elif msg_event == "media":
                    # Decode base64 PCMU audio and convert to PCM16 for OpenAI
                    media = data.get("media", {})
                    payload = media.get("payload", "")
                    if payload:
                        import audioop

                        try:
                            pcmu_bytes = base64.b64decode(payload)
                            log.debug("pcmu_decoded", pcmu_bytes_length=len(pcmu_bytes))

                            # Convert PCMU (mulaw) to PCM16 at 8kHz
                            pcm16_8k = audioop.ulaw2lin(pcmu_bytes, 2)
                            log.debug("audio_converted_to_pcm16", pcm16_bytes_length=len(pcm16_8k))

                            # Upsample from 8kHz to 24kHz for OpenAI Realtime API
                            pcm16_24k, _ = audioop.ratecv(pcm16_8k, 2, 1, 8000, 24000, None)
                            log.debug(
                                "audio_upsampled", from_size=len(pcm16_8k), to_size=len(pcm16_24k)
                            )

                            log.debug("sending_audio_to_realtime", size_bytes=len(pcm16_24k))
                            await realtime_session.send_audio(pcm16_24k)
                            log.debug("audio_sent_successfully")

                            audio_chunk_count += 1
                            # Log periodically to avoid spam
                            if audio_chunk_count % 50 == 0:
                                log.info("audio_chunks_sent", count=audio_chunk_count)

                            # NOTE: Don't commit manually - server_vad handles turn detection
                            # Committing too frequently interrupts OpenAI's speech detection
                        except Exception as e:
                            log.exception(
                                "audio_conversion_error", error=str(e), error_type=type(e).__name__
                            )

                elif msg_event == "stop":
                    log.info("telnyx_stream_stopped", total_chunks=audio_chunk_count)
                    # Final commit to process any remaining audio
                    if audio_chunk_count > 0:
                        log.info("final_audio_commit", chunk_count=audio_chunk_count)
                        await realtime_session.commit_audio()
                        log.info("final_commit_complete")
                    break

        except WebSocketDisconnect:
            log.info("telnyx_to_realtime_disconnected")
        except Exception as e:
            log.exception("telnyx_to_realtime_error", error=str(e), error_type=type(e).__name__)

    async def realtime_to_telnyx() -> None:  # noqa: PLR0912, PLR0915
        """Forward audio from GPT Realtime to Telnyx."""
        nonlocal should_end_call
        log.info("realtime_to_telnyx_coroutine_started")

        # Track if end_call was requested
        end_call_requested = False

        try:
            if not realtime_session.connection:
                log.error("no_realtime_connection")
                return

            log.info("realtime_to_telnyx_has_connection")

            # Wait for stream to be ready before processing events
            # This ensures stream_id is set before we try to send audio
            log.info("waiting_for_stream_ready")
            try:
                await asyncio.wait_for(stream_ready.wait(), timeout=30.0)
                log.info("stream_ready_received", stream_id=stream_id)
            except TimeoutError:
                log.warning("stream_ready_timeout", timeout_seconds=30)
                return

            audio_event_count = 0
            total_event_count = 0
            log.info(
                "starting_realtime_event_loop",
                connection_type=type(realtime_session.connection).__name__,
            )

            # Signal that the event listener is now ready to receive events
            # This must be done BEFORE we start iterating to prevent race conditions
            log.info("event_listener_now_ready", about_to_listen=True)
            events_listener_ready.set()

            log.info("entering_async_for_loop_for_realtime_events")
            async for event in realtime_session.connection:
                if total_event_count == 0:
                    log.info(
                        "first_realtime_event_received",
                        event_type=event.type,
                        event_class=type(event).__name__,
                    )
                event_type = event.type
                total_event_count += 1
                if (
                    total_event_count <= INITIAL_EVENT_LOGS
                    or total_event_count % EVENT_LOG_INTERVAL == 0
                ):
                    log.info(
                        "realtime_event_received",
                        event_type=event_type,
                        total_events=total_event_count,
                    )
                else:
                    log.debug(
                        "realtime_event_received",
                        event_type=event_type,
                        total_events=total_event_count,
                    )

                try:
                    # Handle tool calls
                    if event_type == "response.function_call_arguments.done":
                        log.info(
                            "handling_function_call",
                            call_id=event.call_id,
                            name=event.name,
                        )
                        result = await realtime_session.handle_function_call_event(event)

                        # Check if end_call was requested
                        if result.get("action") == "end_call":
                            log.info("end_call_action_detected", reason=result.get("reason"))
                            end_call_requested = True
                            # Continue processing to let the AI finish its response

                    # Handle audio output - convert from PCM16 to PCMU for Telnyx
                    elif event_type == "response.audio.delta":
                        if hasattr(event, "delta") and event.delta:
                            import audioop

                            try:
                                log.debug(
                                    "audio_delta_event_received",
                                    delta_length=len(event.delta) if event.delta else 0,
                                )

                                # Decode base64 PCM16 from OpenAI (24kHz)
                                pcm16_24k = base64.b64decode(event.delta)
                                log.debug("pcm16_decoded", pcm16_bytes_length=len(pcm16_24k))

                                # Resample from 24kHz to 8kHz for Telnyx
                                pcm16_8k, _ = audioop.ratecv(pcm16_24k, 2, 1, 24000, 8000, None)
                                log.debug(
                                    "audio_resampled",
                                    from_size=len(pcm16_24k),
                                    to_size=len(pcm16_8k),
                                )

                                # Convert PCM16 to PCMU (mulaw) for Telnyx
                                pcmu_bytes = audioop.lin2ulaw(pcm16_8k, 2)
                                log.debug(
                                    "audio_converted_to_pcmu", pcmu_bytes_length=len(pcmu_bytes)
                                )

                                # Encode back to base64 for Telnyx
                                payload = base64.b64encode(pcmu_bytes).decode("utf-8")
                                log.debug("payload_encoded", payload_length=len(payload))

                                # Verify stream_id is set before sending
                                if not stream_id:
                                    log.warning("stream_id_not_set_skipping_audio")
                                    continue

                                log.debug("sending_media_to_telnyx", stream_id=stream_id)
                                # Telnyx bidirectional streaming format - no stream_id needed for outbound
                                await websocket.send_text(
                                    json.dumps(
                                        {
                                            "event": "media",
                                            "media": {"payload": payload},
                                        }
                                    )
                                )
                                log.debug("media_sent_to_telnyx")

                                audio_event_count += 1
                                if audio_event_count == 1:
                                    log.info(
                                        "first_audio_delta_sent_to_telnyx",
                                        pcm16_bytes=len(pcm16_24k),
                                        stream_id=stream_id,
                                    )
                                elif audio_event_count % 10 == 0:
                                    log.info("audio_delta_batch", audio_events=audio_event_count)
                            except Exception as e:
                                log.exception(
                                    "audio_delta_error", error=str(e), error_type=type(e).__name__
                                )

                    # Capture transcript events
                    elif (
                        enable_transcript
                        and event_type == "conversation.item.input_audio_transcription.completed"
                    ):
                        # User speech transcription
                        if hasattr(event, "transcript") and event.transcript:
                            realtime_session.add_user_transcript(event.transcript)
                            log.debug("user_transcript_captured", length=len(event.transcript))

                    elif enable_transcript and event_type == "response.audio_transcript.delta":
                        # Assistant speech transcript delta
                        if hasattr(event, "delta") and event.delta:
                            realtime_session.accumulate_assistant_text(event.delta)

                    elif enable_transcript and event_type == "response.audio_transcript.done":
                        # Assistant speech transcript complete
                        realtime_session.flush_assistant_text()

                    # Handle error events from OpenAI - log the actual error
                    elif event_type == "error":
                        error_msg = getattr(event, "error", None)
                        error_code = (
                            getattr(error_msg, "code", "unknown") if error_msg else "unknown"
                        )
                        error_message = (
                            getattr(error_msg, "message", str(event)) if error_msg else str(event)
                        )
                        log.error(
                            "openai_realtime_error",
                            error_code=error_code,
                            error_message=error_message,
                        )

                    # Handle response completion - check if we should end the call
                    elif event_type == "response.done":
                        log.info("realtime_event", event_type=event_type)

                        # If end_call was requested and the response is done, hangup
                        if end_call_requested:
                            log.info(
                                "response_complete_after_end_call_hanging_up",
                                call_control_id=call_control_id,
                            )
                            # Hangup the call via Telnyx API
                            if call_control_id and agent_id and db:
                                try:
                                    from app.models.agent import Agent

                                    # Get agent to find user
                                    result_agent = await db.execute(
                                        select(Agent).where(Agent.id == uuid.UUID(agent_id))
                                    )
                                    agent_obj = result_agent.scalar_one_or_none()

                                    if agent_obj:
                                        # agent_obj.user_id is already the integer user ID
                                        user_id_int_for_hangup = agent_obj.user_id
                                        if user_id_int_for_hangup:
                                            from app.api.telephony import get_telnyx_service

                                            workspace_uuid_for_hangup = (
                                                uuid.UUID(workspace_id) if workspace_id else None
                                            )
                                            telnyx_service = await get_telnyx_service(
                                                user_id_int_for_hangup,
                                                db,
                                                workspace_uuid_for_hangup,
                                            )
                                            if telnyx_service:
                                                await telnyx_service.hangup_call(call_control_id)
                                                log.info(
                                                    "call_hangup_sent",
                                                    call_control_id=call_control_id,
                                                )
                                            else:
                                                log.warning("no_telnyx_service_for_hangup")
                                        else:
                                            log.warning("user_id_not_found_for_hangup")
                                    else:
                                        log.warning("agent_not_found_for_hangup")
                                except Exception as hangup_error:
                                    log.exception(
                                        "hangup_call_error",
                                        error=str(hangup_error),
                                        error_type=type(hangup_error).__name__,
                                    )
                            # Set flag and break the loop to end the call
                            should_end_call = True
                            break

                    # Log other relevant events for debugging
                    elif event_type in [
                        "response.audio.done",
                        "input_audio_buffer.speech_started",
                        "input_audio_buffer.speech_stopped",
                    ]:
                        log.debug("realtime_event", event_type=event_type)

                    else:
                        log.debug("unhandled_realtime_event", event_type=event_type)

                except Exception as e:
                    log.exception(
                        "event_processing_error",
                        event_type=event_type,
                        error=str(e),
                        error_type=type(e).__name__,
                    )

        except StopAsyncIteration:
            log.info("realtime_connection_closed_normally", total_events=total_event_count)
        except Exception as e:
            log.exception(
                "realtime_to_telnyx_error",
                error=str(e),
                error_type=type(e).__name__,
                total_events=total_event_count,
            )

    # Run both directions concurrently with timeout to prevent hung tasks
    log.info("starting_bidirectional_stream_tasks")
    try:
        await asyncio.wait_for(
            asyncio.gather(
                telnyx_to_realtime(),
                realtime_to_telnyx(),
                return_exceptions=True,
            ),
            timeout=300.0,  # 5 minute max call duration before forced cleanup
        )
    except TimeoutError:
        log.warning("telnyx_bridge_timeout", message="Call exceeded max duration, forcing cleanup")

    log.info("bidirectional_stream_tasks_completed")

    # Close WebSocket to hang up the call if end_call was triggered
    if should_end_call:
        log.info("closing_websocket_for_end_call")
        with contextlib.suppress(Exception):
            await websocket.close(code=1000, reason="Call ended by agent")

    return call_control_id
