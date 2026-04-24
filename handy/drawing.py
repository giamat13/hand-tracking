"""OpenCV drawing utilities (no state mutations)."""

import cv2
import numpy as np

import handy.state as state
from .config import (
    COLOR_RIGHT,
    COLOR_TEXT,
    COLOR_TRAIL,
    HAND_CONNECTIONS,
)


def draw_skeleton(frame, lm_list: list, color: tuple, h: int, w: int) -> None:
    pts = [(int(lm[0] * w), int(lm[1] * h)) for lm in lm_list]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (200, 200, 200), 1, cv2.LINE_AA)
    for pt in pts:
        cv2.circle(frame, pt, 5, color, -1, cv2.LINE_AA)
        cv2.circle(frame, pt, 6, (255, 255, 255), 1, cv2.LINE_AA)


def draw_trail(frame, trail) -> None:
    pts = list(trail)
    for i in range(1, len(pts)):
        alpha = i / len(pts)
        color = tuple(int(c * alpha) for c in COLOR_TRAIL)
        cv2.line(frame, pts[i - 1], pts[i], color, max(1, int(alpha * 5)), cv2.LINE_AA)


def draw_info_box(frame, label: str, wx: int, wy: int, color: tuple) -> None:
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    bx = max(0, wx - tw // 2)
    by = max(60, wy - 40)
    cv2.rectangle(frame, (bx - 6, by - th - 8), (bx + tw + 6, by + 4), (0, 0, 0), -1)
    cv2.putText(frame, label, (bx, by), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)


def draw_ui(frame, fps: float, hand_count: int) -> None:
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 50), (10, 10, 10), -1)
    hint = "ESC=quit  S=screenshot  G=settings" + ("  R=reload" if state.DEBUG_MODE else "")
    cv2.putText(
        frame, f"HANDY  |  {hint}",
        (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_TEXT, 1, cv2.LINE_AA,
    )
    cv2.putText(
        frame, f"FPS: {fps:.0f}",
        (w - 120, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_TRAIL, 2, cv2.LINE_AA,
    )
    cv2.putText(
        frame, f"Hands: {hand_count}",
        (w - 240, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_RIGHT, 2, cv2.LINE_AA,
    )
    mouse_status = f"Mouse: {'ON' if state.MOUSE_ENABLED else 'OFF'}  Hand: {state.CONTROL_HAND}"
    cv2.putText(
        frame, mouse_status,
        (12, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
        COLOR_TRAIL if state.MOUSE_ENABLED else (100, 100, 100), 1, cv2.LINE_AA,
    )
    if state.DEBUG_MODE:
        cv2.putText(
            frame, "DEBUG",
            (w - 68, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 80, 255), 2, cv2.LINE_AA,
        )


def draw_loading(frame, dots: int) -> None:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (10, 10, 10), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    title = "Hand Tracker"
    (tw, _), _ = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 1.4, 3)
    cv2.putText(
        frame, title,
        ((w - tw) // 2, h // 2 - 80), cv2.FONT_HERSHEY_SIMPLEX, 1.4, COLOR_TRAIL, 3, cv2.LINE_AA,
    )

    cx, cy, radius, num_segments = w // 2, h // 2, 30, 12
    for i in range(num_segments):
        angle = (i / num_segments) * 2 * np.pi - (dots * 0.4)
        brightness = int(255 * (i / num_segments))
        color = (0, brightness, brightness // 2)
        x1 = int(cx + (radius - 8) * np.cos(angle))
        y1 = int(cy + (radius - 8) * np.sin(angle))
        x2 = int(cx + radius * np.cos(angle))
        y2 = int(cy + radius * np.sin(angle))
        cv2.line(frame, (x1, y1), (x2, y2), color, 3, cv2.LINE_AA)

    text = "Loading model" + "." * (dots % 4)
    (lw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
    cv2.putText(
        frame, text,
        ((w - lw) // 2, h // 2 + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (220, 220, 220), 2,
        cv2.LINE_AA,
    )

    bar_w, bar_h = 300, 8
    bx = (w - bar_w) // 2
    by = h // 2 + 90
    cv2.rectangle(frame, (bx, by), (bx + bar_w, by + bar_h), (50, 50, 50), -1)
    fill = int(bar_w * ((dots % 20) / 20))
    cv2.rectangle(frame, (bx, by), (bx + fill, by + bar_h), COLOR_TRAIL, -1)
