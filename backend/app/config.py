from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing_extensions import Annotated

BACKEND_DIR = Path(__file__).resolve().parent.parent

CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    version: str = "0.1.0"

    # Supabase (optional until P7; /health reports db_ready=false without it)
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # LLMs
    groq_api_key: str = ""
    groq_models: CsvList = Field(
        default_factory=lambda: ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    )
    gemini_api_keys: CsvList = Field(default_factory=list)
    gemini_models: CsvList = Field(
        default_factory=lambda: ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite"]
    )
    llm_mode: Literal["real", "fake"] = "real"
    gemini_mode: Literal["real", "fake"] = "fake"

    # HTTP
    cors_origins: CsvList = Field(default_factory=lambda: ["http://localhost:3000"])
    cors_origin_regex: str = r"https://.*\.vercel\.app"

    # Targets / safety
    allowed_target_hosts: CsvList = Field(default_factory=list)  # empty = any public host
    demo_target_hosts: CsvList = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    allow_local_targets: bool = True  # dev only; set false on HF Space

    # Runtime
    max_concurrent_personas: int = 6
    screenshot_mode: Literal["key", "all", "none"] = "key"
    browser_headless: bool = True

    @field_validator(
        "groq_models", "gemini_api_keys", "gemini_models", "cors_origins",
        "allowed_target_hosts", "demo_target_hosts", mode="before",
    )
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
