from __future__ import annotations

import sys
import subprocess
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from git_command_center import models
from git_command_center.diff_service import DiffService
from git_command_center.git_runner import GitCommandRunner


class DiffEngineContractTests(unittest.TestCase):
    def test_exposes_a_structured_diff_line_model(self) -> None:
        self.assertTrue(hasattr(models, "DiffLine"))

    def test_parses_hunk_line_numbers_and_change_counts(self) -> None:
        diff = DiffService.parse("""diff --git a/app.py b/app.py
index 123..456 100644
--- a/app.py
+++ b/app.py
@@ -4,2 +4,3 @@ example
 old = 1
-removed = True
+added = True
+more = True
 tail = 2
""")[0]

        hunk = diff.hunks[0]
        self.assertEqual((hunk.old_start, hunk.new_start), (4, 4))
        self.assertEqual((hunk.additions, hunk.deletions), (2, 1))
        self.assertEqual([(line.old_line, line.new_line) for line in hunk.lines[:3]], [(4, 4), (5, None), (None, 5)])

    def test_stages_one_selected_hunk_without_staging_the_other(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for command in (["git", "init", "-q"], ["git", "config", "user.email", "test@example.com"], ["git", "config", "user.name", "Test"]):
                subprocess.run(command, cwd=root, check=True)
            path = root / "notes.txt"
            path.write_text("one\ntwo\nthree\nfour\nfive\nsix\nseven\neight\nnine\nten\n", encoding="utf-8")
            subprocess.run(["git", "add", "notes.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
            path.write_text("ONE\ntwo\nthree\nfour\nfive\nsix\nseven\neight\nnine\nTEN\n", encoding="utf-8")

            service = DiffService(GitCommandRunner())
            diff = service.working_tree(root, "notes.txt")[0]
            result = service.stage_hunk(root, diff, diff.hunks[0])
            staged = subprocess.run(["git", "diff", "--cached"], cwd=root, check=True, capture_output=True, text=True).stdout
            unstaged = subprocess.run(["git", "diff"], cwd=root, check=True, capture_output=True, text=True).stdout

            self.assertTrue(result.succeeded, result.stderr)
            self.assertIn("+ONE", staged)
            self.assertNotIn("+TEN", staged)
            self.assertIn("+TEN", unstaged)

            staged_file = service.staged(root, "notes.txt")[0]
            undo = service.unstage_hunk(root, staged_file, staged_file.hunks[0])
            after_undo = subprocess.run(["git", "diff", "--cached"], cwd=root, check=True, capture_output=True, text=True).stdout

            self.assertTrue(undo.succeeded, undo.stderr)
            self.assertEqual(after_undo, "")


if __name__ == "__main__":
    unittest.main()
