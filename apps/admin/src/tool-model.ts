export type ToolRow = {
  tool: string;
  total: number;
  outcomes: Record<string, number>;
  success_rate: number | null;
  average?: number | null;
  p50?: number | null;
  p95?: number | null;
  samples?: number;
};
export type ToolReport = {
  hours: number;
  estimated: boolean;
  errors: string[];
  collection: { status: string; targets: { instance: string; up: boolean }[] };
  tools: ToolRow[];
};
export function toolTotals(rows: ToolRow[]) {
  const total = rows.reduce((n, row) => n + row.total, 0);
  const success = rows.reduce((n, row) => n + (row.outcomes.succeeded || 0), 0);
  const measured = rows.filter(
    (row) => row.average != null && (row.samples || 0) > 0,
  );
  const samples = measured.reduce((n, row) => n + row.samples!, 0);
  return {
    total,
    unsuccessful: total - success,
    successRate: total > 0 ? success / total : null,
    average: samples
      ? measured.reduce((n, row) => n + row.average! * row.samples!, 0) /
        samples
      : null,
  };
}
export function sortTools(rows: ToolRow[], sort: string) {
  return [...rows].sort((a, b) =>
    sort === "latency"
      ? (b.p95 ?? -1) - (a.p95 ?? -1)
      : sort === "reliability"
        ? (a.success_rate ?? 2) - (b.success_rate ?? 2)
        : b.total - a.total,
  );
}
