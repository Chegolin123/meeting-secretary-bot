"""Тесты: конфигурация."""

from secretary.config import Settings


def test_defaults():
    s = Settings()
    assert s.max_file_mb == 20
    assert s.max_file_bytes == 20 * 1024 * 1024
    assert s.stt_provider == "assemblyai"
    assert s.language_code == "ru"


def test_env_override(monkeypatch):
    monkeypatch.setenv("MAX_FILE_MB", "50")
    monkeypatch.setenv("STT_PROVIDER", "speechkit")
    s = Settings()
    assert s.max_file_mb == 50
    assert s.max_file_bytes == 50 * 1024 * 1024
    assert s.stt_provider == "speechkit"


def test_proxy_optional():
    s = Settings(telegram_proxy=None)
    assert s.telegram_proxy is None
    s2 = Settings(telegram_proxy="socks5://127.0.0.1:1082")
    assert s2.telegram_proxy.startswith("socks5://")