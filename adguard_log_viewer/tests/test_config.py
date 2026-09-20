"""Configuration layering: environment > app options > defaults."""

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


class TestContainerEnvironment:
    """s6-overlay strips the environment from the process it launches.

    The Home Assistant base images use s6 as their init, and it hands the
    launched process a bare environment — ``PATH``, ``PWD`` and little else —
    keeping the real one in ``/run/s6/container_environment``. Programs are
    meant to be started through ``with-contenv``; the Dockerfile now does that,
    and this fallback means the app is correct even when it is not.

    Without it the app never saw ``SUPERVISOR_TOKEN``, so it could not ask
    the Supervisor where AdGuard is, and never saw ``TZ``, so every timestamp
    was UTC.
    """

    def test_a_variable_is_read_from_the_s6_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_dir = tmp_path / "container_environment"
        env_dir.mkdir()
        (env_dir / "SUPERVISOR_TOKEN").write_text("abc123", encoding="utf-8")
        (env_dir / "TZ").write_text("Europe/Budapest\n", encoding="utf-8")
        monkeypatch.setenv("S6_ENVIRONMENT_DIR", str(env_dir))
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
        monkeypatch.delenv("TZ", raising=False)

        settings = Settings()
        assert settings.supervisor_token == "abc123"
        assert settings.has_supervisor is True
        # A trailing newline is s6's, not part of the value.
        assert settings.timezone == "Europe/Budapest"

    def test_a_real_environment_variable_still_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_dir = tmp_path / "container_environment"
        env_dir.mkdir()
        (env_dir / "SUPERVISOR_TOKEN").write_text("from-s6", encoding="utf-8")
        monkeypatch.setenv("S6_ENVIRONMENT_DIR", str(env_dir))
        monkeypatch.setenv("SUPERVISOR_TOKEN", "from-env")
        assert Settings().supervisor_token == "from-env"

    def test_the_options_file_is_still_consulted_after_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_dir = tmp_path / "container_environment"
        env_dir.mkdir()
        monkeypatch.setenv("S6_ENVIRONMENT_DIR", str(env_dir))
        monkeypatch.delenv("ADGUARD_URL", raising=False)
        path = write_options(tmp_path, {"adguard_url": "http://from-options"})
        monkeypatch.setenv("OPTIONS_FILE", str(path))
        assert Settings().adguard_url == "http://from-options"

    def test_a_missing_directory_is_not_an_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("S6_ENVIRONMENT_DIR", str(tmp_path / "nope"))
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
        assert Settings().supervisor_token == ""
        assert Settings().has_supervisor is False

    def test_an_unreadable_entry_is_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_dir = tmp_path / "container_environment"
        env_dir.mkdir()
        # A directory where a file is expected.
        (env_dir / "SUPERVISOR_TOKEN").mkdir()
        monkeypatch.setenv("S6_ENVIRONMENT_DIR", str(env_dir))
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
        assert Settings().supervisor_token == ""

    def test_an_empty_value_does_not_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_dir = tmp_path / "container_environment"
        env_dir.mkdir()
        (env_dir / "ADGUARD_URL").write_text("\n", encoding="utf-8")
        monkeypatch.setenv("S6_ENVIRONMENT_DIR", str(env_dir))
        monkeypatch.delenv("ADGUARD_URL", raising=False)
        assert Settings().adguard_url == ""
