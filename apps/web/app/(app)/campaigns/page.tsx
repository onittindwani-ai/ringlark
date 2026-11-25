"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Upload } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, ConfirmDialog, DataTable, Dialog, EmptyState, Field, TableSkeleton, notify, type Column } from "@sendora/ui-kit";
import { CsvFileInput } from "@/components/CsvFileInput";
import { importBlocker, toRows } from "@/lib/csv";
import { ListSkeleton, LoadError, PageHead, Textarea } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import { PERSON_CHIP, why } from "@/lib/labels";
import type { Agent, Campaign, Me, TargetRow } from "@/lib/types";

/** Shown greyed out in the paste box as an example of the shape. It is never sent. */
const SAMPLE = "first_name,last_name,phone,timezone,email\nAva,Alder,+14155550177,America/New_York,ava@example.test\n";
function Targets({ c }: { c: Campaign }) {
  const q = useQuery({ queryKey: ["targets", c.id], queryFn: () => get<TargetRow[]>(`/campaigns/${c.id}/targets`) });
  const columns: Column<TargetRow>[] = [
    { key: "name", header: "Person", width: "1.2fr", render: (r) => r.name || "(no name)", sortValue: (r) => r.name },
    { key: "phone", header: "Phone", width: "1.2fr", sortValue: (r) => r.phone },
    { key: "tz", header: "Time zone", width: "1.3fr", render: (r) => r.timezone || "none", sortValue: (r) => r.timezone },
    { key: "now", header: "Right now", width: "2fr", render: (r) => <Badge tone={r.can_call_now ? "success" : r.why === "outside_hours" || r.why === "daily_cap" ? "neutral" : "warning"}>{why(r.why)}</Badge>, sortValue: (r) => r.why },
  ];
  if (q.isError) return <LoadError error={q.error} onRetry={() => q.refetch()} what="targets" />;
  if (!q.data) return <TableSkeleton rows={6} columns={4} />;
  return <div className="rm-noopen"><DataTable label={`Targets of ${c.name}`} rows={q.data} rowKey={(r) => String(r.id)} columns={columns} height={420} /></div>;
}

export default function CampaignsPage() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => get<Me>("/auth/me") });
  const { canWrite } = useRole();
  const list = useQuery({ queryKey: ["campaigns"], queryFn: () => get<Campaign[]>("/campaigns") });
  const agents = useQuery({ queryKey: ["agents"], queryFn: () => get<Agent[]>("/agents") });
  const [sel, setSel] = useState<number | null>(null);
  const [startId, setStartId] = useState<number | null>(null);
  const [create, setCreate] = useState(false);
  const [imp, setImp] = useState(false);
  const [name, setName] = useState("");
  const [agentId, setAgentId] = useState<number | null>(null);
  const [needConsent, setNeedConsent] = useState(true);
  const [csv, setCsv] = useState("");
  const refresh = () => qc.invalidateQueries({ predicate: (x) => x.queryKey[0] !== "me" });
  const act = useMutation({ mutationFn: (v: { id: number; a: "start" | "pause"; ack?: boolean }) => post(`/campaigns/${v.id}/${v.a}`, v.ack ? { acknowledge_timezone_warnings: true } : undefined), onSuccess: (_r, v) => { notify.success(v.a === "start" ? "Campaign started. Calls still follow every rule." : "Campaign paused."); refresh(); }, onError: (e: Error) => notify.error("That did not work", e.message) });
  const make = useMutation({ mutationFn: () => post("/campaigns", { name, agent_id: agentId ?? agents.data?.find((a) => a.kind === "outbound")?.id, require_prior_consent: needConsent }), onSuccess: () => { notify.success("Campaign created as a draft. Add people, then start it."); setCreate(false); setName(""); setNeedConsent(true); refresh(); }, onError: (e: Error) => notify.error("Could not create it", e.message) });
  const importer = useMutation({ mutationFn: (id: number) => post<{ created: number; duplicates: number; flagged: Record<string, number> }>(`/campaigns/${id}/targets`, { rows: toRows(csv) }), onSuccess: (r) => { const f = Object.entries(r.flagged).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(", "); notify.success(`Imported ${r.created} ${r.created === 1 ? "person" : "people"}.${r.duplicates ? ` ${r.duplicates} ${r.duplicates === 1 ? "duplicate" : "duplicates"} skipped.` : ""}${f ? ` Flagged: ${f}.` : ""}`); setImp(false); setCsv(""); refresh(); }, onError: (e: Error) => notify.error("Import failed", e.message) });
  if (list.isError) return <div className="rm-page"><PageHead title="Campaigns" /><LoadError error={list.error} onRetry={() => list.refetch()} what="campaigns" /></div>;
  const owner = me.data?.role === "owner";
  const blocker = importBlocker(csv);
  const startWarnings = list.data?.find((c) => c.id === startId)?.timezone_warnings ?? 0;
  const open = list.data?.find((c) => c.id === sel) ?? list.data?.[0];
  return (
    <div className="rm-page">
      <PageHead title="Campaigns" sub="A campaign is a list of people, an agent, and the rules for when it may call. The table says in plain words who can be called right now and who cannot." actions={<Button variant="primary" feedback={false} disabled={!canWrite} disabledReason="Viewers cannot create campaigns" onClick={() => setCreate(true)}><Plus size={14} aria-hidden />New campaign</Button>} />
      {!list.data ? <ListSkeleton /> : list.data.length === 0 ? <Card><EmptyState title="No campaigns yet" body="Create one, import a list of people, review who can be called, then start it." /></Card> : (
        <>
          <div className="rm-cols">{list.data.map((c) => (
            <Card key={c.id} title={c.name} lift>
              <div className="rm-stack">
                <div className="sx-row"><Badge tone={c.status === "running" ? "success" : c.status === "paused" ? "warning" : "neutral"}>{c.status === "draft" ? "not started" : c.status}</Badge><span className="rm-mini">Agent {c.agent}</span></div>
                <p className="rm-mini">Calls {String(c.window_start_hour).padStart(2, "0")}:00 to {String(c.window_end_hour).padStart(2, "0")}:00 in the person's own time zone{c.weekdays_only ? ", weekdays only" : ""}. At most {c.daily_cap} a day ({c.calls_today} today), {c.max_attempts} tries a person, {c.retry_gap_days} day apart. Voicemail {c.allow_voicemail ? "on" : "off"}. Phone menu: {c.ivr_policy === "hangup" ? "hang up" : `press ${c.ivr_extension} once`}. {c.require_prior_consent ? "Only people with a call consent on file are called." : "The consent check is off: people with no call consent on file can be called."}</p>
                <div className="sx-row">{Object.entries(c.targets).map(([k, v]) => <Badge key={k}>{v} {PERSON_CHIP[k] ?? k}</Badge>)}</div>
                <div className="sx-row">
                  <Button size="sm" feedback={false} onClick={() => setSel(c.id)} aria-pressed={open?.id === c.id}>Show people</Button>
                  <Button size="sm" disabled={!canWrite} disabledReason="Viewers cannot import people" onClick={() => { setSel(c.id); setCsv(""); setImp(true); }}><Upload size={14} aria-hidden />Import</Button>
                  {c.status === "running" ? <Button size="sm" disabled={!canWrite} disabledReason="Viewers cannot pause a campaign" onClick={async () => { await act.mutateAsync({ id: c.id, a: "pause" }); }}>Pause</Button> : <Button size="sm" variant="primary" disabledReason={owner ? undefined : "Only the owner can start a campaign"} disabled={!owner} feedback={false} onClick={() => setStartId(c.id)}>Start</Button>}
                </div>
              </div>
            </Card>))}</div>
          {open ? <Card title={`People in ${open.name}`}><Targets c={open} /></Card> : null}
        </>)}
      <Dialog open={create} onOpenChange={setCreate} title="New campaign" description="It starts as a draft and never dials until the owner starts it." actions={<Button variant="primary" disabled={name.trim().length < 2} disabledReason="Give it a name" onClick={async () => { await make.mutateAsync(); }}>Create</Button>}>
        <div className="rm-stack"><Field label="Name" value={name} onChange={setName} maxLength={120} />
          <label className="sx-label" style={{ display: "grid", gap: 5 }}>Agent<select className="rm-select" value={agentId ?? ""} onChange={(e) => setAgentId(Number(e.target.value))}>{(agents.data ?? []).filter((a) => a.kind === "outbound").map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
          <label className="sx-row" style={{ cursor: "pointer" }}><input type="checkbox" checked={needConsent} disabled={!owner} title={owner ? undefined : "Only the owner can turn the consent check off"} onChange={(e) => setNeedConsent(e.target.checked)} />Only call people with a call consent on file (recommended)</label>
          <p className="rm-mini">Add a <code>call_consent</code> column with yes for each person who agreed to be called when you import them. Without it nobody in this campaign is called.</p></div>
      </Dialog>
      <Dialog open={imp} onOpenChange={setImp} title="Import people" description="Choose a CSV file or paste rows. The columns are first_name, last_name, phone, timezone, email, and call_consent (yes for a person who agreed to be called). Rows with a bad number or time zone are kept and flagged, and are never called." actions={<Button variant="primary" disabled={blocker !== null} disabledReason={blocker ?? undefined} onClick={async () => { if (open) await importer.mutateAsync(open.id); }}>Import</Button>}>
        <div className="rm-stack"><CsvFileInput onText={setCsv} /><Textarea label="Or paste CSV text" value={csv} placeholder={SAMPLE} rows={6} onChange={(e) => setCsv(e.target.value)} /></div>
      </Dialog>
      <ConfirmDialog open={startId !== null} onOpenChange={(o) => !o && setStartId(null)} title="Start this campaign?" description={`Calls begin as soon as the rules allow, up to the daily cap. In draft mode or with the kill switch on, nothing is dialled.${startWarnings ? ` ${startWarnings} ${startWarnings === 1 ? "person has" : "people have"} a time zone that does not fit the area code of their number, so their calling hours may be wrong. Starting means you have looked at them (they are listed under /api/campaigns/${startId}/timezone-warnings).` : ""}`} confirmLabel="Start" onConfirm={() => { if (startId) void act.mutateAsync({ id: startId, a: "start", ack: startWarnings > 0 }); }} />
    </div>
  );
}
