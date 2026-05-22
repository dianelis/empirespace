from pathlib import Path

from crawl_jobs import (
    KNOWN_COUNTRIES,
    OUTPUT_FIELDS,
    STATE_CODES,
    dedupe_jobs,
    extract_jobs_from_html,
    extract_salary_range,
    is_known_country,
    parse_location_fields,
    normalize_state,
    write_csv,
    sanitize_job_title,
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
        {"job_title": "Test Engineer", "job_url": "", "location": "Remote"},
        {"job_title": "Test Engineer", "job_url": "", "location": "Remote"},
    ]
    deduped = dedupe_jobs(rows)
    assert [row["job_url"] for row in deduped] == [
        "https://example.com/jobs/1",
        "https://example.com/jobs/2",
        "https://example.com/jobs/3",
        "",
    ]


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
            "job_confidence_score": "3",
            "status": "found",
        }
    ]


def test_rejects_generic_company_pages_as_jobs():
    html = """
    <nav>
      <a href="/about">About</a>
      <a href="/team">Team</a>
      <a href="/contact">Contact</a>
      <a href="/careers">Careers</a>
      <a href="/careers/open-positions">Open Positions</a>
      <a href="/news/aerospace-product-launch">Aerospace Product Launch</a>
      <a href="/products/orbital-platform">Product</a>
      <a href="/apply">Apply</a>
    </nav>
    """
    rejected = []
    jobs = extract_jobs_from_html(html, "https://example.com/careers", rejected_candidates=rejected)
    rejected_titles = {row["candidate_title"].lower() for row in rejected}
    rejected_urls = {row["candidate_url"] for row in rejected}

    assert jobs == []
    assert "about" in rejected_titles
    assert "team" in rejected_titles
    assert "contact" in rejected_titles
    assert "careers" in rejected_titles
    assert "open positions" in rejected_titles
    assert "aerospace product launch" in rejected_titles
    assert "product" in rejected_titles
    assert any(url.endswith("/apply") for url in rejected_urls)


def test_accepts_valid_job_cards_and_ats_links():
    html = """
    <section class="jobs">
      <article class="job-card">
        <a href="/jobs/software-engineer">Software Engineer</a>
        <span>Location: Brooklyn, NY</span>
        <span>Apply now</span>
      </article>
      <article class="job-card">
        <a href="/openings/mechanical-engineer">Mechanical Engineer</a>
        <span>Requirements: propulsion systems</span>
      </article>
      <article class="opening">
        <a href="https://boards.greenhouse.io/example/jobs/123">Avionics Engineer</a>
      </article>
      <article class="posting">
        <a href="https://jobs.lever.co/example/jobs/abc">Operations Manager</a>
      </article>
    </section>
    """
    jobs = extract_jobs_from_html(html, "https://example.com/careers")
    titles = {job["job_title"] for job in jobs}

    assert "Software Engineer" in titles
    assert "Mechanical Engineer" in titles
    assert "Avionics Engineer" in titles
    assert "Operations Manager" in titles
    assert all(int(job["job_confidence_score"]) >= 3 for job in jobs)


def test_jsonld_jobposting_and_apply_card_are_valid():
    html = """
    <script type="application/ld+json">
      {
        "@type": "JobPosting",
        "title": "Aerospace Scientist",
        "url": "https://example.com/jobs/aerospace-scientist",
        "jobLocation": {"address": {"addressLocality": "Rochester", "addressRegion": "NY"}}
      }
    </script>
    <article class="role-card">
      <h2>Electrical Technician</h2>
      <p>Location: Buffalo, NY</p>
      <p>Responsibilities include spacecraft test operations.</p>
      <a href="/roles/electrical-technician">Apply</a>
    </article>
    """
    jobs = extract_jobs_from_html(html, "https://example.com/careers")
    titles = {job["job_title"] for job in jobs}

    assert "Aerospace Scientist" in titles
    assert "Electrical Technician" in titles


def test_prose_text_is_rejected_as_location_and_falls_back_to_company_city():
    fields = parse_location_fields(
        "Build skills in STEM, leadership, and teamwork before high school graduation.",
        {"location": "Owego"},
    )
    assert fields == {
        "location": "Owego, NY, United States",
        "city": "Owego",
        "state": "NY",
        "country": "United States",
    }


def test_category_fragments_are_rejected_as_locations():
    fields = parse_location_fields("Quality, &, Operational, Excellen|New, Grads", {"location": "Greece"})
    assert fields["location"] == "Greece, NY, United States"
    assert fields["city"] == "Greece"
    assert fields["state"] == "NY"
    assert fields["country"] == "United States"


def test_multi_city_location_uses_first_valid_city_state_pair():
    fields = parse_location_fields("Greenville, Texas, Plano, Texas, Rockwall, Texas")
    assert fields["location"] == "Greenville, Texas, Plano, Texas, Rockwall, Texas"
    assert fields["city"] == "Greenville"
    assert fields["state"] == "TX"
    assert fields["country"] == "United States"


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


def test_broad_opportunity_pages_are_rejected_as_jobs():
    html = """
    <article class="job-card">
      <a href="/careers/candidates/students-early-careers/high-school.html">
        High School Internship Opportunities
      </a>
      <p>Build skills in STEM, leadership, and teamwork before high school graduation.</p>
      <p>Apply now</p>
    </article>
    """
    rejected = []
    jobs = extract_jobs_from_html(html, "https://example.com/careers", rejected_candidates=rejected)

    assert jobs == []
    assert rejected
    assert rejected[0]["rejection_reason"] == "broad_opportunity_page"


def test_polluted_titles_fall_back_to_job_url_slug():
    assert (
        sanitize_job_title(
            "Spec, Configuration Management 1 Engineering, Services Greenville, TX",
            "https://careers.example.com/job/greenville/spec-configuration-management-1/12345",
        )
        == "Spec Configuration Management"
    )
    assert (
        sanitize_job_title(
            "Senior Associate, Quality Engineering Quality, &, Operational, Excellen|New, Grads Cincinnati, OH",
            "https://careers.example.com/job/cincinnati/senior-associate-quality-engineering/12345",
        )
        == "Senior Associate Quality Engineering"
    )


def test_salary_range_extraction():
    assert extract_salary_range("Salary range: $80,000 - $120,000") == ("80000", "120000")
    assert extract_salary_range("Compensation: $90k to $110k") == ("90000", "110000")
    assert extract_salary_range("Battery sale price: $19.99") == ("", "")


def test_csv_output_headers(tmp_path):
    output = tmp_path / "jobs_out.csv"
    write_csv(output, [], OUTPUT_FIELDS)
    assert output.read_text(encoding="utf-8").splitlines()[0] == ",".join(OUTPUT_FIELDS)


def test_committed_frontend_csv_has_clean_dropdown_fields():
    import csv

    rows = list(csv.DictReader(Path("client/public/data/jobs_out.csv").open(encoding="utf-8")))
    for row in rows:
        for field in ("city", "state", "country"):
            value = row.get(field, "")
            assert "teamwork" not in value.lower()
            assert "graduation" not in value.lower()
            assert "configuration management" not in value.lower()
            assert value != "&"
        title = row.get("job_title", "").lower()
        assert "internship program" not in title
        assert "early talent" not in title
        assert "student programs" not in title
        country = row.get("country", "")
        state = row.get("state", "")
        if country:
            assert is_known_country(country), f"Unexpected country {country!r}"
        if state and country == "United States":
            assert normalize_state(state) in STATE_CODES
        if country and country != "United States":
            assert country in KNOWN_COUNTRIES
