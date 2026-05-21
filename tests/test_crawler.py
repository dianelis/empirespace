import requests

import discover_jobs_pages
from crawl_jobs import (
    LOG_FIELDS,
    crawl_company,
    fetch_status,
    make_log_row,
    write_csv,
)


class DummyResponse:
    def __init__(self, status_code=200, text="", url="https://example.com/careers", content_type="text/html"):
        self.status_code = status_code
        self.text = text
        self.url = url
        self.headers = {"Content-Type": content_type}


def test_make_log_row_contains_expected_fields():
    row = {
        "company_id": "abc",
        "company_name": "Example Space",
        "company_website": "https://example.com",
    }
    log = make_log_row(row, "https://example.com/careers", "success", "200", 2, "")
    assert set(log) == set(LOG_FIELDS)
    assert log["company_name"] == "Example Space"
    assert log["status"] == "success"
    assert log["jobs_found"] == "2"


def test_crawl_company_no_jobs_found(monkeypatch):
    def fake_fetch(url, timeout=15):
        return discover_jobs_pages.FetchResult(
            url=url,
            final_url=url,
            status_code="200",
            content_type="text/html",
            html="<html><body><h1>Careers</h1></body></html>",
        )

    monkeypatch.setattr("crawl_jobs.fetch_url", fake_fetch)

    rows, logs = crawl_company(
        {"company_name": "Example", "company_website": "https://example.com", "careers_url": "https://example.com/careers"},
        timeout=1,
        sleep_seconds=0,
        max_pages=1,
    )
    assert rows[0]["status"] == "no_jobs_found"
    assert logs[0]["status"] == "no_jobs_found"


def test_empty_html_maps_to_parse_error(monkeypatch):
    def fake_fetch(url, timeout=15):
        return discover_jobs_pages.FetchResult(
            url=url,
            final_url=url,
            status_code="200",
            content_type="text/html",
            html="",
        )

    monkeypatch.setattr("crawl_jobs.fetch_url", fake_fetch)

    rows, logs = crawl_company(
        {"company_name": "Example", "company_website": "https://example.com", "careers_url": "https://example.com/careers"},
        timeout=1,
        sleep_seconds=0,
        max_pages=1,
    )
    assert rows[0]["status"] == "parse_error"
    assert logs[0]["status"] == "parse_error"
    assert logs[0]["error_message"] == "empty_html"


def test_fetch_status_timeout():
    assert fetch_status("timeout") == ("timeout", "timeout")


def test_request_timeout_handling_with_mocked_requests(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise requests.Timeout("too slow")

    monkeypatch.setattr(discover_jobs_pages.requests, "get", raise_timeout)
    result = discover_jobs_pages.fetch_url("https://example.com/careers", timeout=1)
    assert result.error == "timeout"


def test_http_error_handling_with_mocked_requests(monkeypatch):
    def return_404(*args, **kwargs):
        return DummyResponse(status_code=404, text="<html>missing</html>", url="https://example.com/missing")

    monkeypatch.setattr(discover_jobs_pages.requests, "get", return_404)
    result = discover_jobs_pages.fetch_url("https://example.com/missing", timeout=1)
    assert result.error == "http_404"
    assert fetch_status(result.error, result.html) == ("request_failed", "http_404")


def test_non_html_response_handling_with_mocked_requests(monkeypatch):
    def return_pdf(*args, **kwargs):
        return DummyResponse(status_code=200, text="%PDF", content_type="application/pdf")

    monkeypatch.setattr(discover_jobs_pages.requests, "get", return_pdf)
    result = discover_jobs_pages.fetch_url("https://example.com/file.pdf", timeout=1)
    assert result.error == "non_html_response"


def test_log_csv_headers(tmp_path):
    output = tmp_path / "crawl_log.csv"
    write_csv(output, [], LOG_FIELDS)
    assert output.read_text(encoding="utf-8").splitlines()[0] == ",".join(LOG_FIELDS)
