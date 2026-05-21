import { ExternalLink } from "lucide-react";
import { Badge } from "./ui/badge";
import { Card } from "./ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import type { Job } from "../types";

type JobTableProps = {
  jobs: Job[];
};

const display = (value: string) => value || "—";

export function JobTable({ jobs }: JobTableProps) {
  if (!jobs.length) {
    return (
      <Card className="p-10 text-center">
        <p className="text-lg font-medium text-foreground">No matching jobs</p>
        <p className="mt-2 text-sm text-muted-foreground">Try broadening the search or clearing filters.</p>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Company</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Job Title</TableHead>
              <TableHead>Location</TableHead>
              <TableHead>City</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Country</TableHead>
              <TableHead>Remote</TableHead>
              <TableHead>Salary Min</TableHead>
              <TableHead>Salary Max</TableHead>
              <TableHead>Last Seen</TableHead>
              <TableHead>Apply</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.map((job) => (
              <TableRow key={job.id}>
                <TableCell className="min-w-44 font-medium text-foreground">{display(job.company)}</TableCell>
                <TableCell className="min-w-36">
                  {job.category ? <Badge>{job.category}</Badge> : "—"}
                </TableCell>
                <TableCell className="min-w-72 text-foreground">{display(job.title)}</TableCell>
                <TableCell className="min-w-44 text-muted-foreground">{display(job.location)}</TableCell>
                <TableCell>{display(job.city)}</TableCell>
                <TableCell>{display(job.state)}</TableCell>
                <TableCell>{display(job.country)}</TableCell>
                <TableCell>{display(job.remote)}</TableCell>
                <TableCell>{display(job.salaryMin)}</TableCell>
                <TableCell>{display(job.salaryMax)}</TableCell>
                <TableCell className="min-w-28">{display(job.lastSeenAt)}</TableCell>
                <TableCell>
                  {job.applyUrl ? (
                    <a
                      className="inline-flex items-center gap-1 rounded-md border border-primary/30 px-2.5 py-1.5 text-xs font-medium text-primary transition hover:bg-primary/10"
                      href={job.applyUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Apply
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  ) : (
                    "—"
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}
