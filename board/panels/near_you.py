"""Near you: the Gazette engine, reduced to one line.

This is the whole Notice project — the Delta Rule, the template table, the
proximity matching — collapsed into a single row that usually reads
"Nothing". At roughly one local item every ten days that is the correct
size for it. As a standalone product it was starvation; as the row you are
glad is empty, it works.

Quiet is not a failure here. The row says what it last saw and when, so an
empty row is legible as "checked, nothing found" rather than "broken".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from notice.delta import Profile, evaluate, build_card
from notice.novelty import HeadlineCorpus
from .base import Panel, PanelResult, State


@dataclass
class NearYouPanel:
    profile: Profile
    collect: object                    # callable returning list[Candidate]
    corpus: HeadlineCorpus
    allow_unverified_novelty: bool = False
    panel_id: str = "near_you"
    label: str = "Near you"

    def render(self) -> PanelResult:
        candidates = self.collect()
        hits = []
        for c in candidates:
            criteria = evaluate(c, self.profile, self.corpus,
                                self.allow_unverified_novelty)
            if all(r.passed for r in criteria):
                try:
                    hits.append((c, build_card(c, criteria,
                                               self.profile.attributes)))
                except ValueError:
                    continue

        local = [(c, card) for c, card in hits
                 if card.why_you and "nationwide" not in card.why_you]

        if not local:
            last = _most_recent(hits) or None
            note = (
                "No gazetted change on your street or in your suburb."
            )
            if last:
                note += (
                    f" Last was {last[1].what.rstrip('.')}, "
                    f"{last[0].published.strftime('%-d %B')}."
                )
            return PanelResult(
                state=State.QUIET,
                reading="Nothing",
                note=note,
                meta={"checked": len(candidates)},
            )

        c, card = local[0]
        return PanelResult(
            state=State.LIVE,
            reading=str(len(local)),
            unit="change" if len(local) == 1 else "changes",
            note=f"{card.effect} {card.why_you}",
            link_label="Open the notice",
            link_url=card.source_url,
            meta={"checked": len(candidates), "hits": len(local)},
        )


def _most_recent(hits):
    if not hits:
        return None
    return max(hits, key=lambda pair: pair[0].published)
