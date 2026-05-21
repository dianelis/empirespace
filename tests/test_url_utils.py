from discover_jobs_pages import normalize_url, pick_existing_careers_urls
from crawl_jobs import canonicalize_url


def test_normalize_url_adds_scheme_and_trims_slash():
    assert normalize_url("Example.com/careers/") == "https://example.com/careers"


def test_normalize_url_rejects_missing_or_invalid_values():
    assert normalize_url("") == ""
    assert normalize_url("not a url") == ""


def test_protocol_relative_url_normalizes_to_https():
    assert normalize_url("//jobs.example.com/openings/") == "https://jobs.example.com/openings"


def test_canonicalize_url_drops_tracking_but_keeps_job_ids():
    url = "https://example.com/jobs/view?utm_source=x&gh_jid=123&ref=abc"
    assert canonicalize_url(url) == "https://example.com/jobs/view?gh_jid=123"


def test_multiple_career_urls_are_collected():
    row = {"careers_url": "https://example.com/jobs; https://boards.example.com/company"}
    assert pick_existing_careers_urls(row) == [
        "https://example.com/jobs",
        "https://boards.example.com/company",
    ]
