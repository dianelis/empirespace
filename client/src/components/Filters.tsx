import { Search, X } from "lucide-react";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";
import { Input } from "./ui/input";
import { Select } from "./ui/select";
import { ALL_FILTER } from "../constants";
import type { FilterOptions, FiltersState } from "../types";

type FiltersProps = {
  filters: FiltersState;
  options: FilterOptions;
  onChange: (next: FiltersState) => void;
};

const allOption = { label: "All", value: ALL_FILTER };

const toOptions = (values: string[]) => [
  allOption,
  ...values.map((value) => ({ label: value, value })),
];

export function Filters({ filters, options, onChange }: FiltersProps) {
  const update = (key: keyof FiltersState, value: string) => onChange({ ...filters, [key]: value });

  return (
    <Card>
      <CardContent className="grid gap-4 p-4">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Search company or job title"
            value={filters.search}
            onChange={(event) => update("search", event.target.value)}
          />
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <Select
            label="Category"
            placeholder="All categories"
            value={filters.category}
            onValueChange={(value) => update("category", value)}
            options={toOptions(options.categories)}
          />
          <Select
            label="City"
            placeholder="All cities"
            value={filters.city}
            onValueChange={(value) => update("city", value)}
            options={toOptions(options.cities)}
          />
          <Select
            label="State"
            placeholder="All states"
            value={filters.state}
            onValueChange={(value) => update("state", value)}
            options={toOptions(options.states)}
          />
          <Select
            label="Country"
            placeholder="All countries"
            value={filters.country}
            onValueChange={(value) => update("country", value)}
            options={toOptions(options.countries)}
          />
          <Select
            label="Remote"
            placeholder="All remote statuses"
            value={filters.remote}
            onValueChange={(value) => update("remote", value)}
            options={toOptions(options.remoteStatuses)}
          />
        </div>
        <div className="flex justify-end">
          <Button
            type="button"
            onClick={() =>
              onChange({
                search: "",
                category: ALL_FILTER,
                city: ALL_FILTER,
                state: ALL_FILTER,
                country: ALL_FILTER,
                remote: ALL_FILTER,
              })
            }
          >
            <X className="mr-2 h-4 w-4" />
            Reset
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
