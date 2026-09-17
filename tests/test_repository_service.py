from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from git_command_center.models import GitCommandResult
from git_command_center.repository_service import RepositoryService


class RepositoryServiceTests(unittest.TestCase):
    def test_parses_head_hash_and_subject(self) -> None:
        self.assertEqual(
            RepositoryService._parse_head("a1b2c3\x1fUseful commit\n"),
            ("a1b2c3", "Useful commit"),
        )

    def test_reports_non_repository_for_a_missing_directory(self) -> None:
        state = RepositoryService().inspect(Path(__file__).parent / "does-not-exist")

        self.assertFalse(state.is_repository)
        self.assertIsNotNone(state.error)


if __name__ == "__main__":
    unittest.main()
