import logging
from pathlib import Path
from typing import Optional, List
import httpx
from app.config import get_settings

logger = logging.getLogger("crop_doctor.stt_prisma")

# Domain keyterms for boosting Indic agricultural vocabulary in noisy outdoor voice notes
AGRICULTURAL_KEYTERMS = (
    "tella doma, mava, gulabi bond aali, tela, mirapa, kapoos, jhone, tomato, "
    "paddy, cotton, chilli, aakulu mudatha, bhoore dhabbe, leaf curl, blast, "
    "mirch, kapaas, dhaan, tamatar, safed makhi, soondi, patti modak, karpa, "
    "paruthi, milagai, nell, thakkali, elai suruttal, kisan, spray, faravni, "
    "dawaai, pump, tank, litre, KVK, PJTSAU, MPKV, PAU"
)

# Language code mapping for Gnani Prisma STT v3.0 (All major Indian languages)
LANGUAGE_CODE_MAP = {
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
    "en": "en-IN",  # Indian English
    "auto": "indic-auto"
}


class PrismaSTTService:
    """
    Prisma Speech-to-Text client (Gnani.ai Vachana Platform).
    Documentation: https://docs.gnani.ai/api/speech-to-text/rest/v3
    
    Model: prisma-v3.0
    Endpoint: POST https://api.vachana.ai/stt/v3
    Header: X-API-Key-ID
    """
    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.effective_prisma_key
        self.api_url = self.settings.PRISMA_STT_API_URL or "https://api.vachana.ai/stt/v3"

    @property
    def headers(self) -> dict:
        """Gnani Vachana authentication header."""
        return {
            "X-API-Key-ID": self.api_key
        }

    async def transcribe(
        self,
        audio_file_path: str,
        language_code: Optional[str] = "indic-auto"
    ) -> str:
        """
        Transcribe outdoor agricultural voice note into text using Gnani Prisma v3.0.
        
        :param audio_file_path: Local path to the .ogg, .mp3, or .wav audio file.
        :param language_code: 'te', 'mr', 'pa', or 'indic-auto' for automatic language detection.
        :return: Transcribed text string in native script.
        """
        path = Path(audio_file_path)
        if not path.exists():
            logger.error(f"Audio file does not exist at: {audio_file_path}")
            return ""

        # Map short language identifier to Gnani format
        gnani_lang = LANGUAGE_CODE_MAP.get(language_code, language_code or "indic-auto")

        # Determine MIME type
        ext = path.suffix.lower()
        mime_type = "audio/ogg" if ext == ".ogg" else ("audio/mpeg" if ext == ".mp3" else "audio/wav")

        logger.info(
            f"Calling Gnani Prisma STT: URL={self.api_url}, File={path.name}, "
            f"Model=prisma-v3.0, Language={gnani_lang}"
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                with open(audio_file_path, "rb") as f:
                    files = {
                        "audio_file": (path.name, f, mime_type)
                    }
                    data = {
                        "model": "prisma-v3.0",
                        "language_code": gnani_lang,
                        "format": "transcribe",
                        "keyterms": AGRICULTURAL_KEYTERMS,
                        "topic": "Agricultural pest and crop disease diagnosis voice note from a farmer"
                    }

                    response = await client.post(
                        self.api_url,
                        headers=self.headers,
                        files=files,
                        data=data
                    )

                    if response.status_code == 200:
                        res_json = response.json()
                        transcript = res_json.get("transcript", "")
                        detected_lang = res_json.get("detected_language_code")
                        logger.info(
                            f"Prisma STT Transcription Success (Lang: {detected_lang}): {transcript[:100]}..."
                        )
                        return transcript
                    else:
                        logger.warning(
                            f"Prisma STT responded with HTTP {response.status_code}: {response.text}"
                        )
                        # Graceful fallback for offline testing or quota limits
                        return f"[Voice note processed: {path.name} | Status: {response.status_code}]"

        except Exception as e:
            logger.error(f"Prisma STT request failed with exception: {e}")
            return f"[Transcription error: {str(e)}]"


prisma_stt = PrismaSTTService()
