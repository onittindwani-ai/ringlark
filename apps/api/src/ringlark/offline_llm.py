"""Offline stand in for the model. Plain rules, NOT a language model. Accuracy of anything measured with it says nothing about a live model.

It answers the same prompts the live model gets (same task markers, same JSON shapes), so every path of the product runs with no key and no network:
- agent_turn: replays the call so far through the rule agent and returns its last turn in the model's JSON shape
- read_caller: the caller reader's label
- summarise_call and summarise_week: short templates
"""

from __future__ import annotations

import json
import re

from sendora_core.llm import LLMResponse


def _block(prompt: str, source: str) -> str:
    m = re.search(r"<<UNTRUSTED_CONTENT>> source=" + re.escape(source) + r"\n(.*?)\n<<END_UNTRUSTED_CONTENT>>", prompt, re.S)
    return m.group(1) if m else ""


class _Quiet:
    """A tool runner that remembers nothing and touches nothing, for replaying a call."""

    def run(self, tool: str, args: dict) -> dict:
        return {"ok": True}


def answer_agent_turn(prompt: str, system: str) -> str:
    from ringlark.agent_offline import OfflineAgent

    body = system.split("The owner's instructions for this agent:\n", 1)[-1].split("\n\nText between <<UNTRUSTED", 1)[0]
    slots = json.loads((re.search(r"Times: (\[.*?\])", system) or [None, "[]"])[1]) or ["Tuesday at 3 pm", "Wednesday at 2 pm"]
    agent = OfflineAgent(body, {"agent_name": "Casey", "company": "Harbor Light Dental", "purpose": "", "slots": slots, "allow_voicemail": False, "ivr_policy": "hangup"}, _Quiet())
    agent.open()
    earlier = [ln[len("CALLER: "):] for ln in _block(prompt, "call so far").splitlines() if ln.startswith("CALLER: ")]
    for line in earlier:
        agent.reply(line)
    turns = agent.reply(_block(prompt, "latest words")) if not agent.done else []
    say = " ".join(t.text for t in turns if t.text)
    calls = []
    for t in turns:
        if not t.tool:
            continue
        a = t.args
        calls.append({"tool": t.tool, "slot": a.get("slot"), "person_name": a.get("name"), "reason": a.get("reason"), "disposition": a.get("disposition"), "note": a.get("note"), "digit": a.get("digit"), "kind": a.get("kind")})
    return json.dumps({"say": say, "tool_calls": calls})


class OfflineBackend:
    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int, **_kw) -> LLMResponse:
        task = (re.search(r"\[task:([a-z_]+)\]", prompt) or [None, ""])[1]
        if task == "agent_turn":
            text = answer_agent_turn(prompt, system)
        elif task == "read_caller":
            from ringlark.caller_reader import read_utterance

            r = read_utterance(_block(prompt, "latest words"), _block(prompt, "channel") or "voice")
            text = json.dumps({"label": r.label, "confidence": 0.6, "reason": f"Offline rules: {r.rule or 'no rule matched'}."})
        elif task == "summarise_call":
            facts = json.loads(prompt.split("FACTS:", 1)[1].strip().split("\nEND", 1)[0])
            parts = [f"{facts['direction'].capitalize()} call, {facts['turns']} turns, outcome {facts['disposition'].replace('_', ' ')}."]
            first = _block(prompt, "caller's first words")
            if first:
                parts.append(f"The person's first words: \"{first[:90]}\".")
            if facts.get("tools"):
                parts.append("The agent used: " + ", ".join(facts["tools"]) + ".")
            text = " ".join(parts)
        elif task == "summarise_week":
            text = "A rule based summary: see the numbers above. A live model would write a short narrative here."
        else:
            text = "Offline stand in model: no answer for this task."
        return LLMResponse(text, max(1, len(prompt) // 4), max(1, len(text) // 4), model)
