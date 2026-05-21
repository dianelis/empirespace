import Papa from "papaparse";
import type { Job } from "../types";

type RawRow = Record<string, string | undefined>;

const value = (row: RawRow, keys: string[]) => {
  for (const key of keys) {
    const found = (row[key] ?? "").trim();
    if (found) return found;
  }
  return "";
};

const hasColumn = (row: RawRow, keys: string[]) =>
  keys.some((key) => Object.prototype.hasOwnProperty.call(row, key));

const titleCase = (text: string) =>
  text
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");

const inferRemote = (row: RawRow, location: string) => {
  const remote = value(row, ["remote_status", "remote", "remoteStatus"]);
  if (remote) return titleCase(remote);
  return /remote/i.test(location) ? "Remote" : "Not specified";
};

const locationParts = (location: string) => {
  const parts = location
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);

  return {
    city: parts[0] ?? "",
    state: parts[1] ?? "",
    country: parts[2] ?? "",
  };
};

const formatSalary = (rawValue: string) => {
  const value = rawValue.trim();
  if (!value) return "";
  if (!/^\d+(?:\.\d+)?$/.test(value)) return value;

  const amount = Number(value);
  if (!Number.isFinite(amount)) return value;

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: amount % 1 === 0 ? 0 : 2,
  }).format(amount);
};

const normalizeRow = (row: RawRow, index: number): Job | null => {
  const company = value(row, ["company_name", "organization_name", "company"]);
  const title = value(row, ["job_title", "title"]);
  const applyUrl = value(row, ["job_url", "apply_url", "canonical_job_url", "source_job_url"]);
  const location = value(row, ["location", "location_text"]);
  const parts = locationParts(location);
  const hasStructuredLocation =
    hasColumn(row, ["location_city", "city"]) ||
    hasColumn(row, ["location_state", "state"]) ||
    hasColumn(row, ["location_country", "country"]);
  const status = value(row, ["status", "detail_fetch_status"]);

  if (!title) return null;

  return {
    id: value(row, ["job_id"]) || `${company}-${title}-${index}`,
    company,
    category: value(row, ["category", "company_category"]),
    title,
    location,
    city: value(row, ["location_city", "city"]) || (hasStructuredLocation ? "" : parts.city),
    state: value(row, ["location_state", "state"]) || (hasStructuredLocation ? "" : parts.state),
    country: value(row, ["location_country", "country"]) || (hasStructuredLocation ? "" : parts.country),
    remote: inferRemote(row, location),
    salaryMin: formatSalary(value(row, ["salary_min", "salaryMin"])),
    salaryMax: formatSalary(value(row, ["salary_max", "salaryMax"])),
    lastSeenAt: value(row, ["last_seen_at", "date_found", "found_at"]),
    applyUrl,
    status,
  };
};

export const parseJobsCsv = (csv: string): Job[] =>
  Papa.parse<RawRow>(csv, {
    header: true,
    skipEmptyLines: true,
  })
    .data.map(normalizeRow)
    .filter((job): job is Job => Boolean(job));

export const loadJobs = async (): Promise<Job[]> => {
  const response = await fetch(`${import.meta.env.BASE_URL}data/jobs_out.csv`, {
    cache: "no-cache",
  });

  if (!response.ok) {
    throw new Error(`Unable to load jobs CSV (${response.status})`);
  }

  return parseJobsCsv(await response.text());
};
