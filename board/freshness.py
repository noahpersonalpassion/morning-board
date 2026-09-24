"""The board checking whether it is itself out of date.

Every panel on this board refuses to show a stale figure as a current one.
The service worker was quietly breaking that rule for the whole page: it
serves the cached copy first, so after a rebuild you get yesterday's board,
rendered exactly like today's, with no way to tell. The footer's build time
is the only clue and it is at the bottom.

That is the same failure the fuel panel refuses to commit, one level up. So
the page now applies its own rule to itself: it asks the network what the
current build is, and if it is holding an older one it says so and offers a
reload. Silently, if it cannot ask — offline, the cached board is the right
thing to show, and the footer already states when it was built.

The check costs one small request and never blocks rendering.
"""

from __future__ import annotations

STYLE = """
  .stale {
    display: none; margin: 0; padding: 10px 13px;
    background: var(--warn-bg); color: var(--warn);
    border-radius: 9px; font-size: 13px; line-height: 1.45;
  }
  .stale.show { display: block; }
  .stale button {
    font: inherit; font-weight: 600; color: inherit;
    background: none; border: 0; padding: 0; margin-left: 4px;
    text-decoration: underline; text-underline-offset: 3px; cursor: pointer;
  }
"""

MARKUP = (
    '<p class="stale" id="stale" role="status">'
    'This is an older board. '
    '<button type="button" id="reload">Load the current one</button>'
    '</p>'
)


def script(built_iso: str) -> str:
    return f"""
<script>
(function () {{
  var BUILT = {built_iso!r};
  var el = document.getElementById('stale');
  var btn = document.getElementById('reload');
  if (!el || !btn) return;

  btn.addEventListener('click', function () {{
    // Drop the cached shell before reloading, or the worker just serves the
    // same stale copy back and the button appears to do nothing.
    var done = function () {{ location.reload(); }};
    if (!('caches' in window)) return done();
    caches.keys()
      .then(function (ks) {{ return Promise.all(ks.map(function (k) {{ return caches.delete(k); }})); }})
      .then(done, done);
  }});

  // Ask the network directly what the current build is. Offline this throws,
  // and the cached board stays up without complaint — which is correct.
  fetch('./board.json?t=' + Date.now(), {{ cache: 'no-store' }})
    .then(function (r) {{ return r.ok ? r.json() : null; }})
    .then(function (live) {{
      if (live && live.built && live.built > BUILT) el.classList.add('show');
    }})
    .catch(function () {{ /* offline: nothing to say */ }});
}})();
</script>
"""
