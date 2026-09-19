from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from git_command_center import models


class ManagementContractTests(unittest.TestCase):
    def test_exposes_branch_model(self) -> None:
        self.assertTrue(hasattr(models, "BranchRecord"))


if __name__ == "__main__":
    unittest.main()
