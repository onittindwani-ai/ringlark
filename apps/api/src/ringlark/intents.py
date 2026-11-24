"""Reading what a caller said, with plain rules. No model. Used by the offline agent and by the post call checks.

These are rules written by the build, so any score measured with them is a score for these rules, not for a language model.
"""

from __future__ import annotations

import re

R = lambda p: re.compile(p, re.I)  # noqa: E731

STOP = R(r"(stop|quit|never|don'?t|do not|no more)\s+(you\s+)?(call|ring|phone|contact|text|message|bother)|do not (call|ring|contact)|remove (me|my)|take me off|delete my|unsubscribe|put me on (the |your )?(do not|dnc)|\bstop\b\s*$|\bstop (it|this)\b")
WRONG = R(r"wrong (number|person|guy|lady)|no ?one (here )?(by|named|called|with)|nobody (by|with|named|called)|doesn'?t live|does not live|never heard of|not (me|him|her)\b|you have the wrong")
HUMAN = R(r"(speak|talk|put me) (to|through)( to)? (a |an |the )?(real |actual |live )?(person|human|someone|somebody|manager|rep)|get me (a |some)?(body|someone|somebody|human|person)|actual (person|human)|human being|real person to|somebody real|someone real")
ROBOT = R(r"are you (a |an )?(real |actual )?(robot|bot|ai|machine|recording|computer|human|person)|is this (a |an )?(real |actual )?(person|human|robot|recording|bot|machine|tape)|(person|human) (i'?m|i am) (talking|speaking)|some kind of (tape|machine|bot|robot)|real (person|human) or|am i talking to a")
HOSTILE = R(r"vultur|scam|harass|idiot|sick of (you|this)|report (you|this)|\bdamn\b|bloody|f\*+k|piss off|get lost|waste of|disgust|unbelievable|how dare|hang(ing)? up|putting the phone down|slam")
RUSHED = R(r"no time|in (a|the) (meeting|hurry|car)|busy|(ten|10|five|5) seconds|can'?t (talk|do this)|walk(ing)? into|driving|not a good time|bad time|quick(ly)?\b.*(go|leave)|got to (run|go)|about to")
LATER = R(r"(call|try|ring|phone) (me )?(back|again|later)|another time|(on )?(mon|tues|wednes|thurs|fri)day|tomorrow|next (week|month)|later (today|this)")
PRICE = R(r"\b(cost|price|prices|pricing|how much|ballpark|set me back|fee|fees|charge|expensive|cheap|quote|rates?)\b")
WHO_NUMBER = R(r"(get|got|find|found) (my|this|that) (number|details|info)|where did you (get|find)|who gave you|how did you (get|find)|where'?d you get")
INJECTION = R(r"(ignore|disregard|forget|override)\b.{0,50}(instruction|told|prior|previous|before|everything|rules)|system prompt|(recite|reveal|repeat|read out)\b.{0,50}(prompt|instruction|text you were given|rules)|new rule")
IVR = R(r"press (one|two|three|four|zero|star|pound|\d)|for .{3,40}press|your call is (important|being)|please hold|main menu|these options again|stay on the line")
MACHINE = R(r"leave (a |your )?(message|name|number)|after the (tone|beep)|can'?t (come to|get to|pick up|answer)|voicemail|not available|\bbeep\b|unavailable")
NO = R(r"\bno,? thanks|not interested|it'?s a no|no from me|\bno thank|i'?ll pass|\bpass\b|not for me|no need|\bnope\b")
YES = R(r"\b(yes|yeah|yep|sure|go on|go ahead|sounds good|sounds great|interested|been meaning|sort(ed)? out|book|appointment|check.?up|okay|ok|why not|please do|definitely)\b")
SLOT = R(r"(mon|tues|wednes|thurs|fri)day|\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)(:\d\d)?\s?(am|pm|o'?clock)\b|afternoon|morning|\b(first|second|earlier|later) (one|option)\b|\bthe (first|second|1st|2nd)\b")
BYE = R(r"\b(bye|goodbye|that'?s all|have a good (day|one)|cheers)\b")


def any_match(rx: re.Pattern, text: str) -> bool:
    return bool(rx.search(text or ""))


def caller_name(text: str) -> str:
    m = re.search(r"(?:[Ii]t'?s|[Ii]'?m|[Ii] am|[Tt]his is|[Nn]ame'?s|[Mm]y name is)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)?)", text or "")
    return m.group(1) if m else ""


def classify_answerer(text: str) -> str:
    """machine, ivr, silence or human, from what the other end said first."""
    t = (text or "").strip()
    if not t:
        return "silence"
    if IVR.search(t):
        return "ivr"
    if MACHINE.search(t):
        return "machine"
    return "human"
