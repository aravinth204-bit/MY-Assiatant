import os
import tempfile
import threading
import unittest

from src.file_finder import search_files


class FileFinderTests(unittest.TestCase):
    def test_search_matches_file_names_case_insensitively_and_returns_paths(self):
        with tempfile.TemporaryDirectory() as root:
            nested = os.path.join(root, "Documents")
            os.makedirs(nested)
            expected_path = os.path.join(nested, "My-Resume.PDF")
            with open(expected_path, "w", encoding="utf-8") as file:
                file.write("file contents are not searched")

            result = search_files("resume", roots=[root])

        self.assertEqual(result["query"], "resume")
        self.assertEqual(result["matches"], [{
            "name": "My-Resume.PDF",
            "path": expected_path,
        }])
        self.assertEqual(result["scanned_directories"], 2)
        self.assertFalse(result["truncated"])

    def test_search_stops_at_the_result_limit(self):
        with tempfile.TemporaryDirectory() as root:
            for filename in ("report-a.txt", "report-b.txt", "report-c.txt"):
                with open(os.path.join(root, filename), "w", encoding="utf-8") as file:
                    file.write("")

            result = search_files("report", roots=[root], max_results=2)

        self.assertEqual(len(result["matches"]), 2)
        self.assertTrue(result["truncated"])

    def test_rejects_empty_or_overlong_queries(self):
        with self.assertRaises(ValueError):
            search_files("  ", roots=["unused"])
        with self.assertRaises(ValueError):
            search_files("x" * 129, roots=["unused"])

    def test_cancelled_search_reports_progress_and_cancelled_state(self):
        with tempfile.TemporaryDirectory() as root:
            cancel_event = threading.Event()
            cancel_event.set()
            progress_updates = []

            result = search_files(
                "resume",
                roots=[root],
                progress_callback=progress_updates.append,
                cancel_event=cancel_event,
            )

        self.assertTrue(result["cancelled"])
        self.assertEqual(result["scanned_directories"], 0)
        self.assertTrue(progress_updates)


if __name__ == "__main__":
    unittest.main()
