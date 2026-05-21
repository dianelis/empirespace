import Papa from "papaparse";
import jobsCsv from "./jobs_out.csv?raw";
import type { Job } from "../types";

type RawRow = Record<string, string | undefined>;

const value = (row: RawRow, keys: string[]) => {
  for (const key of keys) {
    const found = (row[key] ?? "").trim();
    if (found) return found;
  }
  return "";
};

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

const normalizeRow = (row: RawRow, index: number): Job | null => {
  const company = value(row, ["company_name", "organization_name", "company"]);
  const title = value(row, ["job_title", "title"]);
  const applyUrl = value(row, ["job_url", "apply_url", "canonical_job_url", "source_job_url"]);
  const location = value(row, ["location", "location_text"]);
  const parts = locationParts(location);
  const status = value(row, ["status", "detail_fetch_status"]);

  if (!title) return null;

  return {
    id: value(row, ["job_id"]) || `${company}-${title}-${index}`,
    company,
    category: value(row, ["category", "company_category"]),
    title,
    location,
    city: value(row, ["location_city", "city"]) || parts.city,
    state: value(row, ["location_state", "state"]) || parts.state,
    country: value(row, ["location_country", "country"]) || parts.country,
    remote: inferRemote(row, location),
    salaryMin: value(row, ["salary_min", "salaryMin"]),
    salaryMax: value(row, ["salary_max", "salaryMax"]),
    lastSeenAt: value(row, ["last_seen_at", "date_found", "found_at"]),
    applyUrl,
    status,
  };
};

export const jobs: Job[] = Papa.parse<RawRow>(jobsCsv, {
  header: true,
  skipEmptyLines: true,
})
  .data.map(normalizeRow)
  .filter((job): job is Job => Boolean(job));
