"""What changed since you last looked.

The honest version of an unread badge. It does not nag, it does not count up,
it does not care how long you have been away — it just remembers what each
row said last time you opened the page and quietly marks the ones that have
moved since. If you read the board yesterday, today you should be able to
find the two lines that are different without re-reading all six.

Everything lives in the viewer's own browser. There is no account, no
server, and nothing about when you read your board ever leaves your phone —
which is both the privacy answer and the reason this costs nothing to run.

Three rules keep it from becoming a growth mechanic:

  1. It never says how long you have been away. "You haven't checked in 5
     days" is a guilt trip wearing a fact's clothes.
  2. It marks changes, never counts unread things. There is no badge, no
     number in a circle, nothing that accumulates while you are gone.
  3. On a first visit it says nothing at all. A brand new reader has no
     "since", and inventing one would mean marking every row as new — which
     is noise dressed as information.
"""

from __future__ import annotations

import json
from typing import Any

from .panels.base import PanelResult, State

STYLE = """
  .row .changed {
    display: inline-block; width: 5px; height: 5px; border-radius: 50%;
    background: var(--accent); margin-left: 7px; vertical-align: 2px;
  }
  .since { color: var(--muted); }
  .since b { color: var(--ink); font-weight: 600; }
"""

SCRIPT = """
<script>
(function () {
  // Everything here is best-effort. Private windows, blocked site data and
  // thumbnail capture can all make storage throw or come back empty, and the
  // board has to read correctly in every one of those cases — so a failure
  // means "say nothing", never "show an error".
  var KEY = 'morning-board:last';
  var now = {};
  try {
    now = JSON.parse(document.getElementById('board-state').textContent);
  } catch (e) { return; }

  var before = null;
  try {
    var raw = localStorage.getItem(KEY);
    if (raw) before = JSON.parse(raw);
  } catch (e) { before = null; }

  try {
    localStorage.setItem(KEY, JSON.stringify(now));
  } catch (e) { /* nothing to do; the marks below still work this once */ }

  if (!before) return;               // first visit: there is no "since"

  var changed = [];
  Object.keys(now).forEach(function (label) {
    if (before[label] !== undefined && before[label] !== now[label]) {
      changed.push(label);
    }
  });
  if (!changed.length) return;

  changed.forEach(function (label) {
    var row = document.querySelector('.row[data-label="' + label + '"] .label');
    if (!row) return;
    var dot = document.createElement('span');
    dot.className = 'changed';
    dot.setAttribute('role', 'img');
    dot.setAttribute('aria-label', 'changed since you last looked');
    row.appendChild(dot);
  });

  var line = document.getElementById('since');
  if (line) {
    line.innerHTML = changed.length === 1
      ? '<b>' + changed[0] + '</b> has changed since you last looked.'
      : '<b>' + changed.length + ' rows</b> have changed since you last looked.';
  }
})();
</script>
"""


def state_blob(rows: list[tuple[str, PanelResult]]) -> str:
    """What each row says today, as the thing tomorrow compares against.

    The reading plus the note, not the whole panel: a row whose wording moved
    has changed as far as a reader is concerned, but a row whose build
    timestamp moved has not.
    """
    state: dict[str, Any] = {
        label: f"{r.reading}|{r.unit}|{r.note}"
        for label, r in rows
        if r.state is not State.OFF
    }
    return (
        '<script type="application/json" id="board-state">'
        + json.dumps(state, ensure_ascii=False)
        + "</script>"
    )
