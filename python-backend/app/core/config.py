from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_prefix="GRAPHBOARD_", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/graphboard",
        description="Async SQLAlchemy connection string",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    copilot_model: str = Field(default="gemini-3.6-flash", description="Default Gemini model for copilot operations")
    copilot_thinking_budget: int = Field(default=1024, description="Thinking budget token limit for copilot planner")
    runner_timeout_seconds: float = Field(
        default=5.0, description="Hard timeout in seconds for subprocess workflow execution"
    )


settings = Settings()
