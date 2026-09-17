"""Doc-truth guard (PR #13 / T-1.15, U-15).

After the bridge conversion, no doc/skill/demo may still tell users the stack
runs on host networking (`network_mode: host`, "host networking", the
`localhost:9092`/`localhost:8081` in-container idiom framed as how services reach
each other). Services address peers by container name on `lakehouse-network`; the
host reaches them via published ports.

    U-15  No stale host-network claims in docs/, demos/, .claude/skills/.
          Allowed to discuss host networking historically: SECURITY.md, any
          CHANGELOG, and docs/merge/* (merge analysis).

The scan is phrase-based; keep it narrow enough to avoid false positives on
legitimate mentions (e.g. `host.docker.internal` for the external Ollama sidecar,
or "publish to the host").
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["docs", "demos", ".claude/skills"]

# Phrases that assert the OLD host-networking topology.
STALE_PATTERNS = [
    re.compile(r"network_mode:\s*['\"]?host", re.I),
    re.compile(r"\bhost networking\b", re.I),
    re.compile(r"\bhost[- ]network mode\b", re.I),
    re.compile(r"uses?\s+host\s+networking", re.I),
]

pytestmark = [pytest.mark.network, pytest.mark.merge]


def _allowed(path: Path) -> bool:
    parts = set(path.relative_to(REPO_ROOT).parts)
    name = path.name.upper()
    return "merge" in parts or name.startswith("CHANGELOG") or name == "SECURITY.MD"


def test_u15_no_stale_host_network_claims():
    offenders = []
    for d in SCAN_DIRS:
        for path in (REPO_ROOT / d).rglob("*.md"):
            if _allowed(path):
                continue
            for i, line in enumerate(path.read_text().splitlines(), 1):
                if any(p.search(line) for p in STALE_PATTERNS):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{i}: {line.strip()[:100]}"
                    )
    assert not offenders, "stale host-network claims in docs:\n" + "\n".join(offenders)
