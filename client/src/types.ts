export type Job = {
  id: string;
  company: string;
  category: string;
  title: string;
  location: string;
  city: string;
  state: string;
  country: string;
  remote: string;
  salaryMin: string;
  salaryMax: string;
  lastSeenAt: string;
  applyUrl: string;
  status: string;
};

export type FiltersState = {
  search: string;
  category: string;
  city: string;
  state: string;
  country: string;
  remote: string;
};

export type FilterOptions = {
  categories: string[];
  cities: string[];
  states: string[];
  countries: string[];
  remoteStatuses: string[];
};
