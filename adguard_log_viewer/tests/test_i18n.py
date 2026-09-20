"""The backend's own messages, and that every one of them is translated.

The frontend carries the bulk of the interface text, but a handful of strings
are produced here — validation errors, "not found" replies, and the diagnostics
that explain how AdGuard Home was located. They appear on the same screens as
everything else, so a Hungarian user should not meet them in English.

The parity test below reads the source for ``Message(...)`` calls, so a message
added later without a translation fails the build rather than quietly falling
back to English in front of a user.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.i18n import (
    CATALOG,
    DEFAULT_LANGUAGE,
    LANGUAGES,
    Message,
    current_language,
    detail_of,
    localize,
    localize_all,
    normalize_language,
    reset_current_language,
    resolve_language,
    set_current_language,
)

APP_DIR = Path(__file__).resolve().parents[1] / "app"

#: A msgid made only of placeholders has nothing to translate.
PLACEHOLDERS_ONLY = re.compile(r"^(?:\s*\{\w+\}\s*)+$")


def collect_msgids() -> dict[str, list[str]]:
    """Every literal passed to ``Message(...)``, with where it came from."""
    found: dict[str, list[str]] = {}

    def record(value: str, where: str) -> None:
        found.setdefault(value, []).append(where)

    for path in sorted(APP_DIR.rglob("*.py")):
        if path.name == "i18n.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Message"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                record(node.args[0].value, f"{path.name}:{node.lineno}")
    return found


class TestCatalogue:
    def test_every_message_has_a_translation(self) -> None:
        msgids = collect_msgids()
        assert msgids, "no Message() calls found — has the scan stopped working?"
        for language in LANGUAGES:
            if language == DEFAULT_LANGUAGE:
                continue
            missing = {
                msgid: where
                for msgid, where in msgids.items()
                if msgid not in CATALOG[language] and not PLACEHOLDERS_ONLY.match(msgid)
            }
            assert not missing, f"untranslated ({language}): {missing}"

    def test_no_stale_entries(self) -> None:
        """A translation with no message left to attach to is dead weight."""
        msgids = set(collect_msgids())
        for language in LANGUAGES:
            if language == DEFAULT_LANGUAGE:
                continue
            stale = sorted(set(CATALOG[language]) - msgids)
            assert not stale, f"stale ({language}): {stale}"

    def test_translations_use_the_same_placeholders(self) -> None:
        pattern = re.compile(r"\{(\w+)\}")
        for language, entries in CATALOG.items():
            for msgid, translation in entries.items():
                assert set(pattern.findall(translation)) == set(pattern.findall(msgid)), (
                    f"{language}: placeholders differ for {msgid!r}"
                )


class TestMessage:
    def test_it_is_a_string_holding_the_english_text(self) -> None:
        message = Message("Device not found")
        assert isinstance(message, str)
        assert message == "Device not found"
        assert f"{message}!" == "Device not found!"

    def test_parameters_are_substituted_in_both_languages(self) -> None:
        message = Message("Unknown filter field {field}", field="'nope'")
        assert message == "Unknown filter field 'nope'"
        assert message.localized("hu") == "Ismeretlen szűrőmező: 'nope'"

    def test_a_missing_translation_falls_back_to_english(self) -> None:
        message = Message("Something no catalogue knows about")
        assert message.localized("hu") == "Something no catalogue knows about"

    def test_an_unknown_language_falls_back_to_english(self) -> None:
        assert Message("Device not found").localized("de") == "Device not found"

    def test_a_nested_message_is_translated_too(self) -> None:
        inner = Message("unknown version")
        outer = Message(
            "'{name}' ({version}): {explanation}",
            name="AdGuard Home",
            version=inner,
            explanation=Message("the Supervisor reported no port mapping for this app"),
        )
        assert "unknown version" in outer
        localized = outer.localized("hu")
        assert "ismeretlen verzió" in localized
        assert "porthozzárendelést" in localized

    def test_localize_leaves_plain_values_alone(self) -> None:
        assert localize("plain", "hu") == "plain"
        assert localize(None, "hu") is None
        assert localize_all([Message("Tag not found"), "raw"], "hu") == [
            "A címke nem található",
            "raw",
        ]

    def test_detail_of_keeps_the_message(self) -> None:
        err = ValueError(Message("A tag needs a name"))
        detail = detail_of(err)
        assert isinstance(detail, Message)
        assert detail.localized("hu") == "A címkének kell egy név"

    def test_detail_of_handles_a_plain_error(self) -> None:
        assert detail_of(ValueError("just text")) == "just text"
        assert detail_of(ValueError()) == ""


class TestLanguageResolution:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [("hu", "hu"), ("HU", "hu"), ("hu-HU", "hu"), ("en_GB", "en"), ("de", None), ("", None)],
    )
    def test_normalize(self, given: str, expected: str | None) -> None:
        assert normalize_language(given) == expected

    def test_the_header_wins(self) -> None:
        assert resolve_language("hu-HU,hu;q=0.9,en;q=0.8", "en") == "hu"

    def test_an_unsupported_header_language_is_skipped(self) -> None:
        assert resolve_language("de-DE,de;q=0.9,hu;q=0.5") == "hu"

    def test_the_stored_preference_is_the_fallback(self) -> None:
        assert resolve_language(None, "hu") == "hu"
        assert resolve_language("de", "hu") == "hu"

    def test_auto_is_not_a_language(self) -> None:
        assert resolve_language(None, "auto") == "en"

    def test_nothing_known_means_english(self) -> None:
        assert resolve_language(None, None) == "en"

    def test_the_context_variable_round_trips(self) -> None:
        token = set_current_language("hu")
        try:
            assert current_language() == "hu"
            assert Message("Tag not found").localized() == "A címke nem található"
        finally:
            reset_current_language(token)
        assert current_language() == "en"

    def test_an_unknown_language_is_not_stored(self) -> None:
        token = set_current_language("de")
        try:
            assert current_language() == "en"
        finally:
            reset_current_language(token)


class TestOverTheWire:
    """The language actually reaches the responses a browser gets back."""

    def test_an_error_is_returned_in_the_requested_language(self, bare_client) -> None:
        english = bare_client.get("/api/domains/999999")
        assert english.status_code == 404
        assert english.json()["detail"] == "Domain not found"

        hungarian = bare_client.get(
            "/api/domains/999999", headers={"Accept-Language": "hu-HU,hu;q=0.9"}
        )
        assert hungarian.status_code == 404
        assert hungarian.json()["detail"] == "A domain nem található"

    def test_a_validation_error_is_translated_too(self, bare_client) -> None:
        response = bare_client.post(
            "/api/tags", json={"name": "", "kind": "tag"}, headers={"Accept-Language": "hu"}
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "A címkének kell egy név"

    def test_the_adguard_diagnostics_are_translated(self, bare_client) -> None:
        """The provider status the Settings page shows follows the language."""
        response = bare_client.get("/api/status", headers={"Accept-Language": "hu"})
        assert response.status_code == 200
        detail = response.json()["provider"]["detail"]
        assert "nem létezik ezen a konténeren belül" in detail

    def test_an_unknown_language_falls_back_to_english(self, bare_client) -> None:
        response = bare_client.get("/api/domains/999999", headers={"Accept-Language": "de-DE"})
        assert response.json()["detail"] == "Domain not found"

    def test_requests_do_not_leak_a_language_into_each_other(self, bare_client) -> None:
        bare_client.get("/api/domains/999999", headers={"Accept-Language": "hu"})
        response = bare_client.get("/api/domains/999999")
        assert response.json()["detail"] == "Domain not found"
