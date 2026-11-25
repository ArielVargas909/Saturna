import os

import pytest

from app.core.config import Settings, get_settings


def test_test_environment_uses_long_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "saturna-test-secret-32-bytes-minimo")
    get_settings.cache_clear()
    settings = get_settings()
    assert len(settings.jwt_secret) >= 32
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "secret",
    ["", "cambia-esto-en-produccion", "corta"],
)
def test_production_rejects_missing_or_example_secret(monkeypatch, secret):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", secret)
    with pytest.raises(RuntimeError):
        Settings(_env_file=None)


def test_development_generates_ephemeral_secret(monkeypatch, caplog):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    settings = Settings(_env_file=None)
    assert len(settings.jwt_secret) >= 32
    assert "efímera" in caplog.text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "postgresql://user:pass@ep-demo.aws.neon.tech/neondb?sslmode=require",
            "postgresql+psycopg://user:pass@ep-demo.aws.neon.tech/neondb?sslmode=require",
        ),
        (
            "postgres://user:pass@host/db",
            "postgresql+psycopg://user:pass@host/db",
        ),
        (
            "sqlite:///./saturna.db",
            "sqlite:///./saturna.db",
        ),
    ],
)
def test_database_url_normalizes_postgres_driver(monkeypatch, raw, expected):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", raw)
    settings = Settings(_env_file=None)
    assert settings.database_url == expected
