"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Card, Field, Button, notify } from "@sendora/ui-kit";
import { useState } from "react";
import { ListSkeleton, LoadError, PageHead } from "@/components/Parts";
import { SOURCE_LABEL } from "@/lib/labels";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { NumberRow, Settings, Suppression } from "@/lib/types";

const STEPS: { key: string; title: string; body: string }[] = [
  { key: "caller_id_registered", title: "Caller ID registered", body: "Your carrier shows your business name on the call. Done in your Telnyx account for your own business." },
  { key: "stir_shaken_attestation", title: "STIR/SHAKEN attestation", body: "The carrier signs your calls so other carriers can trust them. Ask your carrier which level you have." },
  { key: "a2p_10dlc_brand", title: "Texting: brand registered (A2P 10DLC)", body: "Needed to text US numbers from a normal 10 digit number. Each client registers their own business." },
  { key: "a2p_10dlc_campaign", title: "Texting: campaign registered (A2P 10DLC)", body: "Describes what you text and why. Texting stays off until this is done." },
  { key: "recording_notice_reviewed", title: "Recording notice reviewed", body: "The greeting already says calls may be recorded. Check what your place requires. This is not legal advice." },
];

export default function NumbersPage() {
  const qc = useQueryClient();
  const nums = useQuery({ queryKey: ["numbers"], queryFn: () => get<NumberRow[]>("/numbers") });
  const sup = useQuery({ queryKey: ["suppressions"], queryFn: () => get<Suppression[]>("/suppressions") });
  const st = useQuery({ queryKey: ["settings"], queryFn: () => get<Settings>("/settings") });
  const [phone, setPhone] = useState("");
  const { owner, canWrite } = useRole();
  const tick = useMutation({ mutationFn: (v: { id: number; step: string; done: boolean }) => post(`/numbers/${v.id}/checklist`, { step: v.step, done: v.done }), onSuccess: () => qc.invalidateQueries({ queryKey: ["numbers"] }), onError: (e: Error) => notify.error("Only the owner can change this", e.message) });
  const add = useMutation({ mutationFn: () => post<{ added: boolean }>("/suppressions", { phone }), onSuccess: (r) => { notify[r.added ? "success" : "info"](r.added ? "Added. This number will never be called or texted." : "That number was already on the list."); setPhone(""); qc.invalidateQueries({ predicate: (x) => x.queryKey[0] !== "me" }); }, onError: (e: Error) => notify.error("Could not add it", e.message) });
  const unlist = useMutation({ mutationFn: (v: { id: number; note: string }) => post(`/suppressions/${v.id}/remove`, { note: v.note }), onSuccess: () => { notify.success("Taken off the list. It is in the audit log."); qc.invalidateQueries({ predicate: (x) => x.queryKey[0] !== "me" }); }, onError: (e: Error) => notify.error("Could not take it off", e.message) });
  if (nums.isError) return <div className="rm-page"><PageHead title="Numbers and compliance" /><LoadError error={nums.error} onRetry={() => nums.refetch()} what="numbers" /></div>;
  if (!nums.data) return <div className="rm-page"><PageHead title="Numbers and compliance" /><ListSkeleton /></div>;
  return (
    <div className="rm-page">
      <PageHead title="Numbers and compliance" sub="Rules about calling and texting differ by country and state, and this page is not legal advice. It records what you did with your carrier and shows the rules the dialer enforces." />
      {nums.data.map((n) => {
        const done = STEPS.filter((s) => n.checklist[s.key]).length;
        return (
          <Card key={n.id} title={`${n.label}  ${n.e164}`}>
            <div className="rm-stack">
              <div className="sx-row"><Badge>{n.direction}</Badge><Badge>agent {n.agent || "none"}</Badge><Badge tone={done === STEPS.length ? "success" : "warning"}>{done} of {STEPS.length} steps done</Badge></div>
              <ul className="rm-list">{STEPS.map((s) => (
                <li key={s.key} className="rm-item" style={{ cursor: "default" }}>
                  <span className="rm-item__top"><label className="sx-row" style={{ cursor: "pointer" }}><input type="checkbox" disabled={!owner} title={owner ? undefined : "Only the owner can tick these"} checked={!!n.checklist[s.key]} onChange={(e) => tick.mutate({ id: n.id, step: s.key, done: e.target.checked })} /><strong>{s.title}</strong></label>{n.checklist[s.key] ? <Badge tone="success">done</Badge> : <Badge>not done</Badge>}</span>
                  <span className="rm-mini">{s.body}</span></li>))}</ul>
              <p className="rm-mini">A tick records your word. Ringlark cannot check it with the carrier.</p>
            </div>
          </Card>);
      })}
      <div className="rm-cols">
        <Card title="Rules in force on every call">
          <ul className="rm-list">{[
            `Hours: ${st.data?.window ?? "..."}, weekdays only, using the person's own time zone`,
            "Never a number on the do not call list, or one that took back consent",
            "A daily cap per campaign and a limit on tries, on different days",
            "The greeting always says it is an AI and that the call may be recorded; no greeting, no call",
            "Voicemail only when the campaign allows it and the message says who is calling and why",
            "A phone menu means hang up (or press one configured key once). Never a loop",
            "The kill switch stops everything; draft mode places no call",
          ].map((t) => <li key={t} className="rm-item" style={{ cursor: "default" }}>{t}</li>)}</ul>
        </Card>
        <Card title={sup.data ? `Do not call list (${sup.data.length})` : "Do not call list"}>
          <div className="rm-stack">
            <div className="sx-row" style={{ alignItems: "flex-end" }}><Field label="Add a number" value={phone} onChange={setPhone} placeholder="+14155550100" validate={(v) => (v && !/^\+[1-9]\d{6,14}$/.test(v.replace(/[\s()-]/g, "")) ? "Use a full number with the country code, like +14155550100" : null)} /><Button onClick={async () => { await add.mutateAsync(); }} disabled={!phone || !canWrite} disabledReason={canWrite ? "Type a number first" : "Viewers cannot change the list"}>Add</Button></div>
            {sup.isError ? <LoadError error={sup.error} onRetry={() => sup.refetch()} what="the do not call list" /> : !sup.data ? <ListSkeleton rows={3} /> : <ul className="rm-list" tabIndex={0} aria-label="Do not call list" style={{ maxHeight: 240, overflow: "auto" }}>{(sup.data ?? []).slice(0, 50).map((s) => <li key={s.id} className="rm-item" style={{ cursor: "default" }}><span className="rm-item__top"><strong>{s.phone}</strong><span className="rm-mini">{SOURCE_LABEL(s.source)}</span></span><span className="rm-mini">{s.reason}{owner ? <> · <Button size="sm" aria-label={`Take off the list, ${s.phone}`} onClick={async () => { const why = window.prompt("Why is this number being taken off the list? This is written to the audit log."); if (why && why.trim().length >= 5) await unlist.mutateAsync({ id: s.id, note: why.trim() }); }}>Take off the list</Button></> : null}</span></li>)}</ul>}
          </div>
        </Card>
      </div>
    </div>
  );
}
