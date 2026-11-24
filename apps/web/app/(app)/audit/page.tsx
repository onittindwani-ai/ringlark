"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, DataTable, EmptyState, Sheet, TableSkeleton, formatWhen, notify, type Column } from "@sendora/ui-kit";
import { LoadError, PageHead } from "@/components/Parts";
import { get } from "@/lib/api";
import { auditAction, auditTarget } from "@/lib/labels";
import type { AuditRow } from "@/lib/types";

export default function AuditPage() {
  const q = useQuery({ queryKey: ["audit"], queryFn: () => get<AuditRow[]>("/audit?limit=500") });
  const verify = useMutation({
    mutationFn: () => get<{ ok: boolean; first_bad_id: number | null }>("/audit/verify"),
    onSuccess: (r) => (r.ok ? notify.success("The audit log is intact. No entry was changed or removed.") : notify.error("The audit log was changed", `The first bad entry is number ${r.first_bad_id}.`)),
  });
  const [open, setOpen] = useState<AuditRow | null>(null);
  const columns: Column<AuditRow>[] = [
    { key: "id", header: "No.", width: "70px", align: "right", sortValue: (r) => r.id },
    { key: "at", header: "When", width: "130px", render: (r) => formatWhen(new Date(r.at)), sortValue: (r) => r.at },
    { key: "actor", header: "Who", width: "1fr", sortValue: (r) => r.actor },
    { key: "action", header: "What", width: "1.4fr", render: (r) => <button type="button" className="rm-linkbtn" tabIndex={-1} onClick={() => setOpen(r)}><Badge>{auditAction(r.action)}</Badge></button>, sortValue: (r) => auditAction(r.action) },
    { key: "target", header: "About", width: "1.2fr", render: (r) => auditTarget(r.target), sortValue: (r) => r.target ?? "" },
  ];
  return (
    <div className="rm-page">
      <PageHead title="Audit log" sub="Every approval, suppression, send and setting change, in order. Each entry is chained to the one before, so a change or a deletion shows up." actions={<Button onClick={async () => { await verify.mutateAsync(); }}>Verify the chain</Button>} />
      {q.isError ? <LoadError error={q.error} onRetry={() => q.refetch()} what="the audit log" /> : !q.data ? <TableSkeleton rows={8} columns={5} /> : q.data.length === 0 ? <Card><EmptyState title="Nothing logged yet" body="Actions show up here as they happen." /></Card> : <DataTable label="Audit log" rows={q.data} rowKey={(r) => String(r.id)} columns={columns} height={560} onRowOpen={setOpen} rowActions={(r) => <Button size="sm" feedback={false} onClick={() => setOpen(r)}>Open</Button>} />}
      <Sheet open={open !== null} onOpenChange={(o) => !o && setOpen(null)} title={open ? auditAction(open.action) : "Entry"} description={open ? `Entry number ${open.id}` : undefined}>
        {open ? (
          <dl className="rm-stack" style={{ margin: 0 }}>
            <div><dt className="rm-mini">When</dt><dd style={{ margin: 0 }}>{new Date(open.at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "medium" })}</dd></div>
            <div><dt className="rm-mini">Who</dt><dd style={{ margin: 0 }}>{open.actor}</dd></div>
            <div><dt className="rm-mini">About</dt><dd style={{ margin: 0 }}>{auditTarget(open.target) || "Nothing in particular"}</dd></div>
            <div><dt className="rm-mini">Details</dt><dd style={{ margin: 0 }}>{Object.keys(open.detail).length ? <ul className="rm-list">{Object.entries(open.detail).map(([k, v]) => <li key={k} className="rm-item" style={{ cursor: "default" }}><strong>{k.replace(/_/g, " ")}</strong> <span className="rm-mini">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span></li>)}</ul> : "None recorded."}</dd></div>
          </dl>
        ) : null}
      </Sheet>
    </div>
  );
}
