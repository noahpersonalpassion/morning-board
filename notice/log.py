"""The decision log.

This is the experiment. The site is the demo; this file is what tells you
whether the thesis holds. Every candidate that reaches the Delta Rule is
written here with all four results and their reasons, shipped or not.

Read it every morning during weeks 5-6. The question it answers: how many
genuinely novel, genuinely consequential items exist per week?
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .models import Decision


class DecisionLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, decision: Decision) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(decision.to_json() + "\n")

    def append_all(self, decisions: list[Decision]) -> None:
        for d in decisions:
            self.append(d)

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def seen_keys(self) -> set[str]:
        """Keys already judged, so a daily run does not re-ship yesterday."""
        return {r["key"] for r in self.rows()}


@dataclass
class Summary:
    total: int
    shipped: int
    dropped: int
    dropped_by: Counter
    runs: int

    @property
    def ship_rate(self) -> float:
        return (self.shipped / self.total) if self.total else 0.0

    def render(self) -> str:
        lines = [
            "",
            "  DECISION LOG",
            f"  {self.total} candidates judged over {self.runs} run(s)",
            f"  {self.shipped} shipped, {self.dropped} dropped",
        ]
        if self.dropped_by:
            lines.append("")
            lines.append("  dropped on:")
            width = max(len(k) for k in self.dropped_by)
            for name, n in self.dropped_by.most_common():
                lines.append(f"    {name.ljust(width)}  {n}")
        lines.append("")
        return "\n".join(lines)


def summarise(log: DecisionLog) -> Summary:
    rows = log.rows()
    dropped_by: Counter = Counter()
    shipped = 0
    for r in rows:
        if r["shipped"]:
            shipped += 1
            continue
        for c in r["criteria"]:
            if not c["passed"]:
                dropped_by[c["name"]] += 1
                break
    return Summary(
        total=len(rows),
        shipped=shipped,
        dropped=len(rows) - shipped,
        dropped_by=dropped_by,
        runs=len({r["run_date"] for r in rows}),
    )
