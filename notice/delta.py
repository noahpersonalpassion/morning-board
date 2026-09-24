"""The Delta Rule.

An item ships only if all four pass:

  1 PUBLISHED    traceable to a primary source, with URL and timestamp
  2 SETTLED      it has occurred, or is legally scheduled
  3 CONSEQUENTIAL a stated or computable effect, and the reader is in it
  4 UNOBVIOUS    not in major NZ media in the last 7 days

All four are always evaluated, even after one fails. Short-circuiting would
be faster and would throw away the data v0 exists to collect: you want to
know every reason an item dropped, not just the first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models import Candidate, CriterionResult, Card, Provenance
from .novelty import HeadlineCorpus
from .places import Proximity, proximity, suburbs_named
from .templates import (
    is_vague_title, match_exclusion, match_template, notice_type, split_title,
)

# --- criterion 2: settled vs proposed --------------------------------------

# Language that means a thing is decided, or that a deadline is fixed.
SETTLED_SIGNALS = [
    "comes into force", "came into force", "commences", "commencing",
    "takes effect", "effective from", "with effect from", "confirmed",
    "is amended", "was appointed", "has appointed", "notice is given",
    "closes at", "close at", "closing date", "must be received by",
    "no later than", "expires on", "revoked",
]

# Language that means a thing is still being argued about.
PROPOSAL_SIGNALS = [
    "proposes", "proposed", "proposal", "no decision has been made",
    "seeking feedback", "submissions are invited", "submissions invited",
    "consultation on", "discussion document", "draft",
]

DATE_RE = re.compile(
    r"\b\d{1,2}\s+(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+\d{4}\b",
    re.I,
)


@dataclass
class Rule:
    """One consequence rule. If it fires, its `population` becomes why_you."""

    rule_id: str
    population: str            # plain words, shown to the reader
    any_terms: list[str]       # at least one must appear
    all_terms: list[str] = field(default_factory=list)
    requires_attribute: str | None = None   # reader must declare this

    def matches(self, text: str, profile: "Profile") -> bool:
        low = text.lower()
        if self.requires_attribute and self.requires_attribute not in profile.attributes:
            return False
        if self.all_terms and not all(t in low for t in self.all_terms):
            return False
        return any(t in low for t in self.any_terms)


@dataclass
class Profile:
    """Who the reader is. In the shipped product this never leaves the device."""

    region_terms: list[str]           # e.g. ["auckland", "tamaki makaurau"]
    attributes: list[str]             # e.g. ["diesel_vehicle", "renter"]
    rules: list[Rule]
    # Where the reader actually lives. Streets are checked first, then
    # suburbs; both stay on the device in the shipped product.
    streets: list[str] = field(default_factory=list)
    suburbs: list[str] = field(default_factory=list)
    # How close a place-specific notice must be before it is worth sending.
    # SUBURB by default: REGION means every Auckland land notice, STREET
    # alone misses the one about the next street over.
    proximity_floor: Proximity = Proximity.SUBURB


# Used to tell a REGIONAL notice from a NATIONAL one.
#
# The first version of this rule required a notice to name the reader's
# region, which silently dropped every national change — the RUC rate rise
# in the fixture went out on "names no region you are in". A notice that
# names no region is national and reaches everyone; only a notice that names
# OTHER regions and not yours should drop. The decision log caught this on
# the first run, which is the argument for keeping it.
NZ_REGIONS = {
    "northland": ["northland", "whangarei", "whangārei"],
    "auckland": ["auckland", "tamaki makaurau", "tāmaki makaurau"],
    "waikato": ["waikato", "hamilton", "kirikiriroa"],
    "bay of plenty": ["bay of plenty", "tauranga", "rotorua"],
    "gisborne": ["gisborne", "tairawhiti", "tūranganui"],
    "hawke's bay": ["hawke's bay", "hawkes bay", "napier", "hastings"],
    "taranaki": ["taranaki", "new plymouth"],
    "manawatu-whanganui": ["manawatu", "manawatū", "whanganui",
                           "palmerston north"],
    "wellington": ["wellington", "te whanganui-a-tara", "porirua",
                   "lower hutt", "upper hutt"],
    "tasman": ["tasman", "motueka"],
    "nelson": ["nelson", "whakatū"],
    "marlborough": ["marlborough", "blenheim"],
    "west coast": ["west coast", "greymouth", "westport"],
    "canterbury": ["canterbury", "christchurch", "Ōtautahi", "timaru"],
    "otago": ["otago", "dunedin", "Ōtepoti", "queenstown"],
    "southland": ["southland", "invercargill"],
    "chatham islands": ["chatham islands"],
}


# New Zealand's 67 territorial authorities, mapped to their region.
#
# Without these, a title reading "Smith Road, Dannevirke, Tararua District"
# resolved to NO region, and a notice with no region was treated as national
# — so an Auckland reader was sent land takings in Tararua, Clutha and
# Waitomo. An unrecognised district is not "everywhere"; it is "somewhere I
# could not identify", which is a different answer and a different action.
TERRITORIAL_AUTHORITIES = {
    "far north": "northland", "whangarei": "northland",
    "kaipara": "northland",
    "thames-coromandel": "waikato", "hauraki": "waikato",
    "matamata-piako": "waikato", "waipa": "waikato",
    "otorohanga": "waikato", "south waikato": "waikato",
    "waitomo": "waikato", "taupo": "waikato", "taupō": "waikato",
    "western bay of plenty": "bay of plenty", "whakatane": "bay of plenty",
    "whakatāne": "bay of plenty", "kawerau": "bay of plenty",
    "opotiki": "bay of plenty", "ōpotiki": "bay of plenty",
    "wairoa": "hawke's bay", "central hawke's bay": "hawke's bay",
    "stratford": "taranaki", "south taranaki": "taranaki",
    "ruapehu": "manawatu-whanganui", "rangitikei": "manawatu-whanganui",
    "rangitīkei": "manawatu-whanganui",
    "tararua": "manawatu-whanganui", "horowhenua": "manawatu-whanganui",
    "kapiti coast": "wellington", "kāpiti coast": "wellington",
    "masterton": "wellington", "carterton": "wellington",
    "south wairarapa": "wellington", "hutt city": "wellington",
    "buller": "west coast", "grey district": "west coast",
    "westland": "west coast",
    "kaikoura": "canterbury", "kaikōura": "canterbury",
    "hurunui": "canterbury", "waimakariri": "canterbury",
    "selwyn": "canterbury", "ashburton": "canterbury",
    "mackenzie": "canterbury", "waimate": "canterbury",
    "central otago": "otago", "queenstown-lakes": "otago",
    "clutha": "otago", "waitaki": "otago",
    "gore": "southland",
}

# Too coarse to act on. A land district spans more than one region — "North
# Auckland Land District" covers both Auckland and Northland — so it names a
# place without identifying one. Treated as unresolved, never as national.
COARSE_LOCATIONS = (
    "land district", "land registration district", "north island",
    "south island",
)


def _normalise(text: str) -> str:
    """Fold the typographic characters real notices actually use.

    A live notice titled "Central Hawke's Bay District" uses U+2019 for the
    apostrophe. Matching against the straight-quote "hawke's bay" missed it,
    and the notice shipped to an Auckland reader. Macrons are left alone —
    they are part of the word, not punctuation.
    """
    return (text.lower()
            .replace("’", "'").replace("‘", "'")
            .replace("—", " ").replace("–", " "))


def regions_named(text: str) -> set[str]:
    low = _normalise(text)
    found = {
        region for region, terms in NZ_REGIONS.items()
        if any(_normalise(t) in low for t in terms)
    }
    found |= {
        region for ta, region in TERRITORIAL_AUTHORITIES.items()
        if _normalise(ta) in low
    }
    return found


def mine_direct(named: set[str], profile: "Profile") -> bool:
    return any(
        any(t in r or r in t for t in profile.region_terms) for r in named
    )


def names_a_coarse_place(text: str) -> bool:
    low = _normalise(text)
    return any(c in low for c in COARSE_LOCATIONS)


# --- the criteria -----------------------------------------------------------

def check_published(c: Candidate) -> CriterionResult:
    missing = []
    if not c.url:
        missing.append("url")
    if not c.published:
        missing.append("published timestamp")
    if not c.source_name:
        missing.append("source name")
    if missing:
        return CriterionResult(
            "published", False,
            f"not traceable: missing {', '.join(missing)}",
        )
    return CriterionResult(
        "published", True,
        f"{c.source_name}, {c.published.date().isoformat()}",
        {"url": c.url},
    )


def check_settled(c: Candidate) -> CriterionResult:
    text = c.text().lower()

    # Some sources publish instruments, not reports. A Gazette notice IS the
    # legal act — "Road to be Stopped" is not a plan to stop a road, it is the
    # notice stopping it, effective on publication. The first version of this
    # check demanded commencement language plus a date in the text, and
    # dropped every real Gazette notice on the tuning set, because a notice's
    # title never says "comes into force" and its body is a schedule of legal
    # land descriptions. Presume settled, and let proposal language override.
    if c.settled_on_publication:
        proposal_hits = [s for s in PROPOSAL_SIGNALS if s in text]
        consultative = any(
            s in text for s in
            ("submissions are invited", "submissions invited",
             "seeking feedback", "no decision has been made",
             "discussion document")
        )
        if consultative:
            return CriterionResult(
                "settled", False,
                f"consultative notice: {', '.join(proposal_hits[:3]) or 'invites submissions'}",
                {"proposal_signals": proposal_hits},
            )
        return CriterionResult(
            "settled", True,
            "published in the Gazette, which is the legal act itself",
            {"presumed": True, "proposal_signals": proposal_hits},
        )
    settled_hits = [s for s in SETTLED_SIGNALS if s in text]
    proposal_hits = [s for s in PROPOSAL_SIGNALS if s in text]
    has_date = bool(DATE_RE.search(c.text()))

    # A consultation that is CLOSING is settled even though the thing being
    # consulted on is not: the deadline itself is fixed and unavoidable.
    deadline = any(
        s in text for s in
        ("closes at", "close at", "closing date", "must be received by",
         "no later than")
    )

    if settled_hits and has_date:
        if proposal_hits and not deadline:
            return CriterionResult(
                "settled", False,
                "reads as a proposal with no fixed date: "
                f"{', '.join(proposal_hits[:3])}",
                {"settled_signals": settled_hits, "proposal_signals": proposal_hits},
            )
        return CriterionResult(
            "settled", True,
            f"fixed by: {settled_hits[0]}" + (" (deadline)" if deadline else ""),
            {"settled_signals": settled_hits, "has_date": has_date},
        )

    if proposal_hits:
        return CriterionResult(
            "settled", False,
            f"still proposed: {', '.join(proposal_hits[:3])}",
            {"proposal_signals": proposal_hits},
        )

    return CriterionResult(
        "settled", False,
        "no commencement, effective date or deadline found",
        {"has_date": has_date},
    )


def check_consequential(c: Candidate, profile: Profile) -> CriterionResult:
    """Template first, then geography.

    A notice with no template is one Notice does not yet know how to say in
    plain words. It drops, and the decision log names the template that is
    missing — that log is the backlog for the template table.
    """
    code = notice_type(c.notice_number) if c.notice_number else None

    excluded = match_exclusion(c.title, code)
    if excluded is not None:
        return CriterionResult(
            "consequential", False,
            f"deliberately excluded — {excluded.reason}",
            {"excluded": excluded.exclusion_id, "by_decision": True},
        )

    if is_vague_title(c.title):
        return CriterionResult(
            "consequential", False,
            "the title names only its Act — it does not say what changed",
            {"vague_title": True, "needs_fetch": True, "type_code": code},
        )

    template = match_template(c.title, code, profile.attributes)

    if template is None:
        return CriterionResult(
            "consequential", False,
            f"no template reaches you for this kind of notice "
            f"(type '{code or 'unknown'}': {split_title(c.title)[0][:60]})",
            {"needs_template": True, "type_code": code},
        )

    # Region comes from the notice's own tags where it has them, and falls
    # back to the text for sources that carry no tags.
    tagged = {_normalise(t) for t in c.tags}
    named = {r for r, terms in NZ_REGIONS.items()
             if any(_normalise(term) in tagged for term in terms)}
    if not named:
        named = regions_named(c.text())

    # A suburb implies its region. "St Joseph's School, Orakei" and "Church
    # Street East, Penrose" never say Auckland, so region matching alone
    # dropped both as unresolvable when they are plainly local.
    if profile.suburbs and suburbs_named(c.text(), {_normalise(s) for s in profile.suburbs}):
        named = named | {r for r in profile.region_terms if r in NZ_REGIONS}

    # A notice about a specific place that does not say WHICH place cannot be
    # matched to a reader, and for a product built on "this affects your
    # street" a guess is worse than silence. On the tuning set this caught
    # "Revocation of the Reservation Over a Reserve" and a school commissioner
    # notice, both of which had shipped to an Auckland reader on the strength
    # of naming no region at all. These are not permanent drops: the notice
    # page carries a region tag, so they become a fetch, not a rejection.
    _, location = split_title(c.title)
    if template.locates_property and not named:
        # Either it names no place, or it names one this does not recognise.
        # Both are "unknown", never "national". Reading an unrecognised
        # district as nationwide sent Tararua, Clutha and Waitomo land
        # takings to an Auckland reader over the six-week corpus.
        why = (
            "names a place this does not recognise"
            if location else
            "names a specific place but not which one"
        )
        return CriterionResult(
            "consequential", False,
            f"{why} — needs the notice page to resolve the location",
            {"template": template.template_id, "needs_fetch": True,
             "location": location[:80]},
        )

    if template.locates_property and names_a_coarse_place(c.title) and not mine_direct(
            named, profile):
        return CriterionResult(
            "consequential", False,
            "names only a land district, which spans more than one region "
            "— needs the notice page",
            {"template": template.template_id, "needs_fetch": True},
        )

    mine = {r for r in named
            if any(t in r or r in t for t in profile.region_terms)}

    if named and not mine:
        return CriterionResult(
            "consequential", False,
            f"applies to {', '.join(sorted(named))} — not where you are",
            {"template": template.template_id, "regions": sorted(named)},
        )

    prox, where = proximity(
        c.text(),
        streets=profile.streets,
        suburbs=profile.suburbs,
        region_matched=bool(mine),
        region_named=bool(named),
    )

    # A land or school notice that only resolves to "somewhere in Auckland"
    # is noise for 1.7 million people. The floor lets the reader say how
    # close is close enough; national changes bypass it, because a criminal
    # law change is not less relevant for being nationwide.
    if (template.locates_property
            and prox is not Proximity.NATIONAL
            and prox < profile.proximity_floor):
        return CriterionResult(
            "consequential", False,
            f"only resolves to {where} — closer than "
            f"{profile.proximity_floor.name.lower()} is what you asked for",
            {"template": template.template_id, "proximity": prox.name,
              "too_far": True},
        )

    return CriterionResult(
        "consequential", True,
        f"This reaches {template.audience}, {where}.",
        {"template": template.template_id, "proximity": prox.name,
         "regions": sorted(named),
         "locates_property": template.locates_property},
    )


def check_unobvious(
    c: Candidate,
    corpus: HeadlineCorpus,
    allow_unverified: bool = False,
) -> CriterionResult:
    if not corpus.available:
        if allow_unverified:
            return CriterionResult(
                "unobvious", True,
                "NOVELTY UNVERIFIED - no headline corpus available (override)",
                {"override": True},
            )
        return CriterionResult(
            "unobvious", False,
            "cannot verify: no headline corpus available. Refusing to ship "
            "rather than guess.",
            {"failed_outlets": corpus.outlets_failed},
        )

    match = corpus.best_match(c.title)
    if match is None:
        return CriterionResult(
            "unobvious", True,
            f"no coverage in {len(corpus.headlines)} headlines from "
            f"{len(corpus.outlets_ok)} outlets over {corpus.window_days} days",
            {"outlets": corpus.outlets_ok},
        )
    return CriterionResult(
        "unobvious", False,
        f"already reported by {match.headline.outlet}: "
        f"“{match.headline.title}”",
        {"score": match.score, "shared_terms": match.shared,
         "url": match.headline.url},
    )


def evaluate(
    c: Candidate,
    profile: Profile,
    corpus: HeadlineCorpus,
    allow_unverified_novelty: bool = False,
) -> list[CriterionResult]:
    return [
        check_published(c),
        check_settled(c),
        check_consequential(c, profile),
        check_unobvious(c, corpus, allow_unverified_novelty),
    ]


# --- building the card ------------------------------------------------------

def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    parts = re.split(r"(?<=[.!?])\s+", text)
    return parts[0] if parts else text


def _rest(text: str) -> str:
    text = " ".join(text.split())
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(parts[1:]) if len(parts) > 1 else ""


def build_card(c: Candidate, criteria: list[CriterionResult],
               profile_attributes: list[str] | None = None) -> Card:
    """Assemble the reader-facing card.

    Raises if a mandatory field cannot be filled. A card that cannot state
    its effect or its selection rule is not a card — enforcing that here
    rather than in a template is deliberate.
    """
    by_name = {r.name: r for r in criteria}

    code = notice_type(c.notice_number) if c.notice_number else None
    template = match_template(c.title, code, profile_attributes)
    if template is None:
        raise ValueError(f"{c.key}: no template; cannot say this in plain words")

    action, location = split_title(c.title)
    effect = template.effect
    if location and template.locates_property:
        effect = f"{effect} Where: {location}."

    # Many notices take effect on publication ("on the date of publication
    # hereof in the New Zealand Gazette") rather than naming a date. The
    # publication date IS the effective date in that case, so fall back to it
    # rather than refusing to build the card.
    when_m = DATE_RE.search(c.text())
    if when_m:
        when = when_m.group(0)
    elif "date of publication" in c.body.lower():
        when = f"In force from {c.published.strftime('%-d %B %Y')} (on publication)"
    else:
        when = c.published.strftime("%-d %B %Y")

    confidence = (
        "Exact. Stated in the source, not modelled."
        if c.provenance is Provenance.LIVE
        else f"Source state: {c.provenance.value}. Treat with care."
    )

    return Card(
        what=_first_sentence(c.title if c.title.endswith(".") else c.title + "."),
        effect=effect,
        when=when,
        source_name=c.source_name,
        source_url=c.url,
        published=c.published,
        retrieved=c.retrieved,
        provenance=c.provenance,
        confidence=confidence,
        why_you=by_name["consequential"].reason,
        action_label="Open the original notice",
        action_url=c.url,
    )


def default_profile() -> Profile:
    """The v0 reader: an Auckland household in Onehunga, with a diesel vehicle.

    In the product this is set by the reader and never leaves the device.
    The suburbs are the reader's own plus the ones they border, because a
    road stopped one suburb over still changes how you drive to work.
    """
    return Profile(
        region_terms=["auckland", "tamaki makaurau", "tāmaki makaurau"],
        attributes=["diesel_vehicle", "household"],
        streets=["Gerrard Besson Place"],
        suburbs=["Onehunga", "Royal Oak", "Penrose", "Hillsborough",
                 "Mount Roskill", "Ellerslie", "Greenlane"],
        proximity_floor=Proximity.SUBURB,
        rules=[
            Rule(
                "household_charges",
                "You are an Auckland household, and this changes a charge you pay.",
                any_terms=["residential", "rating unit", "targeted rate",
                           "water", "household", "connection"],
            ),
            Rule(
                "vehicle_costs",
                "You told Notice you run a diesel vehicle, and this changes "
                "what it costs to keep on the road.",
                any_terms=["road user charges", "diesel", "vehicle licensing"],
                requires_attribute="diesel_vehicle",
            ),
            Rule(
                "civic_deadline",
                "This is a deadline you cannot undo, and it applies where you live.",
                any_terms=["submissions", "consultation", "enrol", "closes at",
                           "closing date"],
            ),
        ],
    )
