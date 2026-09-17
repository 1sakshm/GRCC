from pathlib import Path
import unittest


class StageOneContractTests(unittest.TestCase):
    def test_stage_one_package_has_a_cli_and_git_layer(self) -> None:
        root = Path(__file__).parents[1]
        for relative_path in (
            "pyproject.toml",
            "src/git_command_center/__main__.py",
            "src/git_command_center/git_runner.py",
            "src/git_command_center/repository_service.py",
        ):
            self.assertTrue((root / relative_path).is_file(), relative_path)


if __name__ == "__main__":
    unittest.main()
