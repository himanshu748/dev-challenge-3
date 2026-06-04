from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    hf_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("HF_API_KEY", "HF_TOKEN"),
    )
    notion_token: str = Field(default="", alias="NOTION_TOKEN")
    notion_parent_page_id: str = Field(default="", alias="NOTION_PARENT_PAGE_ID")

    hf_model: str = "Qwen/Qwen2.5-72B-Instruct"
    notion_mcp_url: str = "https://mcp.notion.com/sse"
    request_timeout_seconds: float = 180.0
    runtime_state_path: Path = BASE_DIR / "data" / "runtime_state.json"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        ],
        alias="CORS_ORIGINS",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
