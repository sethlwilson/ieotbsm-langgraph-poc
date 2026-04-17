from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRUST_API_", env_file=".env")

    database_url: str = "sqlite:///./trust_service.db"
    api_key: str = "dev-key"
    default_tenant: str = "default"
    # Pedigree chain signing (PEM PKCS8); if unset, a dev-only key is derived from api_key.
    signing_private_key_pem: str | None = None
    signing_key_id: str = "dev-1"
    # Public URL for this API (used in A2A Agent Card). Default matches local dev.
    public_base_url: str = "http://127.0.0.1:8088"


settings = Settings()
