"""HTTP API tests against a real, temporary database."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import reset_settings
from app.services.classification import TagResolver
from app.services.ingest_store import store_records
from app.services.rules_service import build_engine
from tests.conftest import make_record


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("INGEST_ENABLED", "false")
    monkeypatch.setenv("PROVIDER", "file")
    monkeypatch.setenv("QUERYLOG_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setenv("LOG_LEVEL", "error")
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    reset_settings()

    from app.main import create_app

    application = create_app()
    with TestClient(application) as test_client:
        state = application.state.app_state
        base = 1_700_000_000_000_000_000
        records = [
            make_record(ts_ns=base + 1, domain="www.youtube.com", client_ip="192.168.1.15",
                        client_name="iPhone"),
            make_record(ts_ns=base + 2, domain="r3.googlevideo.com", client_ip="192.168.1.15",
                        client_name="iPhone"),
            make_record(ts_ns=base + 3, domain="www.google.com", client_ip="192.168.1.16",
                        client_name="MacBook"),
            make_record(ts_ns=base + 4, domain="doubleclick.net", client_ip="192.168.1.20",
                        client_name="TV", reason="FilteredBlackList"),
            make_record(ts_ns=base + 5, domain="index.hu", client_ip="192.168.1.20",
                        client_name="TV"),
        ]
        with state.db.write() as conn:
            engine = build_engine(conn)
            store_records(conn, records, engine=engine, revision=1, resolver=TagResolver())
        yield test_client
    reset_settings()
    os.environ.pop("DATA_DIR", None)


def _search(client: TestClient, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/queries/search", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


class TestSystem:
    def test_health(self, client: TestClient) -> None:
        assert client.get("/api/health").json()["status"] == "ok"

    def test_status_reports_the_data_it_holds(self, client: TestClient) -> None:
        payload = client.get("/api/status").json()
        assert payload["database"]["queries"] == 5
        assert payload["database"]["domains"] == 5
        assert payload["database"]["clients"] == 3
        assert payload["provider"]["available"] is False  # the file does not exist

    def test_meta_describes_the_filter_fields(self, client: TestClient) -> None:
        payload = client.get("/api/meta").json()
        names = {field["name"] for field in payload["fields"]}
        assert {"domain", "person", "tag", "category", "timestamp", "blocked"} <= names

    def test_the_spa_is_served_for_unknown_paths(self, client: TestClient) -> None:
        response = client.get("/devices")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_unknown_api_paths_are_404(self, client: TestClient) -> None:
        assert client.get("/api/nope").status_code == 404


class TestQueries:
    def test_listing(self, client: TestClient) -> None:
        payload = _search(client, {"limit": 10})
        assert payload["total"] == 5
        assert payload["items"][0]["domain"]
        assert "tags" in payload["items"][0]

    def test_the_any_search_from_the_brief(self, client: TestClient) -> None:
        payload = _search(
            client,
            {
                "search": {
                    "terms": ["googl", "youtube", "googlevideo"],
                    "mode": "any",
                    "fields": ["domain"],
                },
                "limit": 50,
            },
        )
        assert {item["domain"] for item in payload["items"]} == {
            "www.youtube.com",
            "r3.googlevideo.com",
            "www.google.com",
        }

    def test_a_nested_filter(self, client: TestClient) -> None:
        payload = _search(
            client,
            {
                "filter": {
                    "op": "and",
                    "children": [
                        {
                            "op": "or",
                            "children": [
                                {"field": "domain", "operator": "contains", "value": "youtube"},
                                {"field": "domain", "operator": "contains",
                                 "value": "googlevideo"},
                            ],
                        },
                        {"field": "client_ip", "operator": "equals", "value": "192.168.1.15"},
                    ],
                },
                "limit": 50,
            },
        )
        assert len(payload["items"]) == 2

    def test_tags_are_attached(self, client: TestClient) -> None:
        payload = _search(
            client,
            {"filter": {"field": "domain", "operator": "equals", "value": "www.youtube.com"}},
        )
        item = payload["items"][0]
        assert {tag["name"] for tag in item["tags"]} >= {"YouTube", "Google"}
        assert {cat["name"] for cat in item["categories"]} >= {"Video"}

    def test_an_invalid_filter_is_a_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/queries/search",
            json={"filter": {"field": "not_a_field", "operator": "equals", "value": "x"}},
        )
        assert response.status_code == 400
        assert "not_a_field" in response.json()["detail"]

    def test_get_form(self, client: TestClient) -> None:
        payload = client.get("/api/queries?search=youtube,googlevideo&mode=any").json()
        assert len(payload["items"]) == 2

    def test_single_query(self, client: TestClient) -> None:
        listing = _search(client, {"limit": 1})
        query_id = listing["items"][0]["id"]
        assert client.get(f"/api/queries/{query_id}").json()["id"] == query_id
        assert client.get("/api/queries/999999").status_code == 404


class TestDashboard:
    def test_overview(self, client: TestClient) -> None:
        payload = client.get("/api/dashboard?range=all").json()
        assert payload["summary"]["total"] == 5
        assert payload["summary"]["blocked"] == 1
        assert payload["summary"]["allowed"] == 4
        assert payload["summary"]["unique_domains"] == 5
        assert payload["summary"]["active_clients"] == 3
        assert payload["top_domains"]
        assert payload["top_categories"]
        assert payload["timeline"]["points"]

    def test_filtered_overview(self, client: TestClient) -> None:
        payload = client.post(
            "/api/dashboard",
            json={
                "filter": {"field": "client_ip", "operator": "equals", "value": "192.168.1.20"},
                "range": "all",
            },
        ).json()
        assert payload["summary"]["total"] == 2
        assert payload["summary"]["blocked"] == 1


class TestDevicesAndPersons:
    def test_device_lifecycle(self, client: TestClient) -> None:
        devices = client.get("/api/devices").json()["items"]
        device = next(item for item in devices if item["ip"] == "192.168.1.15")

        created = client.post("/api/persons", json={"name": "Péter", "color": "#ff0000"})
        assert created.status_code == 201
        person_id = created.json()["id"]

        patched = client.patch(
            f"/api/devices/{device['id']}",
            json={"alias": "Péter telefonja", "person_id": person_id},
        )
        assert patched.status_code == 200
        assert patched.json()["device"]["name"] == "Péter telefonja"

        payload = _search(
            client, {"filter": {"field": "person", "operator": "equals", "value": "Péter"}}
        )
        assert len(payload["items"]) == 2

        detail = client.get(f"/api/devices/{device['id']}/detail?range=all").json()
        assert detail["summary"]["total"] == 2
        assert detail["top_domains"]

    def test_duplicate_person_names_are_rejected(self, client: TestClient) -> None:
        assert client.post("/api/persons", json={"name": "Anna"}).status_code == 201
        assert client.post("/api/persons", json={"name": "Anna"}).status_code == 409

    def test_bulk_assignment(self, client: TestClient) -> None:
        person_id = client.post("/api/persons", json={"name": "Család"}).json()["id"]
        ids = [device["id"] for device in client.get("/api/devices").json()["items"]]
        response = client.post(
            "/api/devices/assign", json={"person_id": person_id, "client_ids": ids}
        )
        assert response.json()["changed"] == len(ids)

    def test_person_detail(self, client: TestClient) -> None:
        person_id = client.post("/api/persons", json={"name": "Anna"}).json()["id"]
        device = client.get("/api/devices").json()["items"][0]
        client.patch(f"/api/devices/{device['id']}", json={"person_id": person_id})
        detail = client.get(f"/api/persons/{person_id}/detail?range=all").json()
        assert detail["person"]["name"] == "Anna"
        assert detail["person"]["devices"]


class TestTagsAndRules:
    def test_builtin_tags_exist(self, client: TestClient) -> None:
        categories = client.get("/api/tags?kind=category").json()["items"]
        assert any(item["name"] == "Advertising" for item in categories)

    def test_custom_tag_lifecycle(self, client: TestClient) -> None:
        created = client.post("/api/tags", json={"name": "Munka", "kind": "tag", "color": "#123"})
        assert created.status_code == 201
        tag_id = created.json()["id"]
        assert client.post("/api/tags", json={"name": "Munka", "kind": "tag"}).status_code == 409
        assert client.patch(f"/api/tags/{tag_id}", json={"color": "#456"}).status_code == 200
        assert client.delete(f"/api/tags/{tag_id}").status_code == 200

    def test_builtin_tags_cannot_be_deleted(self, client: TestClient) -> None:
        tag = next(
            item for item in client.get("/api/tags").json()["items"] if item["builtin"]
        )
        response = client.delete(f"/api/tags/{tag['id']}")
        assert response.status_code == 400

    def test_rule_lifecycle_and_reclassification(self, client: TestClient) -> None:
        response = client.post(
            "/api/rules",
            json={
                "name": "Hirek",
                "priority": 50,
                "conditions": [{"field": "domain", "operator": "suffix", "value": "index.hu"}],
                "tags": [{"name": "Magyar hírek", "kind": "category"}],
            },
        )
        assert response.status_code == 201
        rule_id = response.json()["id"]

        listing = client.get("/api/rules").json()
        assert listing["total"] == 1
        assert listing["pending_reclassification"] > 0

        assert client.post("/api/maintenance/reclassify").status_code == 200
        assert client.delete(f"/api/rules/{rule_id}").status_code == 200

    def test_rule_tester(self, client: TestClient) -> None:
        response = client.post(
            "/api/rules/test",
            json={
                "domain": "m.youtube.com",
                "rule": {
                    "name": "draft",
                    "conditions": [{"field": "domain", "operator": "contains",
                                    "value": "youtube"}],
                    "tags": [{"name": "YouTube", "kind": "tag"}],
                },
            },
        )
        assert response.json()["matched"] is True

        against_live = client.post("/api/rules/test", json={"domain": "doubleclick.net"}).json()
        assert any(match["rule"] == "Google Ads" for match in against_live["matches"])

    def test_manual_domain_tags(self, client: TestClient) -> None:
        tag_id = client.post("/api/tags", json={"name": "Kézi", "kind": "tag"}).json()["id"]
        domain = client.get("/api/domains").json()["items"][0]
        response = client.put(f"/api/domains/{domain['id']}/tags", json={"tag_ids": [tag_id]})
        assert response.status_code == 200
        detail = client.get(f"/api/domains/{domain['id']}?range=all").json()
        assert any(
            tag["name"] == "Kézi" and tag["source"] == "manual" for tag in detail["domain"]["tags"]
        )


class TestSavedFilters:
    def test_lifecycle(self, client: TestClient) -> None:
        created = client.post(
            "/api/saved-filters",
            json={
                "name": "YouTube activity",
                "filter": {
                    "op": "or",
                    "children": [
                        {"field": "domain", "operator": "contains", "value": "youtube"},
                        {"field": "domain", "operator": "contains", "value": "googlevideo"},
                        {"field": "domain", "operator": "contains", "value": "ytimg"},
                    ],
                },
            },
        )
        assert created.status_code == 201
        filter_id = created.json()["id"]

        payload = _search(client, {"saved_filter_id": filter_id, "limit": 50})
        assert {item["domain"] for item in payload["items"]} == {
            "www.youtube.com",
            "r3.googlevideo.com",
        }

        assert client.put(
            f"/api/saved-filters/{filter_id}", json={"name": "YouTube"}
        ).status_code == 200
        assert client.delete(f"/api/saved-filters/{filter_id}").status_code == 200
        assert client.delete(f"/api/saved-filters/{filter_id}").status_code == 404

    def test_an_invalid_saved_filter_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/saved-filters",
            json={"name": "bad", "filter": {"field": "nope", "operator": "equals", "value": "x"}},
        )
        assert response.status_code == 400

    @pytest.mark.parametrize("payload", [None, {}, [], {"op": "and", "children": []}])
    def test_an_empty_saved_filter_is_rejected(self, client: TestClient, payload: object) -> None:
        """An empty filter matches everything.

        Storing one used to be allowed, and the UI then showed a condition
        count for a filter that narrowed nothing — which looked exactly like a
        saved filter that had stopped working.
        """
        response = client.post("/api/saved-filters", json={"name": "empty", "filter": payload})
        assert response.status_code == 400
        assert "at least one condition" in response.json()["detail"]

    def test_an_empty_filter_cannot_be_set_by_update_either(self, client: TestClient) -> None:
        created = client.post(
            "/api/saved-filters",
            json={
                "name": "real",
                "filter": {"field": "domain", "operator": "contains", "value": "youtube"},
            },
        )
        assert created.status_code == 201
        filter_id = created.json()["id"]

        emptied = client.put(f"/api/saved-filters/{filter_id}", json={"filter": {}})
        assert emptied.status_code == 400

        # A rename must still work without touching the filter.
        renamed = client.put(f"/api/saved-filters/{filter_id}", json={"name": "renamed"})
        assert renamed.status_code == 200
        stored = client.get("/api/saved-filters").json()["items"]
        assert stored[0]["filter"] == {
            "field": "domain",
            "operator": "contains",
            "value": "youtube",
        }

    def test_a_term_based_filter_round_trips(self, client: TestClient) -> None:
        """What the Save button now stores for a multi-term search."""
        term_filter = {
            "op": "or",
            "children": [
                {"field": "domain", "operator": "contains", "value": "youtube"},
                {"field": "domain", "operator": "contains", "value": "googlevideo"},
            ],
        }
        created = client.post(
            "/api/saved-filters", json={"name": "YouTube activity", "filter": term_filter}
        )
        assert created.status_code == 201

        direct = _search(
            client,
            {
                "search": {
                    "terms": ["youtube", "googlevideo"],
                    "mode": "any",
                    "fields": ["domain"],
                },
                "range": "all",
                "limit": 50,
            },
        )
        via_saved = _search(
            client, {"saved_filter_id": created.json()["id"], "range": "all", "limit": 50}
        )
        assert {item["domain"] for item in via_saved["items"]} == {
            item["domain"] for item in direct["items"]
        }
        assert via_saved["total"] == direct["total"] > 0


class TestSettings:
    def test_read_and_update(self, client: TestClient) -> None:
        payload = client.get("/api/settings").json()
        assert payload["app"]["ui.theme"] == "system"
        assert payload["addon_options"]["adguard_password_set"] is False

        updated = client.patch(
            "/api/settings", json={"values": {"ui.theme": "dark", "retention_days": 7}}
        )
        assert updated.status_code == 200
        assert updated.json()["app"]["ui.theme"] == "dark"
        assert updated.json()["effective"]["retention_days"] == 7

    def test_rejects_unknown_and_invalid_values(self, client: TestClient) -> None:
        assert client.patch(
            "/api/settings", json={"values": {"nope": 1}}
        ).status_code == 400
        assert client.patch(
            "/api/settings", json={"values": {"ui.theme": "neon"}}
        ).status_code == 400

    def test_the_password_is_never_returned(self, client: TestClient) -> None:
        body = client.get("/api/settings").text
        assert "adguard_password" not in body or "adguard_password_set" in body
        assert '"adguard_password":' not in body


class TestDomains:
    def test_listing_and_detail(self, client: TestClient) -> None:
        listing = client.get("/api/domains?search=youtube").json()
        assert listing["total"] == 1
        domain_id = listing["items"][0]["id"]
        detail = client.get(f"/api/domains/{domain_id}?range=all").json()
        assert detail["summary"]["total"] == 1
        assert detail["top_clients"]

    def test_lookup_by_name(self, client: TestClient) -> None:
        detail = client.get("/api/domains/lookup?name=index.hu&range=all").json()
        assert detail["domain"]["name"] == "index.hu"
        assert client.get("/api/domains/lookup?name=nope.example").status_code == 404


class TestDashboardParts:
    def test_only_the_requested_parts_come_back(self, client: TestClient) -> None:
        payload = client.post(
            "/api/dashboard", json={"range": "all", "parts": ["summary", "top_domains"]}
        ).json()
        assert set(payload) == {"summary", "top_domains"}

    def test_an_unknown_part_is_a_400(self, client: TestClient) -> None:
        response = client.post("/api/dashboard", json={"parts": ["nope"]})
        assert response.status_code == 400

    def test_parallel_parts_match_the_sequential_result(self, client: TestClient) -> None:
        from app.services import dashboard_service

        parallel = client.post("/api/dashboard", json={"range": "all"}).json()
        state = client.app.state.app_state  # type: ignore[attr-defined]
        with state.db.read() as conn:
            sequential = dashboard_service.overview(conn)
        assert parallel["summary"] == sequential["summary"]
        assert parallel["top_domains"] == sequential["top_domains"]


class TestRequestShapes:
    """The request bodies the frontend actually sends must be accepted.

    The schemas use ``extra='forbid'``, so a field the UI adds and the schema
    does not know about is a 422 rather than a silently ignored key. These
    tests pin the shapes the frontend builds.
    """

    def test_query_search_shape(self, client: TestClient) -> None:
        response = client.post(
            "/api/queries/search",
            json={
                "filter": None,
                "search": {
                    "terms": ["googl"],
                    "mode": "any",
                    "fields": ["domain"],
                    "operator": "contains",
                },
                "range": "24h",
                "sort": "time",
                "direction": "desc",
                "limit": 150,
                "include_total": True,
            },
        )
        assert response.status_code == 200, response.text

    def test_dashboard_shape_has_no_sorting(self, client: TestClient) -> None:
        """The dashboard body carries the filter only — no paging or sorting."""
        response = client.post(
            "/api/dashboard",
            json={"filter": None, "search": None, "range": "24h", "top_limit": 10, "buckets": 72},
        )
        assert response.status_code == 200, response.text

        rejected = client.post(
            "/api/dashboard", json={"range": "24h", "sort": "time", "direction": "desc"}
        )
        assert rejected.status_code == 422

    def test_paging_shapes(self, client: TestClient) -> None:
        for extra in ({"before_id": 3}, {"after_id": 1}, {"offset": 2}):
            response = client.post(
                "/api/queries/search",
                json={"range": "all", "limit": 10, "include_total": False, **extra},
            )
            assert response.status_code == 200, response.text


class TestProviderStatusCache:
    def test_status_is_probed_once_per_window(self, client: TestClient) -> None:
        state = client.app.state.app_state  # type: ignore[attr-defined]
        calls = {"count": 0}
        original = state.provider.status

        async def counting_status():  # type: ignore[no-untyped-def]
            calls["count"] += 1
            return await original()

        state.provider.status = counting_status  # type: ignore[method-assign]
        state._provider_status = None

        client.get("/api/status")
        client.get("/api/status")
        client.get("/api/status")
        assert calls["count"] == 1
