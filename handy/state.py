"""Mutable runtime state shared across all modules.

Import pattern (always use module reference, never bare import):
    import handy.state as state
    state.model_ready = True      # ✓ modifies the shared module variable
"""

import queue
import time
from collections import deque

# ── Screen ─────────────────────────────────────────────────────────
SCREEN_W: int = 1920
SCREEN_H: int = 1080

# ── Model ──────────────────────────────────────────────────────────
USE_NEW_API: bool = False
detector = None
hands_old = None
mp_hands = None
mp_draw = None
model_ready: bool = False
model_error = None

# ── Camera ─────────────────────────────────────────────────────────
camera_ready: bool = False
camera_error = None

# ── Debug / hot-reload ─────────────────────────────────────────────
DEBUG_MODE: bool = False
FAST_RELOAD: bool = False

# ── User-adjustable settings (changed via settings window) ─────────
SMOOTH: int = 7
SPEED: int = 5
DYNAMIC_SPEED: bool = True
SPEED_CURVE: float = 2.0
CAM_MARGIN: float = 0.15
DEADZONE: int = 8
MOUSE_ENABLED: bool = False
CONTROL_HAND: str = "Right"
CLICK_COOLDOWN: float = 0.6
SHOW_TRAIL: bool = True
SHOW_COORDS: bool = True
SHOW_LANDMARKS: bool = True

# ── Mouse tracking ─────────────────────────────────────────────────
smooth_x = None
smooth_y = None
prev_hand_x = None
prev_hand_y = None
smooth_dx: float = 0.0
smooth_dy: float = 0.0
last_click: float = 0.0

# ── UI ─────────────────────────────────────────────────────────────
settings_open: bool = False
ui_queue: queue.Queue = queue.Queue()
loading_status: str = "Starting..."

# ── FPS ────────────────────────────────────────────────────────────
fps_buffer: deque = deque(maxlen=30)
prev_time: float = time.time()

# ── Trails ─────────────────────────────────────────────────────────
trails: dict = {}
