import unittest

from lexicon.db import PgConnection


class FakePostgresConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class PgConnectionTests(unittest.TestCase):
    def test_context_commits_without_closing_connection(self):
        raw = FakePostgresConnection()
        conn = PgConnection(raw)

        with conn:
            pass

        self.assertEqual(raw.commits, 1)
        self.assertEqual(raw.rollbacks, 0)
        self.assertFalse(raw.closed)

    def test_context_rolls_back_without_closing_connection(self):
        raw = FakePostgresConnection()
        conn = PgConnection(raw)

        with self.assertRaisesRegex(ValueError, "bad review"):
            with conn:
                raise ValueError("bad review")

        self.assertEqual(raw.commits, 0)
        self.assertEqual(raw.rollbacks, 1)
        self.assertFalse(raw.closed)


if __name__ == "__main__":
    unittest.main()
