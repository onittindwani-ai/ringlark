"""Scan tracked files for things that look like real secrets. Prints file:line and the kind, never the value.

    python tools/scan_secrets.py     exits 1 when it finds something
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = {
    "Anthropic key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "OpenAI style key": re.compile(r"sk-[A-Za-z0-9]{32,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "Notion token": re.compile(r"ntn_[A-Za-z0-9]{20,}"),
    "Slack token": re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
    "Private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "Long hex or base64 secret assignment": re.compile(r"(?i)(secret|token|api_key|password)\s*[:=]\s*['\"][A-Za-z0-9+/=_\-]{32,}['\"]"),
    "Argon2 hash": re.compile(r"\$argon2[a-z]*\$"),
}
SKIP_SUFFIX = {".png", ".jpg", ".pdf", ".ico", ".woff", ".woff2"}
SKIP_NAMES = {"pnpm-lock.yaml", "scan_secrets.py"}
# Test fixtures use obviously dummy values. A match is allowed only when the matched text itself carries one of these markers (the value of the
# assignment), never because some other word on the same line says "example", which used to hide a real key sitting next to an example address.
ALLOW = ("example", "not-for-real", "e2e-only", "dev-only", "stub", "demo-secret", "test-only", "change-me")


def kinds_in(line: str) -> list[str]:
    """The kinds of secret a line holds. A match is let through only when the matched text itself carries an ALLOW marker."""
    return [kind for kind, rx in PATTERNS.items() for m in rx.finditer(line) if not any(a in m.group(0).lower() for a in ALLOW)]


def tracked() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    return [ROOT / f for f in out]


def main() -> int:
    hits = 0
    for f in tracked():
        rel = f.relative_to(ROOT).as_posix()
        if f.suffix in SKIP_SUFFIX or f.name in SKIP_NAMES or not f.is_file() or (rel.startswith("packages/") and "/tests/" in rel):  # the shared packages are scanned too, except their test fixtures
            continue
        try:
            lines = f.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for kind in kinds_in(line):
                print(f"{f.relative_to(ROOT)}:{i}: looks like {kind}")
                hits += 1
    print("secret scan:", "nothing found" if not hits else f"{hits} possible secret(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
