import shutil
import subprocess
import sys
import urllib.request
import os
import tempfile
from pathlib import Path

from build_config import (
    APP_NAME,
    BUILD_ROOT,
    ICON_ICO_PATH,
    INSTALL_APP_DIR,
    MODEL_PATH,
    MODEL_URL,
    PORTABLE_EXE,
    PYINSTALLER_CACHE_DIR,
    RELEASE_DIR,
    SPEC_FILE,
)
from build_assets import ensure_windows_icon


def ensure_model_file():
    if MODEL_PATH.exists():
        return

    print(f"[BUILD] Downloading model file to {MODEL_PATH}...")
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    except Exception as exc:
        raise SystemExit(
            "[BUILD] Failed to download hand_landmarker.task. "
            "Connect to the internet once or place the file next to main.py."
        ) from exc


def clean_previous_build():
    if PORTABLE_EXE.exists():
        PORTABLE_EXE.unlink()


def clean_previous_installer_build():
    if INSTALL_APP_DIR.exists():
        shutil.rmtree(INSTALL_APP_DIR, ignore_errors=True)

def _run_pyinstaller(build_target):
    ensure_model_file()
    ensure_windows_icon()
    RELEASE_DIR.mkdir(exist_ok=True)
    BUILD_ROOT.mkdir(exist_ok=True)
    PYINSTALLER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix="pyinstaller-", dir=BUILD_ROOT))
    dist_dir = run_root / "dist"
    work_dir = run_root / "work"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        str(SPEC_FILE),
    ]
    print("[BUILD] Running:", " ".join(cmd))
    env = os.environ.copy()
    env["PYINSTALLER_CONFIG_DIR"] = str(PYINSTALLER_CACHE_DIR)
    env["HANDY_ICON_ICO"] = str(ICON_ICO_PATH)
    env["HANDY_BUILD_TARGET"] = build_target
    subprocess.run(cmd, check=True, cwd=SPEC_FILE.parent, env=env)
    return dist_dir, run_root


def build_portable_exe():
    clean_previous_build()
    dist_dir, run_root = _run_pyinstaller("portable")

    built_exe = dist_dir / f"{APP_NAME}.exe"
    if not built_exe.exists():
        raise SystemExit(f"[BUILD] Expected EXE not found: {built_exe}")

    shutil.copy2(built_exe, PORTABLE_EXE)
    shutil.rmtree(run_root, ignore_errors=True)
    print(f"[BUILD] Portable EXE ready: {PORTABLE_EXE}")
    return PORTABLE_EXE

def build_installer_app():
    clean_previous_installer_build()
    dist_dir, run_root = _run_pyinstaller("installer")

    built_app_dir = dist_dir / APP_NAME
    built_exe = built_app_dir / f"{APP_NAME}.exe"
    if not built_exe.exists():
        raise SystemExit(f"[BUILD] Expected installer app EXE not found: {built_exe}")

    shutil.copytree(built_app_dir, INSTALL_APP_DIR)
    shutil.rmtree(run_root, ignore_errors=True)
    print(f"[BUILD] Installer app folder ready: {INSTALL_APP_DIR}")
    return INSTALL_APP_DIR


if __name__ == "__main__":
    build_portable_exe()
