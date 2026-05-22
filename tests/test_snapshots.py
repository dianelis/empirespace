from pathlib import Path

from crawl_jobs import OUTPUT_FIELDS
from update_snapshots import read_csv, update_snapshot_storage, write_csv


def write_jobs(path: Path, rows: list[dict[str, str]]) -> None:
    write_csv(path, rows, OUTPUT_FIELDS)


def test_snapshot_storage_updates_history_and_analytics(tmp_path):
    jobs_path = tmp_path / "jobs_out.csv"
    client_output = tmp_path / "client" / "public" / "data" / "jobs_out.csv"
    snapshots_dir = tmp_path / "data" / "snapshots"
    analytics_dir = tmp_path / "data" / "analytics"

    write_jobs(
        jobs_path,
        [
            {
                "company_name": "Company A",
                "job_title": "Software Engineer",
                "job_url": "https://example.com/jobs/1",
                "location": "Brooklyn, NY, United States",
                "city": "Brooklyn",
                "state": "NY",
                "remote": "Remote",
                "status": "success",
            },
            {
                "company_name": "Company B",
                "job_title": "Systems Analyst",
                "job_url": "https://example.com/jobs/2",
                "location": "Boston, MA, United States",
                "city": "Boston",
                "state": "MA",
                "remote": "Not specified",
                "status": "success",
            },
        ],
    )
    update_snapshot_storage(
        jobs_path,
        "2026-05-20",
        client_output,
        snapshots_dir,
        analytics_dir,
    )

    write_jobs(
        jobs_path,
        [
            {
                "company_name": "Company A",
                "job_title": "Software Engineer",
                "job_url": "https://example.com/jobs/1?utm_source=newsletter",
                "location": "Brooklyn, NY, United States",
                "city": "Brooklyn",
                "state": "NY",
                "remote": "Remote",
                "status": "success",
            },
            {
                "company_name": "Company A",
                "job_title": "Test Engineer",
                "job_url": "https://example.com/jobs/test-engineer",
                "location": "Rochester, NY, United States",
                "city": "Rochester",
                "state": "NY",
                "remote": "Not specified",
                "status": "success_after_fallback",
            },
            {
                "company_name": "Company C",
                "status": "no_jobs_found",
            },
        ],
    )
    update_snapshot_storage(
        jobs_path,
        "2026-05-21",
        client_output,
        snapshots_dir,
        analytics_dir,
    )
    update_snapshot_storage(
        jobs_path,
        "2026-05-21",
        client_output,
        snapshots_dir,
        analytics_dir,
    )

    client_rows = read_csv(client_output)
    assert client_rows[0]["snapshot_date"] == "2026-05-21"
    assert client_rows[0]["job_id"]
    assert (snapshots_dir / "jobs_2026-05-21.csv").exists()

    summary_rows = read_csv(analytics_dir / "daily_summary.csv")
    assert [row["snapshot_date"] for row in summary_rows].count("2026-05-21") == 1
    today = next(row for row in summary_rows if row["snapshot_date"] == "2026-05-21")
    assert today["total_jobs"] == "2"
    assert today["total_companies"] == "1"
    assert today["remote_jobs"] == "1"
    assert today["ny_jobs"] == "2"
    assert today["new_jobs_count"] == "1"
    assert today["removed_jobs_count"] == "1"
    assert today["retained_jobs_count"] == "1"
    assert today["top_company_by_jobs"] == "Company A"
    assert today["top_city_by_jobs"] == "Brooklyn"

    new_jobs = [
        row
        for row in read_csv(analytics_dir / "new_jobs.csv")
        if row["comparison_snapshot_date"] == "2026-05-21"
    ]
    removed_jobs = [
        row
        for row in read_csv(analytics_dir / "removed_jobs.csv")
        if row["comparison_snapshot_date"] == "2026-05-21"
    ]
    assert len(new_jobs) == 1
    assert len(removed_jobs) == 1

    company_changes = [
        row
        for row in read_csv(analytics_dir / "company_changes.csv")
        if row["snapshot_date"] == "2026-05-21"
    ]
    company_a = next(row for row in company_changes if row["company_name"] == "Company A")
    company_b = next(row for row in company_changes if row["company_name"] == "Company B")
    assert company_a["net_change"] == "1"
    assert company_b["net_change"] == "-1"
