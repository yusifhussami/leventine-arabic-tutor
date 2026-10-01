import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from lexicon.calendar_feed import next_lesson, save_calendar_url
from lexicon.load import connect

FEED = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260901T150000Z
SUMMARY:Arabic practice
END:VEVENT
BEGIN:VEVENT
DTSTART:20261006T150000Z
SUMMARY:Arabic with the tutor
END:VEVENT
BEGIN:VEVENT
DTSTART:20261008T090000Z
SUMMARY:Dentist
END:VEVENT
BEGIN:VEVENT
DTSTART:20261101T150000Z
SUMMARY:Arabic review
END:VEVENT
END:VCALENDAR
"""


class CalendarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "lexicon.db")

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_next_arabic_event_skips_the_past_and_other_titles(self) -> None:
        save_calendar_url(self.conn, "https://calendar.google.com/calendar/ical/example/basic.ics")
        found = next_lesson(
            self.conn,
            now=datetime(2026, 10, 1, tzinfo=timezone.utc),
            fetch=lambda _url: FEED,
        )
        self.assertEqual(found["summary"], "Arabic with the tutor")
        self.assertTrue(found["start"].startswith("2026-10-06T15:00:00"))

    def test_other_hosts_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            save_calendar_url(self.conn, "https://example.com/secret.ics")
        self.assertIsNone(next_lesson(self.conn))


if __name__ == "__main__":
    unittest.main()
