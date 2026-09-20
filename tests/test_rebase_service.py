from __future__ import annotations
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from git_command_center import models
class RebaseContractTests(unittest.TestCase):
    def test_exposes_rebase_todo_model(self): self.assertTrue(hasattr(models, "RebaseTodo"))
