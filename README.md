# empirespace

Simple command-line job scraping workflow for Empire Space company career pages.

The scraper uses only `requests` and `BeautifulSoup4` for web scraping. It does not use Streamlit, Playwright, Selenium, or browser automation.

## Files

- `data/companies.csv` - input company data copied from the existing workspace CSV.
- `discover_jobs_pages.py` - optional helper script that finds career/job pages and writes an enriched company CSV.
- `crawl_jobs.py` - main CLI crawler that writes job rows for later MySQL ingestion.
- `jobs_out.csv` - generated job results.
- `crawl_log.csv` - generated request/status log.
- `tests/` - pytest coverage for URL handling, parsing, logging, and request failures.
- `.github/workflows/tests.yml` - GitHub Actions workflow that runs syntax checks and pytest.

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

For a quick smoke test:

```bash
python crawl_jobs.py --limit 5
```

To only discover career pages:

```bash
python discover_jobs_pages.py --input data/companies.csv --output output/companies_with_careers.csv --log output/discovery_log.csv
```

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

If no job listings are found for a company, the crawler writes a row with `status` such as `no_jobs_found`, `no_careers_page_found`, `unsupported_source`, `invalid_url`, `request_failed`, `timeout`, `non_html_response`, or `parse_error`.

`crawl_log.csv` includes the company, URL checked, request status, HTTP status, jobs found on that URL, and any error message. One failed request or company is logged and does not stop the full crawl.
