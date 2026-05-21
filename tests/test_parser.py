from pathlib import Path

from crawl_jobs import (
    OUTPUT_FIELDS,
    dedupe_jobs,
    extract_jobs_from_html,
    extract_salary_range,
    parse_location_fields,
    write_csv,
)


FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_successful_job_extraction_from_sample_html():
    jobs = extract_jobs_from_html(read_fixture("sample_careers_page.html"), "https://example.com/careers")

    titles = {job["job_title"] for job in jobs}
    assert "Payload Systems Engineer" in titles
    assert "Software Engineer" in titles
    assert "Guidance Navigation Engineer" in titles

    software_job = next(job for job in jobs if job["job_title"] == "Software Engineer")
    assert software_job["job_url"] == "https://example.com/careers/software-engineer"
    assert software_job["location"] == "New York, NY"
    assert software_job["department"] == "Flight Software"


def test_relative_urls_become_absolute_urls():
    jobs = extract_jobs_from_html(read_fixture("sample_careers_page.html"), "https://example.com/careers")
    assert any(job["job_url"] == "https://example.com/careers/software-engineer" for job in jobs)


def test_deduplication_removes_duplicate_urls_and_titles():
    rows = [
        {"job_title": "Software Engineer", "job_url": "https://example.com/jobs/1", "location": "NY"},
        {"job_title": "Software Engineer", "job_url": "https://example.com/jobs/1?utm_source=x", "location": "NY"},
        {"job_title": "Software Engineer", "job_url": "https://example.com/jobs/2", "location": "NY"},
        {"job_title": "Test Engineer", "job_url": "https://example.com/jobs/3", "location": "Remote"},
    ]
    deduped = dedupe_jobs(rows)
    assert [row["job_title"] for row in deduped] == ["Software Engineer", "Test Engineer"]


def test_empty_html_returns_no_jobs():
    assert extract_jobs_from_html(read_fixture("empty_page.html"), "https://example.com/careers") == []


def test_malformed_html_does_not_crash():
    jobs = extract_jobs_from_html(read_fixture("malformed_page.html"), "https://example.com/careers")
    assert jobs[0]["job_title"] == "Test Engineer"
    assert jobs[0]["job_url"] == "https://example.com/jobs/test-engineer"


def test_missing_optional_fields_are_blank_or_filled_safely():
    html = """
    <script type="application/ld+json">
      {"@type": "JobPosting", "title": "Développeur Engineer"}
    </script>
    """
    jobs = extract_jobs_from_html(html, "https://example.com/careers")
    assert jobs == [
        {
            "job_title": "Développeur Engineer",
            "job_url": "https://example.com/careers",
            "location": "",
            "remote": "Not specified",
            "salary_min": "",
            "salary_max": "",
            "department": "",
            "source_url": "https://example.com/careers",
            "status": "found",
        }
    ]


def test_location_fields_are_parsed_from_job_location():
    fields = parse_location_fields("Endicott, New York, United States")
    assert fields["city"] == "Endicott"
    assert fields["state"] == "NY"
    assert fields["country"] == "United States"


def test_company_location_falls_back_to_new_york():
    fields = parse_location_fields("", {"location": "Brooklyn"})
    assert fields["location"] == "Brooklyn, NY, United States"
    assert fields["city"] == "Brooklyn"
    assert fields["state"] == "NY"
    assert fields["country"] == "United States"


def test_salary_range_extraction():
    assert extract_salary_range("Salary range: $80,000 - $120,000") == ("80000", "120000")
    assert extract_salary_range("Compensation: $90k to $110k") == ("90000", "110000")
    assert extract_salary_range("Battery sale price: $19.99") == ("", "")


def test_csv_output_headers(tmp_path):
    output = tmp_path / "jobs_out.csv"
    write_csv(output, [], OUTPUT_FIELDS)
    assert output.read_text(encoding="utf-8").splitlines()[0] == ",".join(OUTPUT_FIELDS)
