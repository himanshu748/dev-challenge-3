from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY")
    notion_token: str = Field(alias="NOTION_TOKEN")
    notion_parent_page_id: str = Field(alias="NOTION_PARENT_PAGE_ID")

    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    anthropic_beta: str = "mcp-client-2025-04-04"
    notion_mcp_url: str = "https://mcp.notion.com/sse"
    request_timeout_seconds: float = 180.0
    runtime_state_path: Path = BASE_DIR / "data" / "runtime_state.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
