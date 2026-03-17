import httpx
import structlog
from typing import Optional, AsyncGenerator
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import get_settings
from core.enums import Language

logger = structlog.get_logger()
settings = get_settings()

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"


# Voice settings optimized for professional receptionist use
VOICE_SETTINGS = {
    Language.ENGLISH: {
        "stability": 0.55,
        "similarity_boost": 0.80,
        "style": 0.20,
        "use_speaker_boost": True,
    },
    Language.SPANISH: {
        "stability": 0.60,
        "similarity_boost": 0.82,
        "style": 0.18,
        "use_speaker_boost": True,
    },
}

# Model optimized for low-latency conversational use
CONVERSATIONAL_MODEL = "eleven_turbo_v2_5"
HIGH_QUALITY_MODEL = "eleven_multilingual_v2"


class ElevenLabsClient:
    def __init__(self) -> None:
        self.api_key: str = settings.elevenlabs_api_key
        self.voice_id_en: str = settings.elevenlabs_voice_id_en
        self.voice_id_es: str = settings.elevenlabs_voice_id_es
        self.headers: dict = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def get_voice_id(self, language: Language) -> str:
        """Return the correct voice ID based on the caller's language."""
        if language == Language.SPANISH:
            return self.voice_id_es
        return self.voice_id_en

    def get_voice_settings(self, language: Language) -> dict:
        """Return voice settings tuned for the given language."""
        return VOICE_SETTINGS.get(language, VOICE_SETTINGS[Language.ENGLISH])

    # ------------------------------------------------------------------
    # Text-to-speech: standard (returns full audio bytes)
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def synthesize(
        self,
        text: str,
        language: Language = Language.ENGLISH,
        high_quality: bool = False,
    ) -> bytes:
        """
        Convert text to speech and return audio bytes (mp3).
        Use for short confirmations and pre-recorded prompts.
        """
        voice_id = self.get_voice_id(language)
        model = HIGH_QUALITY_MODEL if high_quality else CONVERSATIONAL_MODEL

        payload = {
            "text": text,
            "model_id": model,
            "voice_settings": self.get_voice_settings(language),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}",
                headers=self.headers,
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()

            logger.info(
                "elevenlabs_synthesize_complete",
                language=language,
                voice_id=voice_id,
                text_length=len(text),
            )
            return response.content

    # ------------------------------------------------------------------
    # Text-to-speech: streaming (yields audio chunks)
    # ------------------------------------------------------------------

    async def synthesize_stream(
        self,
        text: str,
        language: Language = Language.ENGLISH,
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream audio chunks for real-time playback during calls.
        Retell AI uses this for low-latency voice responses.
        """
        voice_id = self.get_voice_id(language)

        payload = {
            "text": text,
            "model_id": CONVERSATIONAL_MODEL,
            "voice_settings": self.get_voice_settings(language),
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}/stream",
                headers=self.headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk

        logger.info(
            "elevenlabs_stream_complete",
            language=language,
            voice_id=voice_id,
        )

    # ------------------------------------------------------------------
    # Voice profile helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def get_voice(self, voice_id: str) -> dict:
        """Fetch metadata for a specific voice."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ELEVENLABS_BASE_URL}/voices/{voice_id}",
                headers=self.headers,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info("elevenlabs_voice_fetched", voice_id=voice_id)
            return data

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def list_voices(self) -> list:
        """List all available voices on this ElevenLabs account."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ELEVENLABS_BASE_URL}/voices",
                headers=self.headers,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            voices = data.get("voices", [])
            logger.info("elevenlabs_voices_listed", count=len(voices))
            return voices

    # ------------------------------------------------------------------
    # Retell AI voice config builder
    # ------------------------------------------------------------------

    def build_retell_voice_config(self, language: Language) -> dict:
        """
        Return the voice configuration block that Retell AI expects
        when we assign an ElevenLabs voice to the agent.
        """
        return {
            "provider": "elevenlabs",
            "voice_id": self.get_voice_id(language),
            "model": CONVERSATIONAL_MODEL,
            "speed": 1.0,
            "volume": 1.0,
            "voice_settings": self.get_voice_settings(language),
        }

    async def verify_voices_configured(self) -> dict:
        """
        Confirm that both English and Spanish voice IDs are valid
        and accessible on this account. Call this at startup.
        """
        results = {}
        for language, voice_id in [
            (Language.ENGLISH, self.voice_id_en),
            (Language.SPANISH, self.voice_id_es),
        ]:
            try:
                voice_data = await self.get_voice(voice_id)
                results[language] = {
                    "status": "ok",
                    "name": voice_data.get("name"),
                    "voice_id": voice_id,
                }
                logger.info(
                    "elevenlabs_voice_verified",
                    language=language,
                    voice_name=voice_data.get("name"),
                )
            except Exception as e:
                results[language] = {
                    "status": "error",
                    "voice_id": voice_id,
                    "error": str(e),
                }
                logger.error(
                    "elevenlabs_voice_verification_failed",
                    language=language,
                    voice_id=voice_id,
                    error=str(e),
                )
        return results


# Singleton instance
elevenlabs_client = ElevenLabsClient()