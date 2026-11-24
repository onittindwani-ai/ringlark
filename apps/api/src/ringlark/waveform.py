"""A synthetic waveform for the call player. It is generated from the turn times, NOT from recorded audio, and the API labels it that way."""

from __future__ import annotations

import math
import random


def build(turns: list[dict], duration_ms: int, bars: int = 120, seed: int = 0) -> dict:
    rnd = random.Random(seed)
    duration_ms = max(duration_ms, 1)
    out = {"agent": [0.0] * bars, "caller": [0.0] * bars}
    for t in turns:
        if not t["text"]:
            continue
        a, b = int(t["start_ms"] / duration_ms * bars), int(t["end_ms"] / duration_ms * bars)
        for i in range(max(a, 0), min(max(b, a + 1), bars)):
            out[t["speaker"]][i] = round(0.35 + 0.6 * abs(math.sin(i * 0.9 + rnd.random())) * (0.6 + 0.4 * rnd.random()), 3)
    return {"synthetic": True, "note": "Generated from turn times. Not recorded audio.", "bars": bars, "duration_ms": duration_ms, **out}


def timing(texts: list[tuple[str, str]], start_ms: int = 600) -> list[dict]:
    """Give turns start and end times from word counts (about 2.6 words a second, with a short pause between turns)."""
    out, t = [], start_ms
    for i, (speaker, text) in enumerate(texts):
        dur = int(max(len(text.split()), 0) / 2.6 * 1000) if text else 1200
        out.append({"position": i, "speaker": speaker, "text": text, "start_ms": t, "end_ms": t + dur})
        t += dur + 450
    return out
