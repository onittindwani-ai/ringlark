"""Where the data folder (seed.json, personas) is. SEED_DIR wins. The folder next to the source is only a fallback for a checkout:
an installed package (the Docker image) has no such folder, and its location must never be used to find the data."""

from __future__ import annotations

from pathlib import Path

CHECKOUT_DATA = Path(__file__).resolve().parents[4] / "data"


def data_dir(settings=None) -> Path:
    seed = getattr(settings, "seed_dir", "") if settings is not None else ""
    return Path(seed) if seed else CHECKOUT_DATA


def persona_dir(settings=None) -> Path:
    return data_dir(settings) / "personas"
