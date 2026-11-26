"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Bot, ClipboardCheck, Gauge, Hash, LogOut, Megaphone, Pause, PhoneCall, Plug, Radio, Send, ShieldCheck } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AppShell, Badge, Button, CommandPalette, ConfirmDialog, notify, useTheme, type PaletteItem } from "@sendora/ui-kit";
import { api, get, post } from "@/lib/api";
import { useLiveRefresh, useMe, useRole, useSettings } from "@/lib/hooks";
import type { Overview } from "@/lib/types";

const NAV = [
  { id: "/", label: "Overview", icon: Gauge },
  { id: "/live", label: "Live console", icon: Radio },
  { id: "/calls", label: "Call log", icon: PhoneCall },
  { id: "/campaigns", label: "Campaigns", icon: Megaphone },
  { id: "/agents", label: "Agents and prompts", icon: Bot },
  { id: "/numbers", label: "Numbers and compliance", icon: Hash },
  { id: "/qa", label: "QA review", icon: ClipboardCheck },
  { id: "/followups", label: "Follow ups and approvals", icon: Send },
  { id: "/metrics", label: "Metrics", icon: BarChart3 },
  { id: "/integrations", label: "Integrations", icon: Plug },
  { id: "/audit", label: "Audit log", icon: ShieldCheck },
];

export function AppFrame({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const qc = useQueryClient();
  const me = useMe();
  const { canWrite, owner } = useRole();
  const settings = useSettings();
  const overview = useQuery({ queryKey: ["overview"], queryFn: () => get<Overview>("/overview") });
  const { setChoice } = useTheme();
  const [palette, setPalette] = useState(false);
  const [confirmKill, setConfirmKill] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  useLiveRefresh();

  const killOn = !!settings.data?.kill_switch;
  const active = NAV.find((n) => (n.id === "/" ? path === "/" : path.startsWith(n.id)))?.id ?? "/";
  const demo = me.data?.demo_mode ?? false;
  const refresh = () => qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" });

  const run = useMutation({
    mutationFn: () => post<{ dial: { placed: number; drafted: number; blocked: number; halted?: boolean } }>("/demo/tick"),
    onSuccess: (r) => { if (r.dial.halted) notify.info("Nothing ran: the kill switch is on. Turn it off first."); else notify.success(`Ran every job. Placed ${r.dial.placed} demo calls, drafted ${r.dial.drafted}, held back ${r.dial.blocked}.`); refresh(); },
    onError: (e: Error) => notify.error("The run failed", e.message),
  });
  const advance = useMutation({
    mutationFn: (hours: number) => post("/demo/advance", { hours }),
    onSuccess: () => { notify.info("Moved the demo clock forward."); refresh(); },
  });
  const toggleKill = useMutation({
    mutationFn: (on: boolean) => post("/settings", { kill_switch: on }),
    onSuccess: () => { refresh(); qc.invalidateQueries({ queryKey: ["settings"] }); },
    onError: (e: Error) => notify.error("Could not change the kill switch", e.message),
  });
  const reset = useMutation({
    mutationFn: () => post("/demo/reset"),
    onSuccess: () => { notify.success("Demo data reset."); refresh(); },
    onError: (e: Error) => notify.error("Could not reset", e.message),
  });

  // The palette lists "G then 1" to "G then 9" next to the first nine pages, so they have to work: press G, then the number, outside text fields.
  useEffect(() => {
    let armed = 0;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.closest("[role=dialog], [role=alertdialog]"))) return; // typing, or a dialog is open
      if (e.key.toLowerCase() === "g") { armed = Date.now(); return; }
      if (armed && Date.now() - armed < 1500 && /^[1-9]$/.test(e.key)) { armed = 0; const target = NAV[Number(e.key) - 1]; if (target) router.push(target.id); return; }
      armed = 0;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  const items: PaletteItem[] = useMemo(() => [
    ...NAV.map((n, i) => ({ id: `go-${n.id}`, label: `Go to ${n.label}`, group: "Navigate", shortcut: i < 9 ? ["G", String(i + 1)] : undefined, onSelect: () => router.push(n.id) })),
    { id: "signout", label: "Sign out", group: "Account", onSelect: () => void api("/session", { method: "DELETE" }).catch(() => null).then(() => window.location.assign("/login")) },
    ...(owner ? [killOn ? { id: "kill", label: "Turn the kill switch off", group: "Account", onSelect: () => toggleKill.mutate(false) } : { id: "kill", label: "Pause everything (kill switch)", group: "Account", onSelect: () => setConfirmKill(true) }] : []),
    { id: "dark", label: "Switch to dark theme", group: "Actions", onSelect: () => setChoice("dark") },
    { id: "light", label: "Switch to light theme", group: "Actions", onSelect: () => setChoice("light") },
    ...(demo && canWrite ? [{ id: "run", label: "Run every job now", group: "Demo", onSelect: () => void run.mutateAsync() }, { id: "adv", label: "Move the demo clock forward one day", group: "Demo", onSelect: () => void advance.mutateAsync(24) }] : []),
    ...(demo && owner ? [{ id: "reset", label: "Reset the demo data", group: "Demo", onSelect: () => setConfirmReset(true) }] : []),
  ], [router, setChoice, demo, run, advance, owner, canWrite, killOn, toggleKill]);

  const s = settings.data;
  const o = overview.data;
  return (
    <>
      {/* One status strip that is always there, so nothing below it jumps when the mode is known. */}
      {s?.kill_switch ? (
        <div className="rm-banner rm-banner--danger" role="status"><strong>Kill switch is on.</strong> <span className="rm-hide-sm">No call is placed and no message is sent.</span> <Button size="sm" variant="ghost" disabled={!owner} disabledReason="Only the owner can turn it off" onClick={async () => { await toggleKill.mutateAsync(false); }}>Turn it off</Button></div>
      ) : s?.effective_mode === "draft" ? (
        <div className="rm-banner" role="status"><strong>Draft mode.</strong> <span className="rm-hide-sm">No call is placed and no text is sent. Drafts are saved.</span></div>
      ) : s && demo ? (
        <div className="rm-banner rm-banner--info" role="status"><strong>Demo mode.</strong> <span className="rm-grow rm-hide-sm">Sample people and an offline stand in agent. No call is placed.</span><span className="rm-grow show-sm-only" />
          <Button size="sm" variant="primary" disabled={!canWrite} disabledReason="Viewers cannot run jobs" onClick={async () => { await run.mutateAsync(); }}>Run now</Button>
          <Button size="sm" disabled={!canWrite} disabledReason="Viewers cannot move the clock" onClick={async () => { await advance.mutateAsync(24); }}>+1 day</Button></div>
      ) : s ? (
        <div className="rm-banner rm-banner--live" role="status"><strong>Live.</strong> <span className="rm-hide-sm">Real calls are placed, inside the limits.</span></div>
      ) : (
        <div className="rm-banner rm-banner--info" role="status">Checking the calling mode...</div>
      )}
      <AppShell
        productName="Ringlark"
        nav={NAV.map((n) => ({ ...n, count: n.id === "/qa" ? o?.flagged || undefined : n.id === "/followups" ? o?.pending_approvals || undefined : undefined }))}
        activeId={active}
        onNavigate={(id) => router.push(id)}
        onOpenPalette={() => setPalette(true)}
        breadcrumbs={["Ringlark", NAV.find((n) => n.id === active)?.label ?? ""]}
        topRight={
          <>
            {owner ? <Button size="sm" variant="ghost" feedback={false} className="rm-iconify" aria-label={killOn ? "Turn it off (kill switch)" : "Pause all"} onClick={() => (killOn ? toggleKill.mutate(false) : setConfirmKill(true))}><Pause size={14} aria-hidden /><span className="rm-hide-sm">{killOn ? "Turn it off" : "Pause all"}</span></Button> : null}
            {me.data ? <span className="rm-hide-sm"><Badge tone="accent">{me.data.role}</Badge></span> : null}
            <Button size="sm" variant="ghost" feedback={false} className="rm-iconify" aria-label="Sign out" onClick={async () => { await api("/session", { method: "DELETE" }).catch(() => null); window.location.assign("/login"); }}><LogOut size={14} aria-hidden /><span className="rm-hide-sm">Sign out</span></Button>
          </>
        }
      >
        {children}
      </AppShell>
      <CommandPalette items={items} open={palette} onOpenChange={setPalette} />
      <ConfirmDialog open={confirmKill} onOpenChange={setConfirmKill} title="Pause everything?" description="The kill switch stops every call and every message at once. You can turn it off again from the banner or the top bar." confirmLabel="Pause all" destructive onConfirm={() => void toggleKill.mutateAsync(true)} />
      <ConfirmDialog open={confirmReset} onOpenChange={setConfirmReset} title="Reset the demo?" description="This puts the sample seed data back and clears everything you did in the demo." confirmLabel="Reset" destructive onConfirm={() => void reset.mutateAsync()} />
    </>
  );
}
