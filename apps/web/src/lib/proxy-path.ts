/** What the web server may forward to the private API, and which visitor address it passes on. Plain functions so they can be tested without a server. */

/** The first part of every API path the pages use. Anything else (health, docs, openapi.json, webhooks, tools, sign in) is not forwarded. */
const ALLOWED_FIRST = new Set([
  "overview", "calls", "campaigns", "agents", "personas", "numbers", "qa", "followups", "suppressions", "approvals", "audit", "integrations", "settings", "metrics", "demo", "auth", "events",
]);
const AUTH_OK = new Set(["auth/me", "auth/logout"]);

/** The path to forward, or null when it must be refused. Next hands over each segment already decoded, so a segment may hold a slash, dots or a percent sign. */
export function forwardPath(segments: string[]): string | null {
  if (segments.length === 0) return null;
  for (const s of segments) {
    if (s === "" || s === "." || s === ".." || /[\/\\%\u0000-\u001f\u007f]/.test(s)) return null;
  }
  const joined = segments.join("/");
  const first = segments[0] ?? "";
  if (!ALLOWED_FIRST.has(first)) return null;
  if (first === "auth" && !AUTH_OK.has(joined)) return null;
  return joined;
}

/** The address the platform in front of this server saw: the LAST entry of x-forwarded-for. Earlier entries were written by the visitor and are not trusted. */
export function visitorAddress(header: string | null): string {
  if (!header) return "";
  const parts = header.split(",").map((p) => p.trim()).filter(Boolean);
  const last = parts[parts.length - 1] ?? "";
  return /^[0-9a-fA-F:.]{2,45}$/.test(last) ? last : "";
}
