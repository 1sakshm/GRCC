from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from git_command_center.git_runner import GitCommandRunner


class GitCommandRunnerTests(unittest.TestCase):
    def test_runs_git_without_a_shell_and_records_result(self) -> None:
        runner = GitCommandRunner()

        result = runner.run(["--version"])

        self.assertTrue(result.succeeded)
        self.assertIn("git version", result.stdout)
        self.assertEqual(runner.history, (result,))

    def test_rejects_nul_in_arguments_before_execution(self) -> None:
        with self.assertRaises(ValueError):
            GitCommandRunner().run(["status\x00unsafe"])


if __name__ == "__main__":
    unittest.main()
