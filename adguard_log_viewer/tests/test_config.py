"""Configuration layering: environment > add-on options > defaults."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import Settings, load_options, reset_settings


@pytest.fixture(autouse=True)
def clean_settings() -> None:
    reset_settings()
    yield
    reset_settings()


def write_options(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "options.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestOptionsFile:
    def test_missing_file_is_not_an_error(self, tmp_path: Path) -> None:
        assert load_options(tmp_path / "nope.json") == {}

    def test_broken_file_is_not_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "options.json"
        path.write_text("{not json", encoding="utf-8")
        assert load_options(path) == {}

    def test_options_are_read(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = write_options(
            tmp_path,
            {
                "adguard_url": "http://10.0.0.5:3000",
                "adguard_username": "ha-user",
                "adguard_password": "secret",
                "poll_interval": 30,
                "retention_days": 7,
                "log_level": "debug",
                "adguard_verify_ssl": True,
            },
        )
        monkeypatch.setenv("OPTIONS_FILE", str(path))
        for name in ("ADGUARD_URL", "POLL_INTERVAL", "RETENTION_DAYS", "LOG_LEVEL"):
            monkeypatch.delenv(name, raising=False)

        settings = Settings()
        assert settings.adguard_url == "http://10.0.0.5:3000"
        assert settings.adguard_username == "ha-user"
        assert settings.adguard_password == "secret"
        assert settings.poll_interval == 30
        assert settings.retention_days == 7
        assert settings.log_level == "debug"
        assert settings.adguard_verify_ssl is True

    def test_environment_wins_over_options(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = write_options(tmp_path, {"poll_interval": 30, "adguard_url": "http://from-file"})
        monkeypatch.setenv("OPTIONS_FILE", str(path))
        monkeypatch.setenv("POLL_INTERVAL", "5")
        monkeypatch.setenv("ADGUARD_URL", "http://from-env")

        settings = Settings()
        assert settings.poll_interval == 5
        assert settings.adguard_url == "http://from-env"

    def test_empty_option_falls_through_to_the_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = write_options(tmp_path, {"adguard_url": "", "log_level": ""})
        monkeypatch.setenv("OPTIONS_FILE", str(path))
        monkeypatch.delenv("ADGUARD_URL", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        settings = Settings()
        assert settings.adguard_url == ""
        assert settings.log_level == "info"


class TestClamping:
    @pytest.mark.parametrize(
        ("option", "value", "attribute", "expected"),
        [
            ("poll_interval", 0, "poll_interval", 2),
            ("poll_interval", 999_999, "poll_interval", 3600),
            ("retention_days", -5, "retention_days", 0),
            ("ingest_batch_size", 1, "ingest_batch_size", 50),
            ("max_pages_per_poll", 0, "max_pages_per_poll", 1),
            ("poll_interval", "not a number", "poll_interval", 10),
        ],
    )
    def test_out_of_range_values_are_clamped(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        option: str,
        value: object,
        attribute: str,
        expected: int,
    ) -> None:
        path = write_options(tmp_path, {option: value})
        monkeypatch.setenv("OPTIONS_FILE", str(path))
        monkeypatch.delenv(option.upper(), raising=False)
        assert getattr(Settings(), attribute) == expected


class TestRedaction:
    def test_the_password_is_never_exposed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = write_options(tmp_path, {"adguard_password": "hunter2"})
        monkeypatch.setenv("OPTIONS_FILE", str(path))
        monkeypatch.delenv("ADGUARD_PASSWORD", raising=False)

        redacted = Settings().redacted()
        assert "hunter2" not in json.dumps(redacted)
        assert redacted["adguard_password_set"] is True
