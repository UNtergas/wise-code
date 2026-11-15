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
