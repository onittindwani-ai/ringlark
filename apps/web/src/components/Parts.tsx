"use client";
import { forwardRef, type ReactNode, type TextareaHTMLAttributes } from "react";
import { Badge, ErrorState, Skeleton, type BadgeTone } from "@sendora/ui-kit";
import { ApiError } from "@/lib/api";

export function PageHead({ title, sub, actions }: { title: string; sub?: string; actions?: ReactNode }) {
  return (
    <div className="rm-head">
      <div>
        <h1 className="rm-title">{title}</h1>
        {sub ? <p className="rm-sub">{sub}</p> : null}
      </div>
      {actions ? <div className="sx-row">{actions}</div> : null}
    </div>
  );
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string; error?: string | null }>(function Textarea({ label, hint, error, id, ...rest }, ref) {
  const tid = id ?? `ta-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div className="sx-field">
      <label className="sx-label" htmlFor={tid}>{label}</label>
      <textarea ref={ref} id={tid} className="rm-textarea" aria-invalid={error ? true : undefined} aria-describedby={error ? `${tid}-e` : hint ? `${tid}-h` : undefined} {...rest} />
      {error ? <span id={`${tid}-e`} className="sx-field__error" role="alert">{error}</span> : hint ? <span id={`${tid}-h`} className="sx-field__hint">{hint}</span> : null}
    </div>
  );
}) ;

export function LoadError({ error, onRetry, what }: { error: unknown; onRetry: () => void; what: string }) {
  const msg = error instanceof ApiError ? error.message : "Something went wrong.";
  return <ErrorState title={`Could not load ${what}`} whatHappened={msg} howToFix="Check that the API is running and you are signed in, then try again." onRetry={onRetry} />;
}

export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div style={{ display: "grid", gap: 13, padding: 8 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <div key={i} style={{ display: "grid", gap: 8 }}><Skeleton height={16} width="45%" /><Skeleton height={13} width="80%" /></div>)}
    </div>
  );
}

import { outcome } from "@/lib/labels";
export const OutcomeBadge = ({ code }: { code: string }) => { const o = outcome(code); return <Badge tone={o.tone}>{o.label}</Badge>; };
