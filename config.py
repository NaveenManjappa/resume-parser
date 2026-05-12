from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    gemini_api_key: str = Field(..., description="API key for Google Gemini")
    gemini_model: str = Field(
        default="gemini-2.5-flash", description="Gemini model identifier"
    )
    max_retries: int = Field(
        default=3, ge=0, le=10, description="Max instructor retry count per extraction"
    )
    log_level: str = Field(default="INFO", description="Python logging level")
    app_api_key: str = Field(
        ..., description="Shared API key required to access the extract endpoint"
    )

    cors_origins:list[str] = Field(...,description="The url which needs to be added to the origins")


settings = Settings()  # type: ignore[call-arg]
