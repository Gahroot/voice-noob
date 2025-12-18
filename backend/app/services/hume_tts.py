"""Hume Octave TTS (Text-to-Speech) service.

Hume Octave is a next-generation TTS system with ~100ms latency.
Supports voice design, voice cloning, and 100+ pre-built voices.

Latest models (Dec 2025):
- Octave 2: ~100ms latency, instant mode, word-level timestamps
"""

import base64
from collections.abc import AsyncIterator
from typing import Any

import structlog
from hume import AsyncHumeClient
from hume.tts import (
    FormatMp3,
    FormatPcm,
    FormatWav,
    PostedUtterance,
    PostedUtteranceVoiceWithId,
    PostedUtteranceVoiceWithName,
)

logger = structlog.get_logger()

# Pre-built Hume voices (subset of available voices)
HUME_VOICES = {
    "kora": {"name": "Kora", "description": "Warm and professional female voice"},
    "aoede": {"name": "Aoede", "description": "Clear and articulate female voice"},
    "orpheus": {"name": "Orpheus", "description": "Rich and expressive male voice"},
    "charon": {"name": "Charon", "description": "Deep and authoritative male voice"},
    "calliope": {"name": "Calliope", "description": "Melodic and friendly female voice"},
    "atlas": {"name": "Atlas", "description": "Strong and confident male voice"},
    "helios": {"name": "Helios", "description": "Bright and energetic male voice"},
    "luna": {"name": "Luna", "description": "Soft and calming female voice"},
}

# Audio format options
AUDIO_FORMATS = {
    "mp3": FormatMp3(type="mp3"),
    "wav": FormatWav(type="wav"),
    "pcm": FormatPcm(type="pcm"),
}


class HumeOctaveTTS:
    """Hume Octave TTS service for text-to-speech synthesis.

    Features:
    - Ultra-low latency (~100ms with instant mode)
    - Voice design via text descriptions
    - Voice cloning from audio samples
    - 100+ pre-built voices
    - Word-level timestamps for lip-sync
    """

    def __init__(
        self,
        api_key: str,
        default_voice: str = "kora",
    ) -> None:
        """Initialize Hume Octave TTS.

        Args:
            api_key: Hume API key
            default_voice: Default voice ID or name
        """
        self.api_key = api_key
        self.default_voice = default_voice
        self._client: AsyncHumeClient | None = None
        self.logger = logger.bind(component="hume_tts")

    @property
    def client(self) -> AsyncHumeClient:
        """Get or create Hume client."""
        if self._client is None:
            self._client = AsyncHumeClient(api_key=self.api_key)
        return self._client

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        voice_description: str | None = None,
        audio_format: str = "pcm",
    ) -> bytes:
        """Synthesize speech from text.

        Args:
            text: Text to synthesize
            voice: Voice ID or name (optional, uses default if not provided)
            voice_description: Voice description for voice design (optional)
            audio_format: Output format (mp3, wav, pcm)

        Returns:
            Audio data as bytes
        """
        voice_id = voice or self.default_voice
        format_obj = AUDIO_FORMATS.get(audio_format, AUDIO_FORMATS["pcm"])

        self.logger.info(
            "synthesizing_speech",
            text_length=len(text),
            voice=voice_id,
            format=audio_format,
        )

        try:
            # Build utterance with voice
            if voice_description:
                # Use voice design via description
                utterance = PostedUtterance(
                    text=text,
                    description=voice_description,
                )
            elif voice_id in HUME_VOICES:
                # Use pre-built voice by name
                utterance = PostedUtterance(
                    text=text,
                    voice=PostedUtteranceVoiceWithName(name=voice_id),
                )
            else:
                # Assume it's a voice ID
                utterance = PostedUtterance(
                    text=text,
                    voice=PostedUtteranceVoiceWithId(id=voice_id),
                )

            # Synthesize
            response = await self.client.tts.synthesize_json(
                utterances=[utterance],
                format=format_obj,
            )

            # Extract audio from response
            if response.generations and len(response.generations) > 0:
                generation = response.generations[0]
                if generation.audio:
                    audio_data = base64.b64decode(generation.audio)
                    self.logger.info(
                        "synthesis_complete",
                        audio_bytes=len(audio_data),
                    )
                    return audio_data

            self.logger.warning("no_audio_in_response")
            return b""

        except Exception as e:
            self.logger.exception("synthesis_error", error=str(e))
            raise

    async def synthesize_streaming(
        self,
        text: str,
        voice: str | None = None,
        voice_description: str | None = None,
        audio_format: str = "pcm",
        instant_mode: bool = True,
    ) -> AsyncIterator[tuple[bytes, dict[str, Any] | None]]:
        """Synthesize speech with streaming output.

        Args:
            text: Text to synthesize
            voice: Voice ID or name
            voice_description: Voice description for voice design
            audio_format: Output format (mp3, wav, pcm)
            instant_mode: Enable instant mode for lower latency

        Yields:
            Tuples of (audio_chunk, timestamp_info)
        """
        voice_id = voice or self.default_voice
        format_obj = AUDIO_FORMATS.get(audio_format, AUDIO_FORMATS["pcm"])

        self.logger.info(
            "synthesizing_speech_streaming",
            text_length=len(text),
            voice=voice_id,
            instant_mode=instant_mode,
        )

        try:
            # Build utterance
            if voice_description:
                utterance = PostedUtterance(
                    text=text,
                    description=voice_description,
                )
            elif voice_id in HUME_VOICES:
                utterance = PostedUtterance(
                    text=text,
                    voice=PostedUtteranceVoiceWithName(name=voice_id),
                )
            else:
                utterance = PostedUtterance(
                    text=text,
                    voice=PostedUtteranceVoiceWithId(id=voice_id),
                )

            # Stream synthesis
            async for chunk in self.client.tts.synthesize_json_streaming(
                utterances=[utterance],
                format=format_obj,
                instant_mode=instant_mode,
                include_timestamp_types=["word"],
            ):
                # Extract audio and timestamps
                if hasattr(chunk, "audio") and chunk.audio:
                    audio_data = base64.b64decode(chunk.audio)

                    # Extract word timestamps if available
                    timestamps = None
                    if hasattr(chunk, "timestamps") and chunk.timestamps:
                        timestamps = {
                            "words": [
                                {
                                    "word": ts.word,
                                    "start": ts.start,
                                    "end": ts.end,
                                }
                                for ts in chunk.timestamps
                                if hasattr(ts, "word")
                            ]
                        }

                    yield audio_data, timestamps

        except Exception as e:
            self.logger.exception("streaming_synthesis_error", error=str(e))
            raise

    async def list_voices(self) -> list[dict[str, Any]]:
        """List available voices.

        Returns:
            List of voice information dicts
        """
        try:
            voices_response = await self.client.tts.voices.list_voices()
            voices = []
            for voice in voices_response.voices:
                voices.append(
                    {
                        "id": voice.id,
                        "name": voice.name,
                        "description": getattr(voice, "description", None),
                    }
                )
            return voices
        except Exception as e:
            self.logger.exception("list_voices_error", error=str(e))
            # Return pre-built voices as fallback
            return [
                {"id": k, "name": v["name"], "description": v["description"]}
                for k, v in HUME_VOICES.items()
            ]

    async def create_voice_from_description(
        self,
        name: str,
        description: str,
    ) -> dict[str, Any]:
        """Create a custom voice from a text description.

        Args:
            name: Name for the voice
            description: Text description of the voice characteristics

        Returns:
            Created voice information
        """
        try:
            voice = await self.client.tts.voices.create_voice(
                name=name,
                description=description,
            )
            return {
                "id": voice.id,
                "name": voice.name,
                "description": description,
            }
        except Exception as e:
            self.logger.exception("create_voice_error", error=str(e))
            raise

    async def close(self) -> None:
        """Close the client connection."""
        if self._client:
            # AsyncHumeClient doesn't have explicit close, but we can clear it
            self._client = None
