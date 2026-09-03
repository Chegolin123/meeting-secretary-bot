"""Конфигурация приложения (env-driven)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str = ""
    telegram_proxy: str | None = None  # socks5://host:port — туннель к api.telegram.org

    # STT
    stt_provider: str = "assemblyai"  # v1.3.0: assemblyai | speechkit
    assemblyai_api_key: str = ""
    assemblyai_base_url: str = "https://api.assemblyai.com"
    assemblyai_proxy: str | None = None  # socks5://127.0.0.1:1082 — стабильный маршрут через NL VPS
    speechkit_api_key: str = ""  # или speechkit_iam_token (для сервисных аккаунтов)
    speechkit_iam_token: str = ""
    speechkit_folder_id: str = ""

    # Оплата (v1.1.0): stars | yookassa
    payment_provider: str = "stars"

    # LLM
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # Приложение
    max_file_mb: int = 20  # лимит Bot API на скачивание (Local Bot API Server — v1.1.0)
    retention_days: int = 7  # файлы храним 7 дней, затем удаляем (решение Н1)
    language_code: str = "ru"
    db_path: str = "data/secretary.db"
    data_dir: str = "data"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    admin_tg_ids: str = ""  # владельцы бота через запятую (admin-панель)

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()