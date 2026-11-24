"""A language model behind the same `AgentBackend` protocol as the offline stand in. LIVE USE IS UNVERIFIED: it has only run against a local fake server and recorded fixtures.

It is used when LLM_BACKEND=anthropic (or fixture, to replay recordings). The model decides what to say next, but the rules that protect the person
on the call are code that runs around it, and no word the person says can switch them off:

1. the greeting, with the AI disclosure and the recording notice, is built by code (`build_greeting`), never by the model;
2. every caller turn is read by the rules first (`caller_reader`). A request to stop, a withdrawn consent, a machine or a phone menu are handled by
   the rule agent with no model call at all, so a stop request always wins and a model that has been talked round cannot argue with it;
3. whatever the model answers is checked: it must match the schema, may only name the six tools, a booking must use an offered time, a text goes only
   when the person has not withdrawn consent, a key press must be the configured key and only once, and a disposition must be one of the allowed codes;
4. what it says is checked: no claim to be a person (replaced by the disclosure), an honest admission when asked if it is a machine, no invented price,
   no leaking of the instructions, no link, at most 40 words;
5. anything wrong (a bad answer, the kill switch, the budget, an error) ends the call politely and marks it "needs review". It never keeps talking unguarded.

There is no tool for placing a call, so a caller cannot make the agent dial anyone: the schema has no such name.
"""

from __future__ import annotations

import re

from ringlark import model_tasks
from ringlark.agent_offline import AgentTurn, OfflineAgent, ToolRunner
from ringlark.caller_reader import read_utterance
from ringlark.disclosure import claims_human
from ringlark.models import DISPOSITIONS
from sendora_core.llm import LLM, LLMError
from sendora_core.safety import KillSwitchError

AI_ADMIT = re.compile(r"\bAI\b|artificial|automated|not a (real )?(person|human)", re.I)
PRICE_RE = re.compile(r"\$\s?\d|\d+\s?(dollars|bucks)", re.I)
LEAK_RE = re.compile(r"my instructions|system prompt|i was told to|my prompt", re.I)
LINK_RE = re.compile(r"https?://|www\.|\b[\w.-]+@[\w-]+\.[a-z]{2,}\b", re.I)
SMS_KINDS = ("booking_link", "confirmation", "callback")
FAIL_SAFE = "I'm sorry, I'll have someone from the practice call you. Goodbye."
ADMISSION = "I'm an AI assistant, not a person."
PRICE_LINE = "Prices depend on what you need, so I won't guess. The practice can send you the details."


class LiveModelAgent:
    def __init__(self, llm: LLM, prompt_body: str, ctx: dict, tools: ToolRunner):
        self.llm, self.body, self.ctx, self.tools = llm, prompt_body, ctx, tools
        self.rules = OfflineAgent(prompt_body, ctx, tools)  # greeting, stop, consent, machine and menu handling
        self.history: list[tuple[str, str]] = []
        self.done, self.pressed, self.consent_revoked, self.booked = False, False, False, False

    # ---- the protocol
    def open(self) -> list[AgentTurn]:
        turns = self.rules.open()  # the greeting is code, with the AI disclosure
        self.history.append(("agent", turns[0].text))
        return turns

    def first_contact(self, heard: str) -> list[AgentTurn] | None:
        out = self.rules.first_contact(heard)
        self.done = self.rules.done
        return out

    def reply(self, caller_text: str, channel: str = "voice") -> list[AgentTurn]:
        if self.done:
            return []
        text = (caller_text or "").strip()
        self.history.append(("caller", text))
        reading = read_utterance(text, channel)
        if reading.label in ("do_not_call", "consent_opt_out", "voicemail", "phone_menu") or not text:
            return self._by_rules(text, channel, reading.label)
        try:
            out = model_tasks.agent_turn(self.llm, self.body, self.history[:-1], text, self.ctx.get("slots") or [])
        except (LLMError, KillSwitchError, ValueError):  # includes the budget error and a schema mismatch
            return self._fail_safe()
        return self._checked(out, reading)

    # ---- the rule path
    def _by_rules(self, text: str, channel: str, label: str) -> list[AgentTurn]:
        turns = self.rules.reply(text, channel)
        self.done = self.rules.done
        if label == "consent_opt_out":
            self.consent_revoked = True
        self.history.append(("agent", " ".join(t.text for t in turns if t.text)))
        return turns

    def _fail_safe(self) -> list[AgentTurn]:
        self.done = True
        self.history.append(("agent", FAIL_SAFE))
        return [AgentTurn(text=FAIL_SAFE), AgentTurn(tool="end_call", args={"disposition": "needs_review", "note": "The model did not give a usable answer. A person should look."})]

    # ---- checking what the model gave back
    def _checked(self, out: model_tasks.TurnOut, reading) -> list[AgentTurn]:
        say = self._clean_say(out.say, reading)
        turns = [AgentTurn(text=say)] if say else []
        for call in out.tool_calls:
            t = self._tool(call)
            if t is None:
                continue
            turns.append(t)
            if t.tool in ("end_call", "transfer_to_human"):
                self.done = self.done or t.tool == "end_call"
        if not turns:
            return self._fail_safe()
        if any(t.tool == "transfer_to_human" for t in turns) and not any(t.tool == "end_call" for t in turns):
            turns.append(AgentTurn(tool="end_call", args={"disposition": "transferred", "note": "Handed to a person."}))
            self.done = True
        self.history.append(("agent", " ".join(t.text for t in turns if t.text)))
        return turns

    def _clean_say(self, say: str, reading) -> str:
        s = (say or "").strip()
        if claims_human(s) or LEAK_RE.search(s) or LINK_RE.search(s):
            s = ADMISSION if reading.label == "robot_question" or claims_human(s) else ""
        if PRICE_RE.search(s):
            s = PRICE_LINE
        if reading.label == "robot_question" and not AI_ADMIT.search(s):
            s = f"{ADMISSION} {s}".strip()
        words = s.split()
        return " ".join(words[:40]) if len(words) > 40 else s

    def _tool(self, c: model_tasks.ToolCall) -> AgentTurn | None:
        slots = self.ctx.get("slots") or []
        if c.tool == "end_call":
            code = c.disposition if c.disposition in DISPOSITIONS else "needs_review"
            if code == "booked" and not self.booked:  # "booked" is only true after a booking that passed the checks
                code = "needs_review"
            return AgentTurn(tool="end_call", args={"disposition": code, "note": (c.note or "")[:300]})
        if c.tool == "book_meeting":
            if c.slot not in slots or not (c.person_name or "").strip():
                return None  # only a time that was offered, and only with a name
            self.booked = True
            return AgentTurn(tool="book_meeting", args={"slot": c.slot, "name": c.person_name.strip(), **({"email": c.email} if c.email else {})})
        if c.tool == "send_sms":
            if self.consent_revoked or c.kind not in SMS_KINDS:
                return None
            return AgentTurn(tool="send_sms", args={"kind": c.kind})
        if c.tool == "press_digit":
            key = self.ctx.get("ivr_extension")
            if self.pressed or self.ctx.get("ivr_policy") != "press_once" or not key or c.digit != key:
                return None
            self.pressed = True
            return AgentTurn(tool="press_digit", args={"digit": key})
        if c.tool == "transfer_to_human":
            return AgentTurn(tool="transfer_to_human", args={"reason": (c.reason or "caller asked for a person")[:120]})
        return AgentTurn(tool="lookup_crm", args={})
