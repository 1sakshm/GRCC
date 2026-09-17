from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from git_command_center.ui import TerminalUI


class TerminalUITests(unittest.TestCase):
    def test_uses_ascii_when_output_is_not_an_interactive_terminal(self) -> None:
        ui = TerminalUI()

        self.assertTrue(ui.ascii_only)
        self.assertTrue(ui._border(50, "top", "TITLE").startswith("+"))


if __name__ == "__main__":
    unittest.main()
