from __future__ import annotations
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from git_command_center import models
from git_command_center.operation_service import parse_conflicts

class OperationContractTests(unittest.TestCase):
    def test_exposes_conflict_block_model(self) -> None:
        self.assertTrue(hasattr(models, "ConflictBlock"))

    def test_parses_ours_base_and_theirs(self) -> None:
        block = tuple(parse_conflicts(["before", "<<<<<<< ours", "left", "||||||| base", "middle", "=======", "right", ">>>>>>> theirs"]))[0]
        self.assertEqual(block.ours, ("left",)); self.assertEqual(block.base, ("middle",)); self.assertEqual(block.theirs, ("right",))
