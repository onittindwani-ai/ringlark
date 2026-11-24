"use client";
import { Pause, Play, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge, Button, SegmentedControl } from "@sendora/ui-kit";
import { fmtMs, outcome } from "@/lib/labels";
import type { CallDetail } from "@/lib/types";

type Mode = "live" | "scrub";
const STATE_LABEL: Record<string, string> = { ringing: "Ringing", connected: "Connected", speaking: "Agent speaking", listening: "Caller speaking", thinking: "Agent thinking", ended: "Ended" };

/** The signature of Ringlark. A recorded call plays back in time: waveform, streaming transcript and agent state move together.
 *  `live` shows only what has been said so far. `scrub` shows the whole transcript and lets you drag to any moment. */
export function CallPlayer({ detail, mode, autoPlay = false }: { detail: CallDetail; mode: Mode; autoPlay?: boolean }) {
  const total = Math.max(detail.duration_ms + 1200, 3000);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(autoPlay);
  const [speed, setSpeed] = useState<"1" | "4">("1");
  const tRef = useRef(0);
  const raf = useRef<number | null>(null);
  const last = useRef(0);
  const listRef = useRef<HTMLOListElement | null>(null);

  useEffect(() => { tRef.current = 0; setT(0); setPlaying(autoPlay); }, [detail.id, autoPlay]);
  const step = useCallback((now: number) => {
    const dt = now - last.current; last.current = now;
    tRef.current = Math.min(total, tRef.current + dt * Number(speed));
    setT(tRef.current);
    if (tRef.current >= total) { setPlaying(false); return; }
    raf.current = requestAnimationFrame(step);
  }, [speed, total]);
  useEffect(() => {
    if (!playing) return;
    last.current = performance.now();
    raf.current = requestAnimationFrame(step);
    return () => { if (raf.current) cancelAnimationFrame(raf.current); };
  }, [playing, step]);
  const seek = (ms: number) => { tRef.current = ms; setT(ms); };

  const turns = detail.turns.filter((x) => x.text);
  const current = turns.find((x) => t >= x.start_ms && t < x.end_ms);
  const ended = t >= total - 1000 || (turns.length > 0 && t >= turns[turns.length - 1]!.end_ms + 400);
  const state = ended ? "ended" : t < 700 ? "ringing" : current ? (current.speaker === "agent" ? "speaking" : "listening") : t < 1200 ? "connected" : "thinking";
  const w = detail.waveform;
  const played = (i: number) => (i / w.bars) * w.duration_ms <= t;

  useEffect(() => {
    if (playing && listRef.current) listRef.current.querySelector("[data-current='true']")?.scrollIntoView({ block: "nearest" });
  }, [current?.position, playing]);

  const words = (txt: string, start: number, end: number) => {
    if (mode === "scrub" || t >= end) return txt;
    const all = txt.split(" ");
    const n = Math.ceil((all.length * Math.max(t - start, 0)) / Math.max(end - start, 1));
    return all.slice(0, n).join(" ");
  };
  const visible = mode === "live" ? turns.filter((x) => t >= x.start_ms) : turns;
  const o = outcome(detail.disposition);

  return (
    <div className="rm-player">
      <div className="rm-player__top">
        <span className={`rm-state rm-state--${state}`} role="status" aria-live="polite"><span className="rm-state__dot" aria-hidden />{STATE_LABEL[state]}</span>
        {ended ? <Badge tone={o.tone}>{o.label}</Badge> : null}
        <span className="rm-mini sx-num" style={{ marginLeft: "auto" }}>{fmtMs(t)} / {fmtMs(detail.duration_ms)}</span>
      </div>
      <div className="rm-wave" aria-hidden={mode === "live"}>
        <svg viewBox={`0 0 ${w.bars} 40`} preserveAspectRatio="none" role="img" aria-label="Synthetic waveform of the call, agent above and caller below">
          {w.agent.map((v, i) => <rect key={`a${i}`} x={i + 0.15} width={0.7} y={20 - v * 18} height={Math.max(v * 18, 0.4)} className={played(i) ? "rm-bar-agent" : "rm-bar-off"} rx={0.3} />)}
          {w.caller.map((v, i) => <rect key={`c${i}`} x={i + 0.15} width={0.7} y={20.8} height={Math.max(v * 18, 0.4)} className={played(i) ? "rm-bar-caller" : "rm-bar-off"} rx={0.3} />)}
          <line x1={(t / w.duration_ms) * w.bars} x2={(t / w.duration_ms) * w.bars} y1={0} y2={40} className="rm-playhead" />
        </svg>
        <span className="rm-wave__note">Synthetic waveform, generated from the turn times. Not recorded audio.</span>
      </div>
      <div className="rm-controls">
        <Button size="sm" feedback={false} onClick={() => { if (t >= total) seek(0); setPlaying((p) => !p); }} aria-label={playing ? "Pause" : "Play"}>{playing ? <Pause size={14} aria-hidden /> : <Play size={14} aria-hidden />}{playing ? "Pause" : "Play"}</Button>
        <Button size="sm" variant="ghost" feedback={false} onClick={() => { seek(0); setPlaying(true); }} aria-label="Restart"><RotateCcw size={14} aria-hidden />Restart</Button>
        <SegmentedControl label="Speed" value={speed} onChange={setSpeed} options={[{ value: "1", label: "1x" }, { value: "4", label: "4x" }]} />
        {mode === "scrub" ? <input className="rm-scrub" type="range" min={0} max={total} step={50} value={Math.round(t)} aria-label="Call position" aria-valuetext={`${fmtMs(t)} of ${fmtMs(detail.duration_ms)}`} onChange={(e) => { setPlaying(false); seek(Number(e.target.value)); }} /> : null}
      </div>
      <ol className="rm-transcript" ref={listRef} aria-label="Transcript">
        {visible.length === 0 ? <li className="rm-mini">The call is connecting...</li> : null}
        {visible.map((x) => {
          const cur = current?.position === x.position;
          return (
            <li key={x.position} data-current={cur} className={`rm-line rm-line--${x.speaker} ${mode === "scrub" && t < x.start_ms ? "rm-line--future" : ""}`}>
              <button type="button" className="rm-line__btn" onClick={() => { setPlaying(false); seek(x.start_ms); }} disabled={mode === "live"} aria-label={`Jump to ${fmtMs(x.start_ms)}`}>
                <span className="rm-line__who">{x.speaker === "agent" ? "Agent" : "Caller"} <span className="sx-num">{fmtMs(x.start_ms)}</span></span>
                <span className="rm-line__text">{words(x.text, x.start_ms, x.end_ms)}{cur && mode === "live" ? <span className="rm-caret" aria-hidden /> : null}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function usePlayerSummary(detail: CallDetail | undefined) {
  return useMemo(() => (detail ? outcome(detail.disposition) : null), [detail]);
}
