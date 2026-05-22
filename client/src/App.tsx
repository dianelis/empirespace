import { useEffect, useMemo, useState } from "react";
import { Orbit } from "lucide-react";
import { Filters } from "./components/Filters";
import { JobTable } from "./components/JobTable";
import { StatsCards } from "./components/StatsCards";
import { ALL_FILTER } from "./constants";
import { loadJobs } from "./data/jobs";
import type { FilterOptions, FiltersState, Job } from "./types";

const initialFilters: FiltersState = {
  search: "",
  category: ALL_FILTER,
  city: ALL_FILTER,
  state: ALL_FILTER,
  country: ALL_FILTER,
};

const unique = (values: string[]) =>
  Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b));

const usStateCodes = new Set([
  "AL",
  "AK",
  "AZ",
  "AR",
  "CA",
  "CO",
  "CT",
  "DE",
  "DC",
  "FL",
  "GA",
  "HI",
  "ID",
  "IL",
  "IN",
  "IA",
  "KS",
  "KY",
  "LA",
  "ME",
  "MD",
  "MA",
  "MI",
  "MN",
  "MS",
  "MO",
  "MT",
  "NE",
  "NV",
  "NH",
  "NJ",
  "NM",
  "NY",
  "NC",
  "ND",
  "OH",
  "OK",
  "OR",
  "PA",
  "RI",
  "SC",
  "SD",
  "TN",
  "TX",
  "UT",
  "VT",
  "VA",
  "WA",
  "WV",
  "WI",
  "WY",
]);

const normalizeUsStateCode = (value: string) => {
  const state = value.trim().toUpperCase();
  return usStateCodes.has(state) ? state : "";
};

const matchesFilter = (value: string, filter: string) => filter === ALL_FILTER || value === filter;
const matchesStateFilter = (value: string, filter: string) =>
  filter === ALL_FILTER || normalizeUsStateCode(value) === filter;

function filterJobs(allJobs: Job[], filters: FiltersState) {
  const query = filters.search.trim().toLowerCase();

  return allJobs.filter((job) => {
    const matchesSearch =
      !query ||
      job.company.toLowerCase().includes(query) ||
      job.title.toLowerCase().includes(query);

    return (
      matchesSearch &&
      matchesFilter(job.category, filters.category) &&
      matchesFilter(job.city, filters.city) &&
      matchesStateFilter(job.state, filters.state) &&
      matchesFilter(job.country, filters.country)
    );
  });
}

function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [filters, setFilters] = useState<FiltersState>(initialFilters);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let isMounted = true;

    loadJobs()
      .then((loadedJobs) => {
        if (isMounted) {
          setJobs(loadedJobs);
          setLoadError("");
        }
      })
      .catch((error: Error) => {
        if (isMounted) {
          setLoadError(error.message);
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const options = useMemo<FilterOptions>(
    () => ({
      categories: unique(jobs.map((job) => job.category)),
      cities: unique(jobs.map((job) => job.city)),
      states: unique(jobs.map((job) => normalizeUsStateCode(job.state))),
      countries: unique(jobs.map((job) => job.country)),
    }),
    [jobs],
  );

  const filteredJobs = useMemo(() => filterJobs(jobs, filters), [filters, jobs]);

  return (
    <main className="relative min-h-screen overflow-hidden">
      <div className="starfield" />
      <div className="relative mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-10">
        <header className="flex flex-col gap-4 py-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
              <Orbit className="h-3.5 w-3.5" />
              Empire Space jobs index
            </div>
            <h1 className="text-4xl font-semibold tracking-normal text-foreground sm:text-5xl">
              NY Space Jobs
            </h1>
            <p className="mt-3 max-w-2xl text-base leading-7 text-muted-foreground">
              A curated view of space, aerospace, and defense jobs collected from public career pages.
            </p>
          </div>
          <div className="text-sm text-muted-foreground">
            Showing <span className="font-medium text-foreground">{filteredJobs.length}</span> of{" "}
            <span className="font-medium text-foreground">{jobs.length}</span> roles
          </div>
        </header>

        <StatsCards jobs={jobs} />
        <Filters filters={filters} options={options} onChange={setFilters} />
        {isLoading && (
          <div className="rounded-lg border border-border bg-card/80 px-5 py-4 text-sm text-muted-foreground">
            Loading jobs data...
          </div>
        )}
        {loadError && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-5 py-4 text-sm text-destructive">
            {loadError}
          </div>
        )}
        <JobTable jobs={filteredJobs} />
      </div>
    </main>
  );
}

export default App;
