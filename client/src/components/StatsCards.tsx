import { BriefcaseBusiness, Building2, Radar, Satellite } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import type { Job } from "../types";

type StatsCardsProps = {
  jobs: Job[];
};

const formatLatestDate = (jobs: Job[]) => {
  const sorted = jobs
    .map((job) => job.lastSeenAt)
    .filter(Boolean)
    .sort((a, b) => b.localeCompare(a));

  return sorted[0] || "Not available";
};

export function StatsCards({ jobs }: StatsCardsProps) {
  const totalCompanies = new Set(jobs.map((job) => job.company).filter(Boolean)).size;
  const remoteJobs = jobs.filter((job) => /remote/i.test(job.remote || job.location)).length;

  const cards = [
    { label: "Total jobs", value: jobs.length.toLocaleString(), icon: BriefcaseBusiness },
    { label: "Companies", value: totalCompanies.toLocaleString(), icon: Building2 },
    { label: "Remote jobs", value: remoteJobs.toLocaleString(), icon: Radar },
    { label: "Latest seen", value: formatLatestDate(jobs), icon: Satellite },
  ];

  return (
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.label}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle>{card.label}</CardTitle>
            <card.icon className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold text-foreground">{card.value}</div>
          </CardContent>
        </Card>
      ))}
    </section>
  );
}
