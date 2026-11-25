"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, EmptyState, SegmentedControl, formatWhen, notify } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, OutcomeBadge, PageHead } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import { QA_LABEL, readableNote } from "@/lib/labels";
import type { QaRow } from "@/lib/types";

const QA_PAGE = 100;

export default function QaPage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const [show, setShow] = useState<"open" | "all">("open");
  // The queue is read a page at a time, so a call beyond the first page can still be reached and marked as read.
  const [pages, setPages] = useState(1);
  const q = useQuery({ queryKey: ["qa", show, pages], queryFn: () => get<QaRow[]>(`/qa?show=${show}&limit=${pages * QA_PAGE}`) });
  const read = useMutation({ mutationFn: (id: number) => post(`/qa/${id}/review`), onSuccess: () => { notify.success("Marked as read."); qc.invalidateQueries({ predicate: (x) => x.queryKey[0] !== "me" }); }, onError: (e: Error) => notify.error("Could not mark it", e.message) });
  if (q.isError) return <div className="rm-page"><PageHead title="QA review" /><LoadError error={q.error} onRetry={() => q.refetch()} what="the QA queue" /></div>;
  return (
    <div className="rm-page">
      <PageHead title="QA review" sub="Every call is scored by fixed rules (code, not a model). Calls that fail a safety check, and a steady one in five of the rest, wait here for a person to read." actions={<SegmentedControl label="Show" value={show} onChange={(v) => { setShow(v); setPages(1); }} options={[{ value: "open", label: "To read" }, { value: "all", label: "All sampled" }]} />} />
      {!q.data ? <ListSkeleton /> : q.data.length === 0 ? <Card><EmptyState title="Nothing to read" body="Flagged calls and sampled calls show up here after the post call jobs run." /></Card> : (
        <div className="rm-cols">{q.data.map((r) => (
          <Card key={r.call_id} title={`Call ${r.call_id}`} lift>
            <div className="rm-stack">
              <div className="sx-row"><Badge tone={r.flagged ? "warning" : "success"}>{r.flagged ? "Flagged" : "Sampled"} · score {r.score}</Badge><OutcomeBadge code={r.disposition} />{r.reviewed ? <Badge>read</Badge> : null}</div>
              <p className="rm-mini">{r.phone} · {r.started_at ? formatWhen(new Date(r.started_at)) : ""}</p>
              {readableNote(r.note) ? <p>{readableNote(r.note)}</p> : null}
              <div className="rm-stack" style={{ gap: 5 }}>{Object.entries(r.checks).filter(([, v]) => !v).map(([k]) => <div key={k} className="rm-check rm-check--bad"><span aria-hidden>✗</span>{QA_LABEL[k] ?? k}</div>)}</div>
              <div className="sx-row"><Link href={`/calls?open=${r.call_id}`} className="rm-mini" style={{ display: "inline-flex", alignItems: "center", minHeight: 32 }}>Open it in the call log</Link>{!r.reviewed ? <Button size="sm" disabled={!canWrite} disabledReason="Viewers cannot mark a call as read" onClick={async () => { await read.mutateAsync(r.call_id); }}>Mark as read</Button> : null}</div>
            </div>
          </Card>))}</div>)}
      {q.data && q.data.length >= pages * QA_PAGE ? <div className="sx-row"><Button onClick={() => setPages(pages + 1)}>Show more calls</Button></div> : null}
    </div>
  );
}
