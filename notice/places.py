"""How close a notice is to the reader.

Region matching answers "is this in my city". For a product whose best
material is *Road Stopped - Gerrard Besson Place, Onehunga*, that is the
wrong question. Everyone in Auckland got that card. Four people needed it.

So a match now has a PROXIMITY, and the card says which one it is. The
reader decides how close is close enough; the default is suburb, because
region-level land notices are noise for 1.7 million people and street-level
alone would miss the notice about the next street over.

Proximity also fixes a coverage gap. A title reading "St Joseph's School,
Orakei" or "Church Street East, Penrose" never says "Auckland", so region
matching dropped it as unresolvable. The reader's own suburb list resolves it.

WHY THERE IS NO NATIONAL SUBURB DATABASE HERE. The first version carried a
hardcoded list of Auckland suburbs, and "support another city" meant
compiling another list — which put a data-entry task between this board and
anyone who does not live in Auckland.

But the list was only ever a guess at something the reader already knows. If
they tell us their region and the suburbs they care about, the lookup has
nothing left to do: "Orakei" in a title, from a reader who says they are in
Auckland and watch Orakei, is a suburb match without any table at all. The
list below is now only a convenience for readers who want a starting point,
and nothing in the matching path depends on it.
"""

from __future__ import annotations

import re
from enum import IntEnum


class Proximity(IntEnum):
    """Ordered: higher is closer. Comparable, so a profile can set a floor."""

    NATIONAL = 1
    REGION = 2
    SUBURB = 3
    STREET = 4


# Auckland suburbs and localities, as they appear in Gazette titles.
# Only the region being served in v0. Adding a region means adding its list.
AUCKLAND_SUBURBS = {
    "albany", "avondale", "balmoral", "bayswater", "beach haven", "birkdale",
    "birkenhead", "blockhouse bay", "botany downs", "browns bay", "bucklands beach",
    "clendon park", "clevedon", "clover park", "coatesville", "dairy flat",
    "devonport", "drury", "eastern beach", "eden terrace", "ellerslie", "epsom",
    "favona", "flat bush", "freemans bay", "glen eden", "glen innes", "glendene",
    "glendowie", "glenfield", "greenlane", "grey lynn", "half moon bay",
    "helensville", "henderson", "herne bay", "hillsborough", "hobsonville",
    "howick", "huapai", "hunters corner", "kelston", "kingsland", "kohimarama",
    "kumeu", "laingholm", "long bay", "lynfield", "mangere", "māngere",
    "mangere bridge", "manukau", "manurewa", "massey", "meadowbank", "mellons bay",
    "milford", "mission bay", "morningside", "mount albert", "mount eden",
    "mount roskill", "mount wellington", "muriwai", "new lynn", "newmarket",
    "newton", "north shore", "northcote", "oneroa", "onehunga", "orakei",
    "ōrākei", "oratia", "otahuhu", "ōtāhuhu", "otara",
    "ōtāra", "pakuranga", "panmure", "papakura", "papatoetoe",
    "parnell", "penrose", "pinehill", "point chevalier", "ponsonby", "pukekohe",
    "puhoi", "pūhoi", "remuera", "riverhead", "rosedale", "rothesay bay",
    "royal oak", "sandringham", "silverdale", "snells beach", "st heliers",
    "st johns", "st marys bay", "stanmore bay", "sunnynook", "swanson",
    "takanini", "takapuna", "tamaki", "tāmaki", "te atatu", "titirangi",
    "torbay", "tuakau", "waiheke", "waimauku", "wairau valley", "waitakere",
    "waitakerē", "warkworth", "wattle downs", "wellsford", "wesley",
    "western springs", "whangaparaoa", "whangaparāoa", "whenuapai",
    "wiri", "wynyard quarter",
}

# Street-type words, used to pull a street name out of a title.
STREET_TYPES = (
    "road", "street", "avenue", "drive", "lane", "place", "crescent",
    "terrace", "way", "parade", "highway", "close", "grove", "rise",
    "quay", "esplanade", "boulevard", "court", "mews", "track",
)

_STREET_RE = re.compile(
    r"\b((?:[A-ZĀ-ſ][\w'’Ā-ſ-]*\s+){1,3}"
    r"(?:" + "|".join(t.capitalize() for t in STREET_TYPES) + r"))\b"
)


def _norm(text: str) -> str:
    return (text.lower()
            .replace("’", "'").replace("‘", "'")
            .replace("—", " ").replace("–", " "))


def suburbs_named(text: str, known: set[str] = AUCKLAND_SUBURBS) -> set[str]:
    """Suburbs mentioned in the text, matched on word boundaries.

    Boundaries matter: "Epsom" must not match inside "Epsomville", and
    "Newton" must not fire on "Newtown".
    """
    low = _norm(text)
    out = set()
    for s in known:
        if re.search(r"(?<![\w'])" + re.escape(_norm(s)) + r"(?![\w'])", low):
            out.add(s)
    return out


def streets_named(text: str) -> set[str]:
    """Street names in the title, e.g. {'Gerrard Besson Place'}."""
    return {m.group(1).strip() for m in _STREET_RE.finditer(text)}


def proximity(
    text: str,
    *,
    streets: list[str],
    suburbs: list[str],
    region_matched: bool,
    region_named: bool,
) -> tuple[Proximity, str]:
    """How close this notice is, and the phrase that explains it.

    Checked closest-first, because the closest true statement is the one
    worth showing: "this is your street" beats "this is in Auckland".
    """
    low = _norm(text)

    for s in streets:
        if _norm(s) and _norm(s) in low:
            return Proximity.STREET, f"on {s}, where you live"

    found_suburbs = suburbs_named(text, {_norm(s) for s in suburbs}) if suburbs else set()
    if found_suburbs:
        name = sorted(found_suburbs)[0].title()
        return Proximity.SUBURB, f"in {name}, your suburb"

    if region_matched:
        return Proximity.REGION, "in your region"

    if not region_named:
        return Proximity.NATIONAL, "nationwide"

    # Named a region, and it was not the reader's. The caller drops this.
    return Proximity.NATIONAL, "elsewhere"
