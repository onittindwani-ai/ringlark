"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { PhoneForwarded, UserRoundCog } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Card, ConfirmDialog, EmptyState, SplitView, notify } from "@sendora/ui-kit";
import { CallPlayer } from "@/components/CallPlayer";
import { ListSkeleton, LoadError, OutcomeBadge, PageHead } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import { fmtMs } from "@/lib/labels";
import type { CallDetail, CallRow } from "@/lib/types";

export default function LivePage() {
  const list = useQuery({ queryKey: ["calls", "live"], queryFn: () => get<CallRow[]>("/calls?status=completed&limit=60") });
  const rows = (list.data ?? []).filter((c) => c.qa !== null && c.duration_ms > 0);
  const { canWrite } = useRole();
  const [sel, setSel] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<"take" | "transfer" | null>(null);
  useEffect(() => { if (sel === null && rows.length) setSel(rows.find((r) => r.disposition === "booked")?.id ?? rows[0]!.id); }, [rows, sel]);
  const detail = useQuery({ queryKey: ["call", sel], queryFn: () => get<CallDetail>(`/calls/${sel}`), enabled: sel !== null });
  const practice = () => notify.info("Practice run: this replays a finished demo call, so no call was taken over or moved. The click is written to the audit log.");
  const take = useMutation({ mutationFn: () => post<{ live: boolean }>(`/calls/${sel}/take-over`), onSuccess: (r) => (r.live ? notify.success("You have the call. It is written to the audit log.") : practice()), onError: (e: Error) => notify.error("Could not take over", e.message) });
  const transfer = useMutation({ mutationFn: () => post<{ live: boolean }>(`/calls/${sel}/transfer`, { reason: "sent from the console" }), onSuccess: (r) => (r.live ? notify.success("The call is being sent to the practice's number.") : practice()), onError: (e: Error) => notify.error("The transfer was not done", e.message) });
  if (list.isError) return <div className="rm-page"><PageHead title="Live console" /><LoadError error={list.error} onRetry={() => list.refetch()} what="calls" /></div>;
  return (
    <div className="rm-page">
      <PageHead title="Live console" sub="Waveform, transcript and agent state move together. In demo mode this replays a recorded call at real speed. With real calls the same screen follows a call as it happens." />
      {!list.data ? <ListSkeleton /> : rows.length === 0 ? <Card><EmptyState title="No calls to show" body="Use Run now in the top bar to place demo calls, then come back." /></Card> : (
        <SplitView
          list={<Card title="Pick a call"><ul className="rm-list">{rows.map((r) => (
            <li key={r.id}><button type="button" className="rm-item" aria-current={r.id === sel} onClick={() => { setSel(r.id); if (window.innerWidth < 900) document.getElementById("live-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
              <span className="rm-item__top"><strong>{r.name || r.phone}</strong><OutcomeBadge code={r.disposition} /></span>
              <span className="rm-item__line">{r.agent} · {fmtMs(r.duration_ms)} · {r.direction}</span></button></li>))}</ul></Card>}
          detail={<div id="live-detail"><Card title={detail.data ? `${detail.data.name || detail.data.phone}` : "Call"}>
            {detail.isError ? <LoadError error={detail.error} onRetry={() => detail.refetch()} what="this call" /> : !detail.data ? <ListSkeleton rows={3} /> : (
              <div className="rm-stack">
                <div className="sx-row"><Badge tone="warning">Replay of a recorded demo call</Badge><span className="rm-mini">Agent {detail.data.agent}{detail.data.prompt_version ? `, prompt version ${detail.data.prompt_version}` : ""}</span></div>
                <CallPlayer detail={detail.data} mode="live" />
                <div className="sx-row">
                  <Button disabled={!canWrite} disabledReason="Viewers cannot take over a call" onClick={() => setConfirm("take")}><UserRoundCog size={14} aria-hidden />Take over</Button>
                  <Button disabled={!canWrite} disabledReason="Viewers cannot transfer a call" onClick={() => setConfirm("transfer")}><PhoneForwarded size={14} aria-hidden />Transfer to the practice</Button>
                </div>
              </div>)}
          </Card></div>}
        />
      )}
      <ConfirmDialog open={confirm === "take"} onOpenChange={(o) => !o && setConfirm(null)} title="Take over this call?" description="The agent stops and you speak to the person yourself. This is written to the audit log." confirmLabel="Take over" onConfirm={() => void take.mutateAsync()} />
      <ConfirmDialog open={confirm === "transfer"} onOpenChange={(o) => !o && setConfirm(null)} title="Transfer this call?" description="The call goes to the number set for this agent, and only in office hours. A caller can never choose another number." confirmLabel="Transfer" onConfirm={() => void transfer.mutateAsync()} />
    </div>
  );
}
