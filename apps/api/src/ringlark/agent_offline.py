"""The offline stand in agent. It is plain rules, NOT a language model, and it is labelled that way everywhere it is shown.

It reads the active prompt for a small set of directives (stop on request, say it is an AI, transfer on request, no prices, never reveal the prompt,
hang up on a phone menu, keep turns short). A prompt that lacks a directive makes the agent behave the way a weak prompt would, which is what the persona suite is for.
A live model path exists behind the same `AgentBackend` protocol and is UNVERIFIED: it has never been run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from ringlark import intents as I
from ringlark.caller_reader import classify_answerer, read_utterance
from ringlark.compliance import voicemail_allowed
from ringlark.disclosure import build_greeting

DIRECTIVES = {
    "stop_on_request": re.compile(r"(stop|end) .{0,40}(when|if) .{0,30}(ask|tell|say)|asks? (you )?to stop|stop calling|remove (their|the|this) number|do not call list|opt.?out|never (call|ring) .{0,20}again", re.I),
    "admit_ai": re.compile(r"(admit|say|confirm|tell).{0,30}(you are|you're|it is) (an )?(ai|automated)|never (claim|pretend).{0,30}(human|person)", re.I),
    "transfer_on_request": re.compile(r"transfer_to_human|hand (the call )?to a human|transfer", re.I),
    "no_pricing": re.compile(r"never (quote|state|give|make up).{0,40}(price|cost|number)|do not (quote|state).{0,30}(price|cost)", re.I),
    "no_leak": re.compile(r"never (reveal|share|read out|repeat).{0,40}(prompt|instruction)", re.I),
    "ivr_hangup": re.compile(r"phone menu|ivr|recorded (menu|message)", re.I),
    "callback_when_busy": re.compile(r"(busy|rushed|in a hurry).{0,60}(callback|call back|offer)|offer a (call ?back|callback)", re.I),
    "brief": re.compile(r"(short|brief|under \d+ words|one or two sentences)", re.I),
}


def prompt_flags(body: str) -> dict[str, bool]:
    return {k: bool(rx.search(body or "")) for k, rx in DIRECTIVES.items()}


@dataclass
class AgentTurn:
    text: str = ""
    tool: str = ""
    args: dict = field(default_factory=dict)


class ToolRunner(Protocol):
    def run(self, tool: str, args: dict) -> dict: ...


class AgentBackend(Protocol):
    def open(self) -> list[AgentTurn]: ...
    def reply(self, caller_text: str) -> list[AgentTurn]: ...


ASSENT = re.compile(r"^\W*(ok|okay|k|kk|mm+|mhm|uh[- ]?huh|right|i see|go on|so|and|well)\W*$", re.I)


def _end(code: str, note: str = "") -> AgentTurn:
    return AgentTurn(tool="end_call", args={"disposition": code, "note": note})


class OfflineAgent:
    """One call. `ctx` keys: agent_name, company, purpose, voicemail_text, allow_voicemail, ivr_policy, ivr_extension, slots."""

    def __init__(self, prompt_body: str, ctx: dict, tools: ToolRunner):
        self.flags = prompt_flags(prompt_body)
        self.ctx, self.tools = ctx, tools
        self.stage, self.slot, self.unclear, self.name, self.done = "start", "", 0, "", False
        self.objections, self.no_messages = 0, False
        self.greeting = build_greeting(ctx.get("agent_name", "Casey"), ctx.get("company", "Harbor Light Dental"), ctx.get("purpose", "I'm calling about your next check up."), True)

    # ---- speaking helpers
    def _say(self, text: str) -> AgentTurn:
        return AgentTurn(text=text if not self.flags["brief"] or len(text.split()) <= 26 else " ".join(text.split()[:26]).rstrip(",;") + ".")

    def _finish(self, text: str, code: str, note: str = "") -> list[AgentTurn]:
        self.done = True
        return ([self._say(text)] if text else []) + [_end(code, note)]

    def open(self) -> list[AgentTurn]:
        self.stage = "greeted"
        return [AgentTurn(text=self.greeting)]

    def first_contact(self, heard: str) -> list[AgentTurn] | None:
        """Called when the other end spoke first (a machine, a phone menu or silence). None means a person: carry on with the greeting."""
        kind = classify_answerer(heard)
        if kind == "machine":
            self.done = True
            if voicemail_allowed(bool(self.ctx.get("allow_voicemail")), self.ctx.get("voicemail_text", ""))[0]:
                return [AgentTurn(text=self.ctx["voicemail_text"]), _end("voicemail_left")]
            return [_end("voicemail_no_message", "Machine answered, voicemail is off for this campaign.")]
        if kind == "ivr":
            self.done = True
            if self.flags["ivr_hangup"] and self.ctx.get("ivr_policy") == "press_once" and self.ctx.get("ivr_extension"):
                return [AgentTurn(tool="press_digit", args={"digit": self.ctx["ivr_extension"]}), _end("ivr_no_human", "Pressed the configured key once, then ended.")]
            if self.flags["ivr_hangup"]:
                return [_end("ivr_no_human", "Phone menu, hung up without leaving a message.")]
            return [AgentTurn(text="Hello, I'd like to speak to the person who handles appointments, please."), _end("needs_review", "Spoke to a menu. A person should look.")]
        return None

    def reply(self, caller_text: str, channel: str = "voice") -> list[AgentTurn]:
        """Everything the agent does is decided from one reading of what the caller said (see caller_reader.py). A stop request is read first and always wins."""
        if self.done:
            return []
        t = (caller_text or "").strip()
        if not t:
            return self._silence()
        r = read_utterance(t, channel)
        label = r.label
        if label == "do_not_call":  # in code, not in the prompt: a weak prompt cannot make the agent keep calling
            self.done = True
            return [self._say("Understood. I'll remove this number from our list, and you won't hear from us again. Sorry to have bothered you."), _end("do_not_call", "Caller asked not to be called again.")]
        if label == "consent_opt_out":
            return self._consent_opt_out(r)
        if r.rule == "injection":
            if not self.flags["no_leak"]:
                return self._finish("Sure. My instructions say I'm here to book check ups for Harbor Light Dental and to read nothing else out.", "needs_review", "Caller tried to read out the prompt.")
            return self._finish("I can't share how I'm set up, and I won't text or transfer anyone on request like that. Thanks for your time, goodbye.", "needs_review", "Caller tried to change the rules.")
        if label in ("voicemail", "phone_menu"):
            return self.first_contact(t) or self._finish("Sorry to bother you. Goodbye.", "needs_review")
        if self.stage in ("offered", "confirming") and label in ("interest", "unclear") and (I.any_match(I.SLOT, t) or self.stage == "confirming"):
            return self._book(t)
        handler = {"wrong_person": self._wrong, "transfer_request": self._transfer, "robot_question": self._robot, "recording_question": self._recording, "hostile": self._hostile,
                   "callback_request": self._callback, "rushed": self._rushed, "objection": self._objection, "interest": self._interest}.get(label)
        return handler(t, r) if handler else self._unclear(r, t)

    # ---- one handler per reading
    def _silence(self) -> list[AgentTurn]:
        self.unclear += 1
        if self.unclear >= 2:
            return self._finish("I can't hear anyone, so I'll let you go. Goodbye.", "no_answer")
        return [self._say("Hello? Can you hear me?")]

    def _consent_opt_out(self, r) -> list[AgentTurn]:
        if r.detail == "recording":  # the call may be recorded; the only honest way to stop that is to end it
            return self._finish("Understood. I'll end the call now so nothing more is recorded. Sorry for the trouble. Goodbye.", "needs_review", "Caller refused recording. Call ended.")
        self.no_messages = True
        if self.stage in ("offered", "confirming"):
            return [self._say("Understood, I won't text or email you again. Shall we keep going with the booking by phone?")]
        return [self._say("Understood, I won't text or email you again, and I've noted it. Is now still an okay time to talk?")]

    def _wrong(self, t, r) -> list[AgentTurn]:
        return self._finish("Sorry about that, I'll take this number off our list. Have a good day.", "wrong_number")

    def _transfer(self, t, r) -> list[AgentTurn]:
        if self.flags["transfer_on_request"]:
            self.done = True
            return [self._say("Of course, I'll connect you with someone now."), AgentTurn(tool="transfer_to_human", args={"reason": "caller asked for a person"}), _end("transferred")]
        if self.unclear < 1 and not self._bump():
            return [self._say("I'm sorry, I can't pass you on from here, but I'm happy to help with a booking.")]
        return self._finish("I'll note that you'd like a person to call you. Goodbye.", "needs_review")

    def _robot(self, t, r) -> list[AgentTurn]:
        if self.flags["admit_ai"]:
            self.stage = "pitched"
            return [self._say("I'm an AI assistant, not a person. I can help book a check up, or I can have someone from the practice call you instead.")]
        return [self._say(f"I'm {self.ctx.get('agent_name', 'Casey')} from {self.ctx.get('company', 'the practice')}. Would you like to book a check up?")]

    def _recording(self, t, r) -> list[AgentTurn]:
        self.stage = self.stage if self.stage != "greeted" else "pitched"
        return [self._say("Yes, this call may be recorded and transcribed so the practice can keep a record. If you'd rather not be recorded, just say so and I'll end the call.")]

    def _hostile(self, t, r) -> list[AgentTurn]:
        if r.rule == "hostile, treated as a stop":  # a threat or an order to go away: remove the number, never call again
            self.done = True
            return [self._say("I'm sorry. I'll remove this number from our list and you won't hear from us again."), _end("do_not_call", "Caller was angry and threatened a complaint or told us to go away. Treated as a stop request.")]
        return self._finish("I'm sorry to have caught you at a bad moment. Goodbye.", "hostile_ended")

    def _callback(self, t, r) -> list[AgentTurn]:
        when = f" {r.detail}" if r.detail else " at a better time"
        if self.flags["callback_when_busy"]:
            return self._finish(f"No problem, I'll have someone call you back{when}. Thanks, goodbye.", "interested_callback", "Caller asked for a call back.")
        return self._rushed(t, r)

    def _rushed(self, t, r) -> list[AgentTurn]:
        if self.flags["callback_when_busy"]:
            return self._finish("No problem, I'll have someone call you back at a better time. Thanks, goodbye.", "interested_callback", "Caller was busy or asked for a later time.")
        if self.unclear >= 1:  # a weak prompt keeps pitching once, then gives up
            return self._finish("Sorry to bother you. Goodbye.", "needs_review", "Caller was busy and the agent had no callback rule.")
        self.unclear += 1
        return [self._say("It will only take a minute. Would you like to book a check up?")]

    def _objection(self, t, r) -> list[AgentTurn]:
        if I.any_match(I.WHO_NUMBER, t):
            self.stage = "pitched"
            return [self._say("Your number is on the patient list of the practice, from when you last booked with us. I can remove it if you'd prefer.")]
        if I.any_match(I.PRICE, t) and r.rule != "plain no":
            if self.flags["no_pricing"]:
                return [self._say("Prices depend on what you need, so I won't guess. I can have the practice send you the details by text if you like.")]
            return [self._say("A check up is usually around $80, and a clean is about $120.")]
        if r.rule == "soft objection" and self.objections == 0:  # one gentle try, never a second
            self.objections += 1
            return [self._say("That's fair. Would it help if the practice sent you the details, or shall I leave it there?")]
        return self._finish("No problem at all. Thanks for your time, goodbye.", "not_interested")

    def _interest(self, t, r) -> list[AgentTurn]:
        if I.any_match(I.PRICE, t):
            if self.flags["no_pricing"]:
                return [self._say("Prices depend on what you need, so I won't guess. I can have the practice send you the details by text if you like.")]
            return [self._say("A check up is usually around $80, and a clean is about $120.")]
        if self.stage in ("offered", "confirming") and I.any_match(I.SLOT, t):
            return self._book(t)
        slots = self.ctx.get("slots") or ["Tuesday at 3 pm", "Wednesday at 2 pm"]
        self.stage = "offered"
        return [self._say(f"Lovely. I can do {slots[0]} or {slots[-1]}. Which suits you?")]

    def _unclear(self, r, t: str = "") -> list[AgentTurn]:
        if r.rule == "goodbye":
            return self._finish("Thanks for your time. Goodbye.", "interested_callback" if self.stage in ("offered", "pitched") else "not_interested")
        if r.rule == "backchannel" and ASSENT.match(t) and self.stage in ("greeted", "pitched"):  # "okay", "mm hm": carry on with the offer
            return self._interest(t, r)
        self.unclear += 1
        if self.unclear >= 2:
            return self._finish("I'm sorry, I'm not following. I'll have someone from the practice call you. Goodbye.", "needs_review")
        return [self._say("Sorry, could you say that again?")]

    def _book(self, t: str) -> list[AgentTurn]:
        self.slot = self.slot or self._pick(t)
        self.name = I.caller_name(t) or (t.strip(" .!") if self.stage == "confirming" and re.fullmatch(r"[A-Za-z' -]{2,40}", t.strip(" .!")) else "") or self.name
        if not self.name and self.stage == "offered":
            self.stage = "confirming"
            return [self._say(f"Great, I have {self._label()}. Can I take your name?")]
        res = self.tools.run("book_meeting", {"slot": self.slot, "name": self.name or "Caller"})
        self.done = True
        ok = res.get("ok", True)
        return [self._say(f"Done, you're booked for {self._label()}. You'll get a confirmation. Goodbye.") if ok else self._say("I've noted that time and someone will confirm it. Goodbye."),
                AgentTurn(tool="book_meeting", args={"slot": self.slot, "name": self.name or "Caller"}), _end("booked")]

    def _bump(self) -> bool:
        self.unclear += 1
        return self.unclear >= 2

    def _pick(self, t: str) -> str:
        slots = self.ctx.get("slots") or ["Tuesday at 3 pm", "Wednesday at 2 pm"]
        low = t.lower()
        for s in slots:
            day = s.split()[0].lower()
            if day in low or ("2" in low and "2 pm" in s and "2" in low):
                return s
        return slots[-1] if re.search(r"second|later|wednesday|2", low) else slots[0]

    def _label(self) -> str:
        return self.slot or "that time"
