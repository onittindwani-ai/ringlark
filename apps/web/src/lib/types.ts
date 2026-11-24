export interface Overview {
  calls: number; completed: number; calls_today: number; booked: number; talk_rate: number; book_rate: number; avg_qa: number | null; flagged: number;
  dispositions: { code: string; count: number }[]; blocked: { reason: string; count: number }[]; drafted: number; suppressed: number; pending_approvals: number;
  targets: Record<string, number>; campaigns_running: number; series: { day: string; calls: number; booked: number }[]; followups_pending: number;
}
export interface CallRow {
  id: number; direction: string; status: string; disposition: string; phone: string; name: string; agent: string; campaign_id: number | null; attempt: number; started_at: string | null;
  duration_ms: number; blocked_reason: string; summary: string; qa: number | null; flagged: boolean; answered_by: string; taken_over: boolean;
}
export interface Turn { position: number; speaker: "agent" | "caller"; text: string; start_ms: number; end_ms: number }
export interface Waveform { synthetic: boolean; note: string; bars: number; duration_ms: number; agent: number[]; caller: number[] }
export interface FollowUp { id: number; call_id: number; channel: string; to: string; subject: string; body: string; status: string; blocked_reason: string; approval_id: number | null; created_at: string; name?: string }
export interface CallDetail extends CallRow { turns: Turn[]; waveform: Waveform; prompt_version: number | null; qa_checks: Record<string, boolean>; qa_note: string; followups: FollowUp[] }
export interface ReplayEvent { t: number; type: "state" | "word" | "tool"; state?: string; speaker?: string; word?: string; turn?: number; tool?: string; disposition?: string }
export interface Replay { call_id: number; synthetic_waveform: boolean; events: ReplayEvent[] }
export interface Campaign {
  id: number; name: string; agent: string; agent_id: number; number_id: number | null; status: string; window_start_hour: number; window_end_hour: number; weekdays_only: boolean; daily_cap: number; max_attempts: number;
  retry_gap_days: number; allow_voicemail: boolean; voicemail_text: string; ivr_policy: string; ivr_extension: string; targets: Record<string, number>; calls_today: number;
}
export interface TargetRow { id: number; name: string; phone: string; timezone: string; status: string; sms_consent: boolean; persona: string; can_call_now: boolean; why: string }
export interface PromptVersion { id: number; version: number; note: string; created_by: string; created_at: string; body: string }
export interface Agent { id: number; name: string; kind: string; voice: string; voice_source: string; transfer_number: string; active_version_id: number | null; candidate_version_id: number | null; ab_enabled: boolean; ab_share_b: number; versions: PromptVersion[] }
export interface DiffResult { lines: { kind: "same" | "add" | "del"; text: string }[]; flags_a: Record<string, boolean>; flags_b: Record<string, boolean> }
export interface Persona { id: string; category: string; title: string; caller: string[]; expect: Record<string, unknown>; setup: Record<string, unknown> }
export interface SimResult { engine: string; transcript: { speaker: string; text: string }[]; disposition: string; tools: { tool: string; args: Record<string, unknown> }[]; checks: Record<string, boolean> }
export interface SuiteResult { engine: string; label: string; personas: number; passed: number; pass_rate: number; checks_total: number; checks_passed: number; by_category: Record<string, string>; failures: { id: string; category: string; failed_checks: string[]; disposition: string }[]; note: string }
export interface NumberRow { id: number; e164: string; label: string; direction: string; agent: string; country: string; checklist: Record<string, boolean> }
export interface QaRow { call_id: number; score: number; flagged: boolean; note: string; checks: Record<string, boolean>; reviewed: boolean; disposition: string; phone: string; started_at: string | null }
export interface ApprovalRow { id: number; action: string; summary: string; risk: string; status: string; requested_by: string; decided_by: string | null; note: string | null; created_at: string; payload: Record<string, unknown> }
export interface AuditRow { id: number; actor: string; action: string; target: string | null; detail: Record<string, unknown>; at: string }
export interface AdapterRow { category: string; name: string; tier: string; live_verified: boolean; notes: string; selected: boolean; env_vars: string[]; configured: boolean }
export interface Integrations { categories: string[]; adapters: AdapterRow[]; demo_mode: boolean }
export interface Settings { mode: string; effective_mode: string; kill_switch: boolean; demo_mode: boolean; problems: string[]; window: string; follow_ups_need_approval: boolean; llm: string }
export interface Me { user: string; role: string; demo_mode: boolean }
export interface VersionMetric { agent: string; version: number; note: string; calls: number; booked: number; book_rate: number | null; avg_qa: number | null }
export interface Suppression { id: number; phone: string; reason: string; source: string; created_at: string }
