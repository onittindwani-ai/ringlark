"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { AreaChart, Badge, Card, CountUp, EmptyState, Gauge, Stat } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, OutcomeBadge, PageHead } from "@/components/Parts";
import { get } from "@/lib/api";
import { shortDay, why } from "@/lib/labels";
import type { Overview, Settings } from "@/lib/types";

export default function OverviewPage() {
  const q = useQuery({ queryKey: ["overview"], queryFn: () => get<Overview>("/overview") });
  const st = useQuery({ queryKey: ["settings"], queryFn: () => get<Settings>("/settings") });
  if (q.isError) return <div className="rm-page"><PageHead title="Overview" /><LoadError error={q.error} onRetry={() => q.refetch()} what="the overview" /></div>;
  if (!q.data) return <div className="rm-page"><PageHead title="Overview" /><ListSkeleton rows={4} /></div>;
  const o = q.data;
  const maxD = Math.max(1, ...o.dispositions.map((d) => d.count));
  // Never say "Live" when the mode could not be read: that is the one word that must not be a guess.
  const mode = !st.data ? "not known yet" : st.data.kill_switch ? "Kill switch on" : st.data.effective_mode === "draft" ? "Draft mode" : st.data.demo_mode ? "Demo mode" : "Live";
  return (
    <div className="rm-page">
      <PageHead title="Overview" sub="Is anything being called that should not be, how the last calls went, and what needs a person." />
      <div className="rm-top">
        <Card title="Safe to dial?" lift>
          <div className="rm-hero">
            <div className="rm-ring-wrap"><Gauge value={o.avg_qa !== null ? o.avg_qa / 100 : 0} size={144} label="average QA" display={o.avg_qa !== null ? `${Math.round(o.avg_qa)}` : "n/a"} /></div>
            <div className="rm-stack">
              <div><span className="rm-big"><CountUp value={o.suppressed} /></span> <span className="rm-mini">numbers on the do not call list</span></div>
              <div className="rm-mini">Mode: <strong>{mode}</strong>. Calling window: {st.data?.window ?? "not known yet"}. {o.drafted ? `${o.drafted} calls were saved as drafts.` : "No drafts waiting."} Every call checks hours in the person's own time zone, the do not call list, consent, the daily cap and the retry limit before it is dialled.</div>
              <div className="sx-row">{o.flagged ? <Link href="/qa"><Badge tone="warning">{o.flagged} calls to read</Badge></Link> : <Badge tone="success">No flagged calls</Badge>}<Link href="/followups"><Badge tone={o.pending_approvals ? "accent" : "neutral"}>{o.pending_approvals} approvals</Badge></Link></div>
            </div>
          </div>
        </Card>
        <div className="rm-stats2">
          <Card><Stat label="Calls placed" value={o.calls} note={`${o.calls_today} today`} /></Card>
          <Card><Stat label="Meetings booked" value={o.booked} note={`${(o.book_rate * 100).toFixed(0)}% of finished calls`} /></Card>
          <Card><Stat label="Talked to a person" value={Math.round(o.talk_rate * 100)} format={(n) => `${n}%`} note="not machine or menu" /></Card>
          <Card><Stat label="Campaigns running" value={o.campaigns_running} note={`${o.followups_pending} follow ups waiting`} /></Card>
        </div>
      </div>
      <div className="rm-cols">
        <Card title="Calls and bookings, last 7 days">
          {o.series.some((d) => d.calls) ? <AreaChart data={o.series.map((d) => ({ ...d, day: shortDay(d.day) }))} xKey="day" series={[{ key: "calls", label: "Calls" }, { key: "booked", label: "Booked" }]} height={200} /> : <EmptyState title="No calls yet" body="Use Run now in the top bar and the first demo calls will show up here." />}
        </Card>
        <Card title="How calls ended">
          {o.dispositions.length ? (
            <div className="rm-funnel" role="list" aria-label="Calls by outcome">
              {o.dispositions.map((d) => <div key={d.code} className="rm-funnel__row" role="listitem"><OutcomeBadge code={d.code} /><div className="rm-funnel__bar"><div className="rm-funnel__fill" style={{ width: `${(d.count / maxD) * 100}%` }} /></div><span className="sx-num" style={{ textAlign: "right" }}>{d.count}</span></div>)}
            </div>
          ) : <EmptyState title="Nothing finished yet" body="Outcomes appear here as calls end." />}
        </Card>
      </div>
      <Card title="Held back by the rules">
        {o.blocked.length ? <ul className="rm-list">{o.blocked.map((b) => <li key={b.reason} className="rm-item" style={{ cursor: "default" }}><span className="rm-item__top"><strong>{why(b.reason)}</strong><Badge tone="warning">{b.count}</Badge></span></li>)}</ul> : <p className="rm-mini">Nothing has been held back yet. Run the jobs and every skipped person will be listed here with the reason.</p>}
      </Card>
    </div>
  );
}
