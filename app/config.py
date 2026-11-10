from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """
    Application Settings loaded from environment variables and .env file.
    All critical external configurations are centralized here.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server configuration
    APP_ENV: str = Field(default="development", description="Environment: development, staging, production")
    APP_HOST: str = Field(default="0.0.0.0", description="Host address for FastAPI server")
    APP_PORT: int = Field(default=8000, description="Port for FastAPI server")
    MEDIA_STORAGE_DIR: str = Field(default="storage", description="Local folder path for saving media")

    # WhatsApp Cloud API credentials
    WHATSAPP_PHONE_NUMBER_ID: str = Field(default="", description="WhatsApp Cloud API Phone Number ID")
    WHATSAPP_ACCESS_TOKEN: str = Field(default="", description="Meta User/System User Access Token")
    WHATSAPP_VERIFY_TOKEN: str = Field(default="crop_doctor_webhook_secret_verify_token_2026", description="Webhook verification token")
    WHATSAPP_API_VERSION: str = Field(default="v19.0", description="Meta Graph API Version")

    # Supabase Database credentials
    SUPABASE_URL: str = Field(default="", description="Supabase project URL")
    SUPABASE_KEY: str = Field(default="", description="Supabase service role or anon key")
    DATABASE_URL: str = Field(default="", description="Direct PostgreSQL connection string with pgvector")

    # Unified API Key & Specific Provider URLs
    VACH_API_KEY: str = Field(
        default="vach_1ytE2CY5X2Euwn8j6obEOkXQfjU3xmwjPYPQnZiWxranIUsOtWXKQhEThb0f05PrfJiG5Qzc33uDWeI1fn3ymZeZJCX5gy3j_2c4cca1ed3f7a995b53781a5238db1f0",
        description="Master API Key provided for speech/LLM/TTS services"
    )

    # Prisma STT (Speech to Text)
    PRISMA_STT_API_URL: str = Field(default="", description="Prisma STT endpoint")
    PRISMA_API_KEY: str = Field(default="", description="Prisma API Key")

    # Evon LLM (Reasoning)
    EVON_API_URL: str = Field(default="", description="Evon Chat Completion / Reasoning endpoint")
    EVON_API_KEY: str = Field(default="", description="Evon API Key")

    # Timbre TTS (Voice Generation)
    TIMBRE_TTS_API_URL: str = Field(default="", description="Timbre TTS audio generation endpoint")
    TIMBRE_API_KEY: str = Field(default="", description="Timbre API Key")

    # Vision Model
    VISION_API_KEY: str = Field(default="", description="Vision Model API Key")

    @property
    def effective_prisma_key(self) -> str:
        return self.PRISMA_API_KEY or self.VACH_API_KEY

    @property
    def effective_evon_key(self) -> str:
        return self.EVON_API_KEY or self.VACH_API_KEY

    @property
    def effective_timbre_key(self) -> str:
        return self.TIMBRE_API_KEY or self.VACH_API_KEY

    @property
    def storage_path(self) -> Path:
        p = Path(self.MEDIA_STORAGE_DIR)
        try:
            p.mkdir(parents=True, exist_ok=True)
            (p / "images").mkdir(parents=True, exist_ok=True)
            (p / "audio").mkdir(parents=True, exist_ok=True)
            return p
        except (OSError, PermissionError):
            # Fallback for serverless read-only filesystems (Vercel Lambda /tmp)
            tmp_p = Path("/tmp/storage")
            tmp_p.mkdir(parents=True, exist_ok=True)
            (tmp_p / "images").mkdir(parents=True, exist_ok=True)
            (tmp_p / "audio").mkdir(parents=True, exist_ok=True)
            return tmp_p


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings singleton instance."""
    return Settings()

