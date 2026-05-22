# empirespace

Simple command-line job scraping workflow for Empire Space company career pages.

The scraper uses only `requests` and `BeautifulSoup4` for web scraping. It does not use Streamlit, Playwright, Selenium, or browser automation.

## Files

- `data/companies.csv` - input company data copied from the existing workspace CSV.
- `discover_jobs_pages.py` - optional helper script that finds career/job pages and writes an enriched company CSV.
- `crawl_jobs.py` - main CLI crawler that writes job rows for later MySQL ingestion.
- `update_snapshots.py` - helper that stores dated snapshots and analytics CSVs after a scrape.
- `jobs_out.csv` - generated job results.
- `crawl_log.csv` - generated request/status log.
- `data/snapshots/jobs_YYYY-MM-DD.csv` - dated historical job snapshots.
- `data/analytics/daily_summary.csv` - daily rollup of job counts and changes.
- `data/analytics/new_jobs.csv` - cumulative new-job comparison rows by snapshot date.
- `data/analytics/removed_jobs.csv` - cumulative removed-job comparison rows by snapshot date.
- `data/analytics/company_changes.csv` - company-level hiring changes by snapshot date.
- `output/discovered_pages.csv` - generated career page inventory for later manual/API review.
- `output/failed_companies.csv` - generated non-success company summary.
- `client/` - static React dashboard for reviewing the scraped CSV output.
- `tests/` - pytest coverage for URL handling, parsing, logging, and request failures.
- `.github/workflows/tests.yml` - GitHub Actions workflow that runs syntax checks and pytest.
- `.github/workflows/deploy-client.yml` - GitHub Pages deployment workflow for the React dashboard.
- `.github/workflows/daily-scrape.yml` - daily/manual scraper refresh that updates the dashboard CSV and deploys GitHub Pages.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

To crawl the included company CSV:

```bash
python crawl_jobs.py --input data/companies.csv --output jobs_out.csv --log crawl_log.csv
```

The crawler uses a shared `requests.Session`, polite headers, configurable timeouts, and retry/backoff settings:

```bash
python crawl_jobs.py --timeout 15 --retries 2 --backoff 0.5
```

If a known careers URL fails, the crawler now tries fallback discovery before marking the company failed:

- retries the known URL with polite headers and redirects enabled
- tries common paths such as `/careers`, `/jobs`, `/join-us`, and `/open-positions`
- scans the company homepage for career-like links
- detects external ATS/job boards such as Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Breezy, Recruitee, JazzHR, iCIMS, Jobvite, ADP, UKG, and BambooHR
- limits discovery to the homepage, careers-like links, and known ATS links

For a quick smoke test:

```bash
python crawl_jobs.py --limit 5
```

The `--limit` flag is only for testing the crawler path. It will produce a partial `jobs_out.csv` with only the first companies in `data/companies.csv`.

To only discover career pages:

```bash
python discover_jobs_pages.py --input data/companies.csv --output output/companies_with_careers.csv --log output/discovery_log.csv
```

## Frontend Dashboard

The `client/` app is a static React + Vite dashboard for reviewing NY Space Jobs from a committed CSV snapshot.

To refresh the dashboard data after a crawl:

```bash
python crawl_jobs.py --input data/companies.csv --output jobs_out.csv --log crawl_log.csv
python update_snapshots.py --jobs jobs_out.csv --snapshot-date "$(date +%F)"
```

To run it locally:

```bash
cd client
npm install
npm run dev
```

To build the GitHub Pages version:

```bash
cd client
npm run build
```

The dashboard reads `client/public/data/jobs_out.csv`, shows stats, client-side search, filters, and clickable apply links. It is frontend-only: no Streamlit, backend, or MySQL connection is used.

## Daily Refresh

GitHub Actions runs `.github/workflows/daily-scrape.yml` once per day at 6:00 AM New York time and can also be started manually from the Actions tab. The workflow schedules both `0 10 * * *` and `0 11 * * *` UTC, then uses `America/New_York` time inside the job so daylight saving time still lands on the 6:00 AM run.

The workflow installs Python dependencies, runs the scraper, writes `client/public/data/jobs_out.csv`, stores `data/snapshots/jobs_YYYY-MM-DD.csv`, updates `data/analytics/*.csv`, commits changed data back to `main` with `Daily jobs snapshot update`, builds the Vite app, and deploys GitHub Pages.

## Test

```bash
pytest
python -m compileall .
```

## Output Columns

`jobs_out.csv` includes:

- `job_id`
- `snapshot_date`
- `company_id`
- `company_name`
- `company_website`
- `careers_url`
- `job_title`
- `job_url`
- `location`
- `city`
- `state`
- `country`
- `remote`
- `salary_min`
- `salary_max`
- `department`
- `category`
- `date_found`
- `last_seen_at`
- `source_url`
- `discovery_method`
- `status`

When a posting does not publish a job-specific location, the crawler falls back to the company city from `data/companies.csv` and maps it as `City, NY, United States`. Salary fields are populated only when the source HTML or structured job data exposes compensation.

`job_id` is generated from normalized `company_name`, `job_title`, and normalized `job_url`. If `job_url` is missing, it falls back to normalized `company_name`, `job_title`, and `location`. `snapshot_date` is the scraper run date used for historical comparisons.

If no job listings are found for a company, the crawler writes a row with `status` such as `no_jobs_found`, `careers_page_not_found`, `js_rendered_or_unsupported`, `invalid_url`, `request_failed`, `timeout`, `non_html_response`, `parse_error`, `careers_url_failed`, or `fallback_url_failed`.

Standard statuses include `success`, `success_after_fallback`, `careers_url_failed`, `fallback_url_found`, `fallback_url_failed`, `ats_detected`, `no_jobs_found`, `careers_page_found`, `careers_page_not_found`, `invalid_url`, `timeout`, `request_failed`, `parse_error`, `non_html_response`, `js_rendered_or_unsupported`, `duplicate_skipped`, `redirect_detected`, `blocked`, and `unsupported_structure`.

`crawl_log.csv` includes `company_name`, `attempted_url`, `attempt_type`, `status_code`, `scraper_status`, `error_message`, and `timestamp`. One failed request or company is logged and does not stop the full crawl.

`output/discovered_pages.csv` includes `company_name`, `company_website`, `discovered_url`, `discovery_method`, `confidence_score`, and `timestamp`.

JavaScript-heavy pages are not rendered with browser automation. They are marked `js_rendered_or_unsupported` and preserved in the CSV outputs for later manual/API review.
