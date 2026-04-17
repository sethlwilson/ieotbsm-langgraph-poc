from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRUST_API_", env_file=".env")

    database_url: str = "sqlite:///./trust_service.db"
    api_key: str = "dev-key"
    default_tenant: str = "default"


settings = Settings()
