"""Persist user settings to JSON between sessions.

Portable EXE  → settings.json next to the EXE
Installed EXE → %APPDATA%\\Handy\\settings.json
Dev (script)  → settings.json next to main.py
"""

import json
import os
import sys
from pathlib import Path

import handy.state as state

_KEYS = [
    "SMOOTH", "SPEED", "DYNAMIC_SPEED", "SPEED_CURVE", "CAM_MARGIN",
    "DEADZONE", "MOUSE_ENABLED", "CONTROL_HAND", "CLICK_COOLDOWN",
    "SHOW_TRAIL", "SHOW_COORDS", "SHOW_LANDMARKS",
]


def _settings_path() -> Path:
    if state.IS_INSTALLED:
        base = Path(os.environ.get("APPDATA", Path.home())) / "Handy"
    elif getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parents[1]
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


def load() -> None:
    path = _settings_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in _KEYS:
            if key in data:
                setattr(state, key, data[key])
        print(f"[SETTINGS] loaded from {path}")
    except Exception as exc:
        print(f"[SETTINGS] load failed: {exc}")


def save() -> None:
    path = _settings_path()
    try:
        data = {key: getattr(state, key) for key in _KEYS}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[SETTINGS] saved to {path}")
    except Exception as exc:
        print(f"[SETTINGS] save failed: {exc}")
