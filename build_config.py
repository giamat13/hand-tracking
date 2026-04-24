from pathlib import Path

APP_NAME = "Handy"
APP_VERSION = "1.0.0"
APP_PUBLISHER = "Handy"

MODEL_FILENAME = "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
ICON_PNG_FILENAME = "icon.png"

PROJECT_ROOT = Path(__file__).resolve().parent
SPEC_FILE = PROJECT_ROOT / "Handy.spec"
MODEL_PATH = PROJECT_ROOT / MODEL_FILENAME
ICON_PNG_PATH = PROJECT_ROOT / ICON_PNG_FILENAME

BUILD_ROOT = PROJECT_ROOT / "build"
PYINSTALLER_DIST_DIR = BUILD_ROOT / "dist"
PYINSTALLER_WORK_DIR = BUILD_ROOT / "work"
PYINSTALLER_CACHE_DIR = BUILD_ROOT / "pyinstaller-cache"
ICON_ICO_PATH = BUILD_ROOT / "icon.ico"

RELEASE_DIR = PROJECT_ROOT / "release"
PORTABLE_EXE = RELEASE_DIR / f"{APP_NAME}.exe"
INSTALL_APP_DIR = RELEASE_DIR / APP_NAME
INSTALLER_STAGING_DIR = BUILD_ROOT / "installer-output"

INSTALLER_DIR = PROJECT_ROOT / "installer"
INSTALLER_SCRIPT = INSTALLER_DIR / "HandySetup.iss"
INSTALLER_EXE = RELEASE_DIR / f"{APP_NAME}-Setup.exe"

ISCC_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
)
