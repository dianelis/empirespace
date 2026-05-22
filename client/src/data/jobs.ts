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

const stateNames: Record<string, string> = {
  alabama: "AL",
  alaska: "AK",
  arizona: "AZ",
  arkansas: "AR",
  california: "CA",
  colorado: "CO",
  connecticut: "CT",
  delaware: "DE",
  "district of columbia": "DC",
  florida: "FL",
  georgia: "GA",
  hawaii: "HI",
  idaho: "ID",
  illinois: "IL",
  indiana: "IN",
  iowa: "IA",
  kansas: "KS",
  kentucky: "KY",
  louisiana: "LA",
  maine: "ME",
  maryland: "MD",
  massachusetts: "MA",
  michigan: "MI",
  minnesota: "MN",
  mississippi: "MS",
  missouri: "MO",
  montana: "MT",
  nebraska: "NE",
  nevada: "NV",
  "new hampshire": "NH",
  "new jersey": "NJ",
  "new mexico": "NM",
  "new york": "NY",
  "north carolina": "NC",
  "north dakota": "ND",
  ohio: "OH",
  oklahoma: "OK",
  oregon: "OR",
  pennsylvania: "PA",
  "rhode island": "RI",
  "south carolina": "SC",
  "south dakota": "SD",
  tennessee: "TN",
  texas: "TX",
  utah: "UT",
  vermont: "VT",
  virginia: "VA",
  washington: "WA",
  "west virginia": "WV",
  wisconsin: "WI",
  wyoming: "WY",
};

const stateCodes = new Set(Object.values(stateNames));

const countryAliases: Record<string, string> = {
  us: "United States",
  usa: "United States",
  "u.s.": "United States",
  "u.s.a.": "United States",
  "united states": "United States",
  "united states of america": "United States",
  uk: "United Kingdom",
  "u.k.": "United Kingdom",
  uae: "United Arab Emirates",
  "u.a.e.": "United Arab Emirates",
};

const knownCountries = new Set([
  "Australia",
  "Austria",
  "Belgium",
  "Brazil",
  "Canada",
  "China",
  "Denmark",
  "Finland",
  "France",
  "Germany",
  "India",
  "Ireland",
  "Israel",
  "Italy",
  "Japan",
  "Mexico",
  "Netherlands",
  "Norway",
  "Poland",
  "Singapore",
  "South Korea",
  "Spain",
  "Sweden",
  "Switzerland",
  "United Arab Emirates",
  "United Kingdom",
  "United States",
]);

const proseLocationPattern =
  /\b(build skills|teamwork|graduation|responsibilities|requirements|qualifications|benefits|compensation|salary|department|category|function|operational|excellence|learn more|apply now|view details)\b/i;

const jobWordPattern =
  /\b(engineer|engineering|developer|designer|manager|director|analyst|scientist|technician|operator|specialist|associate|coordinator|administrator|architect|assistant|consultant|lead|leader|intern|internship|management|recruiter|sales|operations|product|software|mechanical|electrical|aerospace|propulsion|avionics)\b/i;

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

const normalizeCountry = (rawValue: string) => {
  const cleaned = rawValue.trim();
  const aliased = countryAliases[cleaned.toLowerCase()] ?? cleaned;
  return Array.from(knownCountries).find((country) => country.toLowerCase() === aliased.toLowerCase()) ?? aliased;
};

const isKnownCountry = (rawValue: string) => knownCountries.has(normalizeCountry(rawValue));

const normalizeState = (rawValue: string) => {
  const cleaned = rawValue.trim();
  const upper = cleaned.toUpperCase();
  if (stateCodes.has(upper)) return upper;
  return stateNames[cleaned.toLowerCase()] ?? cleaned;
};

const isState = (rawValue: string) => stateCodes.has(normalizeState(rawValue));

const isRemoteLocation = (rawValue: string) =>
  /^(remote|hybrid|on-site|onsite|remote\s*-\s*(?:us|u\.s\.|united states))$/i.test(rawValue.trim());

const looksLikePlace = (rawValue: string) => {
  const cleaned = rawValue.trim();
  if (!cleaned || cleaned.length > 60) return false;
  if (proseLocationPattern.test(cleaned)) return false;
  if (jobWordPattern.test(cleaned)) return false;
  if (/[|&]/.test(cleaned)) return false;
  if (/\d/.test(cleaned)) return false;
  if ((cleaned.endsWith(".") && cleaned.split(/\s+/).length > 3) || (cleaned.match(/\./g)?.length ?? 0) > 1) return false;
  if (cleaned.split(/\s+/).length > 6) return false;
  return /[a-z]/i.test(cleaned);
};

const emptyLocation = (location = "") => ({
  location,
  city: "",
  state: "",
  country: "",
});

const locationParts = (rawLocation: string) => {
  const location = rawLocation.trim();
  if (!location) return emptyLocation();
  if (isRemoteLocation(location)) return emptyLocation(location);
  if (location.length > 160 || proseLocationPattern.test(location)) return emptyLocation();

  const firstLocation = location.split(/[;|]/, 1)[0]?.trim() ?? "";
  const parts = firstLocation
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);

  if (!parts.length) return emptyLocation();
  if (parts.some((part) => !looksLikePlace(part) && !isState(part) && !isKnownCountry(part))) {
    return emptyLocation();
  }

  let city = "";
  let state = "";
  let country = "";

  if (parts.length >= 4 && isState(parts[1]) && isState(parts[3])) {
    city = parts[0];
    state = normalizeState(parts[1]);
    country = "United States";
  } else if (parts.length >= 3 && isKnownCountry(parts[2])) {
    city = parts[0];
    country = normalizeCountry(parts[2]);
    if (isState(parts[1])) {
      state = normalizeState(parts[1]);
    } else if (country !== "United States" && looksLikePlace(parts[1])) {
      state = parts[1];
    } else {
      return emptyLocation();
    }
  } else if (parts.length >= 3 && isState(parts[parts.length - 1])) {
    city = parts[0];
    state = normalizeState(parts[parts.length - 1]);
    country = "United States";
  } else if (parts.length >= 2 && isState(parts[1])) {
    city = parts[0];
    state = normalizeState(parts[1]);
    country = "United States";
  } else if (parts.length >= 2 && isKnownCountry(parts[1])) {
    city = parts[0];
    country = normalizeCountry(parts[1]);
  } else if (isKnownCountry(parts[0])) {
    country = normalizeCountry(parts[0]);
  } else if (parts.length === 1 && isKnownCountry(parts[0])) {
    country = normalizeCountry(parts[0]);
  } else {
    return emptyLocation();
  }

  if (city && !looksLikePlace(city)) return emptyLocation();
  if (country === "United States" && state && !stateCodes.has(state)) return emptyLocation();
  if (country && !isKnownCountry(country)) return emptyLocation();

  return {
    location,
    city,
    state,
    country,
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

const normalizeApplyUrl = (rawValue: string) => {
  const value = rawValue.trim();
  if (!value) return "";

  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
  } catch {
    return "";
  }
};

const jobDedupeKey = (job: Job) =>
  job.applyUrl ||
  [
    job.company.trim().toLowerCase(),
    job.title.trim().toLowerCase(),
    job.location.trim().toLowerCase(),
  ].join("|");

const dedupeJobs = (jobs: Job[]) => {
  const seen = new Set<string>();
  const deduped: Job[] = [];

  for (const job of jobs) {
    const key = jobDedupeKey(job);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    deduped.push(job);
  }

  return deduped;
};

const normalizeRow = (row: RawRow, index: number): Job | null => {
  const company = value(row, ["company_name", "organization_name", "company"]);
  const title = value(row, ["job_title", "title"]);
  const applyUrl = normalizeApplyUrl(value(row, ["job_url", "apply_url", "canonical_job_url", "source_job_url"]));
  const rawLocation = value(row, ["location", "location_text"]);
  const parsedLocation = locationParts(rawLocation);
  const structuredLocation = locationParts(
    [
      value(row, ["location_city", "city"]),
      value(row, ["location_state", "state"]),
      value(row, ["location_country", "country"]),
    ]
      .filter(Boolean)
      .join(", "),
  );
  const parts = structuredLocation.location ? structuredLocation : parsedLocation;
  const location = parsedLocation.location || structuredLocation.location;
  const status = value(row, ["status", "detail_fetch_status"]);

  if (!title) return null;

  return {
    id: value(row, ["job_id"]) || `${company}-${title}-${index}`,
    company,
    category: value(row, ["category", "company_category"]),
    title,
    location,
    city: parts.city,
    state: parts.state,
    country: parts.country,
    remote: inferRemote(row, location),
    salaryMin: formatSalary(value(row, ["salary_min", "salaryMin"])),
    salaryMax: formatSalary(value(row, ["salary_max", "salaryMax"])),
    lastSeenAt: value(row, ["snapshot_date", "last_seen_at", "date_found", "found_at"]),
    applyUrl,
    status,
  };
};

export const parseJobsCsv = (csv: string): Job[] =>
  dedupeJobs(
    Papa.parse<RawRow>(csv, {
      header: true,
      skipEmptyLines: true,
    })
      .data.map(normalizeRow)
      .filter((job): job is Job => Boolean(job)),
  );

export const loadJobs = async (): Promise<Job[]> => {
  const response = await fetch(`${import.meta.env.BASE_URL}data/jobs_out.csv`, {
    cache: "no-cache",
  });

  if (!response.ok) {
    throw new Error(`Unable to load jobs CSV (${response.status})`);
  }

  return parseJobsCsv(await response.text());
};
