"""Load a reader from reader.json, and refuse to load a broken one.

The board is meant to be forked. That means the first thing a stranger does
is edit this config, and the second thing is run a build — so the failure
they meet has to be a sentence telling them what to fix, not a KeyError from
three modules down.

Every check here exists because getting it wrong produces a board that looks
like it is working. A misspelled region silently matches nothing and the
reader concludes their suburb is quiet. An unknown attribute silently hides
notices forever. Both are invisible, so both are errors at load time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .delta import NZ_REGIONS, Profile, default_profile
from .places import Proximity

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "reader.json"

# Attributes the template table actually gates on. An attribute that is not
# here does nothing, which looks identical to one that is spelled wrong.
KNOWN_ATTRIBUTES = {
    "household", "diesel_vehicle", "sheep_beef_farmer", "pig_farmer",
    "managed_fund_member", "young_children",
}


class ReaderConfigError(ValueError):
    """Raised with a sentence a person can act on."""


@dataclass
class Reader:
    name: str
    place: str
    lat: float
    lon: float
    profile: Profile


def _require(data: dict, key: str, kind: type, path: Path):
    if key not in data:
        raise ReaderConfigError(
            f"{path.name} is missing \"{key}\". See the _comment entries in "
            f"the file for what each key means."
        )
    value = data[key]
    if not isinstance(value, kind):
        raise ReaderConfigError(
            f"{path.name}: \"{key}\" should be "
            f"{'a list' if kind is list else kind.__name__}, got "
            f"{type(value).__name__}."
        )
    return value


def load(path: Path | str | None = None) -> Reader:
    path = Path(path) if path else DEFAULT_PATH
    if not path.exists():
        raise ReaderConfigError(
            f"No {path.name} found at {path}. Copy the one in the repo root "
            f"and edit it."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ReaderConfigError(
            f"{path.name} is not valid JSON: {e.msg} at line {e.lineno}. "
            f"A trailing comma after the last item in a list is the usual cause."
        ) from e

    region = _require(data, "region", str, path).strip().lower()
    if region not in NZ_REGIONS:
        raise ReaderConfigError(
            f"{path.name}: \"{region}\" is not a New Zealand region. "
            f"Use one of: {', '.join(sorted(NZ_REGIONS))}."
        )

    floor_name = str(data.get("proximity_floor", "SUBURB")).strip().upper()
    try:
        floor = Proximity[floor_name]
    except KeyError:
        raise ReaderConfigError(
            f"{path.name}: \"proximity_floor\" should be one of "
            f"{', '.join(p.name for p in Proximity)}, got \"{floor_name}\"."
        ) from None

    suburbs = [s.strip() for s in _require(data, "suburbs", list, path) if s.strip()]
    streets = [s.strip() for s in data.get("streets", []) if str(s).strip()]
    attributes = [a.strip() for a in data.get("attributes", []) if str(a).strip()]

    unknown = sorted(set(attributes) - KNOWN_ATTRIBUTES)
    if unknown:
        raise ReaderConfigError(
            f"{path.name}: unknown attribute(s) {', '.join(unknown)}. "
            f"An attribute that is not recognised silently hides notices "
            f"forever, so this is an error rather than a warning. Known: "
            f"{', '.join(sorted(KNOWN_ATTRIBUTES))}."
        )

    if floor >= Proximity.SUBURB and not suburbs:
        raise ReaderConfigError(
            f"{path.name}: \"proximity_floor\" is {floor.name} but no suburbs "
            f"are listed, so no place-specific notice can ever reach you. "
            f"Add suburbs, or set the floor to REGION."
        )
    if floor is Proximity.STREET and not streets:
        raise ReaderConfigError(
            f"{path.name}: \"proximity_floor\" is STREET but no streets are "
            f"listed. Add streets, or set the floor to SUBURB."
        )

    base = default_profile()
    profile = Profile(
        region_terms=list(NZ_REGIONS[region]),
        attributes=attributes,
        rules=base.rules,
        streets=streets,
        suburbs=suburbs,
        proximity_floor=floor,
    )

    return Reader(
        name=str(data.get("name", "Morning Board")),
        place=str(data.get("place", region.title())),
        lat=float(_require(data, "lat", (int, float), path)),
        lon=float(_require(data, "lon", (int, float), path)),
        profile=profile,
    )
