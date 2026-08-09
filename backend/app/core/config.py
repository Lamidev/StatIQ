from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    FOOTBALL_DATA_API_KEY: str = "490d737d899046f5a464110569805d2b"
    FOOTBALL_DATA_BASE_URL: str = "https://api.football-data.org/v4"
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'matchiq.db'}"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    # API-Football (api-football.com) — for corners & halftime stat verification
    API_FOOTBALL_KEY: str = ""  # Set in .env: API_FOOTBALL_KEY=your_key_here
    API_FOOTBALL_BASE_URL: str = "https://v3.football.api-sports.io"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
