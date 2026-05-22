/// <reference types="cypress" />

const csvRoute = "**/data/jobs_out.csv";

const visitDashboard = () => {
  const consoleErrors: string[] = [];

  cy.intercept("GET", csvRoute, { fixture: "jobs_out.csv" }).as("jobsCsv");
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

const selectFilter = (label: string, option: string) => {
  cy.contains("span", new RegExp(`^${label}$`, "i"))
    .parents("label")
    .find("button")
    .click();
  cy.get("[role='option']").contains(option).click();
};

const assertNoBrokenImages = () => {
  cy.get("body").then(($body) => {
    const images = Array.from($body[0].querySelectorAll("img"));
    for (const image of images) {
      expect((image as HTMLImageElement).naturalWidth, image.getAttribute("src") || "image").to.be.greaterThan(0);
    }
  });
};

describe("NY Space Jobs dashboard", () => {
  it("loads the homepage, stats, and job table", () => {
    const assertNoConsoleErrors = visitDashboard();

    cy.contains("A curated view of space, aerospace, and defense jobs").should("be.visible");
    cy.contains("Total jobs").should("be.visible");
    cy.contains("Companies").should("be.visible");
    cy.get("body").should("not.contain", "Remote jobs");
    cy.contains("Latest seen").should("be.visible");
    cy.contains("Showing 3 of 3 roles").should("be.visible");
    cy.contains("th", "Company").should("be.visible");
    cy.get("thead").should("not.contain", "Remote");
    cy.get("thead").should("not.contain", "Salary Min");
    cy.get("thead").should("not.contain", "Salary Max");
    cy.contains("td", "OrbitWorks").should("be.visible");
    cy.contains("td", "Software Engineer").should("be.visible");
    assertNoBrokenImages();
    assertNoConsoleErrors();
  });

  it("searches by company or job title", () => {
    const assertNoConsoleErrors = visitDashboard();

    cy.get("input[placeholder='Search company or job title']").type("software");
    cy.contains("Showing 1 of 3 roles").should("be.visible");
    cy.contains("Software Engineer").should("be.visible");
    cy.contains("Mechanical Engineer").should("not.exist");
    assertNoConsoleErrors();
  });

  it("filters by category, city, state, and country", () => {
    const assertNoConsoleErrors = visitDashboard();

    selectFilter("Category", "Aerospace");
    cy.contains("Mechanical Engineer").should("be.visible");
    cy.contains("Software Engineer").should("not.exist");

    cy.contains("button", "Reset").click();
    selectFilter("City", "Brooklyn");
    selectFilter("State", "NY");
    selectFilter("Country", "United States");

    cy.contains("Showing 1 of 3 roles").should("be.visible");
    cy.contains("OrbitWorks").should("be.visible");
    cy.contains("Software Engineer").should("be.visible");
    assertNoConsoleErrors();
  });

  it("renders valid apply links", () => {
    const assertNoConsoleErrors = visitDashboard();

    cy.contains("a", "Apply")
      .should("have.attr", "target", "_blank")
      .and("have.attr", "rel")
      .and("include", "noreferrer");
    cy.get("a")
      .contains("Apply")
      .each(($link) => {
        expect($link.attr("href")).to.match(/^https?:\/\//);
      });
    assertNoConsoleErrors();
  });

  it("shows an empty state when no results match", () => {
    const assertNoConsoleErrors = visitDashboard();

    cy.get("input[placeholder='Search company or job title']").type("zzzz no matching jobs");
    cy.contains("Showing 0 of 3 roles").should("be.visible");
    cy.contains("No matching jobs").should("be.visible");
    assertNoConsoleErrors();
  });

  it("keeps the mobile layout inside the viewport", () => {
    const assertNoConsoleErrors = visitDashboard();

    cy.viewport("iphone-6");
    cy.contains("NY Space Jobs").should("be.visible");
    cy.get("input[placeholder='Search company or job title']").should("be.visible");
    cy.window().then((win) => {
      expect(win.document.documentElement.scrollWidth).to.be.at.most(win.innerWidth + 1);
    });
    assertNoConsoleErrors();
  });
});
