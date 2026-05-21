from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (compatible; EmpireSpaceJobsBot/1.0; "
    "+https://github.com/dianelis/empirespace)"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

DEFAULT_TIMEOUT = 15

CAREER_TERMS = (
    "careers",
    "career",
    "jobs",
    "join us",
    "join our team",
    "work with us",
    "open roles",
    "open positions",
    "openings",
    "employment",
    "vacancies",
)

CAREER_PATHS = (
    "/careers",
    "/career",
    "/jobs",
    "/join-us",
    "/work-with-us",
    "/open-positions",
    "/careers/open-positions",
    "/company/careers",
    "/about/careers",
)

ATS_HOST_HINTS = (
    "greenhouse.io",
    "lever.co",
    "workable.com",
    "ashbyhq.com",
    "bamboohr.com",
    "recruitee.com",
    "applytojob.com",
    "jazzhr.com",
    "smartrecruiters.com",
    "icims.com",
    "jobvite.com",
    "taleo.net",
    "dayforcehcm.com",
    "myworkdayjobs.com",
    "workdayjobs.com",
    "teamtailor.com",
    "tal.net",
)

BAD_HOST_HINTS = (
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "twitter.com",
    "x.com",
    "glassdoor.com",
)

BAD_PATH_RE = re.compile(
    r"(privacy|terms|cookie|login|signin|sign-in|register|account|newsletter|subscribe)",
    re.I,
)


@dataclass
class FetchResult:
    url: str
    final_url: str = ""
    status_code: str = ""
    content_type: str = ""
    html: str = ""
    error: str = ""
    redirected: bool = False


@dataclass
class DiscoveryResult:
    careers_url: str = ""
    status: str = "careers_page_not_found"
    source_url: str = ""
    http_status: str = ""
    error: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def is_blank(value: str) -> bool:
    return clean_text(value).lower() in {"", "null", "nullz", "none", "nan", "n/a"}


def normalize_url(url: str) -> str:
    if is_blank(url):
        return ""

    url = clean_text(url)
    if url.startswith("//"):
        url = "https:" + url
    elif not re.match(r"^https?://", url, re.I):
        url = "https://" + url

    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        if any(char.isspace() for char in parsed.netloc):
            return ""

        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")
        return urlunparse((scheme, netloc, path, "", parsed.query, ""))
    except ValueError:
        return ""


def is_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def get_site_root(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}/"
    except ValueError:
        return ""
    return ""


def host_contains(url: str, hints: Tuple[str, ...]) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return any(hint in host for hint in hints)


def is_linkedin_url(url: str) -> bool:
    try:
        return "linkedin.com" in urlparse(url).netloc.lower()
    except ValueError:
        return False


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def is_html_content_type(content_type: str) -> bool:
    if not content_type:
        return True
    content_type = content_type.lower()
    return any(allowed in content_type for allowed in ("text/html", "application/xhtml+xml"))


def read_response_text(response: requests.Response) -> str:
    try:
        return response.text or ""
    except UnicodeError:
        return response.content.decode("utf-8", errors="replace")


def fetch_url(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    session: Optional[requests.Session] = None,
    retries: int = 2,
    backoff: float = 0.5,
) -> FetchResult:
    normalized = normalize_url(url)
    if not normalized:
        return FetchResult(url=url, error="invalid_url")

    active_session = session or create_session()
    attempts = max(0, retries) + 1
    last_result = FetchResult(url=normalized, error="request_failed")

    for attempt in range(attempts):
        try:
            response = active_session.get(
                normalized,
                timeout=timeout,
                allow_redirects=True,
            )
            content_type = response.headers.get("Content-Type", "")
            status_code = str(response.status_code)
            redirected = bool(response.history) or normalize_url(response.url) != normalized

            if response.status_code in {403, 429}:
                last_result = FetchResult(
                    url=normalized,
                    final_url=response.url,
                    status_code=status_code,
                    content_type=content_type,
                    html=read_response_text(response),
                    error="blocked",
                    redirected=redirected,
                )
            elif response.status_code >= 400:
                last_result = FetchResult(
                    url=normalized,
                    final_url=response.url,
                    status_code=status_code,
                    content_type=content_type,
                    html=read_response_text(response),
                    error=f"http_{response.status_code}",
                    redirected=redirected,
                )
            elif not is_html_content_type(content_type):
                return FetchResult(
                    url=normalized,
                    final_url=response.url,
                    status_code=status_code,
                    content_type=content_type,
                    html="",
                    error="non_html_response",
                    redirected=redirected,
                )
            else:
                return FetchResult(
                    url=normalized,
                    final_url=response.url,
                    status_code=status_code,
                    content_type=content_type,
                    html=read_response_text(response),
                    error="",
                    redirected=redirected,
                )

            if attempt < attempts - 1 and response.status_code in {429, 500, 502, 503, 504}:
                time.sleep(backoff * (2 ** attempt))
                continue
            return last_result
        except requests.Timeout:
            last_result = FetchResult(url=normalized, error="timeout")
        except requests.TooManyRedirects:
            last_result = FetchResult(url=normalized, error="redirect_detected")
        except requests.SSLError:
            last_result = FetchResult(url=normalized, error="request_failed:ssl_error")
        except requests.ConnectionError:
            last_result = FetchResult(url=normalized, error="request_failed:connection_error")
        except requests.RequestException as exc:
            last_result = FetchResult(url=normalized, error=f"request_failed:{exc.__class__.__name__}")

        if attempt < attempts - 1:
            time.sleep(backoff * (2 ** attempt))

    return last_result


def looks_usable_page(fetch: FetchResult) -> bool:
    return (
        not fetch.error
        and bool(fetch.html.strip())
        and fetch.status_code.isdigit()
        and int(fetch.status_code) < 400
    )


def score_careers_link(text: str, url: str, base_host: str) -> int:
    if not is_http_url(url):
        return -1
    if is_linkedin_url(url) or host_contains(url, BAD_HOST_HINTS):
        return -1
    if BAD_PATH_RE.search(url):
        return -1

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    text_l = clean_text(text).lower()
    url_l = url.lower()

    term_score = 0
    for term in CAREER_TERMS:
        if term in text_l:
            term_score += 12
        if term.replace(" ", "-") in url_l or term.replace(" ", "") in url_l:
            term_score += 10

    path_has_job_signal = any(
        signal in parsed.path.lower()
        for signal in ("/job", "/career", "/opening", "/position", "/apply", "/vacancy")
    )

    if host != base_host and host_contains(url, ATS_HOST_HINTS) and not term_score and not path_has_job_signal:
        return -1

    score = term_score
    if host == base_host:
        score += 5
    elif host_contains(url, ATS_HOST_HINTS):
        score += 25
    else:
        score -= 5

    if path_has_job_signal:
        score += 8
    if text_l in {"careers", "jobs", "open positions", "open roles"}:
        score += 5

    return score


def find_careers_links(html: str, base_url: str, limit: int = 5) -> List[Tuple[int, str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    try:
        base_host = urlparse(base_url).netloc.lower()
    except ValueError:
        base_host = ""

    candidates: Dict[str, Tuple[int, str, str]] = {}
    for anchor in soup.find_all("a", href=True):
        href = clean_text(anchor.get("href", ""))
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue

        url = normalize_url(urljoin(base_url, href))
        text = clean_text(anchor.get_text(" ", strip=True))
        score = score_careers_link(text, url, base_host)
        if score <= 0:
            continue

        existing = candidates.get(url)
        if not existing or score > existing[0]:
            candidates[url] = (score, url, text)

    return sorted(candidates.values(), key=lambda item: item[0], reverse=True)[:limit]


def split_url_values(value: str) -> List[str]:
    value = clean_text(value)
    if is_blank(value):
        return []

    found_urls = re.findall(r"https?://[^\s|;]+", value, flags=re.I)
    if len(found_urls) > 1:
        return [url.rstrip(",") for url in found_urls]

    return [item for item in re.split(r"[|;\n]+", value) if clean_text(item)]


def pick_existing_careers_urls(row: Dict[str, str]) -> List[str]:
    urls: List[str] = []
    for column in (
        "careers_url",
        "jobs_page_url",
        "career_page_url",
        "job_page_url",
        "careers_page",
    ):
        for raw_value in split_url_values(row.get(column, "")):
            value = normalize_url(raw_value)
            if value and value not in urls:
                urls.append(value)
    return urls


def pick_existing_careers_url(row: Dict[str, str]) -> str:
    urls = pick_existing_careers_urls(row)
    return urls[0] if urls else ""


def pick_company_name(row: Dict[str, str]) -> str:
    for column in ("company_name", "organization_name", "name"):
        value = clean_text(row.get(column, ""))
        if not is_blank(value):
            return value
    return ""


def pick_company_website(row: Dict[str, str]) -> str:
    for column in ("company_website", "organization_link", "website", "url"):
        value = normalize_url(row.get(column, ""))
        if value:
            return value
    return ""


def discover_careers_page(
    company_name: str,
    company_website: str,
    known_url: str = "",
    timeout: int = DEFAULT_TIMEOUT,
    sleep_seconds: float = 0.0,
    session: Optional[requests.Session] = None,
    retries: int = 2,
    backoff: float = 0.5,
) -> DiscoveryResult:
    known_url = normalize_url(known_url)
    if known_url:
        if is_linkedin_url(known_url):
            return DiscoveryResult(
                careers_url="",
                status="js_rendered_or_unsupported",
                source_url=known_url,
                error="unsupported_external_profile",
            )
        return DiscoveryResult(careers_url=known_url, status="careers_page_found", source_url=known_url)

    website = normalize_url(company_website)
    if not website:
        return DiscoveryResult(status="invalid_url", error="missing_company_website")
    if is_linkedin_url(website) or host_contains(website, BAD_HOST_HINTS):
        return DiscoveryResult(
            status="js_rendered_or_unsupported",
            source_url=website,
            error="unsupported_external_profile",
        )

    active_session = session or create_session()
    fetch = fetch_url(website, timeout=timeout, session=active_session, retries=retries, backoff=backoff)
    if sleep_seconds:
        time.sleep(sleep_seconds)

    if looks_usable_page(fetch):
        links = find_careers_links(fetch.html, fetch.final_url or website, limit=1)
        if links:
            _, url, _ = links[0]
            return DiscoveryResult(
                careers_url=url,
                status="careers_page_found",
                source_url=fetch.final_url or website,
                http_status=fetch.status_code,
            )

    root = get_site_root(fetch.final_url or website)
    if root and not fetch.error:
        for path in CAREER_PATHS:
            candidate_url = urljoin(root, path.lstrip("/"))
            candidate_fetch = fetch_url(
                candidate_url,
                timeout=timeout,
                session=active_session,
                retries=retries,
                backoff=backoff,
            )
            if sleep_seconds:
                time.sleep(sleep_seconds)
            if looks_usable_page(candidate_fetch):
                page_text = clean_text(
                    BeautifulSoup(candidate_fetch.html, "html.parser").get_text(" ", strip=True)
                ).lower()
                if any(term in page_text for term in CAREER_TERMS) or "job" in candidate_url:
                    return DiscoveryResult(
                        careers_url=normalize_url(candidate_fetch.final_url or candidate_url),
                        status="careers_page_found",
                        source_url=candidate_url,
                        http_status=candidate_fetch.status_code,
                    )

    if fetch.error.startswith("request_failed") or fetch.error.startswith("http_"):
        status = "request_failed"
    elif fetch.error in {"invalid_url", "timeout", "blocked", "non_html_response", "redirect_detected"}:
        status = fetch.error
    else:
        status = "careers_page_not_found"

    return DiscoveryResult(
        status=status,
        source_url=fetch.final_url or website,
        http_status=fetch.status_code,
        error=fetch.error,
    )


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_discovery(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_path = Path(args.output)
    log_path = Path(args.log)

    rows = read_rows(input_path)
    if args.limit:
        rows = rows[: args.limit]

    output_rows: List[Dict[str, str]] = []
    log_rows: List[Dict[str, str]] = []
    session = create_session()

    for row in rows:
        company_name = pick_company_name(row)
        website = pick_company_website(row)
        known_url = pick_existing_careers_url(row)
        checked_at = now_iso()

        result = discover_careers_page(
            company_name=company_name,
            company_website=website,
            known_url=known_url,
            timeout=args.timeout,
            sleep_seconds=args.sleep,
            session=session,
            retries=args.retries,
            backoff=args.backoff,
        )

        out = dict(row)
        out["careers_url"] = result.careers_url
        out["discovery_status"] = result.status
        out["discovery_source_url"] = result.source_url
        out["discovery_error"] = result.error
        out["last_checked_at"] = checked_at
        output_rows.append(out)

        log_rows.append(
            {
                "checked_at": checked_at,
                "company_name": company_name,
                "company_website": website,
                "url_checked": result.source_url or known_url or website,
                "status": result.status,
                "http_status": result.http_status,
                "error_message": result.error,
            }
        )

    input_fields = list(rows[0].keys()) if rows else []
    extra_fields = [
        "careers_url",
        "discovery_status",
        "discovery_source_url",
        "discovery_error",
        "last_checked_at",
    ]
    output_fields = input_fields + [field for field in extra_fields if field not in input_fields]
    log_fields = [
        "checked_at",
        "company_name",
        "company_website",
        "url_checked",
        "status",
        "http_status",
        "error_message",
    ]

    write_rows(output_path, output_rows, output_fields)
    write_rows(log_path, log_rows, log_fields)
    print(f"Wrote {len(output_rows)} company rows to {output_path}")
    print(f"Wrote {len(log_rows)} log rows to {log_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover company career/job pages.")
    parser.add_argument("--input", default="data/companies.csv", help="Input company CSV.")
    parser.add_argument(
        "--output",
        default="output/companies_with_careers.csv",
        help="CSV with careers_url and discovery fields.",
    )
    parser.add_argument(
        "--log",
        default="output/discovery_log.csv",
        help="Discovery crawl log CSV.",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retries", type=int, default=2, help="Request retries.")
    parser.add_argument("--backoff", type=float, default=0.5, help="Retry backoff base seconds.")
    parser.add_argument("--sleep", type=float, default=0.2, help="Seconds between requests.")
    parser.add_argument("--limit", type=int, default=0, help="Limit companies for testing.")
    return parser.parse_args()


if __name__ == "__main__":
    run_discovery(parse_args())
