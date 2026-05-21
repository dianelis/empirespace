from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from discover_jobs_pages import (
    DEFAULT_TIMEOUT,
    clean_text,
    create_session,
    discover_careers_page,
    fetch_url,
    find_careers_links,
    is_http_url,
    is_linkedin_url,
    normalize_url,
    pick_company_name,
    pick_company_website,
    pick_existing_careers_url,
    pick_existing_careers_urls,
)


OUTPUT_FIELDS = [
    "company_id",
    "company_name",
    "company_website",
    "careers_url",
    "job_title",
    "job_url",
    "location",
    "department",
    "category",
    "date_found",
    "source_url",
    "status",
]

LOG_FIELDS = [
    "checked_at",
    "company_id",
    "company_name",
    "company_website",
    "url_checked",
    "status",
    "http_status",
    "jobs_found",
    "error_message",
]

DISCOVERED_FIELDS = [
    "checked_at",
    "company_id",
    "company_name",
    "company_website",
    "careers_url",
    "source_url",
    "status",
    "http_status",
    "notes",
]

FAILED_FIELDS = [
    "checked_at",
    "company_id",
    "company_name",
    "company_website",
    "careers_url",
    "status",
    "error_message",
]

FAILURE_STATUSES = {
    "careers_page_not_found",
    "invalid_url",
    "timeout",
    "request_failed",
    "parse_error",
    "non_html_response",
    "js_rendered_or_unsupported",
    "blocked",
    "unsupported_structure",
}

JOB_TITLE_WORD_RE = re.compile(
    r"\b("
    r"engineer|engineering|developer|designer|manager|director|analyst|scientist|"
    r"technician|operator|specialist|associate|coordinator|administrator|architect|"
    r"assistant|consultant|lead|leader|intern|internship|recruiter"
    r")s?\b",
    re.I,
)

GENERIC_TITLES = {
    "apply",
    "apply now",
    "career",
    "careers",
    "job",
    "jobs",
    "job search",
    "job details",
    "open jobs",
    "open roles",
    "open positions",
    "positions",
    "view job",
    "view jobs",
    "view all jobs",
    "learn more",
    "read more",
    "join us",
    "join our team",
}

JOB_URL_HINTS = (
    "/job/",
    "/jobs/",
    "/careers/",
    "/career/",
    "/positions/",
    "/openings/",
    "/apply/",
    "/vacancy/",
    "gh_jid=",
    "lever.co/",
    "greenhouse.io/",
    "ashbyhq.com/",
    "workable.com/",
    "bamboohr.com/careers",
    "recruitee.com/",
    "applytojob.com/apply",
    "smartrecruiters.com/",
    "icims.com/jobs",
    "jobvite.com/",
    "taleo.net/",
    "dayforcehcm.com/",
    "myworkdayjobs.com/",
    "workdayjobs.com/",
    "tal.net/",
)

JS_HEAVY_HOST_HINTS = (
    "workdayjobs.com",
    "myworkdayjobs.com",
    "dayforcehcm.com",
    "workforcenow.adp.com",
    "smartrecruiters.com",
    "icims.com",
    "taleo.net",
    "greenhouse.io",
    "ashbyhq.com",
)

JS_TEXT_HINTS = (
    "enable javascript",
    "requires javascript",
    "javascript is required",
    "please enable js",
    "noscript",
)

BLOCKED_TEXT_HINTS = (
    "access denied",
    "forbidden",
    "too many requests",
    "rate limit",
    "captcha",
    "cloudflare",
    "temporarily blocked",
)

NO_OPENINGS_HINTS = (
    "no open positions",
    "no current openings",
    "no jobs found",
    "no vacancies",
    "not hiring",
)

UNSUPPORTED_CAREER_HOST_HINTS = (
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "glassdoor.com",
)

BAD_JOB_URL_RE = re.compile(
    r"(privacy|terms|cookie|login|signin|sign-in|register|account|talent-community|newsletter"
    r"|facebook\.com|instagram\.com|youtube\.com|twitter\.com|x\.com)",
    re.I,
)

DROP_QUERY_PREFIXES = ("utm_",)
DROP_QUERY_KEYS = {"fbclid", "gclid", "msclkid", "_gl", "ref", "source", "campaign"}
KEEP_QUERY_KEYS = {
    "id",
    "jobid",
    "jobId",
    "gh_jid",
    "jid",
    "req",
    "reqid",
    "rid",
    "vacancy",
    "posting",
    "position",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:12]


def is_blank(value: str) -> bool:
    return clean_text(value).lower() in {"", "null", "nullz", "none", "nan", "n/a"}


def canonicalize_url(url: str) -> str:
    normalized = normalize_url(url)
    if not normalized:
        return ""

    try:
        parsed = urlparse(normalized)
        kept: List[Tuple[str, str]] = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key.startswith(DROP_QUERY_PREFIXES) or key in DROP_QUERY_KEYS:
                continue
            if key in KEEP_QUERY_KEYS or key.lower().endswith("id"):
                kept.append((key, value))

        query = urlencode(sorted(kept), doseq=True)
        path = parsed.path.rstrip("/") or "/"
        return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", query, ""))
    except ValueError:
        return normalized


def company_dedupe_key(row: Dict[str, str]) -> str:
    company_name = pick_company_name(row)
    website = pick_company_website(row)
    company_id = clean_text(row.get("company_id", ""))
    return company_id or canonicalize_url(website) or company_name.lower() or stable_id(str(row))


def read_company_rows_with_duplicates(
    path: Path,
    limit: int = 0,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    deduped: Dict[str, Dict[str, str]] = {}
    duplicates: List[Dict[str, str]] = []
    for row in rows:
        key = company_dedupe_key(row)
        existing = deduped.get(key)
        if not existing:
            deduped[key] = row
            continue

        if not pick_existing_careers_url(existing) and pick_existing_careers_url(row):
            duplicates.append(existing)
            deduped[key] = row
        else:
            duplicates.append(row)

    out = list(deduped.values())
    if limit:
        limited = out[:limit]
        limited_keys = {company_dedupe_key(row) for row in limited}
        return limited, [row for row in duplicates if company_dedupe_key(row) in limited_keys]
    return out, duplicates


def read_company_rows(path: Path, limit: int = 0) -> List[Dict[str, str]]:
    rows, _ = read_company_rows_with_duplicates(path, limit=limit)
    return rows


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def object_values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from object_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from object_values(child)


def format_jsonld_location(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        parts = [format_jsonld_location(item) for item in value]
        return "; ".join(part for part in parts if part)
    if not isinstance(value, dict):
        return clean_text(str(value))

    address = value.get("address", value)
    if isinstance(address, dict):
        parts = [
            address.get("addressLocality", ""),
            address.get("addressRegion", ""),
            address.get("addressCountry", ""),
        ]
        return clean_text(", ".join(str(part) for part in parts if part))

    return clean_text(str(address))


def extract_jsonld_jobs(soup: BeautifulSoup, page_url: str) -> List[Dict[str, str]]:
    jobs: List[Dict[str, str]] = []
    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        raw = script.string or script.get_text("", strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for item in object_values(data):
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type", "")
            if isinstance(item_type, list):
                is_job = any(str(t).lower() == "jobposting" for t in item_type)
            else:
                is_job = str(item_type).lower() == "jobposting"
            if not is_job:
                continue

            title = clean_job_title(clean_text(str(item.get("title", ""))))
            if not title:
                continue

            job_url = canonicalize_url(str(item.get("url") or page_url))
            jobs.append(
                {
                    "job_title": title,
                    "job_url": job_url,
                    "location": format_jsonld_location(item.get("jobLocation")),
                    "department": clean_text(
                        str(item.get("occupationalCategory") or item.get("industry") or "")
                    ),
                    "source_url": page_url,
                    "status": "found",
                }
            )

    return jobs


def clean_job_title(title: str) -> str:
    title = clean_text(title)
    title = re.sub(r"^(apply for|apply to|view|read more about)\s+", "", title, flags=re.I)
    title = re.split(r"\b(?:location|department|team|category|function)\s*[:\-]", title, maxsplit=1, flags=re.I)[0]
    title = re.sub(r"\s+\|\s+.*$", "", title)
    title = re.sub(r"\s+-\s+careers?$", "", title, flags=re.I)
    title = title.strip(" -|:")

    if not title or title.lower() in GENERIC_TITLES:
        return ""
    if len(title) > 120:
        return ""
    if len(title.split()) > 14:
        return ""
    return title


def title_from_slug(url: str) -> str:
    try:
        path = urlparse(url).path
    except ValueError:
        return ""

    slug = path.rstrip("/").split("/")[-1]
    slug = re.sub(r"\.[a-z0-9]+$", "", slug, flags=re.I)
    slug = re.sub(r"^\d+[-_]", "", slug)
    slug = re.sub(r"[-_]\d+$", "", slug)
    slug = re.sub(r"\d{4,}", "", slug)
    slug = slug.replace("-", " ").replace("_", " ")
    slug = clean_text(slug)
    if not slug or slug.lower() in GENERIC_TITLES:
        return ""
    if not contains_job_title_word(slug):
        return ""
    return slug.title()


def tag_lines(tag: Any) -> List[str]:
    if not tag:
        return []
    lines = [clean_text(item) for item in tag.stripped_strings]
    return [line for line in lines if line]


def title_from_anchor(anchor: Any, url: str) -> str:
    possible = [
        clean_text(anchor.get_text(" ", strip=True)),
        clean_text(anchor.get("aria-label", "")),
        clean_text(anchor.get("title", "")),
    ]

    parent = anchor.parent
    if parent:
        for line in tag_lines(parent)[:8]:
            possible.append(line)

    for value in possible:
        title = clean_job_title(value)
        if title and contains_job_title_word(title):
            return title

    return title_from_slug(url)


def contains_job_title_word(text: str) -> bool:
    return bool(JOB_TITLE_WORD_RE.search(text or ""))


def looks_like_job_url(url: str) -> bool:
    url_l = url.lower()
    if BAD_JOB_URL_RE.search(url_l):
        return False
    if is_linkedin_url(url):
        return False
    if "teamtailor.com" in urlparse(url).netloc.lower() and "jobs" not in url_l:
        return False
    return any(hint in url_l for hint in JOB_URL_HINTS)


def looks_like_job_text(text: str) -> bool:
    text_l = clean_text(text).lower()
    if not text_l or text_l in GENERIC_TITLES:
        return False
    if len(text_l.split()) > 14:
        return False
    return contains_job_title_word(text_l)


def host_matches(url: str, hints: Sequence[str]) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return any(hint in host for hint in hints)


def page_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return clean_text(soup.get_text(" ", strip=True))


def looks_blocked_page(html: str) -> bool:
    text_l = page_text(html).lower()
    return any(hint in text_l for hint in BLOCKED_TEXT_HINTS)


def looks_no_openings_page(html: str) -> bool:
    text_l = page_text(html).lower()
    return any(hint in text_l for hint in NO_OPENINGS_HINTS)


def is_likely_js_rendered(html: str, page_url: str) -> bool:
    html_l = (html or "").lower()
    text_l = page_text(html).lower()
    script_count = html_l.count("<script")
    has_js_hint = any(hint in html_l or hint in text_l for hint in JS_TEXT_HINTS)
    sparse_shell = len(text_l) < 250 and script_count >= 2
    app_shell = bool(re.search(r'id=["\'](?:root|app|__next)["\']', html_l))

    if has_js_hint:
        return True
    if host_matches(page_url, JS_HEAVY_HOST_HINTS) and (sparse_shell or app_shell or script_count >= 4):
        return True
    if app_shell and sparse_shell:
        return True
    return False


def looks_unsupported_structure(html: str) -> bool:
    text_l = page_text(html).lower()
    if looks_no_openings_page(html):
        return False
    return any(
        hint in text_l
        for hint in ("job listings", "current openings", "open roles", "apply now", "job search")
    )


def extract_location(lines: List[str]) -> str:
    joined = " | ".join(lines[:12])
    match = re.search(r"\b(?:location|locations|city|office)\s*[:\-]\s*([^|]{2,90})", joined, re.I)
    if match:
        return clean_text(match.group(1))

    for line in lines[:8]:
        line_l = line.lower()
        if line_l in {"remote", "hybrid", "on-site", "onsite"}:
            return line
        if "," in line and len(line) <= 80 and not looks_like_job_text(line):
            return line
    return ""


def extract_department(lines: List[str]) -> str:
    joined = " | ".join(lines[:12])
    match = re.search(
        r"\b(?:department|team|category|function)\s*[:\-]\s*([^|]{2,80})",
        joined,
        re.I,
    )
    return clean_text(match.group(1)) if match else ""


def extract_anchor_jobs(soup: BeautifulSoup, page_url: str) -> List[Dict[str, str]]:
    jobs: List[Dict[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = clean_text(anchor.get("href", ""))
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue

        url = canonicalize_url(urljoin(page_url, href))
        if not is_http_url(url):
            continue

        text = clean_text(anchor.get_text(" ", strip=True))
        parent_lines = tag_lines(anchor.parent) if anchor.parent else []
        parent_text = " ".join(parent_lines[:10])
        if not looks_like_job_url(url) and not looks_like_job_text(text + " " + parent_text):
            continue

        title = title_from_anchor(anchor, url)
        if not title:
            continue

        jobs.append(
            {
                "job_title": title,
                "job_url": url,
                "location": extract_location(parent_lines),
                "department": extract_department(parent_lines),
                "source_url": page_url,
                "status": "found",
            }
        )

    return jobs


def extract_jobs_from_html(html: str, page_url: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    jobs = extract_jsonld_jobs(soup, page_url)
    jobs.extend(extract_anchor_jobs(soup, page_url))
    return dedupe_jobs(jobs)


def dedupe_jobs(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen_urls = set()
    seen_titles = set()
    out: List[Dict[str, str]] = []
    for row in rows:
        key = canonicalize_url(row.get("job_url", ""))
        title_key = "|".join(
            [
                clean_text(row.get("job_title", "")).lower(),
                clean_text(row.get("location", "")).lower(),
            ]
        )

        if key and key in seen_urls:
            continue
        if title_key.strip("|") and title_key in seen_titles:
            continue

        if key:
            seen_urls.add(key)
        if title_key.strip("|"):
            seen_titles.add(title_key)
        out.append(row)
    return out


def company_output_base(row: Dict[str, str], careers_url: str) -> Dict[str, str]:
    company_name = pick_company_name(row)
    website = pick_company_website(row)
    company_id = clean_text(row.get("company_id", "")) or stable_id(
        (company_name + "|" + website).lower()
    )
    return {
        "company_id": company_id,
        "company_name": company_name,
        "company_website": website,
        "careers_url": careers_url,
        "category": clean_text(row.get("category", "")),
    }


def make_status_row(
    row: Dict[str, str],
    careers_url: str,
    source_url: str,
    status: str,
) -> Dict[str, str]:
    base = company_output_base(row, careers_url)
    base.update(
        {
            "job_title": "",
            "job_url": "",
            "location": "",
            "department": "",
            "date_found": today_utc(),
            "source_url": source_url,
            "status": status,
        }
    )
    return base


def make_log_row(
    row: Dict[str, str],
    url_checked: str,
    status: str,
    http_status: str = "",
    jobs_found: int = 0,
    error_message: str = "",
) -> Dict[str, str]:
    base = company_output_base(row, "")
    return {
        "checked_at": now_iso(),
        "company_id": base["company_id"],
        "company_name": base["company_name"],
        "company_website": base["company_website"],
        "url_checked": url_checked,
        "status": status,
        "http_status": http_status,
        "jobs_found": str(jobs_found),
        "error_message": error_message,
    }


def make_discovered_page_row(
    row: Dict[str, str],
    careers_url: str,
    source_url: str,
    status: str,
    http_status: str = "",
    notes: str = "",
) -> Dict[str, str]:
    base = company_output_base(row, careers_url)
    return {
        "checked_at": now_iso(),
        "company_id": base["company_id"],
        "company_name": base["company_name"],
        "company_website": base["company_website"],
        "careers_url": careers_url,
        "source_url": source_url,
        "status": status,
        "http_status": http_status,
        "notes": notes,
    }


def make_failed_company_row(
    row: Dict[str, str],
    careers_url: str,
    status: str,
    error_message: str,
) -> Dict[str, str]:
    base = company_output_base(row, careers_url)
    return {
        "checked_at": now_iso(),
        "company_id": base["company_id"],
        "company_name": base["company_name"],
        "company_website": base["company_website"],
        "careers_url": careers_url,
        "status": status,
        "error_message": error_message,
    }


def fetch_status(fetch_error: str, html: str = "") -> Tuple[str, str]:
    if fetch_error == "invalid_url":
        return "invalid_url", "invalid_url"
    if fetch_error == "timeout":
        return "timeout", "timeout"
    if fetch_error == "non_html_response":
        return "non_html_response", "non_html_response"
    if fetch_error == "blocked":
        return "blocked", "blocked_or_rate_limited"
    if fetch_error == "redirect_detected":
        return "redirect_detected", "redirect_loop_or_too_many_redirects"
    if fetch_error.startswith("http_"):
        return "request_failed", fetch_error
    if fetch_error:
        return "request_failed", fetch_error
    if not (html or "").strip():
        return "parse_error", "empty_html"
    return "", ""


def status_from_logs(log_rows: List[Dict[str, str]]) -> str:
    if not log_rows:
        return "no_jobs_found"

    statuses = [row.get("status", "") for row in log_rows if row.get("status") != "redirect_detected"]
    failure_statuses = {
        "invalid_url",
        "request_failed",
        "timeout",
        "non_html_response",
        "parse_error",
        "js_rendered_or_unsupported",
        "blocked",
        "unsupported_structure",
    }
    if statuses and all(status in failure_statuses for status in statuses):
        return statuses[0] or "request_failed"
    return "no_jobs_found"


def crawl_company(
    row: Dict[str, str],
    timeout: int,
    sleep_seconds: float,
    max_pages: int,
    session: Optional[Any] = None,
    retries: int = 2,
    backoff: float = 0.5,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    company_name = pick_company_name(row)
    website = pick_company_website(row)
    known_urls = pick_existing_careers_urls(row)
    known_url = known_urls[0] if known_urls else ""
    log_rows: List[Dict[str, str]] = []

    unsupported_known_urls = [
        url for url in known_urls if is_linkedin_url(url) or host_matches(url, UNSUPPORTED_CAREER_HOST_HINTS)
    ]
    known_urls = [url for url in known_urls if url not in unsupported_known_urls]

    if unsupported_known_urls and not known_urls:
        careers_url_display = "; ".join(unsupported_known_urls)
        log_rows.append(
            make_log_row(
                row,
                careers_url_display,
                "js_rendered_or_unsupported",
                "",
                0,
                "unsupported_external_profile",
            )
        )
        return [
            make_status_row(
                row,
                careers_url_display,
                careers_url_display,
                "js_rendered_or_unsupported",
            )
        ], log_rows

    if known_urls:
        careers_urls = known_urls
        discovery_source = "; ".join(known_urls)
    else:
        discovery = discover_careers_page(
            company_name=company_name,
            company_website=website,
            known_url=known_url,
            timeout=timeout,
            sleep_seconds=sleep_seconds,
            session=session,
            retries=retries,
            backoff=backoff,
        )
        careers_urls = [discovery.careers_url] if discovery.careers_url else []
        discovery_source = discovery.source_url or website

        if not careers_urls:
            status = discovery.status or "careers_page_not_found"
            log_rows.append(
                make_log_row(
                    row,
                    discovery.source_url or known_url or website,
                    status,
                    discovery.http_status,
                    0,
                    discovery.error,
                )
            )
            return [make_status_row(row, "", discovery.source_url or website, status)], log_rows

    careers_url_display = "; ".join(careers_urls)
    urls_to_check = list(careers_urls)
    checked_urls = set()
    found_jobs: List[Dict[str, str]] = []

    while urls_to_check and len(checked_urls) < max_pages:
        url = urls_to_check.pop(0)
        canonical = canonicalize_url(url)
        if canonical in checked_urls:
            continue
        checked_urls.add(canonical)

        fetch = fetch_url(url, timeout=timeout, session=session, retries=retries, backoff=backoff)
        page_url = normalize_url(fetch.final_url or url)
        checked_urls.add(canonicalize_url(page_url))
        if sleep_seconds:
            time.sleep(sleep_seconds)

        status, error_message = fetch_status(fetch.error, fetch.html)
        if status:
            log_rows.append(
                make_log_row(row, url, status, fetch.status_code, 0, error_message)
            )
            continue

        if fetch.redirected:
            log_rows.append(
                make_log_row(
                    row,
                    url,
                    "redirect_detected",
                    fetch.status_code,
                    0,
                    f"redirected_to={page_url}",
                )
            )

        if looks_blocked_page(fetch.html):
            log_rows.append(
                make_log_row(row, page_url, "blocked", fetch.status_code, 0, "blocked_page")
            )
            continue

        try:
            jobs = extract_jobs_from_html(fetch.html, page_url)
        except Exception as exc:
            log_rows.append(
                make_log_row(row, page_url, "parse_error", fetch.status_code, 0, str(exc))
            )
            continue

        found_jobs.extend(jobs)
        if jobs:
            page_status = "success"
        elif is_likely_js_rendered(fetch.html, page_url):
            page_status = "js_rendered_or_unsupported"
        elif looks_unsupported_structure(fetch.html):
            page_status = "unsupported_structure"
        else:
            page_status = "no_jobs_found"
        log_rows.append(make_log_row(row, page_url, page_status, fetch.status_code, len(jobs), ""))

        if len(checked_urls) < max_pages:
            current_page_urls = {
                normalize_url(url).rstrip("/"),
                normalize_url(page_url).rstrip("/"),
            }
            for _, next_url, _ in find_careers_links(fetch.html, page_url, limit=max_pages):
                if normalize_url(next_url).rstrip("/") in current_page_urls:
                    continue
                next_canonical = canonicalize_url(next_url)
                if next_canonical not in checked_urls and next_url not in urls_to_check:
                    urls_to_check.append(next_url)

    found_jobs = dedupe_jobs(found_jobs)
    if not found_jobs:
        status = status_from_logs(log_rows)
        return [make_status_row(row, careers_url_display, discovery_source, status)], log_rows

    output_rows: List[Dict[str, str]] = []
    for job in found_jobs:
        base = company_output_base(row, careers_url_display)
        base.update(
            {
                "job_title": job.get("job_title", ""),
                "job_url": job.get("job_url", ""),
                "location": job.get("location", ""),
                "department": job.get("department", ""),
                "date_found": today_utc(),
                "source_url": job.get("source_url", careers_url_display),
                "status": "success",
            }
        )
        output_rows.append(base)

    return output_rows, log_rows


def dedupe_output_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out: List[Dict[str, str]] = []
    for row in rows:
        job_url = canonicalize_url(row.get("job_url", ""))
        if job_url:
            key = ("job", job_url)
        else:
            key = (
                "status",
                row.get("company_id", ""),
                row.get("company_name", "").lower(),
                row.get("status", ""),
            )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def split_careers_url_display(value: str) -> List[str]:
    return [url.strip() for url in (value or "").split(";") if url.strip()]


def summarize_discovered_pages(output_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    rows: List[Dict[str, str]] = []
    for row in output_rows:
        for careers_url in split_careers_url_display(row.get("careers_url", "")):
            key = (row.get("company_id", ""), careers_url)
            if key in seen:
                continue
            seen.add(key)
            status = row.get("status", "")
            discovered_status = (
                "js_rendered_or_unsupported"
                if status == "js_rendered_or_unsupported"
                else "careers_page_found"
            )
            rows.append(
                make_discovered_page_row(
                    row,
                    careers_url,
                    row.get("source_url", ""),
                    discovered_status,
                    "",
                    f"crawl_status={status}",
                )
            )
    return rows


def summarize_failed_companies(output_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    rows: List[Dict[str, str]] = []
    for row in output_rows:
        status = row.get("status", "")
        if status not in FAILURE_STATUSES:
            continue
        key = (row.get("company_id", ""), status)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            make_failed_company_row(
                row,
                row.get("careers_url", ""),
                status,
                f"source_url={row.get('source_url', '')}",
            )
        )
    return rows


def run_crawl(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_path = Path(args.output)
    log_path = Path(args.log)
    discovered_path = Path(args.discovered_pages)
    failed_path = Path(args.failed_companies)

    company_rows, duplicate_rows = read_company_rows_with_duplicates(input_path, limit=args.limit)
    output_rows: List[Dict[str, str]] = []
    log_rows: List[Dict[str, str]] = []
    session = create_session()

    for index, row in enumerate(company_rows, start=1):
        company_name = pick_company_name(row) or f"company_{index}"
        print(f"[{index}/{len(company_rows)}] {company_name}")
        try:
            jobs, logs = crawl_company(
                row=row,
                timeout=args.timeout,
                sleep_seconds=args.sleep,
                max_pages=args.max_pages_per_company,
                session=session,
                retries=args.retries,
                backoff=args.backoff,
            )
        except Exception as exc:
            jobs = [make_status_row(row, "", pick_company_website(row), "request_failed")]
            logs = [
                make_log_row(
                    row,
                    pick_existing_careers_url(row) or pick_company_website(row),
                    "request_failed",
                    "",
                    0,
                    str(exc),
                )
            ]
        output_rows.extend(jobs)
        log_rows.extend(logs)

    for duplicate in duplicate_rows:
        log_rows.append(
            make_log_row(
                duplicate,
                pick_existing_careers_url(duplicate) or pick_company_website(duplicate),
                "duplicate_skipped",
                "",
                0,
                "duplicate_company",
            )
        )

    output_rows = dedupe_output_rows(output_rows)
    discovered_rows = summarize_discovered_pages(output_rows)
    failed_rows = summarize_failed_companies(output_rows)

    write_csv(output_path, output_rows, OUTPUT_FIELDS)
    write_csv(log_path, log_rows, LOG_FIELDS)
    write_csv(discovered_path, discovered_rows, DISCOVERED_FIELDS)
    write_csv(failed_path, failed_rows, FAILED_FIELDS)

    found_count = sum(1 for row in output_rows if row.get("status") == "success")
    print(f"Wrote {len(output_rows)} rows to {output_path}")
    print(f"Wrote {len(log_rows)} crawl log rows to {log_path}")
    print(f"Wrote {len(discovered_rows)} discovered page rows to {discovered_path}")
    print(f"Wrote {len(failed_rows)} failed company rows to {failed_path}")
    print(f"Found {found_count} job rows")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl company career pages into jobs CSV.")
    parser.add_argument("--input", default="data/companies.csv", help="Input company CSV.")
    parser.add_argument("--output", default="jobs_out.csv", help="Output jobs CSV.")
    parser.add_argument("--log", default="crawl_log.csv", help="Output crawl log CSV.")
    parser.add_argument(
        "--discovered-pages",
        default="output/discovered_pages.csv",
        help="Output discovered career pages CSV.",
    )
    parser.add_argument(
        "--failed-companies",
        default="output/failed_companies.csv",
        help="Output failed/non-success companies CSV.",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retries", type=int, default=2, help="Request retries.")
    parser.add_argument("--backoff", type=float, default=0.5, help="Retry backoff base seconds.")
    parser.add_argument("--sleep", type=float, default=0.2, help="Seconds between requests.")
    parser.add_argument(
        "--max-pages-per-company",
        type=int,
        default=3,
        help="Career/listing pages to fetch per company.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit companies for testing.")
    return parser.parse_args()


if __name__ == "__main__":
    run_crawl(parse_args())
