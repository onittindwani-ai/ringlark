"""One place that decides which agent plays a simulated call: the offline rules agent (default) or the model backed agent.

The simulator and the persona suite both come through here, so they always use the same engine. The demo calls stay offline on purpose.
LIVE USE IS UNVERIFIED (see agent_live.py).
"""

from __future__ import annotations

from ringlark.agent_live import LiveModelAgent
from sendora_core.settings import LLMBackendKind

LABELS = {LLMBackendKind.OFFLINE: "offline rules, not a language model", LLMBackendKind.FIXTURE: "recorded model answers (replay)", LLMBackendKind.ANTHROPIC: "live language model (UNVERIFIED)"}


def engine_label(ctx) -> str:
    return LABELS[ctx.settings.effective_llm_backend]


def backend_factory(ctx, session, prompt_body: str):
    """None for the offline rules agent, otherwise a function (tools, ctx) -> a model backed agent."""
    if ctx.settings.effective_llm_backend is LLMBackendKind.OFFLINE:
        return None
    llm = ctx.llm(session)
    return lambda tools, c: LiveModelAgent(llm, prompt_body, dict(c), tools)
