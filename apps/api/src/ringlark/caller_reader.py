"""Reading one thing a caller said and giving it a label, with plain rules. No model.

The labels are the ones the independent test authors used (see docs/CALLER-READER-EVAL.md): interest, objection, hostile, rushed, do_not_call,
wrong_person, callback_request, transfer_request, consent_opt_out, robot_question, recording_question, voicemail, phone_menu, unclear.

The reader is a set of rules written by the build, so any score measured with it is a score for these rules, not for a language model.
`OfflineAgent` decides from this reading, and the live model path runs the same reading first as a guard (a stop request wins, always). Neither runs inside a real
Ultravox phone call: there the rules are in the voice model's prompt and the transcript is read afterwards (see `live_prompt.py`).

Precedence, on purpose: a request to stop is read before everything else, even before an injection attempt or a sign of interest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ringlark import caller_phrases as P
from ringlark import intents as I

LABELS = ("interest", "objection", "hostile", "rushed", "do_not_call", "wrong_person", "callback_request", "transfer_request", "consent_opt_out",
          "robot_question", "recording_question", "voicemail", "phone_menu", "unclear")
STOP_LABELS = ("do_not_call",)


@dataclass(frozen=True)
class Reading:
    label: str
    rule: str = ""
    detail: str = ""  # a short extra: the time a caller named, or "recording" for a recording opt out


def normalise(text: str) -> str:
    t = (text or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", t).strip().lower()


def _any(patterns, t: str) -> bool:
    return any(p.search(t) for p in (patterns if isinstance(patterns, list) else [patterns]))


def strip_traps(t: str) -> str:
    for rx in P.STOP_TRAPS:
        t = rx.sub(" ", t)
    return t


def classify_answerer(text: str, first_contact: bool = True) -> str:
    """machine, ivr, silence or human. Strong markers count anywhere; weak ones only when the other end spoke first."""
    t = normalise(text)
    if not t:
        return "silence"
    if P.IVR_STRONG.search(t):
        return "ivr"
    if P.MACHINE_STRONG.search(t) or (first_contact and P.MACHINE_WEAK.search(t)):
        return "machine"
    return "human"


def _stop_reading(raw: str, channel: str) -> Reading | None:
    """do_not_call, consent_opt_out or nothing. Traps such as 'stop by after five' are removed first."""
    t = strip_traps(raw)
    if P.CARRIER_WORD.match(t):
        word = t.strip(" .!?").replace(" ", "")
        if channel != "text" and word in ("stop", "stopall", "quit"):
            return Reading("do_not_call", "stop word")
        if channel == "text" or word in ("unsubscribe", "unsub", "optout", "revoke"):
            return Reading("consent_opt_out", "carrier keyword")
        return None
    dnc, consent = _any(P.STOP_PHRASES, t), _any(P.CONSENT, t)
    if dnc and not (consent and not P.CALLWORD.search(t)):
        return Reading("do_not_call", "stop request")
    if consent and (P.BROAD.search(t) or not P.SPECIFIC_CHANNEL.search(t)):  # no named channel, or all of them, or automated contact (our own calls): treat as a stop
        return Reading("do_not_call", "consent revoked for every kind of contact")
    if consent:
        return Reading("consent_opt_out", "consent revoked", "recording" if P.RECORD_ONLY.search(t) and not re.search(r"\b(text|sms|e-?mail|mail|message)", t) else "")
    return None


def named_time(t: str) -> str:
    m = P.TIME_BITS.search(t)
    return m.group(0) if m else ""


def read_utterance(text: str, channel: str = "voice", first_contact: bool = False) -> Reading:
    n = normalise(text)
    if not n:
        return Reading("unclear", "empty")
    stop = _stop_reading(n, channel)
    if stop:
        return stop
    kind = classify_answerer(n, first_contact)
    if kind == "ivr":
        return Reading("phone_menu", "menu")
    if kind == "machine":
        return Reading("voicemail", "machine greeting")
    if P.INJECTION.search(n):
        return Reading("unclear", "injection")
    if _any(P.WRONG, n):
        return Reading("wrong_person", "wrong person")
    if _any(P.ROBOT, n):
        return Reading("robot_question", "asks if it is a machine")
    if _any(P.TRANSFER, n):
        return Reading("transfer_request", "asks for a person")
    if _any(P.RECORDING, n):
        return Reading("recording_question", "asks about recording")
    interested = _any(P.INTEREST, n)
    if (P.HOSTILE.search(n) or P.HOSTILE_STOP.search(n)) and not interested:
        return Reading("hostile", "hostile, treated as a stop" if P.HOSTILE_STOP.search(n) else "hostile")
    if _any(P.CALLBACK, n):
        return Reading("callback_request", "asks for another time", named_time(n))
    if P.RUSHED.search(n):
        return Reading("rushed", "short on time")
    if _any(P.NOT_INTERESTED, n):
        soft = not re.search(r"^\W*(no|nope|nah)\b[ ,.!]*(thanks|thank you)?\W*$|\bnot interested\b|\bno,? ?thanks\b|\bno thank", n)
        return Reading("objection", "soft objection" if soft else "plain no")
    if interested:
        return Reading("interest", "interested")
    if P.PRICE_WORD.search(n):
        return Reading("objection", "talks about price")
    if P.SLOT.search(n):
        return Reading("interest", "names a time")
    if I.any_match(I.BYE, n):
        return Reading("unclear", "goodbye")
    if P.BACKCHANNEL.match(n):
        return Reading("unclear", "backchannel")
    return Reading("unclear", "no rule matched")


def asks_to_stop(text: str, channel: str = "voice") -> bool:
    """True when the person asks for calls to stop. Used by the post call checks and the live path guard."""
    r = _stop_reading(normalise(text), channel)
    return bool(r and r.label == "do_not_call")


def revoked_consent(text: str, channel: str = "voice") -> bool:
    r = _stop_reading(normalise(text), channel)
    return bool(r and r.label == "consent_opt_out")
