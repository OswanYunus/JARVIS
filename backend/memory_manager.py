from pathlib import Path
import json
import re
import time
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
MEMORY_DIR = ROOT / "memory"
PREFERENCES_FILE = MEMORY_DIR / "preferences.json"
ROUTINES_FILE = MEMORY_DIR / "routines.json"
HISTORY_FILE = MEMORY_DIR / "history.json"


class MemoryManager:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root).resolve() if root else ROOT
        self.memory_dir = self.root / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.preferences_file = self.memory_dir / "preferences.json"
        self.routines_file = self.memory_dir / "routines.json"
        self.history_file = self.memory_dir / "history.json"
        self._ensure_files()

    def _ensure_files(self) -> None:
        self._create_if_missing(self.preferences_file, {})
        self._create_if_missing(self.routines_file, {})
        self._create_if_missing(self.history_file, [])

    def _create_if_missing(self, path: Path, default_data: Any) -> None:
        if not path.exists():
            path.write_text(json.dumps(default_data, indent=2), encoding="utf-8")

    def _load_json(self, path: Path, default: Any) -> Any:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return default

    def _save_json(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_preferences(self) -> Dict[str, Any]:
        return self._load_json(self.preferences_file, {})

    def save_preferences(self, preferences: Dict[str, Any]) -> None:
        self._save_json(self.preferences_file, preferences)

    def get_preference(self, key: str, default: Any = None) -> Any:
        preferences = self.load_preferences()
        return preferences.get(key, default)

    def set_preference(self, key: str, value: Any) -> None:
        preferences = self.load_preferences()
        preferences[key] = value
        self.save_preferences(preferences)

    def load_routines(self) -> Dict[str, Any]:
        return self._load_json(self.routines_file, {})

    def save_routines(self, routines: Dict[str, Any]) -> None:
        self._save_json(self.routines_file, routines)

    def load_history(self) -> List[Dict[str, Any]]:
        return self._load_json(self.history_file, [])

    def log_history(self, event: Any) -> None:
        history = self.load_history()
        history.append({"timestamp": int(time.time()), "event": event})
        self._save_json(self.history_file, history)

    def get_memory_context(self) -> Dict[str, Any]:
        return {
            "preferences": self.load_preferences(),
            "routines": self.load_routines(),
        }

    def find_matching_routine(self, message: str) -> Optional[Dict[str, Any]]:
        routines = self.load_routines()
        lowered = message.lower()
        for name, routine in routines.items():
            trigger = str(routine.get("trigger", "")).strip()
            pattern = str(routine.get("pattern", "")).strip()
            tool_call = routine.get("tool_call")
            if not isinstance(tool_call, dict):
                continue
            if trigger and trigger.lower() in lowered:
                return tool_call
            if pattern:
                try:
                    if re.search(pattern, message, re.IGNORECASE):
                        return tool_call
                except re.error:
                    continue
        return None

    def add_routine(self, name: str, trigger: str, tool_call: Dict[str, Any]) -> None:
        routines = self.load_routines()
        routines[name] = {"trigger": trigger, "tool_call": tool_call}
        self.save_routines(routines)
