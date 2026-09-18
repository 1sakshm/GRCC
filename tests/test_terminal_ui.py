from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from git_command_center.ui import TerminalUI
from git_command_center.state import ApplicationState
from git_command_center.models import RepositoryState


class TerminalUITests(unittest.TestCase):
    def test_application_state_tracks_a_working_tree_filter(self) -> None:
        self.assertEqual(ApplicationState().filter_mode, "all")

    def test_uses_ascii_when_output_is_not_an_interactive_terminal(self) -> None:
        ui = TerminalUI()

        self.assertTrue(ui.ascii_only)
        self.assertTrue(ui._border(50, "top", "TITLE").startswith("+"))

    def test_ascii_dashboard_has_no_unicode_characters(self) -> None:
        rows = TerminalUI(ascii_only=True)._dashboard(
            ApplicationState(repository=RepositoryState(Path("repo"), root=Path("repo")), dashboard=True), 70
        )

        self.assertTrue(all(ord(character) < 128 for row in rows for character in row))


if __name__ == "__main__":
    unittest.main()
