/// <reference types="cypress" />

const csvRoute = "**/data/jobs_out.csv";

const visitDashboard = () => {
  cy.intercept("GET", csvRoute, { fixture: "jobs_out.csv" }).as("jobsCsv");
  cy.visit("/");
  cy.wait("@jobsCsv");
  cy.contains("h1", "NY Space Jobs").should("be.visible");
};

describe("NY Space Jobs visual QA", () => {
  it("captures the desktop homepage", () => {
    cy.viewport(1440, 1000);
    visitDashboard();
    cy.screenshot("desktop-homepage", { capture: "viewport" });
  });

  it("captures the mobile homepage", () => {
    cy.viewport("iphone-6");
    visitDashboard();
    cy.screenshot("mobile-homepage", { capture: "viewport" });
  });

  it("captures a filtered results view", () => {
    cy.viewport(1440, 900);
    visitDashboard();
    cy.get("input[placeholder='Search company or job title']").type("Software");
    cy.contains("Showing 1 of 3 roles").should("be.visible");
    cy.screenshot("filtered-results-view", { capture: "viewport" });
  });

  it("captures the empty state", () => {
    cy.viewport(1440, 900);
    visitDashboard();
    cy.get("input[placeholder='Search company or job title']").type("no results for this search");
    cy.contains("No matching jobs").should("be.visible");
    cy.screenshot("empty-state", { capture: "viewport" });
  });

  it("captures the job table with data", () => {
    cy.viewport(1440, 900);
    visitDashboard();
    cy.contains("td", "Software Engineer").should("be.visible");
    cy.screenshot("job-table-with-data", { capture: "viewport" });
  });
});
