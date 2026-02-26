from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LocalFlow"
    env: str = "dev"

    database_url: str = "sqlite:///./localflow.db"

    # LLM provider
    llm_provider: str = "gemini"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    llm_timeout_s: int = 120

    # Prompt packs (directory-based, editable without code changes)
    prompt_pack_dir: str = "localflow/llm/prompt_packs/default"

    # Security for future remote access
    api_key: str | None = None

settings = Settings()
