"""Application configuration loaded from environment variables / .env file."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # YouTube
    youtube_api_key: Optional[str] = None
    max_comments_per_video: int = 200

    # LLM
    llm_provider: str = "openai"
    llm_api_key: Optional[str] = None
    llm_model: str = "gpt-4o-mini"
    llm_api_base: Optional[str] = None

    # Database
    database_url: str = "sqlite:///./podlens.db"

    # Model artifacts
    sentiment_model_dir: str = "./model_artifacts/sentiment_roberta"
    spam_model_dir: str = "./model_artifacts/spam_bert_tiny"
    spam_label_map: Optional[str] = None
    sentiment_label_map: Optional[str] = None
    spam_confidence_threshold: float = 0.5
    model_inference_batch_size: int = 16
    force_cpu: bool = False

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    @field_validator("spam_label_map", "sentiment_label_map")
    @classmethod
    def _validate_label_map_json(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        try:
            json.loads(v)
        except json.JSONDecodeError as exc:
            raise ValueError(f"label map must be valid JSON: {exc}") from exc
        return v

    def parsed_spam_label_map(self) -> Optional[dict]:
        return json.loads(self.spam_label_map) if self.spam_label_map else None

    def parsed_sentiment_label_map(self) -> Optional[dict]:
        return json.loads(self.sentiment_label_map) if self.sentiment_label_map else None

    @property
    def youtube_configured(self) -> bool:
        return bool(self.youtube_api_key and self.youtube_api_key.strip())

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
