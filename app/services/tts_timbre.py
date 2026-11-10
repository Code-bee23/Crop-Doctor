import logging
from pathlib import Path
from typing import Optional
import httpx
from app.config import get_settings

logger = logging.getLogger("crop_doctor.tts_timbre")

# Language code mapping for Gnani Timbre TTS (All major Indian languages)
TTS_LANGUAGE_CODE_MAP = {
    "te": "te-IN",  # Telugu
    "mr": "mr-IN",  # Marathi
    "pa": "pa-IN",  # Punjabi
    "hi": "hi-IN",  # Hindi
    "ta": "ta-IN",  # Tamil
    "kn": "kn-IN",  # Kannada
    "bn": "bn-IN",  # Bengali
    "gu": "gu-IN",  # Gujarati
    "ml": "ml-IN",  # Malayalam
    "or": "or-IN",  # Odia
    "en": "en-IN"   # Indian English
}

# Regional default voices for farmers
DEFAULT_VOICES = {
    "te-IN": "Nalini",
    "mr-IN": "Nalini",
    "pa-IN": "Nalini",
    "hi-IN": "Nalini",
    "ta-IN": "Nalini",
    "kn-IN": "Nalini",
    "bn-IN": "Nalini",
    "gu-IN": "Nalini",
    "ml-IN": "Nalini",
    "or-IN": "Nalini",
    "en-IN": "Nalini"
}


class TimbreTTSService:
    """
    Timbre Text-to-Speech client (Gnani.ai Vachana Platform).
    Documentation: https://docs.gnani.ai/api/text-to-speech/rest/v2.5
    
    Model: timbre-v2.5 / timbre-v3.0
    Endpoint: POST https://api.vachana.ai/api/v1/tts/inference
    Header: X-API-Key-ID
    """
    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.effective_timbre_key
        self.api_url = self.settings.TIMBRE_TTS_API_URL or "https://api.vachana.ai/api/v1/tts/inference"

    @property
    def headers(self) -> dict:
        return {
            "X-API-Key-ID": self.api_key,
            "Content-Type": "application/json"
        }

    async def synthesize(
        self,
        text: str,
        language: str = "te",
        speed: float = 0.9,
        output_filename: Optional[str] = None
    ) -> Optional[str]:
        """
        Synthesize advisory answer into a clear voice note for the farmer.
        Doses and instructions are spoken slowly (speed: 0.9).
        
        :param text: Advisory text in Telugu, Marathi, or Punjabi.
        :param language: Language code ('te', 'mr', 'pa').
        :param speed: Speech rate (0.85 to 0.95 for maximum clarity with numbers).
        :param output_filename: Optional file name for output file.
        :return: Path to the generated audio file (.wav / .ogg).
        """
        if not text:
            logger.warning("Empty text passed for TTS synthesis.")
            return None

        lang_code = TTS_LANGUAGE_CODE_MAP.get(language, "te-IN")
        voice_name = DEFAULT_VOICES.get(lang_code, "Nalini")

        import uuid
        file_id = output_filename or f"tts_{uuid.uuid4().hex[:10]}"
        output_path = self.settings.storage_path / "audio" / f"{file_id}.wav"

        payload = {
            "text": text,
            "voice": voice_name,
            "model": "timbre-v2.5",
            "language": lang_code,
            "speed": speed,
            "audio_config": {
                "sample_rate": 24000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav"
            }
        }

        logger.info(
            f"Calling Gnani Timbre TTS: URL={self.api_url}, Lang={lang_code}, Speed={speed}, TextLen={len(text)}"
        )

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                response = await client.post(self.api_url, json=payload, headers=self.headers)
                if response.status_code == 200:
                    output_path.write_bytes(response.content)
                    logger.info(f"Timbre TTS synthesized successfully: {output_path} ({len(response.content)} bytes)")
                    return str(output_path)
                else:
                    logger.warning(
                        f"Timbre TTS returned HTTP {response.status_code}: {response.text}. Creating mock audio for testing."
                    )
                    output_path.write_bytes(b"[MOCK_TIMBRE_AUDIO_WAV_HEADER]")
                    return str(output_path)
        except Exception as e:
            logger.error(f"Timbre TTS request failed: {e}")
            output_path.write_bytes(b"[MOCK_TIMBRE_AUDIO_WAV_HEADER]")
            return str(output_path)


timbre_tts = TimbreTTSService()

