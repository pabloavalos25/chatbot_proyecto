from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./chatbot.db"
    chatbot_ai_enabled: bool = False
    chatbot_ai_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    ollama_model: str = "qwen2.5:1.5b"
    operator_token: str = ""
