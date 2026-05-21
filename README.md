# empirespace

Simple command-line job scraping workflow for Empire Space company career pages.

The scraper uses only `requests` and `BeautifulSoup4` for web scraping. It does not use Streamlit, Playwright, Selenium, or browser automation.

## Files

- `data/companies.csv` - input company data copied from the existing workspace CSV.
- `discover_jobs_pages.py` - optional helper script that finds career/job pages and writes an enriched company CSV.
- `crawl_jobs.py` - main CLI crawler that writes job rows for later MySQL ingestion.
- `jobs_out.csv` - generated job results.
- `crawl_log.csv` - generated request/status log.
- `output/discovered_pages.csv` - generated career page inventory for later manual/API review.
- `output/failed_companies.csv` - generated non-success company summary.
- `client/` - static React dashboard for reviewing the scraped CSV output.
- `tests/` - pytest coverage for URL handling, parsing, logging, and request failures.
- `.github/workflows/tests.yml` - GitHub Actions workflow that runs syntax checks and pytest.
- `.github/workflows/deploy-client.yml` - GitHub Pages deployment workflow for the React dashboard.

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

For a quick smoke test:

```bash
python crawl_jobs.py --limit 5
```

To only discover career pages:

```bash
python discover_jobs_pages.py --input data/companies.csv --output output/companies_with_careers.csv --log output/discovery_log.csv
```

## Frontend Dashboard

The `client/` app is a static React + Vite dashboard for reviewing NY Space Jobs from a committed CSV snapshot.

To refresh the dashboard data after a crawl:

```bash
cp jobs_out.csv client/src/data/jobs_out.csv
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

The dashboard reads `client/src/data/jobs_out.csv`, shows stats, client-side search, filters, and clickable apply links. It is frontend-only: no Streamlit, backend, or MySQL connection is used.

## Test

```bash
pytest
python -m compileall .
```

## Output Columns

`jobs_out.csv` includes:

- `company_id`
- `company_name`
- `company_website`
- `careers_url`
- `job_title`
- `job_url`
- `location`
- `department`
- `category`
- `date_found`
- `source_url`
- `status`

If no job listings are found for a company, the crawler writes a row with `status` such as `no_jobs_found`, `careers_page_not_found`, `js_rendered_or_unsupported`, `invalid_url`, `request_failed`, `timeout`, `non_html_response`, or `parse_error`.

Standard statuses include `success`, `no_jobs_found`, `careers_page_found`, `careers_page_not_found`, `invalid_url`, `timeout`, `request_failed`, `parse_error`, `non_html_response`, `js_rendered_or_unsupported`, `duplicate_skipped`, `redirect_detected`, `blocked`, and `unsupported_structure`.

`crawl_log.csv` includes the company, URL checked, request status, HTTP status, jobs found on that URL, and any error message. One failed request or company is logged and does not stop the full crawl.

JavaScript-heavy pages are not rendered with browser automation. They are marked `js_rendered_or_unsupported` and preserved in the CSV outputs for later manual/API review.
