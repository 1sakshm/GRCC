from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class UserSettings:
    theme: str = "midnight"
    use_mouse: bool = True
    ascii_only: bool = False
    refresh_seconds: float = 3.0
    external_editor: str | None = None
    last_repository: str | None = None


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        base = Path(os.environ.get("APPDATA", Path.home())) / "GitCommandCenter"
        self.path = path or base / "settings.json"

    def load(self) -> UserSettings:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return UserSettings(**{key: value for key, value in payload.items() if key in UserSettings.__dataclass_fields__})
        except (OSError, json.JSONDecodeError, TypeError):
            return UserSettings()

    def save(self, settings: UserSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
        temporary.replace(self.path)

