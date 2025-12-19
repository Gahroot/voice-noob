"""Hume EVI (Empathic Voice Interface) service for voice agents.

Hume EVI is a voice-to-voice AI with emotion understanding capabilities.
This service manages WebSocket connections to Hume's EVI API.

Latest models (Dec 2025):
- EVI 3: English-only, highest quality voice
- EVI 4-mini: Multilingual (11 languages), lower latency
"""

import json
import types
import uuid
from typing import TYPE_CHECKING, Any

import structlog
from hume.client import AsyncHumeClient
from hume.empathic_voice.types import SessionSettings

if TYPE_CHECKING:
    from hume.empathic_voice.chat.socket_client import (  # type: ignore[attr-defined]
        ChatWebsocketConnection,
    )

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.integrations import get_workspace_integrations
from app.api.settings import get_user_api_keys
from app.core.auth import user_id_to_uuid
from app.services.tools.registry import ToolRegistry

logger = structlog.get_logger()

# Hume EVI supported languages (EVI 4-mini)
HUME_SUPPORTED_LANGUAGES = {
    "en-US": "English",
    "ja-JP": "Japanese",
    "ko-KR": "Korean",
    "es-ES": "Spanish",
    "fr-FR": "French",
    "pt-BR": "Portuguese",
    "it-IT": "Italian",
    "de-DE": "German",
    "ru-RU": "Russian",
    "hi-IN": "Hindi",
    "ar-SA": "Arabic",
}

# Hume emotion categories (top-level prosody emotions)
HUME_EMOTION_CATEGORIES = [
    "admiration",
    "adoration",
    "aesthetic_appreciation",
    "amusement",
    "anger",
    "anxiety",
    "awe",
    "awkwardness",
    "boredom",
    "calmness",
    "concentration",
    "confusion",
    "contemplation",
    "contempt",
    "contentment",
    "craving",
    "determination",
    "disappointment",
    "disgust",
    "distress",
    "doubt",
    "ecstasy",
    "embarrassment",
    "empathic_pain",
    "entrancement",
    "envy",
    "excitement",
    "fear",
    "guilt",
    "horror",
    "interest",
    "joy",
    "love",
    "nostalgia",
    "pain",
    "pride",
    "realization",
    "relief",
    "romance",
    "sadness",
    "satisfaction",
    "shame",
    "surprise_negative",
    "surprise_positive",
    "sympathy",
    "tiredness",
    "triumph",
]


class EmotionEntry:
    """Single emotion measurement from Hume EVI."""

    def __init__(
        self,
        emotions: dict[str, float],
        timestamp: str | None = None,
        role: str = "user",
    ) -> None:
        from datetime import UTC, datetime

        self.emotions = emotions  # {emotion_name: score 0.0-1.0}
        self.timestamp = timestamp or datetime.now(UTC).isoformat()
        self.role = role  # "user" or "assistant"

    def to_dict(self) -> dict[str, Any]:
        return {
            "emotions": self.emotions,
            "timestamp": self.timestamp,
            "role": self.role,
        }

    @property
    def top_emotion(self) -> tuple[str, float]:
        """Get the highest scoring emotion."""
        if not self.emotions:
            return ("neutral", 0.0)
        top = max(self.emotions.items(), key=lambda x: x[1])
        return top


class TranscriptEntry:
    """Single transcript entry with emotion data."""

    def __init__(
        self,
        role: str,
        content: str,
        emotions: dict[str, float] | None = None,
        timestamp: str | None = None,
    ) -> None:
        from datetime import UTC, datetime

        self.role = role
        self.content = content
        self.emotions = emotions or {}
        self.timestamp = timestamp or datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "emotions": self.emotions,
            "timestamp": self.timestamp,
        }


class HumeEVISession:
    """Manages a Hume EVI session for voice conversations.

    Handles:
    - WebSocket connection to Hume EVI API
    - Tool integration via ToolRegistry
    - Audio streaming
    - Emotion/expression measurement tracking
    - Transcript accumulation with emotion data
    """

    def __init__(
        self,
        db: AsyncSession,
        user_id: int,
        agent_config: dict[str, Any],
        session_id: str | None = None,
        workspace_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize Hume EVI session.

        Args:
            db: Database session
            user_id: User ID (int, from users.id)
            agent_config: Agent configuration (system prompt, tools, language, etc.)
            session_id: Optional session ID
            workspace_id: Workspace UUID (required for API key isolation)
            agent_id: Agent UUID (for tracking which agent executed tools)
        """
        self.db = db
        self.user_id = user_id
        self.user_id_uuid = user_id_to_uuid(user_id)
        self.workspace_id = workspace_id
        self.agent_id = agent_id
        self.agent_config = agent_config
        self.session_id = session_id or str(uuid.uuid4())
        self.client: AsyncHumeClient | None = None
        self.socket: ChatWebsocketConnection | None = None
        self.tool_registry: ToolRegistry | None = None
        # Transcript and emotion tracking
        self._transcript_entries: list[TranscriptEntry] = []
        self._emotion_entries: list[EmotionEntry] = []
        self._current_assistant_text: str = ""
        # Pending greeting
        self._pending_initial_greeting: str | None = None
        self._greeting_triggered: bool = False
        self.logger = logger.bind(
            component="hume_evi",
            session_id=self.session_id,
            user_id=str(user_id),
            workspace_id=str(workspace_id) if workspace_id else None,
        )

    async def initialize(self) -> None:
        """Initialize the Hume EVI session."""
        self.logger.info("hume_evi_session_initializing")

        # Get user's API keys
        user_settings = await get_user_api_keys(
            self.user_id_uuid, self.db, workspace_id=self.workspace_id
        )

        if not user_settings or not user_settings.hume_api_key:
            self.logger.warning("workspace_missing_hume_key")
            raise ValueError(
                "Hume API key not configured for this workspace. "
                "Please add it in Settings > Workspace API Keys."
            )

        api_key = user_settings.hume_api_key
        self.logger.info("using_workspace_hume_key", key_length=len(api_key))

        # Initialize Hume client
        self.client = AsyncHumeClient(api_key=api_key)

        # Get integration credentials for tools
        integrations: dict[str, Any] = {}
        if self.workspace_id:
            integrations = await get_workspace_integrations(
                self.user_id_uuid, self.workspace_id, self.db
            )

        # Initialize tool registry
        self.tool_registry = ToolRegistry(
            self.db, self.user_id, integrations=integrations, workspace_id=self.workspace_id
        )

        # Connect to Hume EVI
        await self._connect_evi()

        self.logger.info("hume_evi_session_initialized")

    async def _connect_evi(self) -> None:  # noqa: PLR0915
        """Connect to Hume EVI WebSocket."""
        if not self.client:
            raise ValueError("Hume client not initialized")

        # Determine EVI version based on language
        language = self.agent_config.get("language", "en-US")
        # EVI 3 is English-only, EVI 4-mini supports multiple languages
        evi_version = "3" if language == "en-US" else "4-mini"

        self.logger.info("connecting_to_hume_evi", evi_version=evi_version, language=language)

        # Get workspace timezone
        workspace_timezone = "UTC"
        if self.workspace_id:
            from app.models.workspace import Workspace

            result = await self.db.execute(
                select(Workspace).where(Workspace.id == self.workspace_id)
            )
            workspace = result.scalar_one_or_none()
            if workspace and workspace.settings:
                workspace_timezone = workspace.settings.get("timezone", "UTC")

        # Build system prompt with context
        system_prompt = self.agent_config.get("system_prompt", "You are a helpful voice assistant.")
        language_name = HUME_SUPPORTED_LANGUAGES.get(language, language)

        # Get current datetime for context
        from datetime import datetime
        from zoneinfo import ZoneInfo

        try:
            tz = ZoneInfo(workspace_timezone)
            now = datetime.now(tz)
            current_datetime = now.strftime("%A, %B %d, %Y at %I:%M %p")
        except Exception:
            current_datetime = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

        # Build tool definitions for Hume (need this before building prompt)
        enabled_tools = self.agent_config.get("enabled_tools", [])

        # Check if appointment booking tools are enabled
        has_booking_tools = any(
            tool in enabled_tools for tool in ["crm", "calendly", "cal-com", "gohighlevel"]
        )

        # Build booking enforcement rules if booking tools are available
        booking_rules = ""
        if has_booking_tools:
            booking_rules = """

[CRITICAL BOOKING RULES]
* When customer requests to book/schedule an appointment, you MUST call the book_appointment tool IMMEDIATELY
* NEVER say "I'll book", "I'll schedule", "Let me book", "I'm booking now" WITHOUT calling the tool in the same turn
* When customer confirms a date/time (says "yes", "that works", "book it", etc.), call book_appointment RIGHT AWAY
* For ambiguous dates like "Tuesday" or "next week", use parse_date tool FIRST to get ISO format, THEN call book_appointment
* Do NOT promise to book without executing the tool - this causes customer frustration
* Do NOT ask for date/time if customer already provided it - just call book_appointment"""

        full_prompt = f"""[CONTEXT]
Language: {language_name}
Timezone: {workspace_timezone}
Current: {current_datetime}

[RULES]
- Speak ONLY in {language_name}
- Be empathetic and respond to the user's emotional state
- Keep responses concise - this is voice, not text
- Summarize tool results naturally{booking_rules}

[YOUR ROLE]
{system_prompt}"""
        enabled_tool_ids = self.agent_config.get("enabled_tool_ids", {})
        integration_settings = self.agent_config.get("integration_settings", {})
        tools = (
            self.tool_registry.get_all_tool_definitions(
                enabled_tools, enabled_tool_ids, integration_settings
            )
            if self.tool_registry
            else []
        )

        # Hume EVI tool format requires:
        # - type: "function" (required)
        # - name: string (required)
        # - parameters: JSON string (required) - NOT a dict!
        # - description: string (optional)
        hume_tools = []
        for tool in tools:
            # Check if nested under "function" key (OpenAI Chat Completions format)
            if "function" in tool:
                func = tool["function"]
                params = func.get("parameters", {"type": "object", "properties": {}})
                hume_tool = {
                    "type": "function",
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": json.dumps(params),  # Must be JSON string
                }
            else:
                # Flat format (OpenAI Realtime format)
                params = tool.get("parameters", {"type": "object", "properties": {}})
                hume_tool = {
                    "type": "function",
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": json.dumps(params),  # Must be JSON string
                }
            hume_tools.append(hume_tool)

        # Configure session settings
        session_settings = SessionSettings(
            system_prompt=full_prompt,
            tools=hume_tools if hume_tools else None,
        )

        # Store initial greeting for later
        initial_greeting = self.agent_config.get("initial_greeting")
        if initial_greeting:
            self._pending_initial_greeting = initial_greeting

        try:
            # Connect to EVI chat
            self.socket = await self.client.empathic_voice.chat.connect(
                session_settings=session_settings,
            )
            self.logger.info("hume_evi_connected")
        except Exception as e:
            self.logger.exception("hume_evi_connection_failed", error=str(e))
            raise

    async def handle_tool_call(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Handle tool call from Hume EVI.

        Args:
            tool_call: Tool call data from EVI

        Returns:
            Tool execution result
        """
        if not self.tool_registry:
            return {"success": False, "error": "Tool registry not initialized"}

        tool_name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", {})

        self.logger.info(
            "handling_tool_call",
            tool_name=tool_name,
            agent_id=str(self.agent_id) if self.agent_id else None,
        )

        result = await self.tool_registry.execute_tool(
            tool_name, arguments, agent_id=str(self.agent_id) if self.agent_id else None
        )
        return result

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio to Hume EVI.

        Args:
            audio_data: PCM16 audio data
        """
        if not self.socket:
            self.logger.error("send_audio_failed_no_socket")
            return

        try:
            import base64

            audio_base64 = base64.b64encode(audio_data).decode("utf-8")
            await self.socket.send_audio(audio_base64)
            self.logger.debug("audio_sent_to_hume", size_bytes=len(audio_data))
        except Exception as e:
            self.logger.exception("send_audio_error", error=str(e))

    async def trigger_initial_greeting(self) -> bool:
        """Trigger initial greeting if pending.

        Returns:
            True if greeting was triggered
        """
        if not self._pending_initial_greeting or self._greeting_triggered:
            return False

        if not self.socket:
            return False

        self._greeting_triggered = True
        greeting = self._pending_initial_greeting

        self.logger.info("triggering_initial_greeting", greeting=greeting[:50])

        try:
            # Send user message to trigger greeting response
            await self.socket.send_user_input(
                f"[Call connected. Say this greeting now: {greeting}]"
            )
            return True
        except Exception as e:
            self.logger.exception("initial_greeting_failed", error=str(e))
            return False

    def add_user_transcript(
        self,
        text: str,
        emotions: dict[str, float] | None = None,
    ) -> None:
        """Add user transcript with emotion data."""
        if text.strip():
            entry = TranscriptEntry(
                role="user",
                content=text.strip(),
                emotions=emotions,
            )
            self._transcript_entries.append(entry)
            if emotions:
                self._emotion_entries.append(EmotionEntry(emotions=emotions, role="user"))

    def add_assistant_transcript(self, text: str) -> None:
        """Add assistant transcript."""
        if text.strip():
            entry = TranscriptEntry(role="assistant", content=text.strip())
            self._transcript_entries.append(entry)

    def accumulate_assistant_text(self, delta: str) -> None:
        """Accumulate assistant text delta."""
        self._current_assistant_text += delta

    def flush_assistant_text(self) -> None:
        """Flush accumulated assistant text to transcript."""
        if self._current_assistant_text.strip():
            self.add_assistant_transcript(self._current_assistant_text)
        self._current_assistant_text = ""

    def get_transcript(self) -> str:
        """Get full transcript as formatted text."""
        lines = []
        for entry in self._transcript_entries:
            role_label = "User" if entry.role == "user" else "Assistant"
            lines.append(f"[{role_label}]: {entry.content}")
        return "\n\n".join(lines)

    def get_transcript_entries(self) -> list[dict[str, Any]]:
        """Get transcript entries as list of dicts."""
        return [entry.to_dict() for entry in self._transcript_entries]

    def get_emotion_data(self) -> list[dict[str, Any]]:
        """Get all emotion measurements."""
        return [entry.to_dict() for entry in self._emotion_entries]

    def get_emotion_summary(self) -> dict[str, Any]:
        """Get emotion summary for the conversation.

        Returns aggregated emotion data including:
        - Dominant emotions per speaker
        - Emotion timeline
        - Overall sentiment
        """
        if not self._emotion_entries:
            return {"has_emotion_data": False}

        user_emotions = [e for e in self._emotion_entries if e.role == "user"]

        # Calculate average emotions for user
        emotion_totals: dict[str, float] = {}
        for entry in user_emotions:
            for emotion, score in entry.emotions.items():
                emotion_totals[emotion] = emotion_totals.get(emotion, 0) + score

        if user_emotions:
            avg_emotions = {k: v / len(user_emotions) for k, v in emotion_totals.items()}
            top_emotions = sorted(avg_emotions.items(), key=lambda x: x[1], reverse=True)[:5]
        else:
            top_emotions = []

        return {
            "has_emotion_data": True,
            "total_measurements": len(self._emotion_entries),
            "user_measurements": len(user_emotions),
            "top_user_emotions": [{"emotion": e, "score": s} for e, s in top_emotions],
            "timeline": self.get_emotion_data(),
        }

    async def cleanup(self) -> None:
        """Cleanup resources."""
        self.logger.info("hume_evi_session_cleanup_started")

        self.flush_assistant_text()

        if self.socket:
            try:
                await self.socket.close()
                self.logger.info("hume_evi_socket_closed")
            except Exception as e:
                self.logger.warning("socket_close_failed", error=str(e))

        self.logger.info(
            "hume_evi_session_cleanup_completed",
            transcript_entries=len(self._transcript_entries),
            emotion_entries=len(self._emotion_entries),
        )

    async def __aenter__(self) -> "HumeEVISession":
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
