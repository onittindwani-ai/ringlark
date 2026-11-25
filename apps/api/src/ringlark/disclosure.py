"""The AI disclosure and recording notice. Built into every greeting by default, checked before any call."""
from __future__ import annotations

import re

DISCLOSURE_RE = re.compile(r"\b(ai|a\.i\.|artificial|virtual assistant|automated (assistant|agent|call))\b", re.I)
RECORDING_RE = re.compile(r"\b(record(ed|ing)?|transcrib)", re.I)
HUMAN_CLAIM_RE = re.compile(r"\b(i am|i'm|this is) (a )?(real )?(human|person|live agent)\b|\bnot (a )?(robot|bot|ai)\b", re.I)


def build_greeting(agent_name: str, company: str, purpose: str, recording: bool = True) -> str:
    base = f"Hi, this is {agent_name}, an AI assistant calling for {company}. {purpose}"
    if recording:
        base += " This call may be recorded and transcribed. Is now an okay time to talk?"
    else:
        base += " Is now an okay time to talk?"
    return base


def has_disclosure(text: str) -> bool:
    return bool(DISCLOSURE_RE.search(text or ""))


def has_recording_notice(text: str) -> bool:
    return bool(RECORDING_RE.search(text or ""))


def greeting_problems(text: str, recording_notice_required: bool = True) -> list[str]:
    """What a custom greeting is missing. It must say it is an AI, and say the call may be recorded when recording notices are required (RECORDING_NOTICE_REQUIRED, on by default:
    transcripts are always stored). A greeting with a problem is refused when the agent is saved, and is never used on a call (the standard greeting is used instead)."""
    out: list[str] = []
    if not has_disclosure(text):
        out.append("It must say that the caller is an AI (for example \"this is Casey, an AI assistant\").")
    if recording_notice_required and not has_recording_notice(text):
        out.append("It must say that the call may be recorded or transcribed.")
    return out


def claims_human(text: str) -> bool:
    return bool(HUMAN_CLAIM_RE.search(text or ""))
