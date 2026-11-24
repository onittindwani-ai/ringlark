"use client";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Badge, Button, Card, DataTable, EmptyState, Field, FilterBar, Sheet, TableSkeleton, formatWhen, type Column } from "@sendora/ui-kit";
import { CallPlayer } from "@/components/CallPlayer";
import { ListSkeleton, LoadError, OutcomeBadge, PageHead } from "@/components/Parts";
import { get } from "@/lib/api";
import { FOLLOWUP_STATUS, QA_LABEL, fmtMs, outcome, readableNote, why } from "@/lib/labels";
import type { CallDetail, CallRow } from "@/lib/types";

function Detail({ id }: { id: number }) {
  const q = useQuery({ queryKey: ["call", id], queryFn: () => get<CallDetail>(`/calls/${id}`) });
  if (!q.data) return <ListSkeleton rows={4} />;
  const d = q.data;
  const talked = d.turns.some((x) => x.text);
  const checks = Object.entries(d.qa_checks);
  return (
    <div className="rm-stack">
      <p className="rm-mini">{d.summary || "No summary yet."}</p>
      <div className="sx-row"><OutcomeBadge code={d.disposition} />{d.qa !== null ? <Badge tone={d.flagged ? "warning" : "success"}>QA {d.qa}</Badge> : null}{d.prompt_version ? <Badge>prompt v{d.prompt_version}</Badge> : null}<Badge>{d.direction}</Badge></div>
      {talked ? <CallPlayer detail={d} mode="scrub" /> : <p className="rm-mini">{d.status === "drafted" ? "This call was saved as a draft and never placed, so there is nothing to play." : "No one spoke on this call, so there is no transcript or recording to play."}</p>}
      {checks.length ? <h3 style={{ margin: "13px 0 0" }}>QA checks</h3> : null}
      <div className="rm-stack" style={{ gap: 5 }}>{checks.map(([k, v]) => <div key={k} className={`rm-check ${v ? "" : "rm-check--bad"}`}><span aria-hidden>{v ? "✓" : "✗"}</span>{QA_LABEL[k] ?? k}<span className="sx-sr-only">{v ? "passed" : "failed"}</span></div>)}</div>
      {readableNote(d.qa_note) ? <p className="rm-mini">{readableNote(d.qa_note)}</p> : null}
      {d.followups.length ? <><h3 style={{ margin: "13px 0 0" }}>Follow ups</h3><ul className="rm-list">{d.followups.map((f) => <li key={f.id} className="rm-item" style={{ cursor: "default" }}><span className="rm-item__top"><strong>{f.channel === "sms" ? "text message" : f.channel} to {f.to}</strong><Badge>{FOLLOWUP_STATUS[f.status] ?? f.status}</Badge></span><span className="rm-item__line">{f.body}</span></li>)}</ul></> : null}
    </div>
  );
}

function CallsView() {
  const [q, setQ] = useState("");
  const [disp, setDisp] = useState("");
  const [open, setOpen] = useState<CallRow | null>(null);
  const list = useQuery({ queryKey: ["calls", q, disp], queryFn: () => get<CallRow[]>(`/calls?limit=5000&q=${encodeURIComponent(q)}&disposition=${disp}`) });
  // A link such as /calls?open=12 opens that call straight away (the QA page uses it).
  const wanted = Number(useSearchParams().get("open")) || null;
  const opened = useRef(false);
  useEffect(() => {
    if (wanted === null || opened.current) return;
    const row = list.data?.find((r) => r.id === wanted);
    if (row) { opened.current = true; setOpen(row); }
  }, [wanted, list.data]);
  const columns: Column<CallRow>[] = [
    { key: "when", header: "When", width: "130px", render: (r) => (r.started_at ? formatWhen(new Date(r.started_at)) : ""), sortValue: (r) => r.started_at ?? "" },
    { key: "who", header: "Who", width: "1.2fr", render: (r) => <button type="button" className="rm-linkbtn" tabIndex={-1} onClick={() => setOpen(r)}>{r.name || r.phone}</button>, sortValue: (r) => r.name || r.phone },
    { key: "agent", header: "Agent", width: "90px", sortValue: (r) => r.agent },
    { key: "out", header: "Outcome", width: "1.2fr", render: (r) => <OutcomeBadge code={r.disposition || (r.status === "drafted" ? "" : "")} />, sortValue: (r) => r.disposition },
    { key: "qa", header: "QA", width: "70px", align: "right", render: (r) => (r.qa === null ? "" : r.flagged ? <Badge tone="warning">{r.qa}</Badge> : r.qa), sortValue: (r) => r.qa ?? -1 },
    { key: "dur", header: "Length", width: "80px", align: "right", render: (r) => (r.duration_ms ? fmtMs(r.duration_ms) : r.status === "drafted" ? "draft" : ""), sortValue: (r) => r.duration_ms },
  ];
  return (
    <div className="rm-page">
      <PageHead title="Call log" sub="Every call, with a transcript you can scrub. Open one, drag the bar, or click a line to jump to it." />
      <FilterBar>
        <Field label="Search by name or number" value={q} onChange={setQ} placeholder="Name or +1415" clearable />
        <label className="sx-label" style={{ display: "grid", gap: 5 }}>Outcome
          <select className="rm-select" value={disp} onChange={(e) => setDisp(e.target.value)}>
            <option value="">All outcomes</option>{["booked", "interested_callback", "not_interested", "do_not_call", "wrong_number", "transferred", "hostile_ended", "voicemail_left", "voicemail_no_message", "ivr_no_human", "no_answer", "needs_review"].map((c) => <option key={c} value={c}>{outcome(c).label}</option>)}
          </select></label>
      </FilterBar>
      {list.isError ? <LoadError error={list.error} onRetry={() => list.refetch()} what="calls" /> : !list.data ? <TableSkeleton rows={8} columns={6} /> : list.data.length === 0 ? <Card><EmptyState title="No calls match" body="Clear the filters, or use Run now to place demo calls." /></Card> : <DataTable label="Calls" rows={list.data} rowKey={(r) => String(r.id)} columns={columns} height={560} onRowOpen={setOpen} rowActions={(r) => <Button size="sm" feedback={false} onClick={() => setOpen(r)}>Open</Button>} />}
      <Sheet open={open !== null} onOpenChange={(o) => !o && setOpen(null)} title={open ? `${open.name || open.phone}` : "Call"} description={open ? `${open.agent}, attempt ${open.attempt}${open.blocked_reason ? `, ${why(open.blocked_reason)}` : ""}` : undefined}>
        {open ? <Detail id={open.id} /> : null}
      </Sheet>
    </div>
  );
}

export default function CallsPage() {
  return <Suspense fallback={null}><CallsView /></Suspense>;
}
