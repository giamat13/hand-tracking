from pathlib import Path

from build_config import ICON_ICO_PATH, ICON_PNG_PATH


def ensure_windows_icon():
    if not ICON_PNG_PATH.exists():
        raise SystemExit(f"[BUILD] icon.png not found: {ICON_PNG_PATH}")

    ICON_ICO_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(
            "[BUILD] Pillow is required to convert icon.png to icon.ico. "
            "Install it with: pip install pillow"
        ) from exc

    img = Image.open(ICON_PNG_PATH).convert("RGBA")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(ICON_ICO_PATH, format="ICO", sizes=sizes)
    print(f"[BUILD] Windows icon ready: {ICON_ICO_PATH}")
    return ICON_ICO_PATH
