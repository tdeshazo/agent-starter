"""Read and persist user preferences shared by the application entry points."""
import fcntl
import json
import os
import tempfile
from functools import partial
from pathlib import Path

from .preferences import DEFAULT_AGENT_NAME as DEFAULT_AGENT_NAME
from .preferences import UserPreferences, apply_preferences
from .preferences import normalize_agent_name as normalize_agent_name


def settings_path() -> Path:
    """Return the user-level settings file path."""
    config_home = os.getenv("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "simple-agent" / "settings.json"


def _read_settings(target: Path) -> dict:
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_settings(path: Path | None = None) -> dict:
    try:
        return _read_settings(path if path is not None else settings_path())
    except OSError:
        return {}


def save_settings(updates: dict, path: Path | None = None) -> None:
    """Merge preferences into the existing file and replace it atomically."""
    target = path if path is not None else settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Lock a stable file because os.replace changes the settings file's inode.
    with target.with_name(target.name + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = _read_settings(target)
        data.update(updates)
        _replace_settings(target, data)


def _replace_settings(target: Path, data: dict) -> None:
    payload = json.dumps(data, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, target)
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def open_preferences(path: Path | None = None) -> UserPreferences:
    target = path if path is not None else settings_path()
    return UserPreferences(partial(load_settings, target), partial(save_settings, path=target))


def apply_agent_settings(agent, path: Path | None = None) -> None:
    """Apply saved overrides to an agent, keeping its defaults for missing entries."""
    apply_preferences(agent, open_preferences(path).agent())


def load_pet(path: Path | None = None) -> str:
    return open_preferences(path).pet()


def save_pet(pet: str, path: Path | None = None) -> str:
    return open_preferences(path).select_pet(pet)
