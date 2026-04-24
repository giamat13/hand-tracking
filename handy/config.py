"""Immutable constants that do not change after startup."""

# Hand landmark indices
FINGER_TIPS = [4, 8, 12, 16, 20]
MAX_TRAIL = 40

# OpenCV drawing colours (BGR)
COLOR_RIGHT = (0, 200, 255)
COLOR_LEFT = (255, 100, 0)
COLOR_TRAIL = (0, 255, 150)
COLOR_TEXT = (255, 255, 255)

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]

MODEL_FILENAME = "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
