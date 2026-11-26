"""Read and persist user preferences shared by the application entry points."""
import json
import os
import tempfile
import unicodedata
from pathlib import Path


DEFAULT_AGENT_NAME = "Simple Agent"


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
    data = _read_settings(target)
    data.update(updates)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, target)
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def normalize_agent_name(value: object) -> str | None:
    """Accept a nonempty, single-line name suitable for display in the terminal."""
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or any(unicodedata.category(char) in {"Cc", "Cs", "Zl", "Zp"} for char in name):
        return None
    return name


def apply_agent_settings(agent, path: Path | None = None) -> None:
    """Apply saved overrides to an agent, keeping its defaults for missing entries."""
    data = load_settings(path)
    if name := normalize_agent_name(data.get("agent_name")):
        agent.name = name
    if isinstance(prompt := data.get("system_prompt"), str):
        agent.system_prompt = prompt or None
