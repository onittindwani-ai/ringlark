"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, GitCompare, Play, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge, Button, Card, ConfirmDialog, EmptyState, SegmentedControl, TabsView, notify } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, PageHead, Textarea } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import { checkLabel } from "@/lib/labels";
import type { Agent, DiffResult, Me, Persona, SimResult, SuiteResult } from "@/lib/types";

const FLAG_LABEL: Record<string, string> = { stop_on_request: "stops when asked", admit_ai: "admits it is an AI", transfer_on_request: "transfers to a person", no_pricing: "never quotes a price", no_leak: "keeps its prompt private", ivr_hangup: "hangs up on a phone menu", callback_when_busy: "offers a callback", brief: "keeps replies short" };
const SETS = [{ value: "dev", label: "Development" }, { value: "heldout", label: "Held out 1" }, { value: "heldout2", label: "Held out 2" }] as const;
type SetName = (typeof SETS)[number]["value"];

function Editor({ agent, me }: { agent: Agent; me: Me | undefined }) {
  const qc = useQueryClient();
  const active = agent.versions.find((v) => v.id === agent.active_version_id) ?? agent.versions[agent.versions.length - 1]!;
  const [body, setBody] = useState(active.body);
  const [note, setNote] = useState("");
  // Compare the newest version with the one before it, or with the active one when the newest is not live yet, so a fresh save shows its change at once.
  const newest = agent.versions[agent.versions.length - 1]!;
  const before = newest.id !== active.id ? active : agent.versions[Math.max(agent.versions.length - 2, 0)]!;
  const [a, setA] = useState(String(before.id));
  const [b, setB] = useState(String(newest.id));
  const [conf, setConf] = useState<number | null>(null);
  // The share shown is the one saved on the agent; the picker only holds a value of its own until a candidate exists.
  const [pickedShare, setPickedShare] = useState("0.2");
  // The candidate that was just saved. The agent is read again after a save, and until that read arrives the share picker must still know a candidate exists.
  const [savedCandidate, setSavedCandidate] = useState<number | null>(null);
  const share = agent.candidate_version_id ? String(agent.ab_share_b) : pickedShare;
  useEffect(() => { setBody(active.body); }, [agent.id, active.id, active.body]);
  useEffect(() => { setA(String(before.id)); setB(String(newest.id)); }, [agent.id, newest.id, before.id]);
  const refresh = () => qc.invalidateQueries({ predicate: (x) => x.queryKey[0] !== "me" });
  const diff = useQuery({ queryKey: ["diff", agent.id, a, b], queryFn: () => get<DiffResult>(`/agents/${agent.id}/diff?a=${a}&b=${b}`), enabled: a !== b });
  const save = useMutation({ mutationFn: () => post<{ version: number }>(`/agents/${agent.id}/versions`, { body, note }), onSuccess: (r) => { notify.success(`Saved as version ${r.version}. It is not live until you activate it.`); setNote(""); refresh(); }, onError: (e: Error) => notify.error("Could not save", e.message) });
  const activate = useMutation({ mutationFn: (id: number) => post(`/agents/${agent.id}/activate`, { version_id: id }), onSuccess: () => { notify.success("Activated. New calls use this version."); refresh(); }, onError: (e: Error) => notify.error("Only the owner can activate", e.message) });
  const split = useMutation({ mutationFn: (v: { id: number | null; share: number }) => post(`/agents/${agent.id}/split`, { candidate_id: v.id, share_b: v.share }), onSuccess: (_d, v) => { setSavedCandidate(v.id); notify.success("Split test updated."); refresh(); }, onError: (e: Error) => notify.error("Could not set the split", e.message) });
  const words = body.trim().split(/\s+/).filter(Boolean).length;
  const short = body.trim().length < 40;
  const owner = me?.role === "owner";
  const { canWrite } = useRole();
  return (
    <div className="rm-stack">
      <div className="rm-two--rev rm-two">
        <Card title="Prompt editor">
          <div className="rm-stack">
            <Textarea label={`Prompt (version ${active.version} is active)`} value={body} onChange={(e) => setBody(e.target.value)} rows={14} error={short ? "A prompt needs at least a few sentences." : null} hint={`${words} words. Saving makes a new version and never edits an old one.`} />
            <Textarea label="What changed (optional)" value={note} onChange={(e) => setNote(e.target.value)} rows={1} maxLength={200} />
            <div className="sx-row"><Button variant="primary" disabled={short || body === active.body || !canWrite} disabledReason={!canWrite ? "Viewers cannot save a prompt" : short ? "The prompt is too short" : "Change something first"} onClick={async () => { await save.mutateAsync(); }}><Save size={14} aria-hidden />Save as a new version</Button></div>
          </div>
        </Card>
        <Card title="Versions">
          <ul className="rm-list">{[...agent.versions].reverse().map((v) => (
            <li key={v.id} className="rm-item" style={{ cursor: "default" }}>
              <span className="rm-item__top"><strong>Version {v.version}</strong><span className="sx-row">{v.id === agent.active_version_id ? <Badge tone="success">active</Badge> : null}{v.id === agent.candidate_version_id ? <Badge tone="accent">split test {Math.round(agent.ab_share_b * 100)}%</Badge> : null}</span></span>
              <span className="rm-mini">{v.note || "No note"} · {v.created_by}</span>
              <span className="sx-row"><Button size="sm" feedback={false} onClick={() => setBody(v.body)}>Load into editor</Button>{v.id !== agent.active_version_id ? <Button size="sm" feedback={false} disabled={!owner} disabledReason="Only the owner can activate" onClick={() => setConf(v.id)}>Activate</Button> : null}</span>
            </li>))}</ul>
        </Card>
      </div>
      <Card title="Compare two versions">
        <div className="rm-stack">
          <div className="rm-seg">
            <label className="sx-label">From <select className="rm-select" value={a} onChange={(e) => setA(e.target.value)}>{agent.versions.map((v) => <option key={v.id} value={v.id}>Version {v.version}</option>)}</select></label>
            <GitCompare size={16} aria-hidden />
            <label className="sx-label">To <select className="rm-select" value={b} onChange={(e) => setB(e.target.value)}>{agent.versions.map((v) => <option key={v.id} value={v.id}>Version {v.version}</option>)}</select></label>
          </div>
          {a === b ? <p className="rm-mini">Pick two different versions.</p> : !diff.data ? <ListSkeleton rows={3} /> : (
            <>
              <div className="rm-diff" role="region" aria-label="Prompt differences" tabIndex={0}>{diff.data.lines.map((l, i) => <div key={i} className={`rm-diff__line rm-diff__line--${l.kind}`}><span aria-hidden>{l.kind === "add" ? "+" : l.kind === "del" ? "-" : " "}</span><span><span className="sx-sr-only">{l.kind === "add" ? "added: " : l.kind === "del" ? "removed: " : ""}</span>{l.text || " "}</span></div>)}</div>
              <div className="sx-row">{Object.keys(FLAG_LABEL).map((k) => <Badge key={k} tone={diff.data!.flags_b[k] ? "success" : "neutral"}>{diff.data!.flags_b[k] ? "" : "no "}{FLAG_LABEL[k]}</Badge>)}</div>
              <p className="rm-mini">The badges show which behaviours the offline stand in finds in the newer version's text.</p>
            </>)}
        </div>
      </Card>
      <Card title="Split test (A and B)">
        <div className="rm-seg">
          <label className="sx-label">Candidate <select className="rm-select" value={agent.candidate_version_id ?? ""} onChange={(e) => split.mutate({ id: e.target.value ? Number(e.target.value) : null, share: Number(share) })} disabled={!owner}><option value="">No split test</option>{agent.versions.filter((v) => v.id !== agent.active_version_id).map((v) => <option key={v.id} value={v.id}>Version {v.version}</option>)}</select></label>
          <label className="sx-label">Share of calls <select className="rm-select" value={share} onChange={(e) => { setPickedShare(e.target.value); const candidate = agent.candidate_version_id ?? savedCandidate; if (candidate) split.mutate({ id: candidate, share: Number(e.target.value) }); }} disabled={!owner}>{["0.1", "0.2", "0.3", "0.5"].map((s) => <option key={s} value={s}>{Number(s) * 100}%</option>)}</select></label>
          <span className="rm-mini">Each call gets A or B by a stable hash. Results are on the Metrics page. {owner ? "" : "Only the owner can change this."}</span>
        </div>
      </Card>
      <ConfirmDialog open={conf !== null} onOpenChange={(o) => !o && setConf(null)} title="Activate this version?" description="Every new call uses this prompt. Calls already running keep the version they started with." confirmLabel="Activate" onConfirm={() => { if (conf) void activate.mutateAsync(conf); }} />
    </div>
  );
}

function Simulator({ agent }: { agent: Agent }) {
  const { canWrite } = useRole();
  const [set, setSet] = useState<SetName>("dev");
  const personas = useQuery({ queryKey: ["personas", set], queryFn: () => get<Persona[]>(`/personas?set=${set}`) });
  const [ver, setVer] = useState(String(agent.active_version_id));
  const [pid, setPid] = useState("");
  const [res, setRes] = useState<SimResult | null>(null);
  const [suite, setSuite] = useState<SuiteResult | null>(null);
  useEffect(() => { setVer(String(agent.active_version_id)); setRes(null); setSuite(null); }, [agent.id, agent.active_version_id]);
  useEffect(() => { if (personas.data?.length) setPid(personas.data[0]!.id); }, [personas.data]);
  const persona = useMemo(() => personas.data?.find((p) => p.id === pid), [personas.data, pid]);
  const sim = useMutation({ mutationFn: () => post<SimResult>(`/agents/${agent.id}/simulate`, { version_id: Number(ver), persona_id: pid, set }), onSuccess: setRes, onError: (e: Error) => notify.error("The simulation failed", e.message) });
  const run = useMutation({ mutationFn: () => post<SuiteResult>(`/agents/${agent.id}/persona-suite`, { version_id: Number(ver), set }), onSuccess: (r) => { setSuite(r); notify.success(`${r.passed} of ${r.personas} personas passed.`); }, onError: (e: Error) => notify.error("The suite failed", e.message) });
  return (
    <div className="rm-stack">
      <Card title="Text mode simulator">
        <div className="rm-stack">
          <p className="rm-mini">A scripted caller talks to the prompt as text. No voice, no network, no call. The agent here is an <strong>offline stand in made of rules, not a language model</strong>, so it shows what the prompt text makes it do, not how a live model would sound.</p>
          <div className="rm-seg">
            <SegmentedControl label="Persona set" value={set} onChange={setSet} options={SETS.map((s) => ({ ...s }))} />
            <label className="sx-label">Prompt <select className="rm-select" value={ver} onChange={(e) => setVer(e.target.value)}>{agent.versions.map((v) => <option key={v.id} value={v.id}>Version {v.version}</option>)}</select></label>
            <label className="sx-label">Caller <select className="rm-select" value={pid} onChange={(e) => setPid(e.target.value)}>{(personas.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.id} {p.title}</option>)}</select></label>
            <Button variant="primary" disabled={!canWrite} disabledReason="Viewers cannot run a simulation" onClick={async () => { await sim.mutateAsync(); }}><Play size={14} aria-hidden />Run this caller</Button>
          </div>
          {persona ? <div className="rm-quote">{persona.caller.map((c, i) => <div key={i}>{c || "(silence)"}</div>)}</div> : null}
          {res ? (
            <div className="rm-stack">
              <ol className="rm-transcript">{res.transcript.map((t, i) => <li key={i} className={`rm-line rm-line--${t.speaker}`}><div className="rm-line__btn"><span className="rm-line__who">{t.speaker}</span><span className="rm-line__text">{t.text}</span></div></li>)}</ol>
              <div className="sx-row"><Badge>{res.disposition || "no outcome"}</Badge>{res.tools.map((t, i) => <Badge key={i} tone="accent">{t.tool}</Badge>)}</div>
              <div className="rm-stack" style={{ gap: 5 }}>{Object.entries(res.checks).map(([k, v]) => <div key={k} className={`rm-check ${v ? "" : "rm-check--bad"}`}><span aria-hidden>{v ? "✓" : "✗"}</span>{k.replace(/_/g, " ")}</div>)}</div>
            </div>) : null}
        </div>
      </Card>
      <Card title="Persona suite">
        <div className="rm-stack">
          <p className="rm-mini">Runs every caller of the chosen set against the chosen prompt and checks each against its answer key. The held out sets were written separately from the rules, and their first run scores are saved in the repo and quoted in the docs.</p>
          <div className="sx-row"><Button variant="primary" disabled={!canWrite} disabledReason="Viewers cannot run the suite" onClick={async () => { await run.mutateAsync(); }}><FlaskConical size={14} aria-hidden />Run the suite on version {agent.versions.find((v) => String(v.id) === ver)?.version}</Button></div>
          {suite ? (
            <div className="rm-stack">
              <div className="sx-row"><Badge tone={suite.pass_rate >= 0.9 ? "success" : suite.pass_rate >= 0.6 ? "warning" : "danger"}>{suite.passed} of {suite.personas} passed ({Math.round(suite.pass_rate * 100)}%)</Badge><Badge>{suite.checks_passed} of {suite.checks_total} checks</Badge><Badge tone="warning">offline rules, not a language model</Badge></div>
              <ul className="rm-list">{Object.entries(suite.by_category).map(([k, v]) => <li key={k} className="rm-item" style={{ cursor: "default" }}><span className="rm-item__top"><strong>{k.replace(/_/g, " ")}</strong><Badge tone={v.startsWith("1/") ? "success" : "danger"}>{v}</Badge></span></li>)}</ul>
              {suite.failures.length ? <><h3 style={{ margin: "8px 0 0" }}>Misses</h3><ul className="rm-list">{suite.failures.map((f) => <li key={f.id} className="rm-item" style={{ cursor: "default" }}><span className="rm-item__top"><strong>{f.id} {f.category.replace(/_/g, " ")}</strong><Badge tone="danger">{f.disposition}</Badge></span><span className="rm-mini">Did not pass: {f.failed_checks.map(checkLabel).join(", ")}</span></li>)}</ul></> : <EmptyState title="No misses" body="Every persona passed its answer key on this set." />}
            </div>) : null}
        </div>
      </Card>
    </div>
  );
}

export default function AgentsPage() {
  const q = useQuery({ queryKey: ["agents"], queryFn: () => get<Agent[]>("/agents") });
  const me = useQuery({ queryKey: ["me"], queryFn: () => get<Me>("/auth/me") });
  const [sel, setSel] = useState<number | null>(null);
  if (q.isError) return <div className="rm-page"><PageHead title="Agents and prompts" /><LoadError error={q.error} onRetry={() => q.refetch()} what="agents" /></div>;
  if (!q.data) return <div className="rm-page"><PageHead title="Agents and prompts" /><ListSkeleton /></div>;
  const agent = q.data.find((a) => a.id === sel) ?? q.data[0]!;
  return (
    <div className="rm-page">
      <PageHead title="Agents and prompts" sub="Each change to a prompt is a new version. Compare, test it on scripted callers, then activate it or send a share of calls to it." />
      <div className="sx-row">
        <SegmentedControl label="Agent" value={String(agent.id)} onChange={(v) => setSel(Number(v))} options={q.data.map((a) => ({ value: String(a.id), label: `${a.name} (${a.kind})` }))} />
        <span className="rm-mini">Voice {agent.voice} ({agent.voice_source}). Transfers go to {agent.transfer_number || "no number"}. Voice quality is judged by a person on a real test call: see the voice options guide.</span>
      </div>
      <TabsView items={[{ value: "edit", label: "Prompts", content: <Editor agent={agent} me={me.data} /> }, { value: "test", label: "Simulator and persona suite", content: <Simulator agent={agent} /> }]} defaultValue="edit" />
    </div>
  );
}
