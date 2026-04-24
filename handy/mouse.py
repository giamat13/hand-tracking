"""Cross-platform mouse control using pynput."""

import time

from pynput.mouse import Button as _MouseButton
from pynput.mouse import Controller as _MouseController

import handy.state as state

_mouse = _MouseController()


def init_screen_size() -> None:
    """Detect screen dimensions and store in state.SCREEN_W / state.SCREEN_H.

    Uses tkinter (already a dependency via customtkinter) so no extra package needed.
    Falls back to 1920×1080 if detection fails.
    """
    try:
        import tkinter as _tk
        _root = _tk.Tk()
        _root.withdraw()
        state.SCREEN_W = _root.winfo_screenwidth()
        state.SCREEN_H = _root.winfo_screenheight()
        _root.destroy()
    except Exception:
        state.SCREEN_W, state.SCREEN_H = 1920, 1080


def reset_anchor() -> None:
    """Reset delta tracking — call whenever hands leave the frame."""
    state.prev_hand_x = None
    state.prev_hand_y = None
    state.smooth_dx = 0.0
    state.smooth_dy = 0.0


def move_mouse(lm_list: list, gesture: str) -> None:
    if not state.MOUSE_ENABLED:
        return

    tx, ty = lm_list[8][0], lm_list[8][1]

    if gesture == "Fist":
        state.prev_hand_x, state.prev_hand_y = tx, ty
        state.smooth_dx, state.smooth_dy = 0.0, 0.0
        return

    if state.prev_hand_x is None:
        state.prev_hand_x, state.prev_hand_y = tx, ty
        cx, cy = _mouse.position
        state.smooth_x, state.smooth_y = float(cx), float(cy)
        state.smooth_dx, state.smooth_dy = 0.0, 0.0
        return

    dx_raw = (tx - state.prev_hand_x) * state.SCREEN_W
    dy_raw = (ty - state.prev_hand_y) * state.SCREEN_H

    # Guard against large jumps (hand reappeared after absence)
    if abs(dx_raw) > state.SCREEN_W * 0.15 or abs(dy_raw) > state.SCREEN_H * 0.15:
        state.prev_hand_x, state.prev_hand_y = tx, ty
        state.smooth_dx, state.smooth_dy = 0.0, 0.0
        return

    if state.DYNAMIC_SPEED:
        dist = (dx_raw**2 + dy_raw**2) ** 0.5
        if dist < state.DEADZONE:
            state.prev_hand_x, state.prev_hand_y = tx, ty
            return
        norm = dist / (state.SCREEN_W * 0.1)
        scale = min(norm ** state.SPEED_CURVE, 1.0) * state.SPEED * 0.8
        dx_raw *= scale
        dy_raw *= scale
    else:
        if (dx_raw**2 + dy_raw**2) ** 0.5 < state.DEADZONE:
            state.prev_hand_x, state.prev_hand_y = tx, ty
            return
        dx_raw *= state.SPEED * 0.5
        dy_raw *= state.SPEED * 0.5

    state.prev_hand_x, state.prev_hand_y = tx, ty

    # SMOOTH=0 → sluggish (s≈0.05), SMOOTH=100 → instant (s=1.0)
    s = 0.05 + (state.SMOOTH / 100) * 0.95
    state.smooth_dx = state.smooth_dx * (1 - s) + dx_raw * s
    state.smooth_dy = state.smooth_dy * (1 - s) + dy_raw * s
    state.smooth_x = max(0, min(state.SCREEN_W - 1, state.smooth_x + state.smooth_dx))
    state.smooth_y = max(0, min(state.SCREEN_H - 1, state.smooth_y + state.smooth_dy))

    _mouse.position = (int(state.smooth_x), int(state.smooth_y))

    if gesture == "4 Fingers" and time.time() - state.last_click > state.CLICK_COOLDOWN:
        _mouse.click(_MouseButton.left)
        state.last_click = time.time()
