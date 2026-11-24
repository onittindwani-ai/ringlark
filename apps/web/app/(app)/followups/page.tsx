"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Badge, Button, Card, EmptyState, TabsView, formatWhen, notify } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, PageHead } from "@/components/Parts";
import { FOLLOWUP_STATUS } from "@/lib/labels";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { ApprovalRow, FollowUp } from "@/lib/types";

const CHANNEL: Record<string, string> = { sms: "text message", email: "email" };

export default function FollowupsPage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const fu = useQuery({ queryKey: ["followups"], queryFn: () => get<FollowUp[]>("/followups") });
  const ap = useQuery({ queryKey: ["approvals"], queryFn: () => get<ApprovalRow[]>("/approvals") });
  const decide = useMutation({ mutationFn: (v: { id: number; approve: boolean }) => post(`/approvals/${v.id}/decide`, { approve: v.approve }), onSuccess: (_r, v) => { notify.success(v.approve ? "Approved. It is sent on the next run, if the rules allow." : "Rejected. It will not be sent."); qc.invalidateQueries({ predicate: (x) => x.queryKey[0] !== "me" }); }, onError: (e: Error) => notify.error("Could not decide", e.message) });
  if (fu.isError) return <div className="rm-page"><PageHead title="Follow ups and approvals" /><LoadError error={fu.error} onRetry={() => fu.refetch()} what="follow ups" /></div>;
  if (ap.isError) return <div className="rm-page"><PageHead title="Follow ups and approvals" /><LoadError error={ap.error} onRetry={() => ap.refetch()} what="approvals" /></div>;
  const pending = (ap.data ?? []).filter((a) => a.status === "pending");
  // A follow up the person approved is still "pending" in the database until the next run sends it. Say what it is waiting for.
  const approvedIds = new Set((ap.data ?? []).filter((a) => a.status === "approved").map((a) => Number(a.payload.followup_id)));
  const label = (f: FollowUp) => (f.status === "pending" && approvedIds.has(f.id) ? "approved, sends on the next run" : `${FOLLOWUP_STATUS[f.status] ?? f.status}${f.blocked_reason ? `: ${f.blocked_reason.replace(/_/g, " ")}` : ""}`);
  const tone = (s: string) => (s === "sent" ? "success" : s === "blocked" || s === "rejected" ? "danger" : s === "pending" ? "accent" : "neutral");
  return (
    <div className="rm-page">
      <PageHead title="Follow ups and approvals" sub="After a call, Ringlark prepares a text or an email. Nothing goes out until a person approves it, and never to someone on the do not call list." />
      <TabsView defaultValue="approvals" items={[
        { value: "approvals", label: `Approvals (${pending.length})`, content: !ap.data || !fu.data ? <ListSkeleton /> : pending.length === 0 ? <Card><EmptyState title="Nothing waiting" body="Approvals appear here after calls that earn a follow up." /></Card> : (
          <div className="rm-cols">{pending.map((a) => {
            const f = fu.data?.find((x) => x.id === a.payload.followup_id);
            // The text to approve has to be on the card. If it is missing (or empty) there is nothing to approve, so Approve stays off.
            const empty = !f || !f.body.trim();
            return (
              <Card key={a.id} title={`${a.summary}${f?.name ? ` to ${f.name}` : ""}`}>
                <div className="rm-stack">
                  <div className="sx-row"><Badge>{f ? CHANNEL[f.channel] ?? f.channel : "message"}</Badge><span className="rm-mini">{f ? `to ${f.to}` : "recipient unknown"} · {formatWhen(new Date(a.created_at))}{f ? <> · <Link href={`/calls?open=${f.call_id}`}>Call {f.call_id}</Link></> : null}</span></div>
                  {f?.subject ? <strong>{f.subject}</strong> : null}
                  {!f || empty ? <p className="rm-mini" role="alert">This follow up has no text, so there is nothing to approve. Reject it.</p> : <p className="rm-pre">{f.body}</p>}
                  <div className="sx-row"><Button variant="primary" disabled={!canWrite || empty} disabledReason={empty ? "There is no text to approve" : "Viewers cannot approve"} onClick={async () => { await decide.mutateAsync({ id: a.id, approve: true }); }}>Approve</Button><Button disabled={!canWrite} disabledReason="Viewers cannot reject" onClick={async () => { await decide.mutateAsync({ id: a.id, approve: false }); }}>Reject</Button></div>
                </div>
              </Card>);
          })}</div>) },
        { value: "all", label: "All follow ups", content: !fu.data ? <ListSkeleton /> : fu.data.length === 0 ? <Card><EmptyState title="No follow ups yet" body="They appear after calls that end in a booking or a callback." /></Card> : (
          <Card title="Follow ups"><ul className="rm-list">{fu.data.map((f) => <li key={f.id} className="rm-item" style={{ cursor: "default" }}><span className="rm-item__top"><strong>{CHANNEL[f.channel] ?? f.channel} to {f.name || f.to}</strong><Badge tone={tone(f.status)}>{label(f)}</Badge></span><span className="rm-item__line">{f.body}</span></li>)}</ul></Card>) },
      ]} />
    </div>
  );
}
