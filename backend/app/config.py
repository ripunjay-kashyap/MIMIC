import os
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
    # Pinned decision model per persona group (bake-off 2026-10-01): [power+impatient, cautious+chaos, low_literacy+explorer]
    decision_models: CsvList = Field(
        default_factory=lambda: ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "gemini-3.5-flash-lite"]
    )
    groq_rpm: float = 30
    groq_tpm: float = 8000
    llm_mode: Literal["real", "fake"] = "real"
    gemini_mode: Literal["real", "fake"] = "fake"

    # HTTP
    cors_origins: CsvList = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:3001"])
    cors_origin_regex: str = r"https://.*\.vercel\.app"

    # Targets / safety
    allowed_target_hosts: CsvList = Field(default_factory=list)  # empty = any public host
    demo_target_hosts: CsvList = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    allow_local_targets: bool = True  # dev only; Modal sets false

    # Runtime
    max_concurrent_personas: int = 6
    runs_per_ip_per_hour: int = 6  # swarm deploys per client IP (creates allowed 3x this)
    runs_global_per_hour: int = 15
    golden_run_id: str = ""  # known-good completed run, shown as a fallback during judging
    screenshot_mode: Literal["key", "all", "none"] = "key"
    browser_headless: bool = True

    @field_validator(
        "groq_models", "decision_models", "gemini_api_keys", "gemini_models", "cors_origins",
        "allowed_target_hosts", "demo_target_hosts", mode="before",
    )
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    # LangSmith (optional). pydantic-settings doesn't export .env to os.environ, so we do it for the SDK.
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "mimic"

    def export_tracing_env(self) -> None:
        if self.langsmith_tracing and self.langsmith_api_key:
            os.environ.setdefault("LANGSMITH_TRACING", "true")
            os.environ.setdefault("LANGSMITH_API_KEY", self.langsmith_api_key)
            os.environ.setdefault("LANGSMITH_PROJECT", self.langsmith_project)

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.export_tracing_env()
    return settings
