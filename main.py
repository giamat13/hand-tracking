"""
זיהוי ידיים והזזתם - Hand Detection & Gesture Tracking
========================================================
תואם לכל גרסאות mediapipe (ישן וחדש)
דרישות: pip install opencv-python mediapipe numpy

הפעלה: python hand_tracking.py
"""

import cv2
import numpy as np
import time
from collections import deque
import mediapipe as mp

USE_NEW_API = False
detector    = None
hands_old   = None
mp_hands    = None
mp_draw     = None

# ── זיהוי גרסת API ────────────────────────────────────────────────
try:
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python.vision import HandLandmarkerOptions, HandLandmarker
    import urllib.request, os

    MODEL_PATH = "hand_landmarker.task"
    if not os.path.exists(MODEL_PATH):
        print("Downloading hand model (~9MB)...")
        urllib.request.urlretrieve(
            "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
            "hand_landmarker/float16/1/hand_landmarker.task",
            MODEL_PATH
        )
        print("Model downloaded!")

    print("Loading hand detection model (first run may take ~10 sec)...")
    base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    options = HandLandmarkerOptions(
        base_options=base_options,
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.7,
        min_tracking_confidence=0.6
    )
    detector    = HandLandmarker.create_from_options(options)
    USE_NEW_API = True
    print("Using NEW mediapipe API (0.10+)")

except Exception:
    try:
        mp_hands  = mp.solutions.hands
        mp_draw   = mp.solutions.drawing_utils
        hands_old = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.6
        )
        print("Using OLD mediapipe API (0.9.x)")
    except Exception as e:
        print(f"ERROR loading mediapipe: {e}")
        exit(1)

# ── קבועים ─────────────────────────────────────────────────────────
FINGER_TIPS  = [4, 8, 12, 16, 20]
MAX_TRAIL    = 40
COLOR_RIGHT  = (0, 200, 255)
COLOR_LEFT   = (255, 100, 0)
COLOR_TRAIL  = (0, 255, 150)
COLOR_TEXT   = (255, 255, 255)

trails     = {}
fps_buffer = deque(maxlen=30)
prev_time  = time.time()

HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (5,9),(9,10),(10,11),(11,12),
    (9,13),(13,14),(14,15),(15,16),
    (13,17),(17,18),(18,19),(19,20),
    (0,17)
]

# ── ג'סטות ─────────────────────────────────────────────────────────
def fingers_up(lm_list, handedness):
    up     = []
    tip_x  = lm_list[4][0]
    base_x = lm_list[3][0]
    up.append(tip_x < base_x if handedness == "Right" else tip_x > base_x)
    for tip_id in FINGER_TIPS[1:]:
        up.append(lm_list[tip_id][1] < lm_list[tip_id - 2][1])
    return up

def classify_gesture(up):
    count = sum(up)
    if count == 0:                            return "Fist"
    if count == 5:                            return "Open Hand"
    if up[1] and not any(up[2:]):             return "One Finger"
    if up[1] and up[2] and not any(up[3:]):   return "Victory"
    if up[0] and up[4] and not any(up[1:4]): return "Hang Loose"
    if up[0] and not any(up[1:]):             return "Thumbs Up"
    return f"{count} Fingers"

# ── ציור ───────────────────────────────────────────────────────────
def draw_skeleton(frame, lm_list, color, h, w):
    pts = [(int(lm[0]*w), int(lm[1]*h)) for lm in lm_list]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (200,200,200), 1, cv2.LINE_AA)
    for pt in pts:
        cv2.circle(frame, pt, 5, color, -1, cv2.LINE_AA)
        cv2.circle(frame, pt, 6, (255,255,255), 1, cv2.LINE_AA)

def draw_trail(frame, trail):
    pts = list(trail)
    for i in range(1, len(pts)):
        alpha = i / len(pts)
        color = tuple(int(c * alpha) for c in COLOR_TRAIL)
        cv2.line(frame, pts[i-1], pts[i], color, max(1, int(alpha*5)), cv2.LINE_AA)

def draw_info_box(frame, label, wx, wy, color):
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    bx = max(0, wx - tw // 2)
    by = max(60, wy - 40)
    cv2.rectangle(frame, (bx-6, by-th-8), (bx+tw+6, by+4), (0,0,0), -1)
    cv2.putText(frame, label, (bx, by),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

def draw_ui(frame, fps, hand_count):
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0,0), (w,50), (10,10,10), -1)
    cv2.putText(frame, "HAND TRACKER  |  ESC = quit  |  S = screenshot",
                (12,32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_TEXT, 1, cv2.LINE_AA)
    cv2.putText(frame, f"FPS: {fps:.0f}", (w-120,32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_TRAIL, 2, cv2.LINE_AA)
    cv2.putText(frame, f"Hands: {hand_count}", (w-240,32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_RIGHT, 2, cv2.LINE_AA)

def draw_hand(frame, idx, lm_list, label, h, w, use_mp_draw=False, hand_lm_raw=None):
    color = COLOR_RIGHT if label == "Right" else COLOR_LEFT

    if use_mp_draw and hand_lm_raw is not None:
        mp_draw.draw_landmarks(
            frame, hand_lm_raw, mp_hands.HAND_CONNECTIONS,
            mp_draw.DrawingSpec(color=color, thickness=2, circle_radius=4),
            mp_draw.DrawingSpec(color=(200,200,200), thickness=1)
        )
    else:
        draw_skeleton(frame, lm_list, color, h, w)

    tx = int(lm_list[8][0] * w)
    ty = int(lm_list[8][1] * h)
    if idx not in trails:
        trails[idx] = deque(maxlen=MAX_TRAIL)
    trails[idx].append((tx, ty))
    draw_trail(frame, trails[idx])

    up      = fingers_up(lm_list, label)
    gesture = classify_gesture(up)
    wx      = int(lm_list[0][0] * w)
    wy      = int(lm_list[0][1] * h)
    draw_info_box(frame, f"{label}  {gesture}", wx, wy, color)
    cv2.putText(frame, f"({tx},{ty})", (tx+10, ty-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200,255,200), 1, cv2.LINE_AA)

# ── עיבוד פריים ────────────────────────────────────────────────────
def process_frame(frame, h, w):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    if USE_NEW_API:
        mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp = int(time.time() * 1000)
        result    = detector.detect_for_video(mp_image, timestamp)
        if not result.hand_landmarks:
            trails.clear()
            return 0
        for idx, (hand_lms, hand_info) in enumerate(
                zip(result.hand_landmarks, result.handedness)):
            raw_label = hand_info[0].category_name
            label     = "Left" if raw_label == "Right" else "Right"  # תיקון אחרי flip
            lm_list   = [(lm.x, lm.y, lm.z) for lm in hand_lms]
            draw_hand(frame, idx, lm_list, label, h, w)
        return len(result.hand_landmarks)

    else:
        results = hands_old.process(rgb)
        if not results.multi_hand_landmarks:
            trails.clear()
            return 0
        for idx, (hand_lm, hand_info) in enumerate(
                zip(results.multi_hand_landmarks, results.multi_handedness)):
            raw_label = hand_info.classification[0].label
            label     = "Left" if raw_label == "Right" else "Right"  # תיקון אחרי flip
            lm_list = [(lm.x, lm.y, lm.z) for lm in hand_lm.landmark]
            draw_hand(frame, idx, lm_list, label, h, w,
                      use_mp_draw=True, hand_lm_raw=hand_lm)
        return len(results.multi_hand_landmarks)

# ── לולאה ראשית ─────────────────────────────────────────────────────
def main():
    global prev_time

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Camera not found.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    screenshot_cnt = 0
    print("Camera active - ESC to quit, S for screenshot")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w  = frame.shape[:2]

        now       = time.time()
        fps_val   = 1.0 / max(now - prev_time, 1e-6)
        fps_buffer.append(fps_val)
        fps_avg   = sum(fps_buffer) / len(fps_buffer)
        prev_time = now

        hand_count = process_frame(frame, h, w)
        draw_ui(frame, fps_avg, hand_count)

        cv2.imshow("Hand Tracker", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        elif key in (ord('s'), ord('S')):
            fname = f"screenshot_{screenshot_cnt:03d}.png"
            cv2.imwrite(fname, frame)
            print(f"Saved: {fname}")
            screenshot_cnt += 1

    cap.release()
    cv2.destroyAllWindows()
    print("Done!")

if __name__ == "__main__":
    main()