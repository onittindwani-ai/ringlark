import type { BadgeTone } from "@sendora/ui-kit";

export const OUTCOME: Record<string, { label: string; tone: BadgeTone }> = {
  booked: { label: "Booked", tone: "success" }, interested_callback: { label: "Call back", tone: "accent" }, not_interested: { label: "Not interested", tone: "neutral" },
  wrong_number: { label: "Wrong number", tone: "warning" }, do_not_call: { label: "Do not call", tone: "danger" }, voicemail_left: { label: "Voicemail left", tone: "neutral" },
  voicemail_no_message: { label: "Machine, no message", tone: "neutral" }, ivr_no_human: { label: "Phone menu", tone: "neutral" }, hostile_ended: { label: "Upset caller", tone: "warning" },
  transferred: { label: "Transferred", tone: "accent" }, no_answer: { label: "No answer", tone: "neutral" }, needs_review: { label: "Needs a look", tone: "warning" },
};
export const outcome = (code: string) => OUTCOME[code] ?? { label: code ? code.replace(/_/g, " ") : "In progress", tone: "neutral" as BadgeTone };

export const WHY: Record<string, string> = {
  ok: "Can be called now", outside_hours: "Closed in their time zone", do_not_call: "On the do not call list", consent_revoked: "Took back consent", bad_number: "Not a full phone number",
  unknown_timezone: "Time zone unknown", daily_cap: "Daily cap reached", max_attempts: "All attempts used", retry_same_day: "Already tried today", retry_too_soon: "Too soon to retry",
  no_ai_disclosure: "Greeting lacks the AI notice", person_booked: "Already booked, no more calls", person_done: "Finished, no more calls", person_suppressed: "Never to be called", campaign_not_running: "Waiting for the campaign to start", kill_switch: "Kill switch is on", draft_mode: "Draft mode: nothing is dialled", call_in_progress: "A call is already running", no_consent_on_file: "No consent on file",
};
export const why = (r: string) => WHY[r] ?? r.replace(/_/g, " ");

export const QA_LABEL: Record<string, string> = {
  disclosed_ai: "Said it is an AI", recording_notice: "Gave the recording notice", no_human_claim: "Never claimed to be human", honoured_stop: "Honoured a request to stop", no_invented_price: "Did not make up a price",
  short_turns: "Kept replies short", ended_cleanly: "Ended with an outcome", no_prompt_leak: "Kept its instructions private",
};

/** The QA note starts with "Failed: ended_cleanly, ..." for the code. The checks are listed in plain words next to it, so only the rest of the note is shown. */
export const readableNote = (note: string): string => note.replace(/^Failed: [a-z_]+(, [a-z_]+)*\.?\s*/, "").trim();
/** A check name from the scorer in plain words ("ended_cleanly" is "Ended with an outcome"). Persona checks have their own names, so unknown ones just lose the underscores. */
export const checkLabel = (k: string) => QA_LABEL[k] ?? k.replace(/_/g, " ");

export const fmtMs = (ms: number) => { const s = Math.max(0, Math.floor(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };

/** "2026-11-19" as "Nov 19" for a chart axis. The day is a plain calendar date, so it is formatted in UTC and never shifts. */
export const shortDay = (iso: string) => {
  const d = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
};

export const AUDIT_ACTION: Record<string, string> = {
  "call.processed": "Call finished and scored", "call.taken_over": "Call taken over", "call.taken_over_practice": "Take over clicked on a replay", "call.transfer_practice": "Transfer clicked on a replay", "call.transferred": "Call transferred",
  "campaign.created": "Campaign created", "campaign.start": "Campaign started", "campaign.pause": "Campaign paused", "number.checklist": "Number checklist changed", "prompt.activated": "Prompt version activated",
  "prompt.split_set": "Split test changed", "prompt.version_added": "Prompt version saved", "qa.reviewed": "Call marked as read", "settings.force_draft": "Draft mode changed", "settings.kill_switch": "Kill switch changed",
  "sms.opt_out": "Text opt out recorded", "suppression.added": "Number added to the do not call list", "targets.imported": "People imported", "approval.requested": "Approval asked for", "approval.approved": "Approved", "approval.rejected": "Rejected",
};
export const auditAction = (a: string) => AUDIT_ACTION[a] ?? a.replace(/[._]/g, " ");
/** "call:74" as "Call 74". Anything else is shown as it is. */
export const auditTarget = (t: string | null) => {
  if (!t) return "";
  const m = /^([a-z]+):(\d+)$/.exec(t);
  const kind = m?.[1], id = m?.[2];
  if (!kind || !id) return t;
  return kind === "phone" ? `Phone ending ${id}` : `${kind.charAt(0).toUpperCase()}${kind.slice(1)} ${id}`;
};

/** Where a do not call entry came from: "call:74" is the call where the person asked, "seed" is the practice's own starting list. */
export const SOURCE_LABEL = (src: string) => (src === "seed" ? "Starting list" : /^call:\d+$/.test(src) ? `Call ${src.slice(5)}` : src);

/** Where a person stands in a campaign, in plain words. Used by Metrics (long form) and the campaign chips (short form). */
export const PERSON_STATUS: Record<string, string> = { new: "Not called yet", queued: "Queued", contacted: "Called, may be tried again", booked: "Booked", done: "Finished, no more calls", suppressed: "Never to be called" };
export const PERSON_CHIP: Record<string, string> = { new: "not called yet", queued: "queued", contacted: "called", booked: "booked", done: "finished", suppressed: "never to call" };
/** A follow up's state: "pending" is not a word an owner uses. */
export const FOLLOWUP_STATUS: Record<string, string> = { pending: "waiting", sent: "sent", drafted: "saved as a draft", blocked: "not sent", rejected: "rejected" };
