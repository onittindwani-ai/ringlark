"use client";
import { useQuery } from "@tanstack/react-query";
import { AreaChart, Badge, Card, DataTable, EmptyState, TableSkeleton, type Column } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, PageHead } from "@/components/Parts";
import { get } from "@/lib/api";
import { PERSON_STATUS, shortDay } from "@/lib/labels";
import type { Overview, VersionMetric } from "@/lib/types";


export default function MetricsPage() {
  const ov = useQuery({ queryKey: ["overview"], queryFn: () => get<Overview>("/overview") });
  const vm = useQuery({ queryKey: ["versions"], queryFn: () => get<VersionMetric[]>("/metrics/versions") });
  const cols: Column<VersionMetric>[] = [
    { key: "a", header: "Agent", width: "1fr", render: (r) => r.agent, sortValue: (r) => r.agent },
    { key: "v", header: "Version", width: "90px", render: (r) => `v${r.version}`, sortValue: (r) => r.version },
    { key: "n", header: "What changed", width: "2fr", render: (r) => r.note || "No note", sortValue: (r) => r.note },
    { key: "c", header: "Calls", width: "80px", align: "right", render: (r) => r.calls, sortValue: (r) => r.calls },
    { key: "b", header: "Booked", width: "110px", align: "right", render: (r) => (r.book_rate === null ? "no calls yet" : `${r.booked} (${Math.round(r.book_rate * 100)}%)`), sortValue: (r) => r.book_rate ?? -1 },
    { key: "q", header: "Average QA", width: "110px", align: "right", render: (r) => r.avg_qa ?? "", sortValue: (r) => r.avg_qa ?? -1 },
  ];
  if (ov.isError) return <div className="rm-page"><PageHead title="Metrics" /><LoadError error={ov.error} onRetry={() => ov.refetch()} what="metrics" /></div>;
  if (!ov.data) return <div className="rm-page"><PageHead title="Metrics" /><ListSkeleton /></div>;
  const o = ov.data;
  return (
    <div className="rm-page">
      <PageHead title="Metrics" sub="All numbers are counts read from the database. Small samples are noise: do not decide a prompt winner on a handful of calls." />
      <div className="rm-cols">
        <Card title="Calls per day">{o.series.some((d) => d.calls) ? <AreaChart data={o.series.map((d) => ({ ...d, day: shortDay(d.day) }))} xKey="day" series={[{ key: "calls", label: "Calls" }, { key: "booked", label: "Booked" }]} height={220} /> : <EmptyState title="No data yet" body="Run the demo jobs first." />}</Card>
        <Card title="People by status"><ul className="rm-list">{Object.entries(o.targets).map(([k, v]) => <li key={k} className="rm-item" style={{ cursor: "default" }}><span className="rm-item__top"><strong>{PERSON_STATUS[k] ?? k}</strong><Badge>{v}</Badge></span></li>)}</ul></Card>
      </div>
      <Card title="Prompt versions side by side">{vm.isError ? <LoadError error={vm.error} onRetry={() => vm.refetch()} what="the prompt versions" /> : !vm.data ? <TableSkeleton rows={4} columns={6} /> : <div className="rm-noopen"><DataTable label="Prompt versions" rows={vm.data} rowKey={(r) => `${r.agent}-${r.version}`} columns={cols} height={260} /></div>}</Card>
    </div>
  );
}
