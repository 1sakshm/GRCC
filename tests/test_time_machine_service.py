from __future__ import annotations
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from git_command_center import models
class TimeMachineContractTests(unittest.TestCase):
    def test_exposes_blame_line_model(self): self.assertTrue(hasattr(models, "BlameLine"))
