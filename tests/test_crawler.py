import requests
from argparse import Namespace

import discover_jobs_pages
from crawl_jobs import (
    DISCOVERED_FIELDS,
    FAILED_FIELDS,
    LOG_FIELDS,
    crawl_company,
    fetch_status,
    is_likely_js_rendered,
    make_log_row,
    run_crawl,
    write_csv,
)


class DummyResponse:
    def __init__(self, status_code=200, text="", url="https://example.com/careers", content_type="text/html"):
        self.status_code = status_code
        self.text = text
        self.url = url
        self.headers = {"Content-Type": content_type}
        self.history = []


def test_make_log_row_contains_expected_fields():
    row = {
        "company_id": "abc",
        "company_name": "Example Space",
        "company_website": "https://example.com",
    }
    log = make_log_row(
        row,
        "https://example.com/careers",
        "success",
        "200",
        2,
        "",
        attempt_type="known_careers_url",
    )
    assert set(log) == set(LOG_FIELDS)
    assert log["company_name"] == "Example Space"
    assert log["scraper_status"] == "success"
    assert log["attempt_type"] == "known_careers_url"
    assert log["status_code"] == "200"


def test_crawl_company_no_jobs_found(monkeypatch):
    def fake_fetch(url, timeout=15, session=None, retries=2, backoff=0.5):
        return discover_jobs_pages.FetchResult(
            url=url,
            final_url=url,
            status_code="200",
            content_type="text/html",
            html="<html><body><h1>Careers</h1></body></html>",
        )

    monkeypatch.setattr("crawl_jobs.fetch_url", fake_fetch)

    rows, logs, _ = crawl_company(
        {"company_name": "Example", "company_website": "https://example.com", "careers_url": "https://example.com/careers"},
        timeout=1,
        sleep_seconds=0,
        max_pages=1,
        retries=0,
    )
    assert rows[0]["status"] == "no_jobs_found"
    assert logs[0]["scraper_status"] == "no_jobs_found"


def test_empty_html_maps_to_parse_error(monkeypatch):
    def fake_fetch(url, timeout=15, session=None, retries=2, backoff=0.5):
        return discover_jobs_pages.FetchResult(
            url=url,
            final_url=url,
            status_code="200",
            content_type="text/html",
            html="",
        )

    monkeypatch.setattr("crawl_jobs.fetch_url", fake_fetch)

    rows, logs, _ = crawl_company(
        {"company_name": "Example", "company_website": "https://example.com", "careers_url": "https://example.com/careers"},
        timeout=1,
        sleep_seconds=0,
        max_pages=1,
        retries=0,
    )
    assert rows[0]["status"] == "parse_error"
    assert logs[0]["scraper_status"] == "parse_error"
    assert logs[0]["error_message"] == "empty_html"


def test_fetch_status_timeout():
    assert fetch_status("timeout") == ("timeout", "timeout")


def test_request_timeout_handling_with_mocked_requests(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise requests.Timeout("too slow")

    monkeypatch.setattr(discover_jobs_pages.requests.Session, "get", raise_timeout)
    result = discover_jobs_pages.fetch_url("https://example.com/careers", timeout=1)
    assert result.error == "timeout"


def test_http_error_handling_with_mocked_requests(monkeypatch):
    def return_404(*args, **kwargs):
        return DummyResponse(status_code=404, text="<html>missing</html>", url="https://example.com/missing")

    monkeypatch.setattr(discover_jobs_pages.requests.Session, "get", return_404)
    result = discover_jobs_pages.fetch_url("https://example.com/missing", timeout=1)
    assert result.error == "http_404"
    assert fetch_status(result.error, result.html) == ("request_failed", "http_404")


def test_non_html_response_handling_with_mocked_requests(monkeypatch):
    def return_pdf(*args, **kwargs):
        return DummyResponse(status_code=200, text="%PDF", content_type="application/pdf")

    monkeypatch.setattr(discover_jobs_pages.requests.Session, "get", return_pdf)
    result = discover_jobs_pages.fetch_url("https://example.com/file.pdf", timeout=1)
    assert result.error == "non_html_response"


def test_blocked_http_status_maps_to_blocked(monkeypatch):
    def return_429(*args, **kwargs):
        return DummyResponse(status_code=429, text="<html>rate limit</html>")

    monkeypatch.setattr(discover_jobs_pages.requests.Session, "get", return_429)
    result = discover_jobs_pages.fetch_url("https://example.com/careers", timeout=1, retries=0)
    assert result.error == "blocked"
    assert fetch_status(result.error, result.html) == ("blocked", "blocked_or_rate_limited")


def test_redirect_handling_with_mocked_requests(monkeypatch):
    def return_redirect(*args, **kwargs):
        response = DummyResponse(url="https://jobs.example.com/openings")
        response.history = [DummyResponse(status_code=301, url="https://example.com/careers")]
        return response

    monkeypatch.setattr(discover_jobs_pages.requests.Session, "get", return_redirect)
    result = discover_jobs_pages.fetch_url("https://example.com/careers", timeout=1, retries=0)
    assert result.redirected is True


def test_redirect_loop_maps_to_redirect_detected(monkeypatch):
    def raise_redirect_loop(*args, **kwargs):
        raise requests.TooManyRedirects("loop")

    monkeypatch.setattr(discover_jobs_pages.requests.Session, "get", raise_redirect_loop)
    result = discover_jobs_pages.fetch_url("https://example.com/careers", timeout=1, retries=0)
    assert result.error == "redirect_detected"


def test_js_heavy_detection():
    html = """
    <div id="root"></div>
    <noscript>Please enable JavaScript to view jobs.</noscript>
    <script src="/runtime.js"></script><script src="/app.js"></script>
    """
    assert is_likely_js_rendered(html, "https://jobs.workdayjobs.com/search") is True


def test_crawl_company_js_heavy_status(monkeypatch):
    def fake_fetch(url, timeout=15, session=None, retries=2, backoff=0.5):
        return discover_jobs_pages.FetchResult(
            url=url,
            final_url=url,
            status_code="200",
            content_type="text/html",
            html='<div id="root"></div><noscript>Please enable JavaScript</noscript><script></script><script></script>',
        )

    monkeypatch.setattr("crawl_jobs.fetch_url", fake_fetch)
    rows, logs, _ = crawl_company(
        {"company_name": "Example", "company_website": "https://example.com", "careers_url": "https://jobs.workdayjobs.com/example"},
        timeout=1,
        sleep_seconds=0,
        max_pages=1,
        retries=0,
    )
    assert rows[0]["status"] == "js_rendered_or_unsupported"
    assert logs[0]["scraper_status"] == "js_rendered_or_unsupported"


def test_known_careers_url_falls_back_to_common_path(monkeypatch):
    def fake_fetch(url, timeout=15, session=None, retries=2, backoff=0.5):
        if url.endswith("/bad-careers"):
            return discover_jobs_pages.FetchResult(
                url=url,
                final_url=url,
                status_code="404",
                content_type="text/html",
                html="<html>missing</html>",
                error="http_404",
            )
        if url.rstrip("/").endswith("/careers"):
            return discover_jobs_pages.FetchResult(
                url=url,
                final_url=url,
                status_code="200",
                content_type="text/html",
                html='<a href="/jobs/test-engineer">Test Engineer</a><span>Location: Remote</span>',
            )
        return discover_jobs_pages.FetchResult(
            url=url,
            final_url=url,
            status_code="200",
            content_type="text/html",
            html='<a href="/careers">Careers</a>',
        )

    monkeypatch.setattr("crawl_jobs.fetch_url", fake_fetch)
    rows, logs, discovered = crawl_company(
        {
            "company_name": "Example",
            "company_website": "https://example.com",
            "careers_url": "https://example.com/bad-careers",
        },
        timeout=1,
        sleep_seconds=0,
        max_pages=4,
        retries=0,
    )

    assert rows[0]["status"] == "success_after_fallback"
    assert rows[0]["discovery_method"] == "common_path"
    assert any(log["scraper_status"] == "careers_url_failed" for log in logs)
    assert any(row["discovered_url"] == "https://example.com/careers" for row in discovered)


def test_homepage_scan_detects_external_ats(monkeypatch):
    def fake_fetch(url, timeout=15, session=None, retries=2, backoff=0.5):
        if "greenhouse.io" in url:
            return discover_jobs_pages.FetchResult(
                url=url,
                final_url=url,
                status_code="200",
                content_type="text/html",
                html='<a href="https://boards.greenhouse.io/example/jobs/123">Flight Software Engineer</a>',
            )
        return discover_jobs_pages.FetchResult(
            url=url,
            final_url=url,
            status_code="200",
            content_type="text/html",
            html='<a href="https://boards.greenhouse.io/example">Open positions</a>',
        )

    monkeypatch.setattr("crawl_jobs.fetch_url", fake_fetch)
    rows, logs, discovered = crawl_company(
        {"company_name": "Example", "company_website": "https://example.com"},
        timeout=1,
        sleep_seconds=0,
        max_pages=2,
        retries=0,
    )

    assert rows[0]["status"] == "success_after_fallback"
    assert rows[0]["discovery_method"] == "ats_detected"
    assert any(log["scraper_status"] == "ats_detected" for log in logs)
    assert any(row["discovery_method"] == "ats_detected" for row in discovered)


def test_run_crawl_creates_all_csv_outputs(tmp_path, monkeypatch):
    input_csv = tmp_path / "companies.csv"
    input_csv.write_text(
        "company_name,company_website,careers_url\n"
        "Example,https://example.com,https://example.com/careers\n",
        encoding="utf-8",
    )

    def fake_fetch(url, timeout=15, session=None, retries=2, backoff=0.5):
        return discover_jobs_pages.FetchResult(
            url=url,
            final_url=url,
            status_code="200",
            content_type="text/html",
            html='<a href="/jobs/test-engineer">Test Engineer</a><span>Location: Remote</span>',
        )

    monkeypatch.setattr("crawl_jobs.fetch_url", fake_fetch)
    args = Namespace(
        input=str(input_csv),
        output=str(tmp_path / "jobs_out.csv"),
        log=str(tmp_path / "crawl_log.csv"),
        discovered_pages=str(tmp_path / "discovered_pages.csv"),
        failed_companies=str(tmp_path / "failed_companies.csv"),
        timeout=1,
        retries=0,
        backoff=0,
        sleep=0,
        max_pages_per_company=1,
        limit=0,
    )
    run_crawl(args)

    assert (tmp_path / "jobs_out.csv").exists()
    assert (tmp_path / "crawl_log.csv").exists()
    assert (tmp_path / "discovered_pages.csv").exists()
    assert (tmp_path / "failed_companies.csv").exists()
    assert (tmp_path / "discovered_pages.csv").read_text(encoding="utf-8").splitlines()[0] == ",".join(DISCOVERED_FIELDS)
    assert (tmp_path / "failed_companies.csv").read_text(encoding="utf-8").splitlines()[0] == ",".join(FAILED_FIELDS)


def test_log_csv_headers(tmp_path):
    output = tmp_path / "crawl_log.csv"
    write_csv(output, [], LOG_FIELDS)
    assert output.read_text(encoding="utf-8").splitlines()[0] == ",".join(LOG_FIELDS)
