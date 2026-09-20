"""AdGuard query log parsing, for both the API and the file format."""

from __future__ import annotations

import base64
import json

import pytest

from app.ingest.api_provider import parse_api_record
from app.ingest.dns_wire import parse_base64_message, parse_message
from app.ingest.file_provider import parse_file_record
from app.ingest.records import reason_name, result_kind
from tests.conftest import dns_response, querylog_line


class TestApiParser:
    def test_parses_a_full_record(self) -> None:
        record = parse_api_record(
            {
                "time": "2024-05-01T10:11:12.123456789Z",
                "question": {"class": "IN", "name": "Www.YouTube.COM.", "type": "a"},
                "client": "192.168.1.15",
                "client_info": {"name": "Peter iPhone"},
                "status": "NOERROR",
                "reason": "FilteredBlackList",
                "elapsedMs": "54.023928",
                "upstream": "https://dns.quad9.net",
                "cached": True,
                "client_proto": "doh",
                "rules": [{"filter_list_id": 7, "text": "||youtube.com^"}],
                "answer": [{"type": "A", "value": "1.2.3.4", "ttl": 300}],
            }
        )
        assert record is not None
        assert record.domain == "www.youtube.com"  # normalised
        assert record.qtype == "A"
        assert record.client_ip == "192.168.1.15"
        assert record.client_name == "Peter iPhone"
        assert record.blocked is True
        assert record.rule_text == "||youtube.com^"
        assert record.filter_list_id == 7
        assert record.elapsed_us == 54024
        assert record.cached is True
        assert record.client_proto == "doh"
        assert record.primary_answer == "1.2.3.4"

    def test_keeps_nanosecond_precision(self) -> None:
        record = parse_api_record(
            {
                "time": "2024-05-01T10:11:12.123456789Z",
                "question": {"name": "a.com", "type": "A"},
                "client": "10.0.0.1",
            }
        )
        assert record is not None
        assert record.ts_ns % 1000 == 789

    def test_falls_back_to_legacy_rule_fields(self) -> None:
        record = parse_api_record(
            {
                "time": "2024-05-01T10:00:00Z",
                "question": {"name": "a.com", "type": "A"},
                "client": "10.0.0.1",
                "rule": "||a.com^",
                "filterId": 3,
            }
        )
        assert record is not None
        assert record.rule_text == "||a.com^"
        assert record.filter_list_id == 3

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"question": {}, "client": "1.1.1.1", "time": "2024-01-01T00:00:00Z"},
            {"question": {"name": "a.com"}, "time": "2024-01-01T00:00:00Z"},
            {"question": {"name": "a.com"}, "client": "1.1.1.1", "time": "nonsense"},
        ],
    )
    def test_rejects_unusable_records(self, payload: dict) -> None:
        assert parse_api_record(payload) is None


class TestFileParser:
    def test_parses_a_json_line(self) -> None:
        record = parse_file_record(
            querylog_line(
                domain="Example.COM.",
                reason=3,
                rules=[{"FilterListID": 7, "Text": "||example.com^"}],
            )
        )
        assert record is not None
        assert record.domain == "example.com"
        assert record.client_ip == "192.168.1.5"
        assert record.reason == "FilteredBlackList"
        assert record.blocked is True
        assert record.rule_text == "||example.com^"
        assert record.filter_list_id == 7
        # Elapsed is a Go duration in nanoseconds.
        assert record.elapsed_us == 12345
        assert record.status == "NOERROR"
        assert record.primary_answer == "93.184.216.34"

    def test_decodes_nxdomain(self) -> None:
        record = parse_file_record(querylog_line(rcode=3))
        assert record is not None
        assert record.status == "NXDOMAIN"

    def test_legacy_rule_fields(self) -> None:
        payload = json.loads(querylog_line())
        payload["Result"] = {"Reason": 3, "FilterID": 9, "Rule": "||old.com^"}
        record = parse_file_record(json.dumps(payload))
        assert record is not None
        assert record.rule_text == "||old.com^"
        assert record.filter_list_id == 9

    @pytest.mark.parametrize("line", ["", "   ", "not json", "{broken", "[]", "null"])
    def test_ignores_garbage_lines(self, line: str) -> None:
        assert parse_file_record(line) is None

    def test_survives_a_truncated_answer(self) -> None:
        payload = json.loads(querylog_line())
        payload["Answer"] = base64.b64encode(b"\x00\x01\x02").decode()
        record = parse_file_record(json.dumps(payload))
        assert record is not None
        assert record.status == ""
        assert record.answers == []


class TestDnsWire:
    def test_decodes_answers(self) -> None:
        status, answers = parse_message(dns_response())
        assert status == "NOERROR"
        assert [(a.type, a.value, a.ttl) for a in answers] == [("A", "93.184.216.34", 60)]

    def test_base64_roundtrip(self) -> None:
        status, answers = parse_base64_message(base64.b64encode(dns_response()).decode())
        assert status == "NOERROR"
        assert len(answers) == 1

    @pytest.mark.parametrize("payload", ["", "!!!", "zzzz", None])
    def test_bad_payloads_do_not_raise(self, payload: str | None) -> None:
        assert parse_base64_message(payload) == ("", [])

    def test_rejects_a_compression_loop(self) -> None:
        # A name pointing at itself must not hang the parser.
        message = b"\x00\x01\x81\x80\x00\x01\x00\x00\x00\x00\x00\x00" + b"\xc0\x0c"
        assert parse_message(message) == ("", [])


class TestReasons:
    def test_numeric_and_string_reasons_agree(self) -> None:
        assert reason_name(3) == "FilteredBlackList"
        assert reason_name("FilteredBlackList") == "FilteredBlackList"
        assert reason_name(11) == "RewriteRule"
        assert reason_name(999) == ""

    @pytest.mark.parametrize(
        ("reason", "kind"),
        [
            ("FilteredBlackList", "blocked"),
            ("FilteredSafeBrowsing", "blocked"),
            ("FilteredBlockedService", "blocked"),
            ("FilteredSafeSearch", "rewritten"),
            ("RewriteRule", "rewritten"),
            ("NotFilteredWhiteList", "allowlisted"),
            ("NotFilteredError", "error"),
            ("NotFilteredNotFound", "allowed"),
            ("", "allowed"),
        ],
    )
    def test_result_kinds(self, reason: str, kind: str) -> None:
        assert result_kind(reason) == kind


class TestErrorSummaries:
    """AdGuard sits behind nginx, whose error pages are HTML.

    Those used to be pasted into the app log verbatim, several lines of
    markup for what is really a four-word message.
    """

    @staticmethod
    def _summary(status: int, text: str, content_type: str = "text/plain") -> str:
        import httpx

        from app.adguard.client import _short_body

        response = httpx.Response(status, text=text, headers={"content-type": content_type})
        return _short_body(response)

    def test_an_nginx_error_page_becomes_its_title(self) -> None:
        page = (
            "<html>\n<head><title>500 Internal Server Error</title></head>\n"
            "<body>\n<center><h1>500 Internal Server Error</h1></center>\n"
            "<hr><center>nginx</center>\n</body>\n</html>"
        )
        summary = self._summary(500, page, "text/html")
        assert summary == " (500 Internal Server Error)"
        assert "<" not in summary

    def test_html_without_a_title_is_stripped_of_markup(self) -> None:
        summary = self._summary(502, "<body><h1>Bad Gateway</h1></body>", "text/html")
        assert "<" not in summary
        assert "Bad Gateway" in summary

    def test_plain_text_is_kept(self) -> None:
        assert self._summary(403, "forbidden by policy") == ": forbidden by policy"

    def test_an_empty_body_adds_nothing(self) -> None:
        assert self._summary(500, "") == ""

    def test_long_bodies_are_truncated(self) -> None:
        assert len(self._summary(500, "x" * 5000)) < 200
