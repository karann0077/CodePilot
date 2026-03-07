from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    database_url: str = "postgresql://codepilot:codepilot@localhost:5432/codepilot"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    llm_mode: str = "hybrid"  # hybrid | gemini_only
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-3.5-sonnet"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "codellama:7b"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    embedding_model: str = "all-MiniLM-L6-v2"
    model_cache_dir: str = "/tmp/codepilot_models/all-MiniLM-L6-v2"
    sandbox_timeout: int = 120
    sandbox_memory_limit: str = "512m"
    sandbox_cpu_limit: float = 1.0
    cache_ttl_seconds: int = 3600
    cache_max_size: int = 1000
    secrets_scan_enabled: bool = True
    cors_origins: str = "*"
    port: int = 8000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
