from __future__ import annotations
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from git_command_center import models
class AnalyticsContractTests(unittest.TestCase):
    def test_exposes_analytics_snapshot(self): self.assertTrue(hasattr(models, "AnalyticsSnapshot"))
