"""Home-screen install and offline reading.

Two small files turn the page into something that lives on a phone's home
screen with its own icon, opens without browser chrome, and still shows this
morning's board on the train with no signal.

The service worker uses stale-while-revalidate deliberately. The board is a
snapshot of a moment, rebuilt once a day, so showing the cached copy
instantly and refreshing behind it is exactly right — and it means the app
opens in well under a second rather than waiting on a network round trip you
do not need.

One rule carries over from the panels: the page always states when it was
built. An offline board showing yesterday is fine; an offline board that
looks like today's is the same lie the fuel panel refuses to tell.
"""

from __future__ import annotations

import json
from pathlib import Path

from .icons import SIZES, write_icons


def manifest(site_name: str, icons: list[str]) -> str:
    return json.dumps(
        {
            "name": site_name,
            "short_name": site_name.split()[0] if site_name else "Board",
            "description": (
                "What changed near you, what closes soon, and what everyone "
                "is talking about. Twenty seconds, then it is done."
            ),
            "start_url": "./",
            "scope": "./",
            "display": "standalone",
            "orientation": "portrait",
            "background_color": "#EFF2F0",
            "theme_color": "#EFF2F0",
            "icons": [
                {
                    "src": f"./{name}",
                    "sizes": f"{size}x{size}",
                    "type": "image/png",
                    "purpose": "any maskable",
                }
                for name, size in zip(icons, SIZES)
            ],
        },
        indent=1,
    )


SERVICE_WORKER = """\
// Stale-while-revalidate. The board is a daily snapshot, so showing the
// cached copy instantly and refreshing behind it is the correct behaviour,
// not a compromise — offline on the train you still get this morning.
//
// But it does mean the first load after a rebuild shows the PREVIOUS board,
// rendered exactly like a current one. That is the same lie the fuel panel
// refuses to tell, so the page checks board.json on load and says plainly
// when it is holding an older build (board/freshness.py).
//
// Bump CACHE when the shell changes, so an old worker cannot keep serving a
// stale page forever.
const CACHE = 'board-v2';
const SHELL = ['./', './index.html', './board.json'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    caches.match(e.request).then((cached) => {
      const live = fetch(e.request)
        .then((res) => {
          if (res && res.status === 200 && res.type === 'basic') {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(e.request, copy));
          }
          return res;
        })
        .catch(() => cached);
      return cached || live;
    })
  );
});
"""

HEAD_TAGS = """\
<link rel="manifest" href="./manifest.json">
<meta name="theme-color" content="#EFF2F0" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0E1210" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="{short_name}">
<link rel="apple-touch-icon" href="./icon-180.png">
<link rel="icon" type="image/png" sizes="192x192" href="./icon-192.png">
"""

REGISTER = """\
<script>
  // Registration is optional: the board is a plain page and works without it.
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('./sw.js').catch(function () {});
    });
  }
</script>
"""


def write_pwa(out_dir: Path, site_name: str) -> dict[str, object]:
    """Write icons, manifest and service worker. Never raises."""
    icons = write_icons(out_dir)
    (out_dir / "sw.js").write_text(SERVICE_WORKER, encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        manifest(site_name, icons), encoding="utf-8"
    )
    short = site_name.split()[0] if site_name else "Board"
    return {
        "icons": icons,
        "head": HEAD_TAGS.format(short_name=short),
        "register": REGISTER,
    }
