from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "SuperBryn Voice Agent"
    app_env: str = "development"
    debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/superbryn_db"

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # LiveKit
    livekit_url: str = "wss://your-project.livekit.cloud"
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # Deepgram (STT)
    deepgram_api_key: str = ""

    # Cartesia (TTS)
    cartesia_api_key: str = ""

    # LLM - OpenAI
    openai_api_key: str = ""

    # Avatar - Beyond Presence
    beyond_presence_api_key: str = ""
    beyond_presence_avatar_id: str = ""
    
    # Logfire (Observability)
    logfire_token: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()

