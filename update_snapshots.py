from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from crawl_jobs import (
    OUTPUT_FIELDS,
    add_tracking_fields,
    canonicalize_url,
    clean_text,
    infer_remote_status,
    is_valid_job_posting,
    parse_location_fields,
)


SUMMARY_FIELDS = [
    "snapshot_date",
    "total_jobs",
    "total_companies",
    "remote_jobs",
    "ny_jobs",
    "new_jobs_count",
    "removed_jobs_count",
    "retained_jobs_count",
    "top_company_by_jobs",
    "top_city_by_jobs",
]

COMPARISON_FIELDS = [
    "comparison_snapshot_date",
    "job_id",
    "company_name",
    "job_title",
    "job_url",
    "location",
    "remote",
    "department",
    "category",
    "source_url",
]

COMPANY_CHANGE_FIELDS = [
    "snapshot_date",
    "company_name",
    "previous_jobs",
    "current_jobs",
    "new_jobs_count",
    "removed_jobs_count",
    "net_change",
]

SUCCESS_STATUSES = {"success", "success_after_fallback"}


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def build_company_location_map(companies_path: Optional[Path]) -> Dict[str, str]:
    if not companies_path or not companies_path.exists():
        return {}

    locations: Dict[str, str] = {}
    for row in read_csv(companies_path):
        location = clean_text(row.get("location", ""))
        if not location:
            continue
        for key in (clean_text(row.get("company_id", "")), clean_text(row.get("company_name", "")).lower()):
            if key and key not in locations:
                locations[key] = location
    return locations


def company_fallback_row(row: Dict[str, str], company_locations: Dict[str, str]) -> Dict[str, str]:
    company_id = clean_text(row.get("company_id", ""))
    company_name = clean_text(row.get("company_name", "")).lower()
    location = company_locations.get(company_id) or company_locations.get(company_name) or ""
    return {"location": location} if location else row


def is_job_row(row: Dict[str, str]) -> bool:
    if not clean_text(row.get("job_title", "")):
        return False
    status = clean_text(row.get("status", ""))
    return not status or status in SUCCESS_STATUSES


def normalize_snapshot_rows(
    rows: List[Dict[str, str]],
    snapshot_date: str,
    company_locations: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    company_locations = company_locations or {}
    normalized = []
    for row in rows:
        normalized.append({field: row.get(field, "") for field in OUTPUT_FIELDS})

    validated = []
    for row in normalized:
        if not is_job_row(row):
            continue
        candidate = dict(row)
        candidate.setdefault("context_text", "")
        if is_valid_job_posting(candidate):
            row["job_title"] = candidate.get("job_title", row.get("job_title", ""))
            row["job_url"] = candidate.get("job_url", row.get("job_url", ""))
            row["job_confidence_score"] = candidate.get("job_confidence_score", "")
            location_fields = parse_location_fields(
                row.get("location", ""),
                company_fallback_row(row, company_locations),
            )
            row.update(location_fields)
            row["remote"] = clean_text(row.get("remote", "")) or infer_remote_status(row.get("location", ""))
            row["last_seen_at"] = snapshot_date
            if not clean_text(row.get("date_found", "")):
                row["date_found"] = snapshot_date
            validated.append(row)
    normalized = validated
    add_tracking_fields(normalized, snapshot_date)
    return dedupe_rows(normalized)


def dedupe_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out: List[Dict[str, str]] = []
    for row in rows:
        if is_job_row(row):
            key = ("job", row.get("job_id") or canonicalize_url(row.get("job_url", "")))
        else:
            key = (
                "status",
                clean_text(row.get("company_name", "")).lower(),
                clean_text(row.get("status", "")).lower(),
                canonicalize_url(row.get("careers_url", "")),
            )

        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def snapshot_path_for(snapshots_dir: Path, snapshot_date: str) -> Path:
    return snapshots_dir / f"jobs_{snapshot_date}.csv"


def snapshot_date_from_path(path: Path) -> str:
    name = path.stem
    if not name.startswith("jobs_"):
        return ""
    return name.replace("jobs_", "", 1)


def latest_previous_snapshot(snapshots_dir: Path, snapshot_date: str) -> Path | None:
    candidates = []
    for path in snapshots_dir.glob("jobs_*.csv"):
        candidate_date = snapshot_date_from_path(path)
        if candidate_date and candidate_date < snapshot_date:
            candidates.append((candidate_date, path))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[-1][1]


def job_rows_by_id(rows: Iterable[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    out = {}
    for row in rows:
        if not is_job_row(row):
            continue
        job_id = clean_text(row.get("job_id", ""))
        if job_id:
            out[job_id] = row
    return out


def count_by_company(rows_by_id: Dict[str, Dict[str, str]]) -> Counter:
    return Counter(clean_text(row.get("company_name", "")) for row in rows_by_id.values())


def top_value(rows: Iterable[Dict[str, str]], field: str) -> str:
    counts = Counter(clean_text(row.get(field, "")) for row in rows if clean_text(row.get(field, "")))
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))[0][0]


def is_remote(row: Dict[str, str]) -> bool:
    return "remote" in clean_text(row.get("remote", "")).lower()


def is_ny_job(row: Dict[str, str]) -> bool:
    state = clean_text(row.get("state", "")).upper()
    location = clean_text(row.get("location", "")).lower()
    return state == "NY" or "new york" in location or ", ny" in location


def comparison_row(snapshot_date: str, row: Dict[str, str]) -> Dict[str, str]:
    return {
        "comparison_snapshot_date": snapshot_date,
        "job_id": row.get("job_id", ""),
        "company_name": row.get("company_name", ""),
        "job_title": row.get("job_title", ""),
        "job_url": row.get("job_url", ""),
        "location": row.get("location", ""),
        "remote": row.get("remote", ""),
        "department": row.get("department", ""),
        "category": row.get("category", ""),
        "source_url": row.get("source_url", ""),
    }


def replace_rows_for_date(
    existing_rows: List[Dict[str, str]],
    new_rows: List[Dict[str, str]],
    date_field: str,
    snapshot_date: str,
) -> List[Dict[str, str]]:
    kept = [row for row in existing_rows if row.get(date_field) != snapshot_date]
    return kept + new_rows


def build_company_changes(
    snapshot_date: str,
    current_rows: Dict[str, Dict[str, str]],
    previous_rows: Dict[str, Dict[str, str]],
    new_ids: set,
    removed_ids: set,
) -> List[Dict[str, str]]:
    current_counts = count_by_company(current_rows)
    previous_counts = count_by_company(previous_rows)
    new_counts = Counter(current_rows[job_id].get("company_name", "") for job_id in new_ids)
    removed_counts = Counter(previous_rows[job_id].get("company_name", "") for job_id in removed_ids)

    companies = set(current_counts) | set(previous_counts) | set(new_counts) | set(removed_counts)
    rows = []
    for company in sorted(companies, key=lambda value: value.lower()):
        company = clean_text(company)
        if not company:
            continue
        previous_total = previous_counts.get(company, 0)
        current_total = current_counts.get(company, 0)
        rows.append(
            {
                "snapshot_date": snapshot_date,
                "company_name": company,
                "previous_jobs": str(previous_total),
                "current_jobs": str(current_total),
                "new_jobs_count": str(new_counts.get(company, 0)),
                "removed_jobs_count": str(removed_counts.get(company, 0)),
                "net_change": str(current_total - previous_total),
            }
        )
    return rows


def update_snapshot_storage(
    jobs_path: Path,
    snapshot_date: str,
    client_output: Path,
    snapshots_dir: Path,
    analytics_dir: Path,
    companies_path: Optional[Path] = None,
) -> None:
    company_locations = build_company_location_map(companies_path)
    current_rows = normalize_snapshot_rows(read_csv(jobs_path), snapshot_date, company_locations)
    previous_path = latest_previous_snapshot(snapshots_dir, snapshot_date)
    previous_rows = read_csv(previous_path) if previous_path else []

    write_csv(client_output, current_rows, OUTPUT_FIELDS)
    write_csv(snapshot_path_for(snapshots_dir, snapshot_date), current_rows, OUTPUT_FIELDS)

    current_jobs = job_rows_by_id(current_rows)
    previous_jobs = job_rows_by_id(previous_rows)
    current_ids = set(current_jobs)
    previous_ids = set(previous_jobs)
    new_ids = current_ids - previous_ids
    removed_ids = previous_ids - current_ids
    retained_ids = current_ids & previous_ids

    job_rows = list(current_jobs.values())
    summary_row = {
        "snapshot_date": snapshot_date,
        "total_jobs": str(len(current_jobs)),
        "total_companies": str(len({row.get("company_name", "") for row in job_rows if row.get("company_name", "")})),
        "remote_jobs": str(sum(1 for row in job_rows if is_remote(row))),
        "ny_jobs": str(sum(1 for row in job_rows if is_ny_job(row))),
        "new_jobs_count": str(len(new_ids)),
        "removed_jobs_count": str(len(removed_ids)),
        "retained_jobs_count": str(len(retained_ids)),
        "top_company_by_jobs": top_value(job_rows, "company_name"),
        "top_city_by_jobs": top_value(job_rows, "city"),
    }

    summary_path = analytics_dir / "daily_summary.csv"
    summary_rows = replace_rows_for_date(
        read_csv(summary_path),
        [summary_row],
        "snapshot_date",
        snapshot_date,
    )
    summary_rows.sort(key=lambda row: row.get("snapshot_date", ""))
    write_csv(summary_path, summary_rows, SUMMARY_FIELDS)

    new_job_rows = [comparison_row(snapshot_date, current_jobs[job_id]) for job_id in sorted(new_ids)]
    removed_job_rows = [
        comparison_row(snapshot_date, previous_jobs[job_id]) for job_id in sorted(removed_ids)
    ]

    new_jobs_path = analytics_dir / "new_jobs.csv"
    removed_jobs_path = analytics_dir / "removed_jobs.csv"
    write_csv(
        new_jobs_path,
        replace_rows_for_date(read_csv(new_jobs_path), new_job_rows, "comparison_snapshot_date", snapshot_date),
        COMPARISON_FIELDS,
    )
    write_csv(
        removed_jobs_path,
        replace_rows_for_date(read_csv(removed_jobs_path), removed_job_rows, "comparison_snapshot_date", snapshot_date),
        COMPARISON_FIELDS,
    )

    company_changes_path = analytics_dir / "company_changes.csv"
    company_changes = build_company_changes(
        snapshot_date,
        current_jobs,
        previous_jobs,
        new_ids,
        removed_ids,
    )
    write_csv(
        company_changes_path,
        replace_rows_for_date(read_csv(company_changes_path), company_changes, "snapshot_date", snapshot_date),
        COMPANY_CHANGE_FIELDS,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Store dated job snapshots and analytics CSVs.")
    parser.add_argument("--jobs", default="jobs_out.csv", help="Fresh scraper jobs CSV.")
    parser.add_argument(
        "--snapshot-date",
        default=today_utc(),
        help="Snapshot date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--client-output",
        default="client/public/data/jobs_out.csv",
        help="Latest CSV served by the React dashboard.",
    )
    parser.add_argument(
        "--snapshots-dir",
        default="data/snapshots",
        help="Directory for dated jobs_YYYY-MM-DD.csv files.",
    )
    parser.add_argument(
        "--analytics-dir",
        default="data/analytics",
        help="Directory for analytics CSV outputs.",
    )
    parser.add_argument(
        "--companies",
        default="data/companies.csv",
        help="Company CSV used for location fallbacks.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    update_snapshot_storage(
        jobs_path=Path(args.jobs),
        snapshot_date=args.snapshot_date,
        client_output=Path(args.client_output),
        snapshots_dir=Path(args.snapshots_dir),
        analytics_dir=Path(args.analytics_dir),
        companies_path=Path(args.companies),
    )


if __name__ == "__main__":
    main()
