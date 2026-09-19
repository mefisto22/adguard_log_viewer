"""Domain matching, tag rules and category rules."""

from __future__ import annotations

import pytest

from app.categorization.engine import CategorizationEngine, CategoryRule, Condition, TagRef
from app.categorization.matchers import match, wildcard_to_regex
from app.common.domains import (
    is_subdomain_of,
    normalize_domain,
    parent_domains,
    registrable_domain,
)
from app.db.database import Database
from app.services.classification import TagResolver, classify_domains, stale_domains
from app.services.rules_service import build_engine, create_rule, delete_rule, update_rule


class TestDomainHelpers:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Example.COM.", "example.com"),
            ("  www.Example.com  ", "www.example.com"),
            ("", ""),
            (None, ""),
            (".", ""),
        ],
    )
    def test_normalisation(self, raw: str | None, expected: str) -> None:
        assert normalize_domain(raw) == expected

    @pytest.mark.parametrize(
        ("domain", "expected"),
        [
            ("www.youtube.com", "youtube.com"),
            ("r5---sn-4g5edndd.googlevideo.com", "googlevideo.com"),
            ("www.news.bbc.co.uk", "bbc.co.uk"),
            ("shop.example.com.au", "example.com.au"),
            ("index.hu", "index.hu"),
            ("localhost", "localhost"),
            ("a.b.c.d.example.org", "example.org"),
        ],
    )
    def test_registrable_domain(self, domain: str, expected: str) -> None:
        assert registrable_domain(domain) == expected

    def test_parent_domains(self) -> None:
        assert parent_domains("a.b.example.com") == [
            "a.b.example.com",
            "b.example.com",
            "example.com",
            "com",
        ]

    @pytest.mark.parametrize(
        ("domain", "suffix", "expected"),
        [
            ("youtube.com", "youtube.com", True),
            ("www.youtube.com", "youtube.com", True),
            ("notyoutube.com", "youtube.com", False),
            ("youtube.com.evil.net", "youtube.com", False),
            ("", "youtube.com", False),
        ],
    )
    def test_is_subdomain_of(self, domain: str, suffix: str, expected: bool) -> None:
        assert is_subdomain_of(domain, suffix) is expected


class TestMatchers:
    @pytest.mark.parametrize(
        ("operator", "subject", "value", "expected"),
        [
            ("suffix", "www.youtube.com", "youtube.com", True),
            ("suffix", "evil-youtube.com", "youtube.com", False),
            ("equals", "youtube.com", "YouTube.com", True),
            ("contains", "r3.googlevideo.com", "googlevideo", True),
            ("startswith", "www.google.com", "www.", True),
            ("endswith", "i.ytimg.com", "ytimg.com", True),
            ("wildcard", "cdn.gstatic.com", "*.gstatic.com", True),
            ("wildcard", "gstatic.com", "*.gstatic.com", False),
            ("regex", "r5---sn-abc.googlevideo.com", r"^r\d+", True),
            ("regex", "example.com", "([broken", False),
            ("nonsense", "example.com", "x", False),
        ],
    )
    def test_operators(self, operator: str, subject: str, value: str, expected: bool) -> None:
        assert match(operator, subject, value) is expected

    def test_wildcard_translation_escapes_dots(self) -> None:
        assert wildcard_to_regex("*.gstatic.com") == r"^.*\.gstatic\.com$"


class TestEngine:
    def test_a_domain_can_carry_several_tags(self, engine: CategorizationEngine) -> None:
        tags = {(tag.name, tag.kind) for tag in engine.classify("www.youtube.com")}
        assert ("YouTube", "tag") in tags
        assert ("Google", "tag") in tags
        assert ("Video", "category") in tags
        assert ("Streaming", "category") in tags

    @pytest.mark.parametrize(
        ("domain", "expected_tag"),
        [
            ("r5---sn-x.googlevideo.com", ("YouTube", "tag")),
            ("graph.facebook.com", ("Facebook", "tag")),
            ("doubleclick.net", ("Advertising", "category")),
            ("vortex.data.microsoft.com", ("Telemetry", "category")),
            ("claude.ai", ("AI", "category")),
            ("index.hu", ("News", "category")),
            ("shelly.cloud", ("IoT", "category")),
            ("steampowered.com", ("Gaming", "category")),
        ],
    )
    def test_builtin_rules(
        self, engine: CategorizationEngine, domain: str, expected_tag: tuple[str, str]
    ) -> None:
        tags = {(tag.name, tag.kind) for tag in engine.classify(domain)}
        assert expected_tag in tags

    def test_unknown_domains_get_nothing(self, engine: CategorizationEngine) -> None:
        assert engine.classify("something-nobody-owns.invalid") == ()

    def test_match_mode_all(self) -> None:
        rule = CategoryRule(
            name="Google video only",
            match_mode="all",
            conditions=(
                Condition(operator="contains", value="google"),
                Condition(operator="contains", value="video"),
            ),
            tags=(TagRef(name="GoogleVideo"),),
        )
        engine = CategorizationEngine([rule])
        assert engine.classify("r3.googlevideo.com")
        assert not engine.classify("www.google.com")

    def test_disabled_rules_are_ignored(self) -> None:
        rule = CategoryRule(
            name="off",
            enabled=False,
            conditions=(Condition(operator="suffix", value="example.com"),),
            tags=(TagRef(name="Example"),),
        )
        assert CategorizationEngine([rule]).classify("example.com") == ()

    def test_explain_reports_the_matching_rules(self, engine: CategorizationEngine) -> None:
        matches = engine.explain("www.youtube.com")
        assert any(entry["rule"] == "YouTube" for entry in matches)

    def test_user_rule_example_from_the_brief(self) -> None:
        """domain contains youtube OR googlevideo OR endsWith ytimg.com."""
        rule = CategoryRule(
            name="YouTube",
            conditions=(
                Condition(operator="contains", value="youtube"),
                Condition(operator="contains", value="googlevideo"),
                Condition(operator="endswith", value="ytimg.com"),
            ),
            tags=(
                TagRef(name="YouTube"),
                TagRef(name="Video", kind="category"),
                TagRef(name="Google"),
            ),
        )
        engine = CategorizationEngine([rule])
        for domain in ("m.youtube.com", "r1.googlevideo.com", "i.ytimg.com"):
            names = {tag.name for tag in engine.classify(domain)}
            assert names == {"YouTube", "Video", "Google"}


class TestPersistedClassification:
    def test_classification_writes_domain_tags(
        self, db: Database, engine: CategorizationEngine
    ) -> None:
        with db.write() as conn:
            conn.execute("INSERT INTO domains (name) VALUES ('www.youtube.com')")
            domain_id = conn.execute("SELECT id FROM domains").fetchone()["id"]
            classify_domains(conn, engine, [(domain_id, "www.youtube.com")], revision=5)

        with db.read() as conn:
            rows = conn.execute(
                "SELECT t.name, t.kind, dt.source FROM domain_tags dt "
                "JOIN tags t ON t.id = dt.tag_id"
            ).fetchall()
            revision = conn.execute("SELECT ruleset_rev FROM domains").fetchone()["ruleset_rev"]
        names = {row["name"] for row in rows}
        assert {"YouTube", "Google", "Video"} <= names
        assert revision == 5
        assert all(row["source"] == "builtin" for row in rows)

    def test_manual_tags_survive_reclassification(
        self, db: Database, engine: CategorizationEngine
    ) -> None:
        with db.write() as conn:
            conn.execute("INSERT INTO domains (name) VALUES ('example.com')")
            domain_id = conn.execute("SELECT id FROM domains").fetchone()["id"]
            tag_id = conn.execute(
                "INSERT INTO tags (name, kind) VALUES ('Mine', 'tag') RETURNING id"
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO domain_tags (domain_id, tag_id, source) VALUES (?, ?, 'manual')",
                (domain_id, tag_id),
            )
            classify_domains(conn, engine, [(domain_id, "example.com")], revision=2)

        with db.read() as conn:
            rows = conn.execute("SELECT source FROM domain_tags").fetchall()
        assert [row["source"] for row in rows] == ["manual"]

    def test_a_rule_change_marks_domains_stale(self, db: Database) -> None:
        with db.write() as conn:
            conn.execute("INSERT INTO domains (name, ruleset_rev) VALUES ('a.com', 1)")
            create_rule(
                conn,
                {
                    "name": "Custom",
                    "conditions": [{"field": "domain", "operator": "suffix", "value": "a.com"}],
                    "tags": [{"name": "Custom", "kind": "tag"}],
                },
            )
            revision = conn.execute(
                "SELECT value FROM settings WHERE key = 'ruleset_rev'"
            ).fetchone()["value"]

        with db.read() as conn:
            pending = stale_domains(conn, revision=int(revision))
        assert pending == [(1, "a.com")]

    def test_user_rules_are_merged_into_the_engine(self, db: Database) -> None:
        with db.write() as conn:
            rule_id = create_rule(
                conn,
                {
                    "name": "Work laptop stuff",
                    "conditions": [
                        {"field": "domain", "operator": "contains", "value": "intranet"}
                    ],
                    "tags": [{"name": "Work", "kind": "category"}],
                },
            )
        with db.read() as conn:
            merged = build_engine(conn)
        assert {tag.name for tag in merged.classify("intranet.corp.local")} == {"Work"}

        with db.write() as conn:
            update_rule(
                conn,
                rule_id,
                {
                    "name": "Work laptop stuff",
                    "conditions": [{"field": "domain", "operator": "contains", "value": "corp"}],
                    "tags": [{"name": "Work", "kind": "category"}],
                },
            )
        with db.read() as conn:
            merged = build_engine(conn)
        assert merged.classify("intranet.corp.local")
        assert not merged.classify("intranet.other.local")

        with db.write() as conn:
            assert delete_rule(conn, rule_id) is True
        with db.read() as conn:
            assert not build_engine(conn).classify("intranet.corp.local")

    def test_tag_resolver_creates_tags_once(self, db: Database) -> None:
        resolver = TagResolver()
        with db.write() as conn:
            resolver.prime(conn)
            first = resolver.resolve(conn, TagRef(name="Brand new", kind="tag"))
            second = resolver.resolve(conn, TagRef(name="Brand new", kind="tag"))
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM tags WHERE name = 'Brand new'"
            ).fetchone()["n"]
        assert first == second
        assert count == 1
