from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from desktop_agent.journal import OperationJournal, operation_key


class OperationJournalTests(unittest.TestCase):
    def test_operation_key_is_stable_across_dictionary_order(self) -> None:
        left = operation_key("grade", {"student": "7", "work": "C3"}, {"grade": 18, "level": "A"})
        right = operation_key("grade", {"work": "C3", "student": "7"}, {"level": "A", "grade": 18})
        self.assertEqual(left, right)

    def test_completed_operation_cannot_be_reserved_as_new(self) -> None:
        with TemporaryDirectory() as directory:
            journal = OperationJournal(Path(directory) / "journal.sqlite3")
            first, inserted = journal.reserve("comment", {"submission": "abc"}, {"text": "Bien"})
            self.assertTrue(inserted)
            journal.transition(first.key, "executing")
            journal.transition(first.key, "verifying")
            journal.transition(first.key, "completed", {"verified": True})

            repeated, inserted = journal.reserve("comment", {"submission": "abc"}, {"text": "Bien"})
            self.assertFalse(inserted)
            self.assertEqual(repeated.status, "completed")

    def test_final_operation_cannot_return_to_executing(self) -> None:
        with TemporaryDirectory() as directory:
            journal = OperationJournal(Path(directory) / "journal.sqlite3")
            operation, _ = journal.reserve("return", {"submission": "abc"}, {})
            journal.transition(operation.key, "cancelled")
            with self.assertRaises(RuntimeError):
                journal.transition(operation.key, "executing")


if __name__ == "__main__":
    unittest.main()
