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
    ATS_HOST_HINTS,
    clean_text,
    create_session,
    fetch_url,
    get_site_root,
    is_http_url,
    is_linkedin_url,
    normalize_url,
    pick_company_name,
    pick_company_website,
    pick_existing_careers_url,
    pick_existing_careers_urls,
)


OUTPUT_FIELDS = [
    "job_id",
    "snapshot_date",
    "company_id",
    "company_name",
    "company_website",
    "careers_url",
    "job_title",
    "job_url",
    "location",
    "city",
    "state",
    "country",
    "remote",
    "salary_min",
    "salary_max",
    "department",
    "category",
    "date_found",
    "last_seen_at",
    "source_url",
    "discovery_method",
    "job_confidence_score",
    "status",
]

LOG_FIELDS = [
    "company_name",
    "attempted_url",
    "attempt_type",
    "status_code",
    "scraper_status",
    "error_message",
    "timestamp",
]

DISCOVERED_FIELDS = [
    "company_name",
    "company_website",
    "discovered_url",
    "discovery_method",
    "confidence_score",
    "timestamp",
]

REJECTED_FIELDS = [
    "company_name",
    "candidate_title",
    "candidate_url",
    "rejection_reason",
    "confidence_score",
    "source_url",
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
    "careers_url_failed",
    "fallback_url_failed",
    "no_jobs_found",
}

JOB_TITLE_WORD_RE = re.compile(
    r"\b("
    r"engineer|engineering|developer|designer|manager|director|analyst|scientist|"
    r"technician|operator|specialist|associate|coordinator|administrator|architect|"
    r"assistant|consultant|lead|leader|intern|internship|management|recruiter|sales|operations|"
    r"product|software|mechanical|electrical|aerospace|propulsion|avionics"
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
    "work with us",
    "company careers",
    "life at company",
    "view details",
}

GENERIC_CAREERS_TITLES = GENERIC_TITLES | {
    "openings",
    "opening",
    "roles",
    "open role",
    "current openings",
    "current roles",
    "life at",
    "life at our company",
    "life at company",
    "company careers",
    "our careers",
    "explore careers",
}

BROAD_OPPORTUNITY_TITLE_RE = re.compile(
    r"\b("
    r"high school|student|students|student programs?|early careers?|early talent|"
    r"new grads?|graduates?|campus|internship opportunities|internship program|"
    r"internships|apprenticeships|explore internship|opportunities"
    r")\b",
    re.I,
)

APPLICATION_SIGNAL_RE = re.compile(
    r"\b("
    r"apply|apply now|submit application|job description|responsibilities|qualifications|"
    r"requirements|compensation|salary|full[- ]time|part[- ]time|internship|contract|"
    r"remote|hybrid|onsite|on-site"
    r")\b",
    re.I,
)

JOB_PATH_RE = re.compile(
    r"("
    r"/jobs?/|/careers?/|/careers?/job|/careers?/jobs?|/positions?/|/openings?/|/roles?/|"
    r"/greenhouse/|/lever/|/ashby/|/workable/|/smartrecruiters/|"
    r"greenhouse\.io/.*/jobs?/|lever\.co/.*/jobs?/|ashbyhq\.com/.*/job/|"
    r"workable\.com/.*/jobs?/|smartrecruiters\.com/.*/jobs?/|gh_jid="
    r")",
    re.I,
)

JOB_DETAIL_ID_RE = re.compile(
    r"/(?:jobs?|careers?|positions?|openings?|roles?)/(?:[^/]+/){0,4}\d{3,}(?:[-/]|$)",
    re.I,
)

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
    "breezy.hr/",
    "adp.com/",
    "ultipro.com/",
    "ukg.com/",
)

FALLBACK_CAREER_PATHS = (
    "/careers",
    "/jobs",
    "/careers/jobs",
    "/join-us",
    "/work-with-us",
    "/open-positions",
    "/opportunities",
    "/company/careers",
    "/about/careers",
    "/team",
)

FALLBACK_LINK_TERMS = (
    "careers",
    "career",
    "jobs",
    "hiring",
    "join",
    "work with us",
    "open positions",
    "opportunities",
    "greenhouse",
    "lever",
    "workable",
    "ashby",
    "breezy",
    "smartrecruiters",
)

ATS_LINK_HOST_HINTS = tuple(
    dict.fromkeys(
        ATS_HOST_HINTS
        + (
            "boards.greenhouse.io",
            "job-boards.greenhouse.io",
            "lever.co",
            "jobs.lever.co",
            "ashbyhq.com",
            "jobs.ashbyhq.com",
            "workable.com",
            "breezy.hr",
            "smartrecruiters.com",
            "recruitee.com",
            "jazzhr.com",
            "icims.com",
            "jobvite.com",
            "adp.com",
            "workforcenow.adp.com",
            "ultipro.com",
            "ukg.com",
            "bamboohr.com",
        )
    )
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
    r"(privacy|terms|cookie|login|signin|sign-in|register|talent-community|newsletter"
    r"|facebook\.com|instagram\.com|youtube\.com|twitter\.com|x\.com)",
    re.I,
)

NEGATIVE_PAGE_TERMS = {
    "about",
    "team",
    "contact",
    "blog",
    "news",
    "press",
    "events",
    "investors",
    "mission",
    "product",
    "products",
    "services",
    "privacy",
    "terms",
    "cookie",
    "login",
    "signup",
    "sign-up",
    "donate",
    "partners",
    "customers",
    "case studies",
    "case-studies",
    "resources",
    "whitepaper",
    "faq",
    "support",
    "home",
    "index",
}

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

STATE_NAMES = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}

STATE_CODES = set(STATE_NAMES.values())

COUNTRY_ALIASES = {
    "usa": "United States",
    "us": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "united states": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "uae": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",
}

KNOWN_COUNTRIES = {
    "Australia",
    "Austria",
    "Belgium",
    "Brazil",
    "Canada",
    "China",
    "Denmark",
    "Finland",
    "France",
    "Germany",
    "India",
    "Ireland",
    "Israel",
    "Italy",
    "Japan",
    "Mexico",
    "Netherlands",
    "Norway",
    "Poland",
    "Singapore",
    "South Korea",
    "Spain",
    "Sweden",
    "Switzerland",
    "United Arab Emirates",
    "United Kingdom",
    "United States",
}

LOCATION_PROSE_RE = re.compile(
    r"\b("
    r"build skills|teamwork|graduation|responsibilities|requirements|qualifications|"
    r"benefits|compensation|salary|department|category|function|operational|"
    r"excellence|learn more|apply now|view details"
    r")\b",
    re.I,
)

REMOTE_HINT_RE = re.compile(r"\b(remote|telecommute|work from home)\b", re.I)
HYBRID_HINT_RE = re.compile(r"\bhybrid\b", re.I)
ONSITE_HINT_RE = re.compile(r"\b(on-site|onsite|in office)\b", re.I)

SALARY_RANGE_RE = re.compile(
    r"\$\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*([kK])?\s*"
    r"(?:-|–|—|to)\s*"
    r"\$?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*([kK])?",
    re.I,
)
SALARY_SINGLE_RE = re.compile(r"\$\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*([kK])?", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:12]


def is_blank(value: str) -> bool:
    return clean_text(value).lower() in {"", "null", "nullz", "none", "nan", "n/a"}


def normalize_identity_part(value: str) -> str:
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return clean_text(value)


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


def format_salary_amount(raw_value: Any, multiplier_hint: str = "") -> str:
    value = clean_text(str(raw_value or ""))
    if not value:
        return ""

    value = value.replace("$", "").replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        return ""

    number = float(match.group(0))
    if multiplier_hint.lower() == "k" or "k" in value.lower():
        number *= 1000

    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def extract_jsonld_salary(item: Dict[str, Any]) -> Tuple[str, str]:
    salary = item.get("baseSalary")
    if not salary:
        return "", ""
    if isinstance(salary, list):
        salary = salary[0] if salary else {}
    if not isinstance(salary, dict):
        amount = format_salary_amount(salary)
        return amount, amount

    value = salary.get("value", salary)
    if isinstance(value, list):
        value = value[0] if value else {}
    if isinstance(value, dict):
        min_value = format_salary_amount(value.get("minValue") or value.get("min_value"))
        max_value = format_salary_amount(value.get("maxValue") or value.get("max_value"))
        exact_value = format_salary_amount(value.get("value"))
        return min_value or exact_value, max_value or exact_value

    amount = format_salary_amount(value)
    return amount, amount


def extract_salary_range(text: str) -> Tuple[str, str]:
    text = clean_text(text)
    if not text:
        return "", ""
    if not re.search(r"\b(salary|compensation|pay\s+range|base\s+pay|wage|hourly|annual)\b", text, re.I):
        return "", ""

    match = SALARY_RANGE_RE.search(text)
    if match:
        low = format_salary_amount(match.group(1), match.group(2) or "")
        high = format_salary_amount(match.group(3), match.group(4) or "")
        return low, high

    match = SALARY_SINGLE_RE.search(text)
    if match:
        amount = format_salary_amount(match.group(1), match.group(2) or "")
        return amount, amount

    return "", ""


def normalize_country(value: str) -> str:
    value = clean_text(value)
    normalized = COUNTRY_ALIASES.get(value.lower(), value)
    for country in KNOWN_COUNTRIES:
        if normalized.lower() == country.lower():
            return country
    return normalized


def is_known_country(value: str) -> bool:
    normalized = normalize_country(value)
    return normalized in KNOWN_COUNTRIES


def normalize_state(value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""
    upper = value.upper()
    if upper in STATE_CODES:
        return upper
    return STATE_NAMES.get(value.lower(), value)


def strip_location_label(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"^(job\s+)?location\s*[:\-]\s*", "", value, flags=re.I)
    value = re.sub(r"^(city|office|locations)\s*[:\-]\s*", "", value, flags=re.I)
    return clean_text(value)


def fallback_company_location(row: Dict[str, str]) -> str:
    city = clean_text(row.get("location", ""))
    if not city or not looks_like_place_name(city):
        return ""
    return f"{city}, NY, United States"


def is_remote_location(value: str) -> bool:
    value = clean_text(value)
    return bool(
        re.fullmatch(
            r"(remote|hybrid|on-site|onsite|remote\s*-\s*(?:us|u\.s\.|united states))",
            value,
            re.I,
        )
    )


def looks_like_place_name(value: str) -> bool:
    value = strip_location_label(value)
    if not value or len(value) > 60:
        return False
    if LOCATION_PROSE_RE.search(value):
        return False
    if contains_job_title_word(value):
        return False
    if re.search(r"[|&]", value):
        return False
    if re.search(r"\d", value):
        return False
    if value.count(".") > 1 or (value.endswith(".") and len(value.split()) > 3):
        return False
    if len(value.split()) > 6:
        return False
    return bool(re.search(r"[A-Za-z]", value))


def is_state_value(value: str) -> bool:
    return normalize_state(value) in STATE_CODES


def blank_location_fields(location: str = "") -> Dict[str, str]:
    return {"location": location, "city": "", "state": "", "country": ""}


def parse_valid_location_fields(location: str) -> Dict[str, str]:
    location = strip_location_label(location)
    if not location:
        return blank_location_fields()
    if is_remote_location(location):
        return blank_location_fields(location)
    if len(location) > 160 or LOCATION_PROSE_RE.search(location):
        return blank_location_fields()

    first_location = re.split(r"\s*(?:;|\|)\s*", location, maxsplit=1)[0]
    first_location = strip_location_label(first_location)
    parts = [strip_location_label(part) for part in first_location.split(",")]
    parts = [part for part in parts if part]
    if not parts:
        return blank_location_fields()
    if any(not looks_like_place_name(part) and not is_state_value(part) and not is_known_country(part) for part in parts):
        return blank_location_fields()

    city = ""
    state = ""
    country = ""

    if len(parts) >= 4 and is_state_value(parts[1]) and is_state_value(parts[3]):
        city = parts[0]
        state = normalize_state(parts[1])
        country = "United States"
    elif len(parts) >= 3 and is_known_country(parts[2]):
        city = parts[0]
        country = normalize_country(parts[2])
        if is_state_value(parts[1]):
            state = normalize_state(parts[1])
        elif country != "United States" and looks_like_place_name(parts[1]):
            state = parts[1]
        else:
            return blank_location_fields()
    elif len(parts) >= 3 and is_state_value(parts[-1]):
        city = parts[0]
        state = normalize_state(parts[-1])
        country = "United States"
    elif len(parts) >= 2 and is_state_value(parts[1]):
        city = parts[0]
        state = normalize_state(parts[1])
        country = "United States"
    elif len(parts) >= 2 and is_known_country(parts[1]):
        city = parts[0]
        country = normalize_country(parts[1])
    elif is_known_country(parts[0]):
        country = normalize_country(parts[0])
    elif len(parts) == 1 and is_known_country(parts[0]):
        country = normalize_country(parts[0])
    else:
        return blank_location_fields()

    if city and not looks_like_place_name(city):
        return blank_location_fields()
    if country == "United States" and state and state not in STATE_CODES:
        return blank_location_fields()
    if country and not is_known_country(country):
        return blank_location_fields()

    return {
        "location": location,
        "city": city,
        "state": state,
        "country": country,
    }


def is_valid_location_text(location: str) -> bool:
    fields = parse_valid_location_fields(location)
    return bool(fields["location"] and (is_remote_location(fields["location"]) or fields["city"] or fields["country"]))


def infer_remote_status(location: str, text: str = "") -> str:
    combined = f"{location} {text}"
    if REMOTE_HINT_RE.search(combined):
        return "Remote"
    if HYBRID_HINT_RE.search(combined):
        return "Hybrid"
    if ONSITE_HINT_RE.search(combined):
        return "On-site"
    return "Not specified"


def parse_location_fields(location: str, row: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    location = strip_location_label(location)
    fields = parse_valid_location_fields(location)
    if fields["location"]:
        return fields

    if row:
        fallback = fallback_company_location(row)
        if fallback and fallback.lower() != location.lower():
            fallback_fields = parse_valid_location_fields(fallback)
            if fallback_fields["location"]:
                return fallback_fields

    return blank_location_fields()


def extract_jsonld_jobs(
    soup: BeautifulSoup,
    page_url: str,
    rejected_candidates: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
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
                if rejected_candidates is not None:
                    rejected_candidates.append(
                        rejection_row(
                            {
                                "job_title": clean_text(str(item.get("title", ""))),
                                "job_url": canonicalize_url(str(item.get("url") or page_url)),
                                "source_url": page_url,
                                "rejection_reason": "generic_title",
                                "job_confidence_score": "-2",
                            }
                        )
                    )
                continue

            job_url = canonicalize_url(str(item.get("url") or page_url))
            location = format_jsonld_location(item.get("jobLocation"))
            salary_min, salary_max = extract_jsonld_salary(item)
            remote = "Remote" if clean_text(str(item.get("jobLocationType", ""))).upper() == "TELECOMMUTE" else infer_remote_status(location)
            candidate = {
                "job_title": title,
                "job_url": job_url,
                "location": location,
                "remote": remote,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "department": clean_text(
                    str(item.get("occupationalCategory") or item.get("industry") or "")
                ),
                "source_url": page_url,
                "context_text": clean_text(json.dumps(item, ensure_ascii=False)),
                "structured_data": True,
                "status": "found",
            }
            if is_valid_job_posting(candidate):
                jobs.append(accepted_job_row(candidate))
            elif rejected_candidates is not None:
                rejected_candidates.append(rejection_row(candidate))

    return jobs


def clean_job_title(title: str) -> str:
    title = clean_text(title)
    title = re.sub(r"^(apply for|apply to|view|read more about)\s+", "", title, flags=re.I)
    title = re.split(r"\b(?:location|department|team|category|function)\s*[:\-]", title, maxsplit=1, flags=re.I)[0]
    if "|" in title or re.search(r",\s*&\s*,", title):
        return ""
    if len([part for part in title.split(",") if part.strip()]) >= 3 and re.search(r",\s*[A-Z]{2}$", title):
        return ""
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

    segments = [segment for segment in path.rstrip("/").split("/") if segment]
    for raw_slug in reversed(segments):
        slug = re.sub(r"\.[a-z0-9]+$", "", raw_slug, flags=re.I)
        slug = re.sub(r"^\d+[-_]", "", slug)
        slug = re.sub(r"[-_]\d+$", "", slug)
        slug = re.sub(r"\d{4,}", "", slug)
        slug = slug.replace("-", " ").replace("_", " ")
        slug = clean_text(slug)
        if not slug or slug.lower() in GENERIC_TITLES:
            continue
        if not contains_job_title_word(slug):
            continue
        return slug.title()
    return ""


def sanitize_job_title(title: str, url: str = "") -> str:
    cleaned = clean_job_title(title)
    if cleaned:
        return cleaned
    return title_from_slug(url)


def tag_lines(tag: Any) -> List[str]:
    if not tag:
        return []
    lines = [clean_text(item) for item in tag.stripped_strings]
    return [line for line in lines if line]


def anchor_context_lines(anchor: Any) -> List[str]:
    ignored_containers = {"nav", "header", "footer", "aside"}
    if anchor.parent and getattr(anchor.parent, "name", "") not in ignored_containers:
        best_lines = tag_lines(anchor.parent)
    else:
        best_lines = []
    for parent in anchor.parents:
        if getattr(parent, "name", "") in {"body", "html"}:
            break
        if getattr(parent, "name", "") in ignored_containers:
            continue

        classes = " ".join(parent.get("class", [])) if hasattr(parent, "get") else ""
        identifier = parent.get("id", "") if hasattr(parent, "get") else ""
        descriptor = f"{classes} {identifier}".lower()
        lines = tag_lines(parent)
        if not lines:
            continue

        is_likely_card = (
            parent.name in {"li", "tr", "article"}
            or any(term in descriptor for term in ("job", "career", "opening", "position", "requisition"))
        )
        if is_likely_card and len(lines) <= 60:
            return lines
        if len(lines) <= 20 and len(" ".join(lines)) <= 1800:
            best_lines = lines

    return best_lines


def title_from_anchor(anchor: Any, url: str) -> str:
    possible = [
        clean_text(anchor.get_text(" ", strip=True)),
        clean_text(anchor.get("aria-label", "")),
        clean_text(anchor.get("title", "")),
    ]

    parent = anchor.parent
    if parent and getattr(parent, "name", "") not in {"nav", "header", "footer", "aside"}:
        for line in tag_lines(parent)[:8]:
            possible.append(line)

    for value in possible:
        title = sanitize_job_title(value, url)
        if title and contains_job_title_word(title):
            return title

    return title_from_slug(url)


def contains_job_title_word(text: str) -> bool:
    return bool(JOB_TITLE_WORD_RE.search(text or ""))


def url_has_job_path(url: str) -> bool:
    return bool(JOB_PATH_RE.search(url or ""))


def url_has_job_detail_id(url: str) -> bool:
    return bool(JOB_DETAIL_ID_RE.search(url or ""))


def has_application_signal(text: str) -> bool:
    return bool(APPLICATION_SIGNAL_RE.search(text or ""))


def title_is_generic(title: str, company_name: str = "") -> bool:
    title_l = clean_text(title).lower()
    if not title_l or len(title_l) < 3:
        return True
    if title_l in GENERIC_CAREERS_TITLES:
        return True
    if len(title_l.split()) == 1 and (title_l in GENERIC_CAREERS_TITLES or contains_job_title_word(title_l)):
        return True
    company_l = clean_text(company_name).lower()
    return bool(company_l and title_l == company_l)


def title_is_broad_opportunity_page(title: str, url: str = "") -> bool:
    title_l = normalize_identity_part(title)
    if not title_l:
        return False
    if title_l in {
        "high school internship opportunities",
        "explore internship opportunities",
        "internship opportunities",
        "internship program",
        "student opportunities",
        "student programs",
        "early careers",
        "early talent and internships",
        "students early careers",
        "new grads",
        "graduate opportunities",
    }:
        return True
    if "opportunit" in title_l and not url_has_job_detail_id(url):
        return True
    if BROAD_OPPORTUNITY_TITLE_RE.search(title_l) and not (url_has_job_detail_id(url) or is_ats_url(url)):
        role_words = [word for word in ("engineer", "manager", "analyst", "technician", "scientist", "operator") if word in title_l]
        return len(role_words) == 0
    return False


def title_has_negative_page_signal(title: str) -> bool:
    title_l = normalize_identity_part(title)
    if not title_l:
        return False
    if title_l in {term.replace("-", " ") for term in NEGATIVE_PAGE_TERMS}:
        return True
    return title_l in {
        "about us",
        "our team",
        "contact us",
        "latest news",
        "press releases",
        "our mission",
        "our products",
        "products",
        "services",
        "case studies",
        "resources",
        "support",
        "home",
        "index",
    }


def url_has_negative_page_signal(url: str) -> bool:
    if not url:
        return False
    if BAD_JOB_URL_RE.search(url):
        return True
    try:
        parsed = urlparse(url)
    except ValueError:
        return True

    path_l = parsed.path.lower().strip("/")
    if not path_l:
        return False

    segments = [segment for segment in re.split(r"/+", path_l) if segment]
    negative_segments = {term for term in NEGATIVE_PAGE_TERMS if " " not in term and "-" not in term}
    for segment in segments:
        normalized = segment.strip()
        normalized_words = normalize_identity_part(normalized)
        if normalized in negative_segments:
            return True
        if normalized_words in {term.replace("-", " ") for term in NEGATIVE_PAGE_TERMS}:
            return True
    return False


def has_negative_page_signal(title: str, url: str) -> bool:
    if title_has_negative_page_signal(title):
        return True
    if url_has_negative_page_signal(url):
        return True
    return False


def calculate_job_confidence(candidate: Dict[str, Any]) -> Tuple[int, List[str]]:
    title = clean_text(candidate.get("job_title", ""))
    url = canonicalize_url(clean_text(candidate.get("job_url", "")))
    context_text = clean_text(candidate.get("context_text", ""))
    source_url = clean_text(candidate.get("source_url", ""))
    location = clean_text(candidate.get("location", ""))
    company_name = clean_text(candidate.get("company_name", ""))
    structured_data = bool(candidate.get("structured_data"))
    score = 0
    reasons: List[str] = []

    if structured_data:
        score += 2
        reasons.append("structured_jobposting")
    if contains_job_title_word(title):
        score += 1
        reasons.append("job_title_keyword")
    if url_has_job_path(url):
        score += 1
        reasons.append("job_url_path")
    if url_has_job_detail_id(url):
        score += 1
        reasons.append("job_detail_id")
    if has_application_signal(context_text):
        score += 1
        reasons.append("application_context")
    if is_valid_location_text(location):
        score += 1
        reasons.append("location_detected")
    if is_ats_url(url) and url_has_job_path(url):
        score += 1
        reasons.append("ats_job_link")

    if title_is_generic(title, company_name):
        score -= 2
        reasons.append("generic_title")
    if title_is_broad_opportunity_page(title, url):
        score -= 2
        reasons.append("broad_opportunity_page")
    if has_negative_page_signal(title, url):
        score -= 2
        reasons.append("negative_page_keyword")
    if source_url and has_negative_page_signal("", source_url) and not url_has_job_path(url):
        score -= 1
        reasons.append("negative_source_page")

    return score, reasons


def is_valid_job_posting(candidate: Dict[str, Any]) -> bool:
    if candidate.get("job_url"):
        candidate["job_url"] = canonicalize_url(candidate.get("job_url", ""))
    sanitized_title = sanitize_job_title(candidate.get("job_title", ""), candidate.get("job_url", ""))
    if sanitized_title:
        candidate["job_title"] = sanitized_title
    score, reasons = calculate_job_confidence(candidate)
    candidate["job_confidence_score"] = str(score)
    candidate["rejection_reason"] = ";".join(reasons)

    if title_is_generic(candidate.get("job_title", ""), candidate.get("company_name", "")):
        candidate["rejection_reason"] = "generic_title"
        return False
    if title_is_broad_opportunity_page(
        candidate.get("job_title", ""),
        canonicalize_url(candidate.get("job_url", "")),
    ):
        candidate["rejection_reason"] = "broad_opportunity_page"
        return False
    if has_negative_page_signal(
        candidate.get("job_title", ""),
        canonicalize_url(candidate.get("job_url", "")),
    ):
        candidate["rejection_reason"] = "negative_page_keyword"
        return False
    if score < 3:
        candidate["rejection_reason"] = candidate.get("rejection_reason") or "low_confidence"
        return False
    return True


def rejection_row(candidate: Dict[str, Any]) -> Dict[str, str]:
    return {
        "company_name": clean_text(candidate.get("company_name", "")),
        "candidate_title": clean_text(candidate.get("job_title", "")),
        "candidate_url": clean_text(candidate.get("job_url", "")),
        "rejection_reason": clean_text(candidate.get("rejection_reason", "")),
        "confidence_score": clean_text(candidate.get("job_confidence_score", "")),
        "source_url": clean_text(candidate.get("source_url", "")),
    }


def accepted_job_row(candidate: Dict[str, Any]) -> Dict[str, str]:
    return {
        "job_title": clean_text(candidate.get("job_title", "")),
        "job_url": clean_text(candidate.get("job_url", "")),
        "location": clean_text(candidate.get("location", "")),
        "remote": clean_text(candidate.get("remote", "")),
        "salary_min": clean_text(candidate.get("salary_min", "")),
        "salary_max": clean_text(candidate.get("salary_max", "")),
        "department": clean_text(candidate.get("department", "")),
        "source_url": clean_text(candidate.get("source_url", "")),
        "job_confidence_score": clean_text(candidate.get("job_confidence_score", "")),
        "status": clean_text(candidate.get("status", "")),
    }


def looks_like_job_url(url: str) -> bool:
    url_l = url.lower()
    if BAD_JOB_URL_RE.search(url_l):
        return False
    if is_linkedin_url(url):
        return False
    if "teamtailor.com" in urlparse(url).netloc.lower() and "jobs" not in url_l:
        return False
    return any(hint in url_l for hint in JOB_URL_HINTS) or url_has_job_path(url)


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
        location = clean_text(match.group(1))
        if is_valid_location_text(location):
            return location

    for line in lines[:8]:
        line_l = line.lower()
        if line_l in {"remote", "hybrid", "on-site", "onsite"}:
            return line
        if "," in line and len(line) <= 100 and not looks_like_job_text(line) and is_valid_location_text(line):
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


def extract_location_from_url(url: str) -> str:
    try:
        path = urlparse(url).path
    except ValueError:
        return ""

    match = re.search(
        r"/job/([A-Za-z][A-Za-z-]+)-([A-Z]{2})-\d{4,}/",
        path,
    )
    if not match:
        return ""
    city = match.group(1).replace("-", " ").title()
    state = match.group(2)
    return f"{city}, {state}, United States"


def extract_anchor_jobs(
    soup: BeautifulSoup,
    page_url: str,
    rejected_candidates: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    jobs: List[Dict[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = clean_text(anchor.get("href", ""))
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue

        url = canonicalize_url(urljoin(page_url, href))
        if not is_http_url(url):
            continue

        text = clean_text(anchor.get_text(" ", strip=True))
        parent_lines = anchor_context_lines(anchor)
        parent_text = " ".join(parent_lines[:10])
        candidate_like = (
            looks_like_job_url(url)
            or looks_like_job_text(text + " " + parent_text)
            or title_has_negative_page_signal(text)
            or url_has_negative_page_signal(url)
            or clean_text(text).lower() in GENERIC_CAREERS_TITLES
        )
        if not candidate_like:
            continue

        title = title_from_anchor(anchor, url)
        if not title:
            if rejected_candidates is not None:
                raw_title = clean_text(text or title_from_slug(url))
                rejected_candidates.append(
                    rejection_row(
                        {
                            "job_title": raw_title,
                            "job_url": url,
                            "source_url": page_url,
                            "rejection_reason": "missing_or_generic_title",
                            "job_confidence_score": "-2",
                        }
                    )
                )
            continue

        salary_min, salary_max = extract_salary_range(parent_text)
        location = extract_location(parent_lines) or extract_location_from_url(url)
        candidate = {
            "job_title": title,
            "job_url": url,
            "location": location,
            "remote": infer_remote_status(location, parent_text),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "department": extract_department(parent_lines),
            "source_url": page_url,
            "context_text": clean_text(f"{text} {parent_text}"),
            "structured_data": False,
            "status": "found",
        }
        if is_valid_job_posting(candidate):
            jobs.append(accepted_job_row(candidate))
        elif rejected_candidates is not None:
            rejected_candidates.append(rejection_row(candidate))

    return jobs


def extract_jobs_from_html(
    html: str,
    page_url: str,
    rejected_candidates: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    jobs = extract_jsonld_jobs(soup, page_url, rejected_candidates)
    jobs.extend(extract_anchor_jobs(soup, page_url, rejected_candidates))
    return dedupe_jobs(jobs)


def dedupe_jobs(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen_urls = set()
    seen_titles = set()
    out: List[Dict[str, str]] = []
    for row in rows:
        key = canonicalize_url(row.get("job_url", ""))

        if key and key in seen_urls:
            continue
        if key:
            seen_urls.add(key)
        else:
            title_key = "|".join(
                [
                    clean_text(row.get("job_title", "")).lower(),
                    clean_text(row.get("location", "")).lower(),
                ]
            )
            if title_key.strip("|") and title_key in seen_titles:
                continue
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
        "job_id": "",
        "snapshot_date": "",
        "job_confidence_score": "",
        "company_id": company_id,
        "company_name": company_name,
        "company_website": website,
        "careers_url": careers_url,
        "category": clean_text(row.get("category", "")),
    }


def generate_job_id(row: Dict[str, str]) -> str:
    company_name = normalize_identity_part(row.get("company_name", ""))
    job_title = normalize_identity_part(row.get("job_title", ""))
    if not company_name or not job_title:
        return ""

    job_url = canonicalize_url(row.get("job_url", ""))
    if job_url:
        key = "|".join([company_name, job_title, job_url])
    else:
        key = "|".join(
            [
                company_name,
                job_title,
                normalize_identity_part(row.get("location", "")),
            ]
        )
    return stable_id(key)


def add_tracking_fields(rows: List[Dict[str, str]], snapshot_date: str) -> List[Dict[str, str]]:
    for row in rows:
        row["snapshot_date"] = snapshot_date
        row["job_id"] = row.get("job_id") or generate_job_id(row)
    return rows


def make_status_row(
    row: Dict[str, str],
    careers_url: str,
    source_url: str,
    status: str,
    discovery_method: str = "",
) -> Dict[str, str]:
    base = company_output_base(row, careers_url)
    location_fields = parse_location_fields("", row)
    base.update(
        {
            "job_title": "",
            "job_url": "",
            "location": location_fields["location"],
            "city": location_fields["city"],
            "state": location_fields["state"],
            "country": location_fields["country"],
            "remote": "Not specified",
            "salary_min": "",
            "salary_max": "",
            "department": "",
            "date_found": today_utc(),
            "last_seen_at": today_utc(),
            "source_url": source_url,
            "discovery_method": discovery_method,
            "status": status,
        }
    )
    return base


def make_log_row(
    row: Dict[str, str],
    attempted_url: str,
    scraper_status: str,
    status_code: str = "",
    jobs_found: int = 0,
    error_message: str = "",
    attempt_type: str = "crawl",
) -> Dict[str, str]:
    return {
        "company_name": pick_company_name(row),
        "attempted_url": attempted_url,
        "attempt_type": attempt_type,
        "status_code": str(status_code or ""),
        "scraper_status": scraper_status,
        "error_message": error_message,
        "timestamp": now_iso(),
    }


def make_discovered_page_row(
    row: Dict[str, str],
    discovered_url: str,
    discovery_method: str,
    confidence_score: Any = "",
) -> Dict[str, str]:
    return {
        "company_name": pick_company_name(row),
        "company_website": pick_company_website(row),
        "discovered_url": discovered_url,
        "discovery_method": discovery_method,
        "confidence_score": str(confidence_score),
        "timestamp": now_iso(),
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

    statuses = [
        row.get("scraper_status") or row.get("status", "")
        for row in log_rows
        if (row.get("scraper_status") or row.get("status", "")) != "redirect_detected"
    ]
    failure_statuses = {
        "invalid_url",
        "request_failed",
        "timeout",
        "non_html_response",
        "parse_error",
        "js_rendered_or_unsupported",
        "blocked",
        "unsupported_structure",
        "careers_url_failed",
        "fallback_url_failed",
    }
    for status in ("no_jobs_found", "unsupported_structure", "js_rendered_or_unsupported"):
        if status in statuses:
            return status
    for status in (
        "invalid_url",
        "timeout",
        "blocked",
        "non_html_response",
        "parse_error",
        "fallback_url_failed",
        "careers_url_failed",
        "request_failed",
        "careers_page_not_found",
    ):
        if status in statuses:
            return status
    if statuses and all(status in failure_statuses for status in statuses):
        return statuses[0] or "request_failed"
    return "no_jobs_found"


def is_ats_url(url: str) -> bool:
    return host_matches(url, ATS_LINK_HOST_HINTS)


def should_retry_fetch(fetch_error: str) -> bool:
    if fetch_error in {"timeout", "blocked", "redirect_detected"}:
        return True
    if fetch_error.startswith("request_failed"):
        return True
    return fetch_error in {"http_429", "http_500", "http_502", "http_503", "http_504"}


def final_failure_status(discovery_method: str) -> str:
    if discovery_method == "known_careers_url":
        return "careers_url_failed"
    return "fallback_url_failed"


def record_discovered_page(
    row: Dict[str, str],
    discovered_rows: List[Dict[str, str]],
    discovered_seen: set,
    discovered_url: str,
    discovery_method: str,
    confidence_score: int,
) -> None:
    normalized = normalize_url(discovered_url)
    if not normalized:
        return

    key = (company_dedupe_key(row), canonicalize_url(normalized), discovery_method)
    if key in discovered_seen:
        return
    discovered_seen.add(key)
    discovered_rows.append(
        make_discovered_page_row(row, normalized, discovery_method, confidence_score)
    )


def add_candidate(
    candidates: List[Dict[str, Any]],
    seen_candidates: set,
    url: str,
    discovery_method: str,
    confidence_score: int,
    depth: int = 0,
    attempt_type: str = "fallback",
) -> bool:
    normalized = normalize_url(url)
    if not normalized:
        return False
    if is_linkedin_url(normalized) or host_matches(normalized, UNSUPPORTED_CAREER_HOST_HINTS):
        return False

    key = canonicalize_url(normalized)
    if key in seen_candidates:
        return False
    seen_candidates.add(key)
    candidates.append(
        {
            "url": normalized,
            "discovery_method": discovery_method,
            "confidence_score": confidence_score,
            "depth": depth,
            "attempt_type": attempt_type,
        }
    )
    return True


def score_fallback_link(text: str, url: str, base_host: str) -> int:
    if not is_http_url(url):
        return 0
    if is_linkedin_url(url) or host_matches(url, UNSUPPORTED_CAREER_HOST_HINTS):
        return 0
    if BAD_JOB_URL_RE.search(url):
        return 0

    try:
        parsed = urlparse(url)
    except ValueError:
        return 0

    host = parsed.netloc.lower()
    text_l = clean_text(text).lower()
    url_l = url.lower()
    score = 0

    for term in FALLBACK_LINK_TERMS:
        compact = term.replace(" ", "")
        dashed = term.replace(" ", "-")
        if term in text_l:
            score += 14
        if dashed in url_l or compact in url_l:
            score += 10

    if is_ats_url(url):
        score += 45
    elif score and host == base_host:
        score += 5
    elif score:
        score -= 5

    if any(signal in parsed.path.lower() for signal in ("/job", "/career", "/opening", "/position")):
        score += 8

    return max(score, 0)


def add_candidates_from_html(
    html: str,
    base_url: str,
    row: Dict[str, str],
    candidates: List[Dict[str, Any]],
    seen_candidates: set,
    discovered_rows: List[Dict[str, str]],
    discovered_seen: set,
    log_rows: List[Dict[str, str]],
    depth: int,
    limit: int = 12,
) -> None:
    soup = BeautifulSoup(html or "", "html.parser")
    try:
        base_host = urlparse(base_url).netloc.lower()
    except ValueError:
        base_host = ""

    scored: Dict[str, Tuple[int, str, str]] = {}
    for anchor in soup.find_all("a", href=True):
        href = clean_text(anchor.get("href", ""))
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue

        url = normalize_url(urljoin(base_url, href))
        text = clean_text(anchor.get_text(" ", strip=True))
        score = score_fallback_link(text, url, base_host)
        if score <= 0:
            continue

        existing = scored.get(url)
        if not existing or score > existing[0]:
            scored[url] = (score, url, text)

    for score, url, _ in sorted(scored.values(), key=lambda item: item[0], reverse=True)[:limit]:
        discovery_method = "ats_detected" if is_ats_url(url) else "linked_page"
        if add_candidate(
            candidates,
            seen_candidates,
            url,
            discovery_method,
            score,
            depth=depth,
            attempt_type=discovery_method,
        ):
            record_discovered_page(
                row,
                discovered_rows,
                discovered_seen,
                url,
                discovery_method,
                score,
            )
            log_rows.append(
                make_log_row(
                    row,
                    url,
                    "ats_detected" if discovery_method == "ats_detected" else "fallback_url_found",
                    "",
                    0,
                    "",
                    attempt_type="discovery",
                )
            )


def add_common_path_candidates(
    row: Dict[str, str],
    candidates: List[Dict[str, Any]],
    seen_candidates: set,
) -> None:
    website = pick_company_website(row)
    root = get_site_root(website)
    if not root:
        return

    for path in FALLBACK_CAREER_PATHS:
        add_candidate(
            candidates,
            seen_candidates,
            urljoin(root, path.lstrip("/")),
            "common_path",
            55,
            depth=0,
            attempt_type="common_path",
        )


def fetch_with_logged_retries(
    row: Dict[str, str],
    candidate: Dict[str, Any],
    timeout: int,
    session: Any,
    retries: int,
    backoff: float,
    sleep_seconds: float,
    log_rows: List[Dict[str, str]],
) -> Optional[Any]:
    attempts = max(0, retries) + 1
    last_fetch = None
    last_status = ""
    last_error_message = ""

    for attempt in range(1, attempts + 1):
        fetch = fetch_url(
            candidate["url"],
            timeout=timeout,
            session=session,
            retries=0,
            backoff=backoff,
        )
        last_fetch = fetch
        if sleep_seconds:
            time.sleep(sleep_seconds)

        page_url = normalize_url(fetch.final_url or candidate["url"])
        status, error_message = fetch_status(fetch.error, fetch.html)
        if fetch.redirected:
            log_rows.append(
                make_log_row(
                    row,
                    candidate["url"],
                    "redirect_detected",
                    fetch.status_code,
                    0,
                    f"redirected_to={page_url}",
                    attempt_type=candidate.get("attempt_type", "crawl"),
                )
            )

        if not status:
            return fetch

        last_status = status
        last_error_message = error_message
        attempt_message = error_message
        if attempts > 1:
            attempt_message = clean_text(f"{attempt_message} attempt={attempt}/{attempts}")
        log_rows.append(
            make_log_row(
                row,
                candidate["url"],
                status,
                fetch.status_code,
                0,
                attempt_message,
                attempt_type=candidate.get("attempt_type", "crawl"),
            )
        )

        if attempt < attempts and should_retry_fetch(fetch.error):
            time.sleep(backoff * (2 ** (attempt - 1)))
            continue
        break

    if last_fetch is not None:
        log_rows.append(
            make_log_row(
                row,
                candidate["url"],
                final_failure_status(candidate.get("discovery_method", "")),
                last_fetch.status_code,
                0,
                last_error_message or last_status,
                attempt_type=candidate.get("attempt_type", "crawl"),
            )
        )
    return None


def seed_fallback_candidates(
    row: Dict[str, str],
    candidates: List[Dict[str, Any]],
    seen_candidates: set,
    discovered_rows: List[Dict[str, str]],
    discovered_seen: set,
    log_rows: List[Dict[str, str]],
    timeout: int,
    session: Any,
    retries: int,
    backoff: float,
    sleep_seconds: float,
) -> None:
    website = pick_company_website(row)
    if not website:
        log_rows.append(
            make_log_row(
                row,
                "",
                "invalid_url",
                "",
                0,
                "missing_company_website",
                attempt_type="fallback_discovery",
            )
        )
        return

    add_common_path_candidates(row, candidates, seen_candidates)

    homepage_candidate = {
        "url": website,
        "discovery_method": "homepage_scan",
        "confidence_score": 40,
        "depth": 0,
        "attempt_type": "homepage_scan",
    }
    homepage_fetch = fetch_with_logged_retries(
        row,
        homepage_candidate,
        timeout=timeout,
        session=session,
        retries=retries,
        backoff=backoff,
        sleep_seconds=sleep_seconds,
        log_rows=log_rows,
    )
    if not homepage_fetch:
        candidates.sort(key=lambda item: int(item.get("confidence_score", 0)), reverse=True)
        return

    page_url = normalize_url(homepage_fetch.final_url or website)
    log_rows.append(
        make_log_row(
            row,
            page_url,
            "fallback_url_found",
            homepage_fetch.status_code,
            0,
            "homepage_scanned",
            attempt_type="homepage_scan",
        )
    )
    add_candidates_from_html(
        homepage_fetch.html,
        page_url,
        row,
        candidates,
        seen_candidates,
        discovered_rows,
        discovered_seen,
        log_rows,
        depth=1,
    )
    candidates.sort(key=lambda item: int(item.get("confidence_score", 0)), reverse=True)


def crawl_company(
    row: Dict[str, str],
    timeout: int,
    sleep_seconds: float,
    max_pages: int,
    session: Optional[Any] = None,
    retries: int = 2,
    backoff: float = 0.5,
    rejected_rows: Optional[List[Dict[str, str]]] = None,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    website = pick_company_website(row)
    known_urls = pick_existing_careers_urls(row)
    log_rows: List[Dict[str, str]] = []
    discovered_rows: List[Dict[str, str]] = []
    discovered_seen: set = set()
    candidates: List[Dict[str, Any]] = []
    seen_candidates: set = set()
    attempted_urls: List[str] = []
    active_session = session or create_session()

    unsupported_known_urls = [
        url for url in known_urls if is_linkedin_url(url) or host_matches(url, UNSUPPORTED_CAREER_HOST_HINTS)
    ]
    known_urls = [url for url in known_urls if url not in unsupported_known_urls]

    for unsupported_url in unsupported_known_urls:
        log_rows.append(
            make_log_row(
                row,
                unsupported_url,
                "js_rendered_or_unsupported",
                "",
                0,
                "unsupported_external_profile",
                attempt_type="known_careers_url",
            )
        )

    for known_url in known_urls:
        add_candidate(
            candidates,
            seen_candidates,
            known_url,
            "known_careers_url",
            100,
            depth=0,
            attempt_type="known_careers_url",
        )

    checked_urls = set()
    found_jobs: List[Dict[str, str]] = []
    fallback_seeded = not bool(candidates)
    if fallback_seeded:
        seed_fallback_candidates(
            row,
            candidates,
            seen_candidates,
            discovered_rows,
            discovered_seen,
            log_rows,
            timeout=timeout,
            session=active_session,
            retries=retries,
            backoff=backoff,
            sleep_seconds=sleep_seconds,
        )

    while len(checked_urls) < max(1, max_pages):
        if not candidates:
            if not fallback_seeded:
                fallback_seeded = True
                seed_fallback_candidates(
                    row,
                    candidates,
                    seen_candidates,
                    discovered_rows,
                    discovered_seen,
                    log_rows,
                    timeout=timeout,
                    session=active_session,
                    retries=retries,
                    backoff=backoff,
                    sleep_seconds=sleep_seconds,
                )
            if not candidates:
                break

        candidate = candidates.pop(0)
        url = candidate["url"]
        canonical = canonicalize_url(url)
        if canonical in checked_urls:
            continue
        checked_urls.add(canonical)
        attempted_urls.append(url)

        fetch = fetch_with_logged_retries(
            row,
            candidate,
            timeout=timeout,
            session=active_session,
            retries=retries,
            backoff=backoff,
            sleep_seconds=sleep_seconds,
            log_rows=log_rows,
        )
        if not fetch:
            continue

        page_url = normalize_url(fetch.final_url or url)
        checked_urls.add(canonicalize_url(page_url))
        discovery_method = candidate.get("discovery_method", "")
        confidence_score = int(candidate.get("confidence_score", 0))

        record_discovered_page(
            row,
            discovered_rows,
            discovered_seen,
            page_url,
            discovery_method,
            confidence_score,
        )

        if looks_blocked_page(fetch.html):
            log_rows.append(
                make_log_row(
                    row,
                    page_url,
                    "blocked",
                    fetch.status_code,
                    0,
                    "blocked_page",
                    attempt_type=candidate.get("attempt_type", "crawl"),
                )
            )
            continue

        try:
            page_rejections: List[Dict[str, str]] = []
            jobs = extract_jobs_from_html(
                fetch.html,
                page_url,
                rejected_candidates=page_rejections,
            )
            if rejected_rows is not None:
                for rejected in page_rejections:
                    rejected_with_company = dict(rejected)
                    rejected_with_company["company_name"] = pick_company_name(row)
                    rejected_rows.append(rejected_with_company)
        except Exception as exc:
            log_rows.append(
                make_log_row(
                    row,
                    page_url,
                    "parse_error",
                    fetch.status_code,
                    0,
                    str(exc),
                    attempt_type=candidate.get("attempt_type", "crawl"),
                )
            )
            continue

        if jobs:
            page_status = "success" if discovery_method == "known_careers_url" else "success_after_fallback"
            for job in jobs:
                enriched = dict(job)
                enriched["careers_url"] = page_url
                enriched["discovery_method"] = discovery_method
                found_jobs.append(enriched)
        elif is_likely_js_rendered(fetch.html, page_url):
            page_status = "js_rendered_or_unsupported"
        elif looks_unsupported_structure(fetch.html):
            page_status = "unsupported_structure"
        else:
            page_status = "no_jobs_found"
        log_rows.append(
            make_log_row(
                row,
                page_url,
                page_status,
                fetch.status_code,
                len(jobs),
                "",
                attempt_type=candidate.get("attempt_type", "crawl"),
            )
        )

        if len(checked_urls) < max(1, max_pages) and int(candidate.get("depth", 0)) < 2:
            current_page_urls = {
                normalize_url(url).rstrip("/"),
                normalize_url(page_url).rstrip("/"),
            }
            before_count = len(candidates)
            add_candidates_from_html(
                fetch.html,
                page_url,
                row,
                candidates,
                seen_candidates,
                discovered_rows,
                discovered_seen,
                log_rows,
                depth=int(candidate.get("depth", 0)) + 1,
                limit=max_pages,
            )
            candidates[:] = [
                item
                for item in candidates
                if normalize_url(item["url"]).rstrip("/") not in current_page_urls
            ]
            if len(candidates) != before_count:
                candidates.sort(key=lambda item: int(item.get("confidence_score", 0)), reverse=True)

    found_jobs = dedupe_jobs(found_jobs)
    if not found_jobs:
        status = status_from_logs(log_rows)
        careers_url_display = "; ".join(attempted_urls or unsupported_known_urls)
        source_url = attempted_urls[-1] if attempted_urls else website
        return [
            make_status_row(
                row,
                careers_url_display,
                source_url,
                status,
                "fallback_discovery" if fallback_seeded else "known_careers_url",
            )
        ], log_rows, discovered_rows

    output_rows: List[Dict[str, str]] = []
    for job in found_jobs:
        careers_url = job.get("careers_url", "")
        base = company_output_base(row, careers_url)
        location_fields = parse_location_fields(job.get("location", ""), row)
        remote = job.get("remote", "") or infer_remote_status(location_fields["location"])
        discovery_method = job.get("discovery_method", "")
        base.update(
            {
                "job_title": job.get("job_title", ""),
                "job_url": job.get("job_url", ""),
                "location": location_fields["location"],
                "city": location_fields["city"],
                "state": location_fields["state"],
                "country": location_fields["country"],
                "remote": remote,
                "salary_min": job.get("salary_min", ""),
                "salary_max": job.get("salary_max", ""),
                "department": job.get("department", ""),
                "date_found": today_utc(),
                "last_seen_at": today_utc(),
                "source_url": job.get("source_url", careers_url),
                "discovery_method": discovery_method,
                "job_confidence_score": job.get("job_confidence_score", ""),
                "status": "success" if discovery_method == "known_careers_url" else "success_after_fallback",
            }
        )
        output_rows.append(base)

    return output_rows, log_rows, discovered_rows


def dedupe_output_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out: List[Dict[str, str]] = []
    for row in rows:
        job_url = canonicalize_url(row.get("job_url", ""))
        if job_url:
            key = ("job", job_url)
        elif clean_text(row.get("job_title", "")):
            key = (
                "job_fallback",
                clean_text(row.get("company_name", "")).lower(),
                clean_text(row.get("job_title", "")).lower(),
                clean_text(row.get("location", "")).lower(),
            )
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


def is_output_job_row(row: Dict[str, str]) -> bool:
    if not clean_text(row.get("job_title", "")):
        return False
    status = clean_text(row.get("status", ""))
    return not status or status in {"success", "success_after_fallback"}


def split_careers_url_display(value: str) -> List[str]:
    return [url.strip() for url in (value or "").split(";") if url.strip()]


def summarize_discovered_pages(output_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    rows: List[Dict[str, str]] = []
    for row in output_rows:
        for careers_url in split_careers_url_display(row.get("careers_url", "")):
            key = (row.get("company_id", ""), canonicalize_url(careers_url))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                make_discovered_page_row(
                    row,
                    careers_url,
                    row.get("discovery_method", "") or "known_careers_url",
                    100 if row.get("status") == "success" else 50,
                )
            )
    return rows


def dedupe_discovered_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out: List[Dict[str, str]] = []
    for row in rows:
        key = (
            clean_text(row.get("company_name", "")).lower(),
            canonicalize_url(row.get("discovered_url", "")),
            row.get("discovery_method", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


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
    rejected_path = Path(
        getattr(args, "rejected_candidates", "output/rejected_candidates.csv")
    )

    company_rows, duplicate_rows = read_company_rows_with_duplicates(input_path, limit=args.limit)
    output_rows: List[Dict[str, str]] = []
    log_rows: List[Dict[str, str]] = []
    discovered_rows: List[Dict[str, str]] = []
    rejected_rows: List[Dict[str, str]] = []
    session = create_session()

    for index, row in enumerate(company_rows, start=1):
        company_name = pick_company_name(row) or f"company_{index}"
        print(f"[{index}/{len(company_rows)}] {company_name}")
        try:
            jobs, logs, discovered = crawl_company(
                row=row,
                timeout=args.timeout,
                sleep_seconds=args.sleep,
                max_pages=args.max_pages_per_company,
                session=session,
                retries=args.retries,
                backoff=args.backoff,
                rejected_rows=rejected_rows,
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
                    attempt_type="company_crawl",
                )
            ]
            discovered = []
        output_rows.extend(jobs)
        log_rows.extend(logs)
        discovered_rows.extend(discovered)

    for duplicate in duplicate_rows:
        log_rows.append(
            make_log_row(
                duplicate,
                pick_existing_careers_url(duplicate) or pick_company_website(duplicate),
                "duplicate_skipped",
                "",
                0,
                "duplicate_company",
                attempt_type="input_dedupe",
            )
        )

    output_rows = dedupe_output_rows(output_rows)
    failed_rows = summarize_failed_companies(output_rows)
    output_rows = [row for row in output_rows if is_output_job_row(row)]
    snapshot_date = clean_text(getattr(args, "snapshot_date", "")) or today_utc()
    output_rows = add_tracking_fields(output_rows, snapshot_date)
    discovered_rows = dedupe_discovered_rows(discovered_rows or summarize_discovered_pages(output_rows))

    write_csv(output_path, output_rows, OUTPUT_FIELDS)
    write_csv(log_path, log_rows, LOG_FIELDS)
    write_csv(discovered_path, discovered_rows, DISCOVERED_FIELDS)
    write_csv(failed_path, failed_rows, FAILED_FIELDS)
    write_csv(rejected_path, rejected_rows, REJECTED_FIELDS)

    found_count = sum(
        1 for row in output_rows if row.get("status") in {"success", "success_after_fallback"}
    )
    print(f"Wrote {len(output_rows)} rows to {output_path}")
    print(f"Wrote {len(log_rows)} crawl log rows to {log_path}")
    print(f"Wrote {len(discovered_rows)} discovered page rows to {discovered_path}")
    print(f"Wrote {len(failed_rows)} failed company rows to {failed_path}")
    print(f"Wrote {len(rejected_rows)} rejected candidate rows to {rejected_path}")
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
    parser.add_argument(
        "--rejected-candidates",
        default="output/rejected_candidates.csv",
        help="Output rejected job candidates CSV for QA.",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retries", type=int, default=2, help="Request retries.")
    parser.add_argument("--backoff", type=float, default=0.5, help="Retry backoff base seconds.")
    parser.add_argument("--sleep", type=float, default=0.2, help="Seconds between requests.")
    parser.add_argument(
        "--max-pages-per-company",
        type=int,
        default=12,
        help="Career/listing pages to fetch per company.",
    )
    parser.add_argument(
        "--snapshot-date",
        default="",
        help="Snapshot date to write into jobs_out.csv. Defaults to the current UTC date.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit companies for testing.")
    return parser.parse_args()


if __name__ == "__main__":
    run_crawl(parse_args())
