"""Settings and save-file locations.

The DeepSeek API key is read from the DEEPSEEK_API_KEY environment variable
first, then from settings.json in the app's data folder. It is never written
anywhere else.
"""
import json
import os
import sys
from pathlib import Path

APP_NAME = "CozyRoads"


def data_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


SETTINGS_PATH = data_dir() / "settings.json"
SAVE_PATH = data_dir() / "save.json"

DEFAULTS = {
    "deepseek_api_key": "",
    "deepseek_model": "deepseek-chat",
    "deepseek_base_url": "https://api.deepseek.com",
    "ambient_ai_greetings": True,
    "player_name": "Traveler",
}


def load_settings() -> dict:
    settings = dict(DEFAULTS)
    try:
        settings.update(json.loads(SETTINGS_PATH.read_text()))
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
    try:
        os.chmod(SETTINGS_PATH, 0o600)  # the file holds an API key
    except OSError:
        pass


def api_key(settings: dict) -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "").strip() or settings.get("deepseek_api_key", "").strip()


def load_save():
    try:
        return json.loads(SAVE_PATH.read_text())
    except (OSError, ValueError):
        return None


def write_save(data: dict) -> None:
    tmp = SAVE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(SAVE_PATH)
