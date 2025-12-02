"""GPT Realtime API service for Premium tier voice agents."""

import json
import types
import uuid
from typing import Any

import structlog
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.integrations import get_workspace_integrations
from app.api.settings import get_user_api_keys
from app.core.auth import user_id_to_uuid
from app.services.tools.registry import ToolRegistry

logger = structlog.get_logger()

# Language code to human-readable name mapping
LANGUAGE_NAMES: dict[str, str] = {
    "en-US": "English",
    "en-GB": "English (British)",
    "es-ES": "Spanish",
    "es-MX": "Spanish (Mexican)",
    "fr-FR": "French",
    "de-DE": "German",
    "it-IT": "Italian",
    "pt-BR": "Portuguese (Brazilian)",
    "pt-PT": "Portuguese",
    "nl-NL": "Dutch",
    "ja-JP": "Japanese",
    "ko-KR": "Korean",
    "zh-CN": "Chinese (Mandarin)",
    "zh-TW": "Chinese (Traditional)",
    "ru-RU": "Russian",
    "ar-SA": "Arabic",
    "hi-IN": "Hindi",
    "pl-PL": "Polish",
    "tr-TR": "Turkish",
    "vi-VN": "Vietnamese",
    "th-TH": "Thai",
    "id-ID": "Indonesian",
    "ms-MY": "Malay",
    "fil-PH": "Filipino",
}


def build_instructions_with_language(
    system_prompt: str,
    language: str,
    enabled_tools: list[str] | None = None,
    timezone: str | None = None,
) -> str:
    """Build comprehensive voice agent instructions.

    Wraps the user's custom system prompt with voice-specific configuration
    including language requirements, conversation guidelines, and tool context.

    Args:
        system_prompt: The agent's custom system prompt (from frontend UI)
        language: Language code (e.g., "en-US", "es-ES")
        enabled_tools: List of enabled tool IDs (optional, for context)
        timezone: Workspace timezone (e.g., "America/New_York", "UTC")

    Returns:
        Complete instructions string optimized for voice conversations
    """
    language_name = LANGUAGE_NAMES.get(language, language)
    tz_name = timezone or "UTC"

    # Get current date/time in the workspace timezone for context
    from datetime import datetime

    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        current_datetime = now.strftime("%A, %B %d, %Y at %I:%M %p")
    except Exception:
        # Fallback if timezone is invalid
        current_datetime = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

    # Build the complete voice agent instructions
    instructions = f"""[CONTEXT]
Language: {language_name}
Timezone: {tz_name}
Current: {current_datetime}

[RULES]
- Speak ONLY in {language_name}
- All times are in {tz_name} timezone
- For booking tools, use ISO format with timezone offset (e.g., 2024-12-01T14:00:00-05:00)
- Keep responses concise - this is voice, not text
- Summarize tool results naturally

[YOUR ROLE]
{system_prompt}"""

    return instructions


class GPTRealtimeSession:
    """Manages a GPT Realtime API session for a voice call.

    Handles:
    - WebSocket connection to OpenAI Realtime API
    - Internal tool integration
    - Audio streaming
    - Tool call routing to internal tool handlers
    """

    def __init__(
        self,
        db: AsyncSession,
        user_id: int,
        agent_config: dict[str, Any],
        session_id: str | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize GPT Realtime session.

        Args:
            db: Database session
            user_id: User ID (int, from users.id)
            agent_config: Agent configuration (system prompt, enabled integrations, etc.)
            session_id: Optional session ID
            workspace_id: Workspace UUID (required for API key isolation)
        """
        self.db = db
        self.user_id = user_id  # int for ToolRegistry (Contact queries)
        self.user_id_uuid = user_id_to_uuid(user_id)  # UUID for UserSettings queries
        self.workspace_id = workspace_id  # For workspace-isolated API key lookup
        self.agent_config = agent_config
        self.session_id = session_id or str(uuid.uuid4())
        self.connection: Any = None
        self.tool_registry: ToolRegistry | None = None
        self.client: AsyncOpenAI | None = None
        self.logger = logger.bind(
            component="gpt_realtime",
            session_id=self.session_id,
            user_id=str(user_id),
            workspace_id=str(workspace_id) if workspace_id else None,
        )

    async def initialize(self) -> None:
        """Initialize the Realtime session with internal tools."""
        self.logger.info("gpt_realtime_session_initializing", workspace_id=str(self.workspace_id))

        # Get user's API keys from settings (uses UUID)
        # Workspace isolation: only use workspace-specific API keys, no fallback
        self.logger.debug("fetching_user_api_keys", user_id_uuid=str(self.user_id_uuid))
        user_settings = await get_user_api_keys(
            self.user_id_uuid, self.db, workspace_id=self.workspace_id
        )

        if user_settings:
            self.logger.debug(
                "user_settings_retrieved", has_openai_key=bool(user_settings.openai_api_key)
            )
        else:
            self.logger.warning("no_user_settings_found", user_id_uuid=str(self.user_id_uuid))

        # Strictly use workspace API key - no fallback to global key for billing isolation
        if not user_settings or not user_settings.openai_api_key:
            self.logger.warning("workspace_missing_openai_key", workspace_id=str(self.workspace_id))
            raise ValueError(
                "OpenAI API key not configured for this workspace. Please add it in Settings > Workspace API Keys."
            )
        api_key = user_settings.openai_api_key
        self.logger.info("using_workspace_openai_key", key_length=len(api_key))

        # Initialize OpenAI client with user's or global API key
        self.logger.debug("initializing_openai_client")
        self.client = AsyncOpenAI(api_key=api_key)
        self.logger.debug("openai_client_created")

        # Get integration credentials for the workspace
        integrations: dict[str, Any] = {}
        if self.workspace_id:
            self.logger.debug(
                "fetching_workspace_integrations", workspace_id=str(self.workspace_id)
            )
            integrations = await get_workspace_integrations(
                self.user_id_uuid, self.workspace_id, self.db
            )
            self.logger.debug("workspace_integrations_fetched", integration_count=len(integrations))

        # Initialize tool registry with enabled tools and workspace context
        self.logger.debug("initializing_tool_registry")
        self.tool_registry = ToolRegistry(
            self.db, self.user_id, integrations=integrations, workspace_id=self.workspace_id
        )
        self.logger.debug("tool_registry_initialized")

        # Connect to OpenAI Realtime API
        self.logger.info("connecting_to_realtime_api")
        await self._connect_realtime_api()

        # Configure session with agent settings, tools, and audio modality
        self.logger.info("configuring_session_after_connection")
        await self._configure_session()

        self.logger.info("gpt_realtime_session_initialized")

    async def _connect_realtime_api(self) -> None:
        """Establish connection to OpenAI Realtime API using official SDK."""
        if not self.client:
            raise ValueError("OpenAI client not initialized")

        # Use the latest production gpt-realtime model (released Aug 2025)
        model = "gpt-realtime-2025-08-28"
        self.logger.info("connecting_to_openai_realtime", model=model)

        try:
            # Use official SDK's realtime.connect() method
            self.connection = await self.client.beta.realtime.connect(model=model).__aenter__()

            self.logger.info("realtime_connection_established")
            # Note: Session configuration is done in initialize() AFTER tool_registry is set

        except Exception as e:
            self.logger.exception(
                "realtime_connection_failed", error=str(e), error_type=type(e).__name__
            )
            raise

    async def _configure_session(self) -> None:
        """Configure Realtime API session with agent settings and internal tools."""
        if not self.connection or not self.tool_registry:
            self.logger.warning(
                "session_config_skipped",
                has_connection=bool(self.connection),
                has_registry=bool(self.tool_registry),
            )
            return

        # Get tool definitions from registry
        enabled_tools = self.agent_config.get("enabled_tools", [])
        tools = self.tool_registry.get_all_tool_definitions(enabled_tools)

        # Get workspace timezone if available
        workspace_timezone = "UTC"
        if self.workspace_id:
            from app.models.workspace import Workspace

            result = await self.db.execute(
                select(Workspace).where(Workspace.id == self.workspace_id)
            )
            workspace = result.scalar_one_or_none()
            if workspace and workspace.settings:
                workspace_timezone = workspace.settings.get("timezone", "UTC")

        # Build instructions with language directive and timezone
        system_prompt = self.agent_config.get("system_prompt", "You are a helpful voice assistant.")
        language = self.agent_config.get("language", "en-US")
        # Default to marin for natural conversational tone
        voice = self.agent_config.get("voice", "marin")
        temperature = self.agent_config.get("temperature", 0.6)
        instructions = build_instructions_with_language(
            system_prompt, language, timezone=workspace_timezone
        )

        session_config = {
            "modalities": ["text", "audio"],
            "instructions": instructions,
            "voice": voice,
            "temperature": temperature,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {"model": "whisper-1"},
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 200,
                "silence_duration_ms": 200,
            },
            "tools": tools,
            "tool_choice": "auto",
        }

        self.logger.info("configuring_session", tool_count=len(tools), enabled_tools=enabled_tools)

        try:
            # Build session configuration using SDK
            await self.connection.session.update(session=session_config)

            self.logger.info(
                "session_configured",
                tool_count=len(tools),
            )
        except Exception as e:
            self.logger.exception(
                "session_config_failed", error=str(e), error_type=type(e).__name__
            )
            raise

    async def handle_tool_call(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Handle tool call from GPT Realtime by routing to internal tools.

        Args:
            tool_call: Tool call from GPT Realtime

        Returns:
            Tool result
        """
        if not self.tool_registry:
            return {"success": False, "error": "Tool registry not initialized"}

        tool_name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", {})

        self.logger.info(
            "handling_tool_call",
            tool_name=tool_name,
            arguments=arguments,
        )

        # Execute tool via internal tool registry
        result = await self.tool_registry.execute_tool(tool_name, arguments)

        return result

    async def process_realtime_events(self) -> None:
        """Process events from OpenAI Realtime API using official SDK.

        This is the main event loop that:
        1. Receives events from OpenAI
        2. Handles tool calls by routing to internal tool handlers
        3. Sends responses back to OpenAI
        """
        if not self.connection:
            raise RuntimeError("Realtime connection not established")

        try:
            async for event in self.connection:
                try:
                    event_type = event.type

                    self.logger.debug("realtime_event_received", event_type=event_type)

                    # Handle function/tool calls
                    if event_type == "response.function_call_arguments.done":
                        await self.handle_function_call_event(event)

                    # Handle audio output
                    elif event_type == "response.audio.delta":
                        # Audio data available in event.delta
                        pass

                    # Handle transcription
                    elif event_type == "conversation.item.input_audio_transcription.completed":
                        # Transcription available in event.transcript
                        pass

                    # Handle errors
                    elif event_type == "error":
                        self.logger.error("realtime_api_error", error=event.error)

                except Exception as e:
                    self.logger.exception("event_processing_error", error=str(e))

        except Exception as e:
            self.logger.exception("realtime_event_loop_error", error=str(e))
            raise

    async def handle_function_call_event(self, event: Any) -> None:
        """Handle function call from GPT Realtime.

        Args:
            event: Function call event from SDK
        """
        call_id = event.call_id
        name = event.name
        arguments = (
            json.loads(event.arguments) if isinstance(event.arguments, str) else event.arguments
        )

        # Execute tool via internal tool registry
        result = await self.handle_tool_call({"name": name, "arguments": arguments})

        # Send result back using SDK
        if self.connection:
            await self.connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                }
            )

        self.logger.info(
            "function_call_completed",
            call_id=call_id,
            tool_name=name,
            success=result.get("success"),
        )

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio input to GPT Realtime using SDK.

        Args:
            audio_data: PCM16 audio data (raw bytes)
        """
        if not self.connection:
            self.logger.error("send_audio_failed_no_connection")
            return

        try:
            import base64

            self.logger.debug("send_audio_called", audio_bytes=len(audio_data))

            # Convert raw bytes to base64 string as required by OpenAI Realtime API
            audio_base64 = base64.b64encode(audio_data).decode("utf-8")
            self.logger.debug("audio_base64_encoded", base64_length=len(audio_base64))

            # Use SDK's input_audio_buffer.append method
            self.logger.debug("appending_to_input_buffer")
            await self.connection.input_audio_buffer.append(audio=audio_base64)
            self.logger.debug(
                "audio_appended_to_realtime",
                size_bytes=len(audio_data),
                base64_length=len(audio_base64),
            )
        except Exception as e:
            self.logger.exception("send_audio_error", error=str(e), error_type=type(e).__name__)

    async def commit_audio(self) -> None:
        """Commit the input audio buffer to trigger OpenAI processing."""
        if not self.connection:
            self.logger.error("commit_audio_failed_no_connection")
            return

        try:
            self.logger.info("committing_audio_buffer_to_openai")
            await self.connection.input_audio_buffer.commit()
            self.logger.info("audio_buffer_committed_successfully")
        except Exception as e:
            self.logger.exception("commit_audio_error", error=str(e), error_type=type(e).__name__)

    async def trigger_initial_response(self, greeting: str | None = None) -> None:
        """Trigger an initial AI response for outbound calls.

        For outbound calls, the AI should speak first rather than waiting for user input.
        This sends a response.create event to trigger the AI to start speaking.

        Args:
            greeting: Optional custom greeting message. If not provided, uses a default.
        """
        if not self.connection:
            self.logger.error("trigger_initial_response_failed_no_connection")
            return

        try:
            self.logger.info("triggering_initial_response", greeting=greeting)

            # Create a conversation item with the greeting instruction
            # Note: We add context but let VAD trigger the response naturally
            # This allows the AI to hear if the user speaks first
            if greeting:
                await self.connection.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": f"[System: The outbound call has connected. If the user hasn't spoken yet, greet them with: {greeting}. If they already introduced themselves, acknowledge what they said and continue naturally.]",
                            }
                        ],
                    }
                )
            else:
                await self.connection.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "[System: The outbound call has connected. If the user hasn't spoken yet, greet them. If they already introduced themselves, acknowledge what they said and continue naturally.]",
                            }
                        ],
                    }
                )

            # Trigger the AI to respond - it will incorporate any user speech it heard
            await self.connection.response.create()

            self.logger.info("initial_response_triggered")
        except Exception as e:
            self.logger.exception(
                "trigger_initial_response_error", error=str(e), error_type=type(e).__name__
            )

    async def cleanup(self) -> None:
        """Cleanup resources."""
        self.logger.info("gpt_realtime_session_cleanup_started")

        # Close Realtime connection
        if self.connection:
            try:
                await self.connection.__aexit__(None, None, None)
            except Exception as e:
                self.logger.exception("connection_close_failed", error=str(e))

        # Cleanup tool registry
        if self.tool_registry:
            # No cleanup needed for internal tools
            pass

        self.logger.info("gpt_realtime_session_cleanup_completed")

    async def __aenter__(self) -> "GPTRealtimeSession":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.cleanup()
