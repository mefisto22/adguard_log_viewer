"""Filter engine: parsing, AND/OR nesting, operators and SQL safety."""

from __future__ import annotations

from typing import Any

import pytest

from app.db.database import Database
from app.filters.nodes import FilterError, Group, Predicate, parse_filter, quick_search_filter
from app.filters.sql_builder import compile_filter
from app.services.classification import TagResolver
from app.services.ingest_store import store_records
from app.services.query_service import list_queries
from tests.conftest import make_record

# -- parsing ----------------------------------------------------------------


class TestParsing:
    def test_empty_filters_are_nothing(self) -> None:
        assert parse_filter(None) is None
        assert parse_filter({}) is None
        assert parse_filter({"op": "and", "children": []}) is None

    def test_a_list_is_treated_as_an_and_group(self) -> None:
        node = parse_filter(
            [
                {"field": "domain", "operator": "contains", "value": "a"},
                {"field": "blocked", "operator": "equals", "value": True},
            ]
        )
        assert isinstance(node, Group)
        assert node.op == "and"

    def test_single_child_groups_collapse(self) -> None:
        node = parse_filter(
            {"op": "or", "children": [{"field": "domain", "operator": "contains", "value": "a"}]}
        )
        assert isinstance(node, Predicate)

    def test_field_aliases_resolve(self) -> None:
        node = parse_filter({"field": "user", "operator": "equals", "value": "Peter"})
        assert isinstance(node, Predicate)
        assert node.field == "person"

    @pytest.mark.parametrize(
        "payload",
        [
            {"field": "nope", "operator": "equals", "value": "x"},
            {"field": "domain", "operator": "nope", "value": "x"},
            {"field": "domain", "operator": "contains"},
            {"field": "domain", "operator": "in", "values": []},
            {"op": "xor", "children": []},
            {"op": "not", "children": []},
            {"op": "and", "children": "nope"},
            "a string",
        ],
    )
    def test_invalid_filters_are_rejected(self, payload: Any) -> None:
        with pytest.raises(FilterError):
            parse_filter(payload)

    def test_depth_is_bounded(self) -> None:
        node: dict[str, Any] = {"field": "domain", "operator": "contains", "value": "a"}
        for _ in range(20):
            node = {"op": "and", "children": [node, node]}
        with pytest.raises(FilterError):
            parse_filter(node)

    def test_comma_separated_in_values(self) -> None:
        node = parse_filter({"field": "query_type", "operator": "in", "value": "A, AAAA ,HTTPS"})
        assert isinstance(node, Predicate)
        assert node.values == ["A", "AAAA", "HTTPS"]


# -- SQL generation ---------------------------------------------------------


class TestSqlGeneration:
    def test_values_are_always_bound(self) -> None:
        compiled = compile_filter(
            parse_filter({"field": "domain", "operator": "contains", "value": "'; DROP TABLE x;--"})
        )
        assert "DROP TABLE" not in compiled.sql
        assert compiled.params == ["%'; DROP TABLE x;--%"]

    def test_like_wildcards_in_the_value_are_escaped(self) -> None:
        compiled = compile_filter(
            parse_filter({"field": "domain", "operator": "contains", "value": "100%_a"})
        )
        assert compiled.params == ["%100\\%\\_a%"]

    def test_negation_uses_not_in_for_lookup_fields(self) -> None:
        compiled = compile_filter(
            parse_filter({"field": "domain", "operator": "not_contains", "value": "ads"})
        )
        assert "q.domain_id NOT IN" in compiled.sql

    def test_response_time_is_converted_to_microseconds(self) -> None:
        compiled = compile_filter(
            parse_filter({"field": "response_time", "operator": "gt", "value": 50})
        )
        assert compiled.params == [50000.0]

    def test_result_kind_expands_to_reasons(self) -> None:
        compiled = compile_filter(
            parse_filter({"field": "result", "operator": "equals", "value": "blocked"})
        )
        assert "q.reason IN" in compiled.sql
        assert "FilteredBlackList" in compiled.params

    def test_empty_filter_compiles_to_true(self) -> None:
        compiled = compile_filter(None)
        assert compiled.is_empty
        assert compiled.where() == ""


# -- behaviour against a real database --------------------------------------


@pytest.fixture
def populated(db: Database, engine: Any, base_ts: int) -> Database:
    records = [
        make_record(ts_ns=base_ts + 1, domain="www.youtube.com", client_ip="192.168.1.15",
                    client_name="iPhone"),
        make_record(ts_ns=base_ts + 2, domain="r3.googlevideo.com", client_ip="192.168.1.15",
                    client_name="iPhone"),
        make_record(ts_ns=base_ts + 3, domain="www.google.com", client_ip="192.168.1.16",
                    client_name="MacBook", qtype="AAAA"),
        make_record(ts_ns=base_ts + 4, domain="doubleclick.net", client_ip="192.168.1.20",
                    client_name="TV", reason="FilteredBlackList"),
        make_record(ts_ns=base_ts + 5, domain="index.hu", client_ip="192.168.1.20",
                    client_name="TV", elapsed_us=250_000),
        make_record(ts_ns=base_ts + 6, domain="gstatic.com", client_ip="192.168.1.30",
                    client_name="Tablet"),
    ]
    with db.write() as conn:
        store_records(conn, records, engine=engine, revision=1, resolver=TagResolver())
        peter = conn.execute(
            "INSERT INTO persons (name) VALUES ('Péter') RETURNING id"
        ).fetchone()["id"]
        anna = conn.execute("INSERT INTO persons (name) VALUES ('Anna') RETURNING id").fetchone()[
            "id"
        ]
        conn.execute(
            "UPDATE clients SET person_id = ? WHERE ip IN ('192.168.1.15', '192.168.1.16')",
            (peter,),
        )
        conn.execute("UPDATE clients SET person_id = ? WHERE ip = '192.168.1.20'", (anna,))
        conn.execute("UPDATE clients SET alias = 'Nappali TV' WHERE ip = '192.168.1.20'")
    return db


def _domains(db: Database, node: Any) -> set[str]:
    with db.read() as conn:
        page = list_queries(conn, filter_node=node, limit=100)
    return {item["domain"] for item in page.items}


class TestAnyAndAll:
    def test_any_of_several_terms(self, populated: Database) -> None:
        """The headline case: ANY over googl / youtube / googlevideo."""
        node = quick_search_filter(
            ["googl", "youtube", "googlevideo"], mode="any", fields=("domain",)
        )
        assert _domains(populated, node) == {
            "www.youtube.com",
            "r3.googlevideo.com",
            "www.google.com",
        }

    def test_all_of_several_terms(self, populated: Database) -> None:
        node = quick_search_filter(["googl", "video"], mode="all", fields=("domain",))
        assert _domains(populated, node) == {"r3.googlevideo.com"}

    def test_search_across_several_fields(self, populated: Database) -> None:
        node = quick_search_filter(["TV"], mode="any", fields=("domain", "client_name"))
        assert _domains(populated, node) == {"doubleclick.net", "index.hu"}

    def test_nested_groups(self, populated: Database) -> None:
        """(domain ~ youtube OR googlevideo) AND (person = Péter OR Anna)."""
        node = parse_filter(
            {
                "op": "and",
                "children": [
                    {
                        "op": "or",
                        "children": [
                            {"field": "domain", "operator": "contains", "value": "youtube"},
                            {"field": "domain", "operator": "contains", "value": "googlevideo"},
                        ],
                    },
                    {
                        "op": "or",
                        "children": [
                            {"field": "person", "operator": "equals", "value": "Péter"},
                            {"field": "person", "operator": "equals", "value": "Anna"},
                        ],
                    },
                    {"field": "timestamp", "operator": "gte", "value": "now-24h"},
                ],
            }
        )
        assert _domains(populated, node) == {"www.youtube.com", "r3.googlevideo.com"}

    def test_not_group(self, populated: Database) -> None:
        node = parse_filter(
            {
                "op": "not",
                "children": [{"field": "domain", "operator": "contains", "value": "googl"}],
            }
        )
        assert _domains(populated, node) == {
            "www.youtube.com",  # contains neither "googl" nor "googlevideo"
            "doubleclick.net",
            "index.hu",
            "gstatic.com",
        }


class TestOperators:
    @pytest.mark.parametrize(
        ("operator", "value", "expected"),
        [
            ("equals", "index.hu", {"index.hu"}),
            ("not_equals", "index.hu", {"www.youtube.com", "r3.googlevideo.com",
                                        "www.google.com", "doubleclick.net", "gstatic.com"}),
            ("contains", "google", {"r3.googlevideo.com", "www.google.com"}),
            ("startswith", "www.", {"www.youtube.com", "www.google.com"}),
            ("endswith", ".hu", {"index.hu"}),
            ("regex", r"^r\d+\.", {"r3.googlevideo.com"}),
            ("regex", r"(youtube|googlevideo)\.com$", {"www.youtube.com", "r3.googlevideo.com"}),
            ("not_regex", r"\.com$", {"index.hu", "doubleclick.net"}),
        ],
    )
    def test_domain_operators(
        self, populated: Database, operator: str, value: str, expected: set[str]
    ) -> None:
        node = parse_filter({"field": "domain", "operator": operator, "value": value})
        assert _domains(populated, node) == expected

    def test_in_and_not_in(self, populated: Database) -> None:
        node = parse_filter(
            {"field": "domain", "operator": "in", "values": ["index.hu", "gstatic.com"]}
        )
        assert _domains(populated, node) == {"index.hu", "gstatic.com"}

        node = parse_filter(
            {"field": "query_type", "operator": "not_in", "values": ["AAAA"]}
        )
        assert "www.google.com" not in _domains(populated, node)

    def test_an_invalid_regex_matches_nothing_instead_of_failing(
        self, populated: Database
    ) -> None:
        node = parse_filter({"field": "domain", "operator": "regex", "value": "([unclosed"})
        assert _domains(populated, node) == set()

    def test_blocked_and_result(self, populated: Database) -> None:
        assert _domains(
            populated, parse_filter({"field": "blocked", "operator": "equals", "value": True})
        ) == {"doubleclick.net"}
        assert _domains(
            populated, parse_filter({"field": "result", "operator": "equals", "value": "blocked"})
        ) == {"doubleclick.net"}

    def test_numeric_comparison(self, populated: Database) -> None:
        node = parse_filter({"field": "response_time", "operator": "gt", "value": 100})
        assert _domains(populated, node) == {"index.hu"}

    def test_registrable_domain(self, populated: Database) -> None:
        node = parse_filter(
            {"field": "registrable_domain", "operator": "equals", "value": "google.com"}
        )
        assert _domains(populated, node) == {"www.google.com"}


class TestIdentityFilters:
    def test_client_ip(self, populated: Database) -> None:
        node = parse_filter({"field": "client_ip", "operator": "equals", "value": "192.168.1.20"})
        assert _domains(populated, node) == {"doubleclick.net", "index.hu"}

    def test_client_name_prefers_the_alias(self, populated: Database) -> None:
        node = parse_filter(
            {"field": "client_name", "operator": "equals", "value": "Nappali TV"}
        )
        assert _domains(populated, node) == {"doubleclick.net", "index.hu"}
        # The AdGuard name it replaced no longer matches.
        node = parse_filter({"field": "client_name", "operator": "equals", "value": "TV"})
        assert _domains(populated, node) == set()

    def test_person_covers_every_device(self, populated: Database) -> None:
        node = parse_filter({"field": "person", "operator": "equals", "value": "Péter"})
        assert _domains(populated, node) == {
            "www.youtube.com",
            "r3.googlevideo.com",
            "www.google.com",
        }

    def test_several_people_at_once(self, populated: Database) -> None:
        node = parse_filter(
            {"field": "person", "operator": "in", "values": ["Péter", "Anna"]}
        )
        assert _domains(populated, node) == {
            "www.youtube.com",
            "r3.googlevideo.com",
            "www.google.com",
            "doubleclick.net",
            "index.hu",
        }

    def test_tag_and_category(self, populated: Database) -> None:
        assert _domains(
            populated, parse_filter({"field": "tag", "operator": "equals", "value": "YouTube"})
        ) == {"www.youtube.com", "r3.googlevideo.com"}
        assert _domains(
            populated,
            parse_filter({"field": "category", "operator": "equals", "value": "Advertising"}),
        ) == {"doubleclick.net"}


class TestPaging:
    def test_limit_offset_and_total(self, populated: Database) -> None:
        with populated.read() as conn:
            first = list_queries(conn, limit=2, offset=0)
            second = list_queries(conn, limit=2, offset=2)
        assert len(first.items) == 2
        assert first.total == 6
        assert first.has_more is True
        assert {item["id"] for item in first.items} & {item["id"] for item in second.items} == set()

    def test_sorting(self, populated: Database) -> None:
        with populated.read() as conn:
            ascending = list_queries(conn, sort="time", direction="asc", limit=10)
            descending = list_queries(conn, sort="time", direction="desc", limit=10)
        assert [item["id"] for item in ascending.items] == list(
            reversed([item["id"] for item in descending.items])
        )

    def test_keyset_paging_with_before_id(self, populated: Database) -> None:
        with populated.read() as conn:
            page = list_queries(conn, limit=3)
            oldest = page.items[-1]["id"]
            older = list_queries(conn, limit=3, before_id=oldest)
        assert all(item["id"] < oldest for item in older.items)

    def test_after_id_returns_only_new_rows(self, populated: Database) -> None:
        with populated.read() as conn:
            everything = list_queries(conn, limit=10)
            newest = everything.newest_id
            delta = list_queries(conn, limit=10, after_id=newest)
        assert delta.items == []


class TestQueryShapeOptimisations:
    """Guards for the rewrites that made large databases usable.

    These assert on the generated SQL because the behaviour they protect only
    shows up as a timing difference, which a unit test cannot see.
    """

    def test_or_ed_domain_terms_share_one_subquery(self) -> None:
        compiled = compile_filter(
            quick_search_filter(
                ["googl", "youtube", "googlevideo"], mode="any", fields=("domain",)
            )
        )
        assert compiled.sql.count("SELECT d.id FROM domains d") == 1
        assert compiled.sql.count("LIKE ?") == 3
        assert compiled.params == ["%googl%", "%youtube%", "%googlevideo%"]

    def test_client_fields_merge_but_person_stays_separate(self) -> None:
        compiled = compile_filter(
            parse_filter(
                {
                    "op": "or",
                    "children": [
                        {"field": "client_ip", "operator": "contains", "value": "192.168"},
                        {"field": "client_name", "operator": "contains", "value": "tv"},
                        {"field": "person", "operator": "equals", "value": "Anna"},
                    ],
                }
            )
        )
        assert compiled.sql.count("SELECT c.id FROM clients c WHERE") == 1
        assert "JOIN persons p" in compiled.sql

    def test_negated_terms_are_not_merged(self) -> None:
        compiled = compile_filter(
            parse_filter(
                {
                    "op": "or",
                    "children": [
                        {"field": "domain", "operator": "contains", "value": "a"},
                        {"field": "domain", "operator": "not_contains", "value": "b"},
                    ],
                }
            )
        )
        assert "q.domain_id IN" in compiled.sql
        assert "q.domain_id NOT IN" in compiled.sql

    def test_merging_preserves_parameter_order(self, populated: Database) -> None:
        node = quick_search_filter(["index", "gstatic"], mode="any", fields=("domain",))
        assert _domains(populated, node) == {"index.hu", "gstatic.com"}

    def test_and_groups_are_not_merged(self) -> None:
        """``domain contains a AND domain contains b`` needs both to hold."""
        compiled = compile_filter(
            parse_filter(
                [
                    {"field": "domain", "operator": "contains", "value": "a"},
                    {"field": "domain", "operator": "contains", "value": "b"},
                ]
            )
        )
        assert compiled.sql.count("SELECT d.id FROM domains d") == 2

    def test_time_sorted_pages_skip_the_joins_while_sorting(self, populated: Database) -> None:
        from app.services.query_service import BASE_SELECT, QUERY_ONLY_SORTS

        assert "time" in QUERY_ONLY_SORTS
        assert "domain" not in QUERY_ONLY_SORTS  # sorting by domain needs the join
        assert BASE_SELECT  # the joined form is still used for lookup-column sorts

        with populated.read() as conn:
            by_time = list_queries(conn, sort="time", limit=10)
            by_domain = list_queries(conn, sort="domain", limit=10)
        assert len(by_time.items) == len(by_domain.items) == 6

    def test_capped_total(self, populated: Database) -> None:
        from app.services import query_service

        with populated.read() as conn:
            page = list_queries(conn, limit=2)
            assert page.total == 6
            assert page.total_capped is False

            original = query_service.COUNT_CAP
            query_service.COUNT_CAP = 3
            try:
                capped = list_queries(conn, limit=2)
            finally:
                query_service.COUNT_CAP = original
        assert capped.total == 3
        assert capped.total_capped is True
