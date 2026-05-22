/// <reference types="cypress" />

const csvRoute = "**/data/jobs_out.csv";
const header = [
  "job_id",
  "snapshot_date",
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
  "last_seen_at",
  "status",
];

type CsvRow = Partial<Record<(typeof header)[number], string>>;

const escapeCsv = (value: string) => {
  if (/[",\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
};

const buildCsv = (rows: CsvRow[]) => [
  header.join(","),
  ...rows.map((row) => header.map((field) => escapeCsv(row[field] ?? "")).join(",")),
].join("\n");

const visitWithCsv = (csv: string) => {
  const consoleErrors: string[] = [];

  cy.intercept("GET", csvRoute, {
    statusCode: 200,
    headers: { "content-type": "text/csv; charset=utf-8" },
    body: csv,
  }).as("jobsCsv");
  cy.on("window:before:load", (win) => {
    cy.stub(win.console, "error").callsFake((...args) => {
      consoleErrors.push(args.map(String).join(" "));
    });
  });

  cy.visit("/");
  cy.wait("@jobsCsv");
  cy.contains("h1", "NY Space Jobs").should("be.visible");

  return () => {
    cy.wrap(null).then(() => {
      expect(consoleErrors, "visible console errors").to.deep.equal([]);
    });
  };
};

const selectFilterButton = (label: string) => {
  cy.contains("span", new RegExp(`^${label}$`, "i"))
    .parents("label")
    .find("button")
    .click();
};

describe("CSV data quality handling", () => {
  it("handles an empty CSV", () => {
    const assertNoConsoleErrors = visitWithCsv(buildCsv([]));

    cy.contains("Showing 0 of 0 roles").should("be.visible");
    cy.contains("No matching jobs").should("be.visible");
    assertNoConsoleErrors();
  });

  it("handles missing company, location, and removed salary fields", () => {
    const assertNoConsoleErrors = visitWithCsv(
      buildCsv([
        {
          job_id: "missing-fields",
          job_title: "Systems Engineer",
          job_url: "https://example.org/jobs/systems-engineer",
          category: "Space & Defense",
          last_seen_at: "2026-05-22",
          status: "success",
        },
        {
          job_id: "missing-title",
          company_name: "Skipped Title Co",
          job_url: "https://example.org/jobs/missing-title",
          status: "success",
        },
      ]),
    );

    cy.contains("Showing 1 of 1 roles").should("be.visible");
    cy.contains("Systems Engineer").should("be.visible");
    cy.contains("Skipped Title Co").should("not.exist");
    cy.contains("th", "Salary Min").should("not.exist");
    cy.contains("th", "Salary Max").should("not.exist");
    assertNoConsoleErrors();
  });

  it("deduplicates duplicate CSV rows", () => {
    const duplicate = {
      company_name: "Duplicate Space",
      job_title: "Software Engineer",
      job_url: "https://duplicate.example/jobs/software-engineer",
      location: "Brooklyn, NY, United States",
      category: "Core Space",
      last_seen_at: "2026-05-22",
      status: "success",
    };
    const assertNoConsoleErrors = visitWithCsv(
      buildCsv([
        { ...duplicate, job_id: "duplicate-a" },
        { ...duplicate, job_id: "duplicate-b" },
      ]),
    );

    cy.contains("Showing 1 of 1 roles").should("be.visible");
    cy.contains("Software Engineer").should("be.visible");
    assertNoConsoleErrors();
  });

  it("drops invalid apply links without crashing", () => {
    const assertNoConsoleErrors = visitWithCsv(
      buildCsv([
        {
          job_id: "invalid-link",
          company_name: "Unsafe Links Inc",
          job_title: "Mechanical Engineer",
          job_url: "javascript:alert(1)",
          location: "Buffalo, NY, United States",
          status: "success",
        },
        {
          job_id: "valid-link",
          company_name: "Safe Links Inc",
          job_title: "Avionics Technician",
          job_url: "https://safe.example/jobs/avionics-technician",
          location: "Rochester, NY, United States",
          status: "success",
        },
      ]),
    );

    cy.contains("Mechanical Engineer").should("be.visible");
    cy.contains("Avionics Technician").should("be.visible");
    cy.get("a")
      .contains("Apply")
      .should("have.attr", "href")
      .and("eq", "https://safe.example/jobs/avionics-technician");
    cy.get("a[href^='javascript:']").should("not.exist");
    assertNoConsoleErrors();
  });

  it("handles malformed CSV rows without crashing", () => {
    const malformedCsv = `${header.join(",")}\n"unclosed,row,that,does,not,match\nvalid,2026-05-22,Recovery Co,,,Recovery Engineer,https://recovery.example/jobs/recovery-engineer,"Recovery, NY, United States",Recovery,NY,United States,Not specified,,,,Aerospace,2026-05-22,success`;
    const assertNoConsoleErrors = visitWithCsv(malformedCsv);

    cy.contains("NY Space Jobs").should("be.visible");
    cy.get("main").should("be.visible");
    assertNoConsoleErrors();
  });

  it("handles very long company names and job titles", () => {
    const longCompany = `Very Long Space Company ${"Orbital ".repeat(18)}`.trim();
    const longTitle = `Principal ${"Aerospace Systems ".repeat(10)}Engineer`.trim();
    const assertNoConsoleErrors = visitWithCsv(
      buildCsv([
        {
          job_id: "long-copy",
          company_name: longCompany,
          job_title: longTitle,
          job_url: "https://long.example/jobs/principal-aerospace-systems-engineer",
          location: "New York, NY, United States",
          category: "Aerospace",
          last_seen_at: "2026-05-22",
          status: "success",
        },
      ]),
    );

    cy.contains("Showing 1 of 1 roles").should("be.visible");
    cy.contains("Very Long Space Company").should("be.visible");
    cy.contains("Principal Aerospace Systems").should("be.visible");
    assertNoConsoleErrors();
  });

  it("keeps non-US state values out of the state dropdown", () => {
    const assertNoConsoleErrors = visitWithCsv(
      buildCsv([
        {
          job_id: "us-state",
          company_name: "Empire Orbit",
          job_title: "Aerospace Engineer",
          job_url: "https://empire.example/jobs/aerospace-engineer",
          location: "Buffalo, NY, United States",
          city: "Buffalo",
          state: "NY",
          country: "United States",
          last_seen_at: "2026-05-22",
          status: "success",
        },
        {
          job_id: "non-us-state",
          company_name: "International Orbit",
          job_title: "Propulsion Engineer",
          job_url: "https://international.example/jobs/propulsion-engineer",
          location: "London, England, United Kingdom",
          city: "London",
          state: "England",
          country: "United Kingdom",
          last_seen_at: "2026-05-22",
          status: "success",
        },
      ]),
    );

    selectFilterButton("State");
    cy.get("[role='option']").contains("NY").should("be.visible");
    cy.get("[role='option']").should("not.contain", "England");
    assertNoConsoleErrors();
  });
});
