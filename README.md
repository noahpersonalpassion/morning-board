# Morning Board

One screen, read in twenty seconds, then closed. What changed near your
address, what closes soon that you cannot undo, and — capped at five — what
everyone is talking about.

Free to run, forever. A GitHub Action rebuilds it once a day and GitHub Pages
serves it. No server, no database, no dependencies beyond the Python standard
library, nothing to pay for and nothing to keep alive.

```bash
python3 build.py              # writes site/index.html and site/board.json
python3 build.py --dry-run    # build and report, write nothing
python3 -m unittest discover -s tests
```

## The one rule

**A panel never raises and never lies.**

If a source is down, slow, paused by its publisher, or returns something
unrecognisable, the row says so. It does not disappear, and it never shows
yesterday's number.

That is enforced in `board/panels/base.py`, not left to each panel's author,
because the failure it prevents is invisible: a stale figure looks exactly
like a current one, and a missing row looks exactly like a row with nothing
to report. Both are indistinguishable from the board working, which is the
worst property a glance surface can have.

The states, and what the mark in the left margin means:

| State | Meaning |
| --- | --- |
| `live` | read successfully, something to report |
| `quiet` | read successfully, nothing to report — **not** a failure |
| `urgent` | something you cannot undo is closing |
| `paused` | the publisher stopped publishing; not our fault |
| `unread` | we could not read it today; our fault or the wire's |
| `off` | not built or not configured yet |

A failed panel never fails the build. `build.py` exits 0 whenever a page was
written, because a failed Action leaves yesterday's page up — the one outcome
worse than an incomplete board.

## Two zones

**Your morning** is about you: your weather, your deadlines, your street.
Instrumented rows, each carrying a state.

**The country** is about everyone: five lines, no instruments, deliberately a
different kind of object. Two rules keep it a panel rather than a feed — five
is a fixed cap and not "today's count", and it is the only part of the board
that can get *shorter* during the day, never longer.

Together they are the two halves of the Delta Rule. Something everyone is
discussing goes in The country; something nobody reported goes in Near You.
Criterion 4 sorts between them rather than deleting one.

## Panels

| Panel | Source | Key needed |
| --- | --- | --- |
| Weather | Open-Meteo | no |
| Deadlines | hand-curated in `board/panels/deadlines.py` | no |
| Near you | NZ Gazette, via the `notice` engine | **yes** |
| Fuel | MBIE weekly CSV | no |
| The country | RNZ RSS | no |
| Transport, Bins | not built | — |

Deadlines is a **permanent row with temporary occupants**. Enrolment is not a
category, it is an occupant: it lives there until 25 October and then leaves
by itself, and the row reads "None open" until something else is closing.
Only things you genuinely cannot undo belong in it.

Near You needs a live feed. Without one it would fall back to the six-week
archive in `fixtures/` and show August's notices as this morning's, so it
reports itself as `off` instead. `BOARD_USE_ARCHIVE=1` opts in explicitly for
looking at the design with real material in it.

## Setup

1. Fork or push this repo to GitHub.
2. Settings → Pages → Source: **GitHub Actions**.
3. Settings → Secrets and variables → Actions, add what you have:
   - `NOTICE_GAZETTE_API_KEY` and `NOTICE_GAZETTE_FEED_URL` — from
     info@gazette.govt.nz. RSS needs a key and is limited to one query a day,
     which is why the Gazette adapter pulls one broad feed and narrows locally.
   - `NOTICE_LEGISLATION_API_KEY` — from contact@pco.govt.nz.
4. Actions tab → **Build the board** → Run workflow.

Never put a key in `board/config.py`. It reads them from the environment so
the file stays safe to commit and safe to fork.

## Making it yours

Edit **`reader.json`**. That is the whole job — your region, the suburbs you
care about, your street, and how close is close enough. It is validated on
load, and a mistake fails the build with a sentence naming the fix rather
than a stack trace three modules down.

There is no national suburb database anywhere in this repo, and that is
deliberate. The strings you write are matched directly against the text of
official notices, so the board works anywhere in New Zealand the day you
fork it. Nobody has to compile a list for your city first.

Keys never go in this file. They come from the environment.

### The proximity floor

`REGION` is every land notice in your city. `SUBURB` is yours and the ones
you border. `STREET` is only yours. National changes — a criminal law
change, emergency rules — ignore the floor entirely, because those are not
less relevant for being nationwide.

Measured against six weeks of real notices, for one Onehunga household:

| Floor | Items per week |
| --- | --- |
| Region | 2.2 |
| Suburb | 0.8 |
| Street | 0.5 |

### The rate is not a property of the board

It is a property of your address. Over the same six weeks:

| Reader | Local items |
| --- | --- |
| Onehunga, Auckland | 3 |
| Whitby, Porirua | 1 |
| Ōtaki, Kāpiti Coast | **8** |

Ōtaki has an expressway being built through it, so land is being taken
street by street — four separate notices naming Rahui Road alone. The board
is loudest exactly where something is happening to you, and silent when
nothing is. That is the whole design working, and it is why a quiet week is
not a broken week.

## Layout

```
build.py                   orchestrator; never fails on a panel
board/
  config.py                who the board is for
  news.py                  the feeds, used by both zones
  render.py                results -> HTML and JSON
  templates/page.html      the shell and all the CSS
  panels/
    base.py                Panel protocol, State, safe_render
    weather.py             Open-Meteo + the week strip
    deadlines.py           permanent row, temporary occupants
    near_you.py            the Gazette engine as one line
    fuel.py                MBIE CSV, with a staleness check
    country.py             RNZ, hard-capped
notice/                    the filter: Delta Rule, templates, proximity
site/                      build output, served by Pages
```

`site/board.json` is published beside the page: the same build as data, so a
phone widget, a shell script or a friend's own page can read the board
without scraping it.
