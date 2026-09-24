"""Turning a Gazette notice into something a person can read.

Built after reading nine days of real notices (15-23 Sep 2026). Two things
that reading changed:

1. THE BODY CANNOT BE SHOWN TO A HUMAN. It is legal text. A real land
   notice describes the affected property as "Part Lot 1 DP 113110, shown as
   Section 201 SO 470828 (part RT NA63C/646)". The original design pulled the
   card's `effect` out of the body by taking its second sentence. Against real
   notices that produces lawyer-speak, not an effect.

   So `effect` comes from a TEMPLATE matched on the notice type and the title's
   leading phrase. A template labels a KIND of notice in plain words. It does
   not interpret the individual notice, it is auditable, and it is the same
   every time. The alternative - having a language model summarise each notice -
   would read better and would quietly break the promise that everything on a
   card is traceable to something published.

   A notice with no matching template does not ship. The template table is
   the backlog: every unmatched notice in the decision log is one row to add.

2. THE LOCATION IS IN THE TITLE, NOT THE BODY, and reliably formatted:
   "<what is happening>-<where>", separated by an em dash.

       Road to be Stopped-215 Taylors Mistake Road, Taylors Mistake, Christchurch City
       Land Acquired for a Pedestrian and Cycle Access Way and Declared Road-Frankley Road, Ferndale, New Plymouth
       Land (Subsurface) and a Restrictive Covenant Acquired for Railway Purposes-City Rail Link Project, 42 Upper Queen Street, Auckland Central

   Region also arrives as a structured tag on the notice page ("Auckland"),
   so region matching needs no text analysis at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Notice type codes, taken from the notice number: 2026-ln5366 -> "ln".
# Observed across nine days of real notices.
TYPE_CODES = {
    "go": "Departmental",
    "gs": "General Section",
    "gn": "General Notices",
    "sl": "Secondary Legislation",
    "ln": "Land Notices",
    "lt": "Land Transfers/Joint Family Homes",
    "au": "Authorities/Other Agencies of State",
    "is": "Incorporated Societies",
    # Insolvency. About two thirds of all volume, and none of it reaches an
    # ordinary reader. Excluded at the source query, not by the Delta Rule.
    "aw": "Applications for Winding up/Liquidations",
    "al": "Appointment/Release of Liquidators",
    "aa": "Appointment/Release of Administrators",
    "ar": "Receivers & Managers",
    "ba": "Bankruptcies",
    "md": "Meetings/Last Dates for Debts & Claims",
    "ds": "Removals",
}

# The types worth asking the Gazette for at all. The search accepts several
# noticeType[] parameters in one request, which is how a single daily query
# (the API key limit) still covers everything that matters.
WORTH_FETCHING = ["sl", "go", "gs", "ln", "au", "gn"]

NOTICE_NUMBER_RE = re.compile(r"^(\d{4})-([a-z]{2})(\d+)$", re.I)

# The em dash that splits a title. Real titles use U+2014; a few use a hyphen
# or add stray spaces, so all three are accepted.
TITLE_SPLIT_RE = re.compile(r"\s*[—–]\s*|\s+-\s+")


@dataclass
class Template:
    """A plain-words label for a KIND of notice."""

    template_id: str
    type_codes: list[str]
    title_starts: list[str]        # matched case-insensitively on the action
    effect: str                    # what this kind of notice means, plainly
    audience: str                  # who it lands on, for why_you
    locates_property: bool = False # True when the title names a specific place
    # The reader must have declared this about themselves for the notice to
    # reach them. Without it the tuning set told an Auckland household about
    # pig levies and sheepmeat levies, which is exactly the undifferentiated
    # feed Notice exists to replace. A template with no attribute reaches
    # everyone, which is the right default for civic and criminal changes.
    requires_attribute: str | None = None
    # Phrases that disqualify a match. Needed because a revocation title
    # contains the whole appointment title: "Revocation of the Notice of
    # Direction to Appoint a Limited Statutory Manager". Without this the
    # appointment template matched a removal and told a school's parents
    # their board had been taken over when in fact it had just been handed
    # back. Opposite news, same sentence.
    title_excludes: list[str] = field(default_factory=list)


TEMPLATES: list[Template] = [
    # --- Land: the narrow, high-stakes core ----------------------------
    Template(
        "road_stopped", ["ln"],
        ["road to be stopped", "road stopped"],
        "A road is being permanently closed. Access for nearby properties "
        "changes when this takes effect.",
        "people who live on or use this road",
        locates_property=True,
    ),
    Template(
        "land_declared_road", ["ln"],
        ["land declared road", "declared road"],
        "Private land is being turned into public road.",
        "the owners of this land and their neighbours",
        locates_property=True,
    ),
    # These four were one template. Having your land taken, having a tunnel
    # dug under it, and having a right of way run across it are not the same
    # event, and one sentence made them read as though they were.
    Template(
        "land_subsurface", ["ln"],
        ["land (subsurface)", "subsurface"],
        "The ground underneath this property is being taken, usually for "
        "tunnelling. The surface stays with the owner, but there will be "
        "permanent limits on building, piling and excavation.",
        "the owners of this land",
        locates_property=True,
    ),
    Template(
        "easement_acquired", ["ln"],
        ["easement acquired", "easement taken"],
        "A permanent right over this land is being taken. The owner keeps "
        "the land, but cannot block what the easement allows.",
        "the owners of this land",
        locates_property=True,
    ),
    Template(
        "land_set_apart", ["ln"],
        ["land set apart"],
        "Land is being formally set aside for a public purpose.",
        "people near this land",
        locates_property=True,
    ),
    Template(
        "land_acquired", ["ln"],
        ["land acquired", "land taken"],
        "This land is being taken under the Public Works Act. The owner "
        "loses it; compensation is handled separately.",
        "the owners and occupiers of this land",
        locates_property=True,
    ),
    Template(
        "reserve_revoked", ["ln"],
        ["revocation of the reservation", "reserve revoked"],
        "Land stops being a reserve, which removes the protections that "
        "came with that status.",
        "people who use this reserve",
        locates_property=True,
    ),
    Template(
        "geographic_name", ["ln"],
        ["notice of final determinations to assign geographic names",
         "assign geographic names"],
        "Official place names are changing.",
        "people who live in the named places",
        locates_property=True,
    ),

    # --- Schools: tiny audience, enormous to them ----------------------
    Template(
        "school_commissioner", ["go"],
        ["notice of appointment of a commissioner",
         "notice of dissolution of the"],
        "This school's elected board has been replaced by a "
        "government-appointed commissioner.",
        "parents and whanau at this school",
        locates_property=True,
    ),
    # Revocation first: its title contains the appointment's title.
    Template(
        "school_manager_removed", ["go"],
        ["revocation of the notice of direction to appoint"],
        "The statutory manager is being removed from this school's board. "
        "The board gets those powers back.",
        "parents and whanau at this school",
        locates_property=True,
    ),
    Template(
        "school_manager_appointed", ["go"],
        ["notice of direction to appoint a limited statutory manager",
         "notice of direction to appoint"],
        "The Ministry is putting a statutory manager over this school's "
        "board. The board loses control of the areas named in the notice.",
        "parents and whanau at this school",
        locates_property=True,
        title_excludes=["revocation"],
    ),
    Template(
        "school_integration", ["go"],
        ["cancellation of integration agreement", "integration agreement"],
        "This school's integration agreement with the Crown is changing, "
        "which affects its status and its funding.",
        "parents and whanau at this school",
        locates_property=True,
    ),

    # --- Emergencies ---------------------------------------------------
    # Extension first: its title contains the plain one.
    Template(
        "transition_extended", ["gs", "sl"],
        ["notice of extension of local transition period",
         "extension of local transition period"],
        "The emergency transition period here has been extended. Councils "
        "keep emergency powers for longer, including over access to "
        "property and roads.",
        "everyone in the affected district",
        locates_property=True,
    ),
    Template(
        "transition_started", ["gs", "sl"],
        ["notice of local transition period", "local transition period"],
        "A local transition period is now in force. Councils have emergency "
        "powers here, including over access to property and roads.",
        "everyone in the affected district",
        locates_property=True,
        title_excludes=["extension"],
    ),
    Template(
        "emergency_rules", ["sl", "gs"],
        ["notification of entry into force of emergency management",
         "entry into force of emergency management"],
        "New Emergency Management rules are now in force nationwide.",
        "everyone",
    ),

    # --- Broad civic ---------------------------------------------------
    # There was a template here for "Notice Under the Social Security Act
    # 2018". It shipped, and it told a beneficiary "a rule under the Social
    # Security Act is changing" — which is no information at all. A title
    # that names only its Act does not say what changed, so it is now caught
    # by the vague-title rule below instead of being given a sentence that
    # pretends to explain it.
    Template(
        "fisheries_closure", ["sl"],
        ["fisheries (", "temporary closure"],
        "A fishing area is being temporarily closed.",
        "people who fish in this area",
        locates_property=True,
    ),

    # --- Second batch: checked against the statute before drafting -----
    #
    # The first draft of the drug order below said possession was NOT an
    # offence. That is the UK regime. Misuse of Drugs Act 1975 s4D(2) says a
    # temporary class drug "must be treated for all purposes as if the drug
    # were a controlled drug that is specified or described in Part 1 of
    # Schedule 3" — Class C1 — so possession IS an offence here. s4D(3)
    # points at the s7(5) prosecutorial discretion for possession and use.
    # Nothing downstream could have caught that sentence being wrong.
    Template(
        "temporary_class_drug", ["sl"],
        ["temporary class drug order", "renewal of temporary class drug order"],
        "A substance has been temporarily made a controlled drug at Class C1 "
        "level. Possessing, using, supplying, making or importing it is now "
        "an offence, though prosecutors have a discretion on possession and "
        "use. The order lasts a year and can be renewed once.",
        "anyone who might come across this substance",
    ),
    Template(
        "meat_levy", ["gs", "sl"],
        ["sheepmeat and beef commodity levies", "commodity levies",
         "notification of levy rates on sheepmeat and beef"],
        "The levy on every sheep and beef animal processed has been set for "
        "the coming year. It is collected per head at slaughter and deducted "
        "by the processor, so farmers carry it.",
        "sheep and beef farmers",
        requires_attribute="sheep_beef_farmer",
    ),
    # Different statute, and it works differently: Pork Industry Board Act
    # 1997 s37 demands the levy from the LICENSEE of the premises, and s39
    # lets that licensee recover it from the pig's owner — "may", not must.
    # Saying "farmers pay it", as the meat levy template does, would be wrong.
    Template(
        "pork_levy", ["sl", "gs"],
        ["levy on pigs slaughtered"],
        "The levy on each pig slaughtered has been set for the coming year. "
        "The processing premises pays it, and may recover it from the pig's "
        "owner by deducting it from what they are paid.",
        "pig farmers and processors",
        requires_attribute="pig_farmer",
    ),
    Template(
        "fmc_exemption", ["sl"],
        ["financial markets conduct (", "exemption notice"],
        "A named investment scheme has been excused from some of its "
        "obligations under the Financial Markets Conduct Act. Something it "
        "was required to tell its members, it may no longer have to.",
        "members of this scheme",
        requires_attribute="managed_fund_member",
    ),
    Template(
        "inquiry_terms", ["go"],
        ["amendment to the terms of reference of the government inquiry",
         "terms of reference of the government inquiry"],
        "The scope of a government inquiry has changed — what it can look "
        "into, or when it must report.",
        "people affected by what the inquiry is examining",
        locates_property=True,
    ),
    Template(
        "ece_licensing", ["sl"],
        ["licensing criteria", "ngā paearu whai raihana"],
        "The licensing standards early childhood services must meet have "
        "changed. It affects what a service has to do to stay licensed.",
        "families using these services, and the people who run them",
        requires_attribute="young_children",
    ),
    # Kept, but it is the weakest of the batch: it may reach only the airport
    # operator rather than any traveller. First real one through the log
    # decides whether it moves to NEVER_SHIP.
    Template(
        "customs_airport", ["go"],
        ["amendment of customs airport designation",
         "customs airport designation"],
        "Where international flights may land and clear customs at this "
        "airport has changed.",
        "people flying internationally through this airport",
        locates_property=True,
    ),
]


@dataclass
class Exclusion:
    """A notice type deliberately kept out of the feed.

    Distinct from having no template. "No template yet" is a backlog item;
    this is a decision, and the decision log records it as one so the
    reasoning stays visible and arguable.

    The principle, from the ACC case: a notice can be genuinely important and
    still not belong here. The test is not "does this topic matter" but "is
    anything about a reader's situation different tomorrow".
    """

    exclusion_id: str
    type_codes: list[str]
    title_starts: list[str]
    reason: str


NEVER_SHIP: list[Exclusion] = [
    Exclusion(
        "acc_funding_policy", ["go"],
        ["funding policy statement"],
        "sets how ACC must think when it later recommends levy rates. "
        "Nothing changes for anyone today; the levy change itself will be a "
        "separate notice, and that one ships.",
    ),
    Exclusion(
        "aml_exemption", ["sl"],
        ["ministerial exemptions under the anti-money laundering",
         "amendment—ministerial exemptions under the anti-money laundering"],
        "excuses named businesses from anti-money-laundering obligations. "
        "Lands on compliance officers, not on people.",
    ),
    Exclusion(
        "appointment_ce", ["go"],
        ["appointment of chief executive", "appointment of a chief executive"],
        "an appointment. Nothing happens to anyone.",
    ),
    Exclusion(
        "annual_report", ["gs", "go"],
        ["annual report of industry body", "annual report"],
        "a document now exists. That is the whole event.",
    ),
]


def match_exclusion(title: str, type_code: str | None) -> Exclusion | None:
    action, _ = split_title(title)
    low = action.lower()
    full = title.strip().lower()
    for e in NEVER_SHIP:
        if type_code and e.type_codes and type_code not in e.type_codes:
            continue
        if any(low.startswith(s) or s in full for s in e.title_starts):
            return e
    return None


def notice_type(notice_number: str) -> str | None:
    """2026-ln5366 -> 'ln'."""
    m = NOTICE_NUMBER_RE.match((notice_number or "").strip())
    return m.group(2).lower() if m else None


def split_title(title: str) -> tuple[str, str]:
    """'Road to be Stopped-215 Taylors Mistake Road, Christchurch City'
    -> ('Road to be Stopped', '215 Taylors Mistake Road, Christchurch City')

    Returns ('', title) shaped input when there is no location part.
    """
    parts = TITLE_SPLIT_RE.split(title.strip(), maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return title.strip(), ""


# A title that names only its Act says nothing about what changed.
#   "Notice Under the Social Security Act 2018"
#   "Notice Pursuant to Section 115 of the Land Transfer Act 2017"
# Both are real. Neither tells a reader anything, and no template can fix
# that without reading the notice and interpreting it — which is the one
# thing Notice does not do. These drop, and the decision log marks them as
# needing the notice page, not as rejected.
VAGUE_TITLE_RE = re.compile(
    r"^notice\s+(under|pursuant\s+to)\b[^—–]*\bact\b[\s,\d]*$", re.I
)


def is_vague_title(title: str) -> bool:
    return bool(VAGUE_TITLE_RE.match(title.strip()))


def match_template(
    title: str, type_code: str | None, attributes: list[str] | None = None
) -> Template | None:
    action, _ = split_title(title)
    low = action.lower()
    full = title.strip().lower()
    attrs = set(attributes or [])
    for t in TEMPLATES:
        if type_code and t.type_codes and type_code not in t.type_codes:
            continue
        if t.requires_attribute and t.requires_attribute not in attrs:
            continue
        if any(x in full for x in t.title_excludes):
            continue
        if any(low.startswith(s) or s in full for s in t.title_starts):
            return t
    return None
