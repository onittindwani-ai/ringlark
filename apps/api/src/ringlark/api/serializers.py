from __future__ import annotations

from ringlark.models import Agent, Call, Campaign, FollowUp, Target
from ringlark.util import aware


def iso(dt) -> str | None:
    return aware(dt).isoformat() if dt else None


def mask(phone: str) -> str:
    return f"{phone[:-4]}{'*' * 0}{phone[-4:]}" if len(phone) > 8 else phone


def call_row(c: Call, name: str = "", agent: str = "", qa=None) -> dict:
    return {"id": c.id, "direction": c.direction, "status": c.status, "disposition": c.disposition, "phone": c.peer_phone, "name": name, "agent": agent, "campaign_id": c.campaign_id, "attempt": c.attempt,
            "started_at": iso(c.started_at or c.created_at), "duration_ms": c.duration_ms, "blocked_reason": c.blocked_reason, "summary": c.summary, "qa": qa.score if qa else None,
            "flagged": bool(qa and qa.flagged), "answered_by": c.answered_by, "taken_over": c.taken_over}


def target_row(t: Target) -> dict:
    return {"id": t.id, "name": f"{t.first_name} {t.last_name}".strip(), "phone": t.phone, "timezone": t.timezone, "status": t.status, "sms_consent": t.sms_consent, "persona": t.demo_persona}


def followup_row(f: FollowUp) -> dict:
    return {"id": f.id, "call_id": f.call_id, "channel": f.channel, "to": f.to, "subject": f.subject, "body": f.body, "status": f.status, "blocked_reason": f.blocked_reason, "approval_id": f.approval_id, "created_at": iso(f.created_at)}


def agent_row(a: Agent) -> dict:
    return {"id": a.id, "name": a.name, "kind": a.kind, "voice": a.voice, "voice_source": a.voice_source, "transfer_number": a.transfer_number, "active_version_id": a.active_version_id, "candidate_version_id": a.candidate_version_id,
            "ab_enabled": a.ab_enabled, "ab_share_b": a.ab_share_b, "versions": [{"id": v.id, "version": v.version, "note": v.note, "created_by": v.created_by, "created_at": iso(v.created_at), "body": v.body} for v in a.versions]}


def campaign_row(c: Campaign) -> dict:
    return {"id": c.id, "name": c.name, "agent_id": c.agent_id, "number_id": c.number_id, "status": c.status, "window_start_hour": c.window_start_hour, "window_end_hour": c.window_end_hour, "weekdays_only": c.weekdays_only,
            "daily_cap": c.daily_cap, "max_attempts": c.max_attempts, "retry_gap_days": c.retry_gap_days, "allow_voicemail": c.allow_voicemail, "voicemail_text": c.voicemail_text, "ivr_policy": c.ivr_policy, "ivr_extension": c.ivr_extension,
            "require_prior_consent": c.require_prior_consent}
