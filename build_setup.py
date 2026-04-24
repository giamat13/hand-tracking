import shutil
import subprocess
import sys
from datetime import datetime

from build_config import (
    APP_NAME,
    APP_PUBLISHER,
    APP_VERSION,
    ICON_ICO_PATH,
    INSTALLER_EXE,
    INSTALL_APP_DIR,
    INSTALLER_STAGING_DIR,
    INSTALLER_SCRIPT,
    ISCC_CANDIDATES,
    RELEASE_DIR,
)
from build_assets import ensure_windows_icon
from build_exe import build_installer_app


def find_iscc():
    path = shutil.which("iscc")
    if path:
        return path

    for candidate in ISCC_CANDIDATES:
        if candidate.exists():
            return str(candidate)

    raise SystemExit(
        "Inno Setup 6 לא מותקן. התקן אותו ואז הרץ שוב את build_setup.py.\n"
        "אפשר בדרך כלל להתקין עם: winget install JRSoftware.InnoSetup"
    )


def build_setup(rebuild_app=False):
    ensure_windows_icon()
    if rebuild_app or not INSTALL_APP_DIR.exists():
        build_installer_app()
    else:
        print(f"[SETUP] Using existing installer app folder: {INSTALL_APP_DIR}")
    RELEASE_DIR.mkdir(exist_ok=True)
    INSTALLER_STAGING_DIR.mkdir(parents=True, exist_ok=True)

    output_base_filename = f"{APP_NAME}-Setup-build"
    staged_installer = INSTALLER_STAGING_DIR / f"{output_base_filename}.exe"
    if staged_installer.exists():
        staged_installer.unlink()

    iscc = find_iscc()
    cmd = [
        iscc,
        f"/DMyAppName={APP_NAME}",
        f"/DMyAppVersion={APP_VERSION}",
        f"/DMyAppPublisher={APP_PUBLISHER}",
        f"/DMyAppExeName={APP_NAME}.exe",
        f"/DMyReleaseDir={RELEASE_DIR}",
        f"/DMyOutputDir={INSTALLER_STAGING_DIR}",
        f"/DMyOutputBaseFilename={output_base_filename}",
        f"/DMySetupIconFile={ICON_ICO_PATH}",
        str(INSTALLER_SCRIPT),
    ]
    print("[SETUP] Running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=INSTALLER_SCRIPT.parent)

    if not staged_installer.exists():
        raise SystemExit(f"[SETUP] Expected staged setup EXE not found: {staged_installer}")

    final_installer = INSTALLER_EXE
    try:
        shutil.copy2(staged_installer, final_installer)
    except PermissionError:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        final_installer = RELEASE_DIR / f"{APP_NAME}-Setup-{timestamp}.exe"
        shutil.copy2(staged_installer, final_installer)
        print(f"[SETUP] Default installer name was locked, wrote fallback file: {final_installer}")

    print(f"[SETUP] Installer ready: {final_installer}")
    return final_installer


if __name__ == "__main__":
    build_setup(rebuild_app="--rebuild-app" in sys.argv)
