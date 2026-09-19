from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from git_command_center import models
from git_command_center.commit_service import CommitService


class CommitHistoryContractTests(unittest.TestCase):
    def test_exposes_structured_commit_model(self) -> None:
        self.assertTrue(hasattr(models, "CommitRecord"))

    def test_parses_decorations_and_assigns_merge_lanes(self) -> None:
        records = tuple(CommitService._parse("a1\x1fb1 c1\x1fAda\x1fa@example.com\x1f2026-01-01T00:00:00Z\x1fMerge work\x1fHEAD -> main\x1e"))
        graphed = CommitService._with_lanes(records)

        self.assertEqual(graphed[0].decorations, ("HEAD -> main",))
        self.assertEqual(graphed[0].parents, ("b1", "c1"))
        self.assertIn("*", graphed[0].graph)


if __name__ == "__main__":
    unittest.main()
