"""The add-on ships correctly.

These tests guard the things that are invisible until Home Assistant refuses to
show the add-on, or until the container starts with a feature silently missing.
Both failure modes have happened:

* ``.gitignore`` had an unanchored ``data/`` rule, which quietly excluded
  ``app/categorization/data/builtin_rules.json``. Everything passed locally
  against the working tree and every categorisation test failed in CI;
* ``config.yaml`` carried ``image: null``, which fails the Supervisor's
  ``docker_image`` validator ("expected a non-empty string"). A rejected
  ``config.yaml`` means the add-on never appears in the store at all.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from app.categorization.engine import BUILTIN_PATH, load_builtin_ruleset

ADDON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ADDON_ROOT.parent
CONFIG = ADDON_ROOT / "config.yaml"

#: Architectures the Supervisor still accepts (supervisor/const.py ARCH_ALL).
SUPPORTED_ARCH = {"aarch64", "amd64"}


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=False
    )


def in_git_repo() -> bool:
    return git("rev-parse", "--is-inside-work-tree").returncode == 0


needs_git = pytest.mark.skipif(not in_git_repo(), reason="not a git checkout")


@pytest.fixture(scope="module")
def config() -> dict:
    with CONFIG.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    assert isinstance(loaded, dict)
    return loaded


class TestBuiltinRuleSet:
    def test_the_file_is_present_and_parses(self) -> None:
        assert BUILTIN_PATH.is_file(), f"{BUILTIN_PATH} is missing from the add-on"
        with BUILTIN_PATH.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        assert payload["rules"]
        assert payload["tags"]

    def test_the_engine_loads_a_non_empty_rule_set(self) -> None:
        """The check that catches a rule file missing from the image.

        Every categorisation, tag and dashboard test fails downstream of this
        one, so assert it directly rather than diagnosing it through them.
        """
        ruleset = load_builtin_ruleset()
        assert len(ruleset.rules) > 50
        assert len(ruleset.tags) > 50

        names = {(tag.name, tag.kind) for tag in ruleset.tags}
        # The labels the rest of the test suite relies on.
        for expected in (
            ("YouTube", "tag"),
            ("Google", "tag"),
            ("Video", "category"),
            ("Streaming", "category"),
            ("Facebook", "tag"),
            ("Advertising", "category"),
            ("Telemetry", "category"),
            ("AI", "category"),
            ("News", "category"),
            ("IoT", "category"),
            ("Gaming", "category"),
        ):
            assert expected in names, f"{expected} is missing from the built-in tags"

    @needs_git
    def test_the_rule_file_is_committed(self) -> None:
        """A file present locally but absent from the repository builds a
        broken image, and no other test can tell the difference."""
        relative = BUILTIN_PATH.relative_to(REPO_ROOT)
        tracked = git("ls-files", "--error-unmatch", str(relative))
        assert tracked.returncode == 0, (
            f"{relative} is not tracked by git. Check .gitignore — an unanchored "
            f"pattern such as 'data/' also matches this directory."
        )

    @needs_git
    def test_nothing_the_image_needs_is_ignored(self) -> None:
        wanted = [
            BUILTIN_PATH,
            ADDON_ROOT / "app" / "static" / "index.html",
            ADDON_ROOT / "config.yaml",
            ADDON_ROOT / "Dockerfile",
            ADDON_ROOT / "requirements.txt",
        ]
        # --no-index makes git answer on the patterns alone. Without it a file
        # that is already tracked is never reported, so a bad pattern added
        # later would slip through unnoticed.
        ignored = [
            path.relative_to(REPO_ROOT)
            for path in wanted
            if git(
                "check-ignore", "--no-index", "-q", str(path.relative_to(REPO_ROOT))
            ).returncode
            == 0
        ]
        assert not ignored, (
            f"these files match a .gitignore pattern: {ignored}. An unanchored rule "
            f"such as 'data/' matches at every depth — anchor it with a leading slash."
        )


class TestAddonConfig:
    def test_required_keys(self, config: dict) -> None:
        for key in ("name", "version", "slug", "description", "arch"):
            assert config.get(key), f"config.yaml is missing '{key}'"

    def test_the_slug_matches_the_directory(self, config: dict) -> None:
        # The Supervisor keys the add-on's data directory off the slug.
        assert config["slug"] == ADDON_ROOT.name

    def test_architectures_are_ones_the_supervisor_accepts(self, config: dict) -> None:
        assert set(config["arch"]) <= SUPPORTED_ARCH
        assert set(config["arch"]) == SUPPORTED_ARCH

    @pytest.mark.parametrize("key", ["image", "codenotary"])
    def test_no_empty_valued_keys_that_fail_validation(self, config: dict, key: str) -> None:
        """``image: null`` fails ``docker_image`` and invalidates the whole file.

        A rejected config.yaml makes the add-on invisible in the store, with
        nothing in the UI to say why. Omitting the key means "build locally",
        which is what this add-on wants.
        """
        if key in config:
            assert config[key], f"'{key}' is present but empty — omit it instead"

    def test_every_default_option_is_declared_in_the_schema(self, config: dict) -> None:
        missing = set(config.get("options", {})) - set(config.get("schema", {}))
        assert not missing, f"options without a schema entry: {sorted(missing)}"

    def test_map_entries_use_the_current_form(self, config: dict) -> None:
        """The dict form avoids the Supervisor's legacy string coercion."""
        entries = config.get("map", [])
        assert all(isinstance(entry, dict) for entry in entries), (
            "use `- type: share` / `read_only: true` rather than the legacy `share:ro` string"
        )
        assert all("type" in entry for entry in entries)

    def test_no_deprecated_map_types(self, config: dict) -> None:
        # Renamed by the Supervisor in 2026.07.
        deprecated = {"addons", "all_addon_configs", "addon_config"}
        used = {
            entry["type"] if isinstance(entry, dict) else str(entry).split(":", 1)[0]
            for entry in config.get("map", [])
        }
        assert not (used & deprecated), f"deprecated map types: {sorted(used & deprecated)}"

    def test_ingress_is_configured(self, config: dict) -> None:
        assert config.get("ingress") is True
        assert isinstance(config.get("ingress_port"), int)
        # Live updates arrive over SSE, which the Supervisor buffers otherwise.
        assert config.get("ingress_stream") is True

    def test_the_supervisor_role_is_the_least_privileged_one_that_works(
        self, config: dict
    ) -> None:
        assert config.get("hassio_api") is True
        assert config.get("hassio_role", "default") == "default"

    def test_the_version_matches_the_changelog(self, config: dict) -> None:
        changelog = (ADDON_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        assert f"## {config['version']}" in changelog

    def test_the_version_matches_the_application(self, config: dict) -> None:
        """``/api/health`` and the Settings page report ``app.__version__``.

        If it drifts from config.yaml, the UI claims a different version than
        the one Home Assistant installed.
        """
        from app import __version__

        assert config["version"] == __version__


class TestDockerfile:
    def test_the_entry_point_restores_the_container_environment(self) -> None:
        """s6-overlay launches CMD with a bare environment.

        The Home Assistant base images use s6 as their init, and it keeps the
        real container environment in /run/s6/container_environment rather than
        passing it on. Without `with-contenv` the add-on never sees
        SUPERVISOR_TOKEN — so it cannot ask the Supervisor where AdGuard Home
        is — and never sees TZ, so every timestamp is UTC.
        """
        dockerfile = (ADDON_ROOT / "Dockerfile").read_text(encoding="utf-8")
        cmd = [line for line in dockerfile.splitlines() if line.startswith("CMD ")]
        assert cmd, "the Dockerfile declares no CMD"
        assert "with-contenv" in cmd[0], (
            f"CMD must start the app through with-contenv, got: {cmd[0]}"
        )

    def test_the_image_installs_only_from_wheels(self) -> None:
        # A missing wheel should fail the build loudly rather than trying to
        # compile Rust on a Raspberry Pi.
        dockerfile = (ADDON_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "--only-binary" in dockerfile


class TestRepository:
    def test_the_repository_descriptor_is_valid(self) -> None:
        with (REPO_ROOT / "repository.yaml").open(encoding="utf-8") as handle:
            repository = yaml.safe_load(handle)
        assert repository.get("name")
        assert repository.get("url")

    def test_the_frontend_build_is_present(self) -> None:
        index = ADDON_ROOT / "app" / "static" / "index.html"
        assert index.is_file(), "run 'npm run build' in frontend/"
        assets = ADDON_ROOT / "app" / "static" / "assets"
        assert any(assets.glob("*.js"))
        assert any(assets.glob("*.css"))

    def test_index_html_references_files_that_exist(self) -> None:
        index = (ADDON_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        for reference in ("./assets/", "assets/"):
            if reference in index:
                break
        else:  # pragma: no cover - only if the build output changes shape
            pytest.fail("index.html references no assets")

        import re

        for match in re.findall(r'(?:src|href)="\.?/?(assets/[^"]+)"', index):
            assert (ADDON_ROOT / "app" / "static" / match).is_file(), f"missing asset {match}"

    def test_no_editor_or_sync_duplicates_shipped(self) -> None:
        """macOS and iCloud leave "index 2.html" copies behind.

        They are byte-for-byte stale duplicates; shipping them bloats the image
        and, worse, makes it ambiguous which file is current.
        """
        duplicates = [
            path.relative_to(ADDON_ROOT)
            for path in ADDON_ROOT.rglob("* [0-9].*")
            if path.is_file() and ".venv" not in path.parts
        ]
        assert not duplicates, f"copies left behind: {duplicates}"


class TestOptionTranslations:
    """Home Assistant renders the add-on's Configuration tab from these.

    The Supervisor picks the file matching the user's own language, so a missing
    entry shows the raw option key — ``adguard_url`` instead of a label and an
    explanation — to exactly the people who most need the explanation.
    """

    @pytest.fixture
    def translations(self) -> dict[str, dict]:
        return {
            path.stem: yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in sorted((ADDON_ROOT / "translations").glob("*.yaml"))
        }

    def test_one_file_per_language_the_app_speaks(self, translations: dict[str, dict]) -> None:
        from app.i18n import LANGUAGES

        assert set(translations) == set(LANGUAGES)

    def test_every_option_is_described_in_every_language(
        self, config: dict, translations: dict[str, dict]
    ) -> None:
        options = set(config["schema"])
        for language, data in translations.items():
            described = data.get("configuration") or {}
            assert set(described) == options, (
                f"{language}.yaml does not match the schema: "
                f"missing {sorted(options - set(described))}, "
                f"unknown {sorted(set(described) - options)}"
            )
            for key, entry in described.items():
                assert entry.get("name"), f"{language}.yaml: {key} has no name"
                assert entry.get("description"), f"{language}.yaml: {key} has no description"

    def test_the_published_port_is_explained_in_every_language(
        self, config: dict, translations: dict[str, dict]
    ) -> None:
        ports = set(config.get("ports") or {})
        for language, data in translations.items():
            assert set(data.get("network") or {}) == ports, f"{language}.yaml: ports differ"
