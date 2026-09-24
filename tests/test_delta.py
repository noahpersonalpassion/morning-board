"""Tests for the Delta Rule.

These lock in the judgements that are easy to get wrong, especially the two
that bit during the first run: a closing consultation IS settled, and a
notice that names no region is national, not irrelevant.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from notice.delta import (  # noqa: E402
    check_consequential, check_settled, check_unobvious, default_profile,
    regions_named,
)
from notice.models import Candidate  # noqa: E402
from notice.templates import (  # noqa: E402
    match_template, notice_type, split_title,
)
from notice.novelty import HeadlineCorpus, significant_terms  # noqa: E402
from notice.places import streets_named, suburbs_named  # noqa: E402

NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)


def make(title: str, body: str = "") -> Candidate:
    return Candidate(
        source_id="t", source_name="Test", external_id=title,
        title=title, body=body, url="https://example.invalid/x",
        published=NOW, retrieved=NOW,
    )


class TestSettled(unittest.TestCase):
    def test_commencement_is_settled(self):
        c = make("Order 2026 commences 1 November 2026",
                 "It comes into force on 1 November 2026.")
        self.assertTrue(check_settled(c).passed)

    def test_bare_proposal_is_not_settled(self):
        c = make("Proposed amendment to the Notice 2019",
                 "The Ministry proposes amending it. No decision has been made.")
        self.assertFalse(check_settled(c).passed)

    def test_closing_consultation_is_settled(self):
        """The thing consulted on is not settled. The DEADLINE is, and the
        deadline is the part the reader cannot undo."""
        c = make("Consultation closes 12 October 2026",
                 "Submissions close at 5pm on 12 October 2026. "
                 "Late submissions cannot be considered.")
        r = check_settled(c)
        self.assertTrue(r.passed, r.reason)
        self.assertIn("deadline", r.reason)

    def test_no_date_is_not_settled(self):
        self.assertFalse(check_settled(make("Something happened")).passed)


class TestConsequential(unittest.TestCase):
    """Against real Gazette titles captured 15-23 Sep 2026."""

    def setUp(self):
        self.profile = default_profile()

    def gz(self, number: str, title: str, tags=None) -> Candidate:
        c = make(title)
        c.notice_number = number
        c.tags = tags or []
        c.settled_on_publication = True
        return c

    def test_own_street_ships_at_street_proximity(self):
        c = self.gz("2026-ln4598",
                    "Road Stopped\u2014Gerrard Besson Place, Onehunga , Auckland")
        r = check_consequential(c, self.profile)
        self.assertTrue(r.passed, r.reason)
        self.assertEqual(r.detail["proximity"], "STREET")
        self.assertIn("where you live", r.reason)

    def test_own_suburb_ships(self):
        c = self.gz("2026-ln5279",
                    "Land Acquired for Education Purposes\u2014Freeland Avenue, "
                    "Mount Roskill, Auckland")
        r = check_consequential(c, self.profile)
        self.assertTrue(r.passed, r.reason)
        self.assertEqual(r.detail["proximity"], "SUBURB")

    def test_same_city_other_suburb_is_too_far(self):
        """The central tension. This IS in the reader's region, and it is
        still noise: a land taking under Auckland Central is nothing to an
        Onehunga household. Region-level matching sent it to 1.7m people."""
        c = self.gz(
            "2026-ln5366",
            "Land (Subsurface) and a Restrictive Covenant Acquired for Railway "
            "Purposes\u2014City Rail Link Project, 42 Upper Queen Street, Auckland Central",
            ["Public Works Act", "Other Councils", "Auckland"],
        )
        r = check_consequential(c, self.profile)
        self.assertFalse(r.passed)
        self.assertTrue(r.detail["too_far"])

    def test_national_change_ignores_the_proximity_floor(self):
        """A criminal law change is not less relevant for being nationwide."""
        c = self.gz("2026-sl5429",
                    "Renewal of Temporary Class Drug Order for Etomidate")
        r = check_consequential(c, self.profile)
        self.assertTrue(r.passed, r.reason)
        self.assertEqual(r.detail["proximity"], "NATIONAL")

    def test_other_region_drops(self):
        c = self.gz(
            "2026-ln5367",
            "Road to be Stopped\u2014215 Taylors Mistake Road, Taylors Mistake, "
            "Christchurch City",
        )
        r = check_consequential(c, self.profile)
        self.assertFalse(r.passed)
        self.assertIn("canterbury", r.reason)

    def test_curly_apostrophe_region(self):
        """Regression: U+2019 in "Central Hawke's Bay District" missed the
        region list and shipped a Hawke's Bay notice to an Auckland reader."""
        c = self.gz(
            "2026-ln5349",
            "Easement Acquired for Roading Recovery Purposes\u2014Wimbledon Road, "
            "P\u014drangahau,  Central Hawke\u2019s Bay District",
        )
        r = check_consequential(c, self.profile)
        self.assertFalse(r.passed)
        self.assertIn("hawke", r.reason)

    def test_unlocatable_place_drops_for_fetch(self):
        """Regression: a notice about a specific place that does not say which
        place shipped to everyone. For a street-level product a guess is worse
        than silence."""
        c = self.gz("2026-ln5365", "Revocation of the Reservation Over a Reserve")
        r = check_consequential(c, self.profile)
        self.assertFalse(r.passed)
        self.assertTrue(r.detail["needs_fetch"])

    def test_national_notice_reaches_everyone(self):
        c = self.gz("2026-sl5374",
                    "Notification of Entry into Force of Emergency Management Rules")
        r = check_consequential(c, self.profile)
        self.assertTrue(r.passed, r.reason)
        self.assertEqual(r.detail["proximity"], "NATIONAL")

    def test_vague_title_drops(self):
        """A title naming only its Act says nothing. Shipping it told a
        beneficiary 'a rule under the Social Security Act is changing'."""
        c = self.gz("2026-sl5421", "Notice Under the Social Security Act 2018")
        r = check_consequential(c, self.profile)
        self.assertFalse(r.passed)
        self.assertTrue(r.detail["vague_title"])

    def test_revocation_is_not_read_as_appointment(self):
        """Regression: the revocation title contains the appointment title,
        so parents were told the board had been taken over when in fact the
        statutory manager was being removed."""
        appointed = match_template(
            "Notice of Direction to Appoint a Limited Statutory Manager for "
            "the Mahana School (3201) Board", "go")
        removed = match_template(
            "Revocation of the Notice of Direction to Appoint a Limited "
            "Statutory Manager for the Mahana School (3201) Board", "go")
        self.assertEqual(appointed.template_id, "school_manager_appointed")
        self.assertEqual(removed.template_id, "school_manager_removed")

    def test_land_actions_are_distinct(self):
        """Regression: land taken, a tunnel underneath, and an easement all
        read as the same sentence."""
        ids = {
            match_template(t, "ln").template_id for t in (
                "Land Acquired for a Road\u2014Frankley Road, New Plymouth",
                "Land (Subsurface) Acquired for Railway Purposes\u2014Auckland",
                "Easement Acquired for Roading Recovery Purposes\u2014Wimbledon Road",
                "Land Set Apart for Water Services Purposes\u2014South Waikato",
            )
        }
        self.assertEqual(len(ids), 4)

    def test_untemplated_notice_drops_and_names_the_gap(self):
        c = self.gz("2026-au5395",
                    "Notice of Instrument Made Under the Financial Market "
                    "Infrastructures Act 2021")
        r = check_consequential(c, self.profile)
        self.assertFalse(r.passed)
        self.assertTrue(r.detail["needs_template"])

    def test_excluded_notice_says_it_was_a_decision(self):
        """An annual report or an appointment is not a backlog item. It was
        ruled out, and the log has to say so or the reasoning disappears."""
        c = self.gz("2026-go5447",
                    "Funding Policy Statement in Relation to the Funding of "
                    "ACC\u2019s Levied Accounts")
        r = check_consequential(c, self.profile)
        self.assertFalse(r.passed)
        self.assertTrue(r.detail["by_decision"])
        self.assertEqual(r.detail["excluded"], "acc_funding_policy")

    def test_occupational_notice_needs_the_attribute(self):
        """Regression: an Auckland household was told about pig levies."""
        c = self.gz("2026-sl4782",
                    "Levy on Pigs Slaughtered on Licensed Premises 2026/27")
        self.assertFalse(check_consequential(c, self.profile).passed)
        self.profile.attributes = self.profile.attributes + ["pig_farmer"]
        self.assertTrue(check_consequential(c, self.profile).passed)


class TestGazetteSettled(unittest.TestCase):
    def gz(self, title: str, body: str = "") -> Candidate:
        c = make(title, body)
        c.settled_on_publication = True
        return c

    def test_gazette_notice_is_settled_on_publication(self):
        """Regression: demanding commencement language plus a date dropped
        every real Gazette notice. The notice IS the legal act."""
        r = check_settled(self.gz("Road to be Stopped\u2014215 Taylors Mistake Road"))
        self.assertTrue(r.passed, r.reason)
        self.assertTrue(r.detail["presumed"])

    def test_consultative_gazette_notice_is_not_settled(self):
        r = check_settled(self.gz(
            "Proposed amendment to a Fisheries Notice",
            "Submissions are invited. No decision has been made."))
        self.assertFalse(r.passed)


class TestTemplates(unittest.TestCase):
    def test_type_code_from_notice_number(self):
        self.assertEqual(notice_type("2026-ln5366"), "ln")
        self.assertEqual(notice_type("2026-go5447"), "go")
        self.assertIsNone(notice_type("nonsense"))

    def test_title_splits_on_em_dash(self):
        action, where = split_title(
            "Road to be Stopped\u2014215 Taylors Mistake Road, Christchurch City")
        self.assertEqual(action, "Road to be Stopped")
        self.assertIn("Taylors Mistake Road", where)

    def test_title_without_location(self):
        action, where = split_title("Notice Under the Social Security Act 2018")
        self.assertEqual(where, "")

    def test_template_gives_plain_words(self):
        t = match_template(
            "Road to be Stopped\u2014215 Taylors Mistake Road", "ln")
        self.assertIsNotNone(t)
        self.assertIn("permanently closed", t.effect)

    def test_unknown_notice_has_no_template(self):
        self.assertIsNone(match_template(
            "Annual Report of Industry Body\u2014Gas Industry Company Limited", "gs"))


class TestUnobvious(unittest.TestCase):
    def _corpus(self, titles: list[str]) -> HeadlineCorpus:
        corpus = HeadlineCorpus()
        from notice.novelty import Headline
        corpus.headlines = [
            Headline(title=t, outlet="Test", published=NOW) for t in titles
        ]
        corpus.outlets_ok = ["Test"]
        return corpus

    def test_covered_item_drops(self):
        corpus = self._corpus(
            ["Road user charges to rise for diesel drivers from October"]
        )
        c = make("Road user charges rates increase confirmed for 1 October 2026")
        r = check_unobvious(c, corpus)
        self.assertFalse(r.passed)
        self.assertIn("already reported", r.reason)

    def test_uncovered_item_ships(self):
        corpus = self._corpus(["Council signals rates rise in annual plan"])
        c = make("Water Services Charges Amendment Order 2026 commences")
        self.assertTrue(check_unobvious(c, corpus).passed)

    def test_one_shared_word_is_not_coverage(self):
        corpus = self._corpus(["Charges laid after Auckland incident"])
        c = make("Water Services Charges Amendment Order 2026")
        self.assertTrue(check_unobvious(c, corpus).passed)

    def test_missing_corpus_refuses_by_default(self):
        """Unverified novelty is not novelty."""
        empty = HeadlineCorpus()
        r = check_unobvious(make("Anything at all"), empty)
        self.assertFalse(r.passed)
        self.assertIn("cannot verify", r.reason)

    def test_missing_corpus_override_is_marked(self):
        empty = HeadlineCorpus()
        r = check_unobvious(make("Anything"), empty, allow_unverified=True)
        self.assertTrue(r.passed)
        self.assertIn("UNVERIFIED", r.reason)
        self.assertTrue(r.detail["override"])


class TestPlaces(unittest.TestCase):
    def test_suburb_needs_a_word_boundary(self):
        """"Newton" must not fire on "Newtown"."""
        self.assertEqual(suburbs_named("a notice about Newtown"), set())
        self.assertIn("newton", suburbs_named("a notice about Newton"))

    def test_street_extracted_from_title(self):
        found = streets_named(
            "Road Stopped\u2014Gerrard Besson Place, Onehunga , Auckland")
        self.assertIn("Gerrard Besson Place", found)

    def test_suburb_implies_its_region(self):
        """"St Joseph\u2019s School, Orakei" never says Auckland."""
        self.assertIn("orakei", suburbs_named("St Joseph\u2019s School, Orakei"))


class TestTokenising(unittest.TestCase):
    def test_numbers_are_kept(self):
        self.assertIn("2026", significant_terms("Order 2026"))

    def test_stopwords_dropped(self):
        self.assertNotIn("the", significant_terms("the order"))

    def test_regions(self):
        self.assertEqual(regions_named("in Christchurch today"), {"canterbury"})
        self.assertEqual(regions_named("a national change"), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestNoticePage(unittest.TestCase):
    """The page parser, against the structure of a real notice page."""

    REAL = """
    <div>Notice Type</div><div>Land Notices</div>
    <div>Notice Title</div>
    <h1>Land (Subsurface) and a Restrictive Covenant Acquired for Railway
    Purposes&#8212;City Rail Link Project, 42 Upper Queen Street, Auckland Central</h1>
    <div>Publication Date</div><div>18 SEP 2026</div>
    <div>Tags</div>
    <a>Public Works Act</a>
    <a>Other Councils</a>
    <a>Auckland</a>
    <div>Notice Number</div><div>2026-ln5366</div>
    """

    def test_reads_the_region_tag(self):
        from notice.sources.notice_page import parse
        page = parse(self.REAL)
        self.assertIsNotNone(page)
        self.assertIn("Auckland", page.tags)
        self.assertIn("Public Works Act", page.tags)
        self.assertEqual(page.number, "2026-ln5366")

    def test_bot_shell_returns_none_not_empty_tags(self):
        """A protection shell has no Tags block. Treating that as 'no tags'
        would silently mark every notice unlocatable instead of failing."""
        from notice.sources.notice_page import parse
        self.assertIsNone(parse("<html><body>Please enable JavaScript</body></html>"))

    def test_resolved_tag_lands_a_notice_in_the_right_region(self):
        """End to end: the tag the page gives is what region matching reads."""
        c = Candidate(
            source_id="gazette", source_name="NZ Gazette",
            external_id="2026-ln5365",
            title="Revocation of the Reservation Over a Reserve",
            body="", url="https://example.invalid/x",
            published=NOW, retrieved=NOW,
            notice_number="2026-ln5365", settled_on_publication=True,
        )
        profile = default_profile()
        self.assertFalse(check_consequential(c, profile).passed)  # unresolvable
        c.tags = ["Reserves Act", "Auckland"]
        r = check_consequential(c, profile)
        # Now locatable: region known, so it is judged on proximity, not
        # dropped as unknown.
        self.assertNotIn("needs_fetch", r.detail)
