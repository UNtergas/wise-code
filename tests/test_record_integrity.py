"""Learning records stay complete and readable: session links, Anki export,
history order, date arguments, and a repeated Markdown import."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_wise import WiseTestCase  # noqa: E402


class SessionLinkTests(WiseTestCase):
    def edges_in(self):
        path = self.project / ".wise-code" / "graph" / "edges.jsonl"
        return path.read_text(encoding="utf-8")

    def test_records_added_after_a_recap_the_same_day_join_the_next_session(self):
        self.run_wise("add", "concept", "name=Strings")
        self.run_wise("add", "session", "goal=morning", day="2026-11-14")
        late = self.out("add", "qa", "source=asked", "q=evening question", "a=gist",
                        "verdict=n/a", "--about", "strings", day="2026-11-14").strip()
        second = self.out("add", "session", "goal=next day", day="2026-11-15").strip()
        self.assertIn(f'{{"from": "{late}", "rel": "in", "to": "{second}"}}',
                      self.edges_in())

    def test_a_record_already_in_a_session_stays_there(self):
        early = self.out("add", "qa", "source=asked", "q=first", "a=gist",
                         "verdict=n/a", day="2026-11-14").strip()
        first = self.out("add", "session", "goal=one", day="2026-11-14").strip()
        second = self.out("add", "session", "goal=two", day="2026-11-15").strip()
        edges = self.edges_in()
        self.assertIn(f'"from": "{early}", "rel": "in", "to": "{first}"', edges)
        self.assertNotIn(f'"from": "{early}", "rel": "in", "to": "{second}"', edges)


class AnkiExportTests(WiseTestCase):
    def card_rows(self):
        self.run_wise("export", "anki")
        text = (self.project / ".wise-code" / "cards.tsv").read_text(encoding="utf-8")
        return text.splitlines()[5:]

    def test_a_front_starting_with_hash_is_not_an_anki_comment(self):
        # Anki ignores every line that starts with "#": the card would vanish.
        self.run_wise("add", "card", "front=#[derive(Debug)] does what?",
                      "back=Generates a Debug impl")
        self.assertEqual(self.card_rows(), [
            '"#[derive(Debug)] does what?"\tGenerates a Debug impl\twise-code'])

    def test_a_field_starting_with_a_quote_is_escaped(self):
        # Anki reads a leading double quote as the start of a quoted field.
        self.run_wise("add", "card", 'front="static" lifetime means?',
                      'back="for the whole program"')
        self.assertEqual(self.card_rows(), [
            '"""static"" lifetime means?"\t"""for the whole program"""\twise-code'])

    def test_plain_fields_stay_unquoted(self):
        self.run_wise("add", "card", 'front=What is a "move"?', "back=Ownership transfer")
        self.assertEqual(self.card_rows(), [
            'What is a "move"?\tOwnership transfer\twise-code'])
