from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
KNOWLEDGE_BASE_DIR = DATA_DIR / "knowledge_base"
FACILITY_DB_PATH = DATA_DIR / "facility_db.json"
VECTOR_STORE_DIR = BASE_DIR / ".chroma"
AUDIO_OUT_DIR = BASE_DIR / ".audio"
WEB_DIR = BASE_DIR / "web"

# All three providers speak the OpenAI protocol, so only the URL changes.
PROVIDER_ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "ollama": None,  # taken from ollama_base_url
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    llm_provider: str = "groq"  # groq | ollama | gemini
    groq_api_key: str = ""
    gemini_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434/v1"

    # Cheap model for routing and summarising, expensive one for reasoning.
    fast_model: str = "llama-3.1-8b-instant"
    smart_model: str = "llama-3.3-70b-versatile"

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    tts_enabled: bool = True

    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieve_top_k: int = 8
    rerank_top_n: int = 4
    min_relevance_score: float = 0.15
    reranker: str = "auto"  # auto | flashrank | lexical | none

    log_level: str = "INFO"
    max_agent_steps: int = 6

    @property
    def llm_base_url(self) -> str:
        if self.llm_provider not in PROVIDER_ENDPOINTS:
            raise ValueError(
                f"Unknown LLM_PROVIDER '{self.llm_provider}'. "
                f"Choose one of: {', '.join(PROVIDER_ENDPOINTS)}"
            )
        return PROVIDER_ENDPOINTS[self.llm_provider] or self.ollama_base_url

    @property
    def llm_api_key(self) -> str:
        keys = {"groq": self.groq_api_key, "gemini": self.gemini_api_key}
        return keys.get(self.llm_provider, "") or "not-required"

    @property
    def tracing_enabled(self) -> bool:
        """Tracing switches itself off when keys are missing - never crashes."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

for _folder in (VECTOR_STORE_DIR, AUDIO_OUT_DIR):
    _folder.mkdir(parents=True, exist_ok=True)
