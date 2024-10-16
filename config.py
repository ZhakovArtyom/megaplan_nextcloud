from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Класс Settings подгружает данные из файла .env."""

    MEGAPLAN_API_KEY: str
    MEGAPLAN_API_URL: str
    NEXTCLOUD_URL: str
    NEXTCLOUD_USERNAME: str
    NEXTCLOUD_PASSWORD: str
    NEXTCLOUD_CSRF_TOKEN: str

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
