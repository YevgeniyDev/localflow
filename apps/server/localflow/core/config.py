from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LocalFlow"
    env: str = "dev"

    database_url: str = "sqlite:///./localflow.db"

    # LLM provider
    llm_provider: str = "ollama"  # later: openai, gemini, etc.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b"
    llm_timeout_s: int = 120

    # Security for future remote access
    api_key: str | None = None

settings = Settings()