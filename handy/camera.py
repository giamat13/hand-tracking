"""Camera capture thread and OpenCV processing loop."""

import os
import subprocess
import sys
import time
from collections import deque

import cv2
import mediapipe as mp

import handy.state as state
from .config import COLOR_LEFT, COLOR_RIGHT, MAX_TRAIL
from .custom_gestures import (
    extract_motion_point,
    normalize_landmarks,
)
from .drawing import (
    draw_info_box,
    draw_loading,
    draw_skeleton,
    draw_trail,
    draw_ui,
)
from .gesture import classify_with_custom, fingers_up
from .mouse import move_mouse, move_mouse_head, reset_anchor
from .actions import execute_action


def _key_matches(key: int, chars: str) -> bool:
    if key < 0:
        return False
    low = key & 0xFF
    for ch in chars:
        if key == ord(ch) or low == (ord(ch) & 0xFF):
            return True
    return False


def _key_to_debug(key: int) -> str:
    if key < 0:
        return "none"
    low = key & 0xFF
    try:
        ch = chr(low) if 32 <= low <= 126 else "?"
    except Exception:
        ch = "?"
    return f"key={key} low={low} char={ch}"


# ── Recording overlay ──────────────────────────────────────────────────────

def _draw_recording_overlay(frame, h: int, w: int) -> None:
    """Show a pulsing REC indicator and sample count while capturing."""
    if state.recording_mode == "motion":
        n = len(state.recording_motion_points)
    else:
        n = len(state.recording_samples)
    target = max(int(state.recording_target_frames), 1)
    ratio = min(n / target, 1.0)

    # Semi-transparent red bar at the top
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (int(w * ratio), 6), (0, 80, 255), -1)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)

    # REC text
    pulse = int(time.time() * 4) % 2 == 0
    color = (0, 0, 255) if pulse else (100, 100, 255)
    current_session = max(state.recording_batch_total - state.recording_batch_remaining + 1, 1)
    batch_text = f"  session {current_session}/{max(state.recording_batch_total, 1)}"
    cv2.putText(frame, f"REC  {n}/{target}{batch_text}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)


# ── Frame processing ───────────────────────────────────────────────────────

def _draw_hand(
    frame, idx: int, lm_list: list, label: str, h: int, w: int,
    use_mp_draw: bool = False, hand_lm_raw=None,
) -> None:
    color = COLOR_RIGHT if label == "Right" else COLOR_LEFT

    if use_mp_draw and hand_lm_raw is not None:
        state.mp_draw.draw_landmarks(
            frame, hand_lm_raw, state.mp_hands.HAND_CONNECTIONS,
            state.mp_draw.DrawingSpec(color=color, thickness=2, circle_radius=4),
            state.mp_draw.DrawingSpec(color=(200, 200, 200), thickness=1),
        )
    else:
        draw_skeleton(frame, lm_list, color, h, w)

    tx = int(lm_list[8][0] * w)
    ty = int(lm_list[8][1] * h)
    motion_point = extract_motion_point(lm_list)

    if idx == 0:
        state.motion_history.append(motion_point)

    up = fingers_up(lm_list, label)
    gesture = classify_with_custom(
        up,
        lm_list,
        state.CUSTOM_GESTURE_TEMPLATES,
        motion_points=list(state.motion_history) if idx == 0 else None,
    )

    controls = (
        state.CONTROL_HAND == "Both"
        or (state.CONTROL_HAND == "Right" and label == "Right")
        or (state.CONTROL_HAND == "Left" and label == "Left")
    )
    if idx == 0 and controls:
        move_mouse(lm_list, gesture)

    # ── Recording: capture normalized snapshots ────────────────────────────
    if idx == 0 and state.recording_gesture:
        if state.recording_mode == "motion":
            if len(state.recording_motion_points) < state.recording_target_frames:
                state.recording_motion_points.append(motion_point)
            else:
                state.recording_gesture = False
        else:
            if len(state.recording_samples) < state.recording_target_frames:
                norm = normalize_landmarks(lm_list)
                if norm is not None:
                    state.recording_samples.append(norm)
            else:
                # Auto-stop when we have enough samples
                state.recording_gesture = False

    # ── Action triggering (only first hand, not while recording) ──────────
    if idx == 0 and not state.recording_gesture:
        execute_action(gesture)

    if idx not in state.trails:
        state.trails[idx] = deque(maxlen=MAX_TRAIL)
    if state.trails[idx]:
        last_x, last_y = state.trails[idx][-1]
        if ((tx - last_x) ** 2 + (ty - last_y) ** 2) ** 0.5 > 80:
            state.trails[idx].clear()
    state.trails[idx].append((tx, ty))

    if state.SHOW_TRAIL:
        draw_trail(frame, state.trails[idx])

    wx = int(lm_list[0][0] * w)
    wy = int(lm_list[0][1] * h)
    draw_info_box(frame, f"{label}  {gesture}", wx, wy, color)

    if state.SHOW_COORDS:
        cv2.putText(
            frame, f"({tx},{ty})", (tx + 10, ty - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 255, 200), 1, cv2.LINE_AA,
        )


def _process_frame(frame, h: int, w: int) -> int:
    """Detect hands and draw overlays. Returns number of hands detected."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    if state.USE_NEW_API:
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp = int(time.time() * 1000)
        result = state.detector.detect_for_video(mp_image, timestamp)
        if not result.hand_landmarks:
            state.trails.clear()
            state.motion_history.clear()
            if state.CONTROL_HAND != "Head":
                reset_anchor()
            return 0
        for idx, (hand_lms, hand_info) in enumerate(
            zip(result.hand_landmarks, result.handedness)
        ):
            raw_label = hand_info[0].category_name
            label = "Left" if raw_label == "Right" else "Right"
            lm_list = [(lm.x, lm.y, lm.z) for lm in hand_lms]
            _draw_hand(frame, idx, lm_list, label, h, w)
        return len(result.hand_landmarks)
    else:
        results = state.hands_old.process(rgb)
        if not results.multi_hand_landmarks:
            state.trails.clear()
            state.motion_history.clear()
            if state.CONTROL_HAND != "Head":
                reset_anchor()
            return 0
        for idx, (hand_lm, hand_info) in enumerate(
            zip(results.multi_hand_landmarks, results.multi_handedness)
        ):
            raw_label = hand_info.classification[0].label
            label = "Left" if raw_label == "Right" else "Right"
            lm_list = [(lm.x, lm.y, lm.z) for lm in hand_lm.landmark]
            _draw_hand(frame, idx, lm_list, label, h, w,
                       use_mp_draw=True, hand_lm_raw=hand_lm)
        return len(results.multi_hand_landmarks)


def _process_face(frame, h: int, w: int) -> bool:
    """Detect face and update head tracking. Returns True if face detected."""
    if not state.face_detector:
        return False

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    try:
        if state.USE_NEW_API:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp = int(time.time() * 1000)
            result = state.face_detector.detect_for_video(mp_image, timestamp)
            if not result.face_landmarks:
                return False
            # Store all face landmarks for better accuracy
            face_lm = result.face_landmarks[0]
            state.face_landmarks = [(lm.x, lm.y, lm.z) for lm in face_lm]

            # Use multiple facial landmarks for better head position accuracy
            # Key landmarks: nose tip (1), nose bridge (168), chin (152), forehead center (10)
            key_landmarks = [1, 168, 152, 10]  # nose tip, nose bridge, chin, forehead
            valid_landmarks = [i for i in key_landmarks if i < len(face_lm)]
            
            if valid_landmarks:
                avg_x = sum(face_lm[i].x for i in valid_landmarks) / len(valid_landmarks)
                avg_y = sum(face_lm[i].y for i in valid_landmarks) / len(valid_landmarks)
            else:
                # Fallback to nose tip if no valid landmarks
                avg_x = face_lm[1].x if len(face_lm) > 1 else face_lm[0].x
                avg_y = face_lm[1].y if len(face_lm) > 1 else face_lm[0].y
        else:
            # Legacy face detection not implemented
            return False

        # Convert to screen coordinates
        head_x = int(avg_x * w)
        head_y = int(avg_y * h)

        # Debug: draw multiple face landmarks
        if state.SHOW_LANDMARKS and state.face_landmarks:
            for i, (lm_x, lm_y, lm_z) in enumerate(state.face_landmarks):
                px = int(lm_x * w)
                py = int(lm_y * h)
                # Draw key landmarks in different colors
                if i in [1, 168, 152, 10]:  # key facial points
                    cv2.circle(frame, (px, py), 3, (0, 255, 0), -1)  # green for key points
                else:
                    cv2.circle(frame, (px, py), 2, (255, 255, 0), -1)  # cyan for other points

        # Draw head position indicator
        cv2.circle(frame, (head_x, head_y), 5, (0, 255, 0), -1)
        cv2.putText(frame, "HEAD", (head_x + 10, head_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        # Update head tracking
        if state.head_smooth_x is None or state.prev_head_x is None:
            state.head_smooth_x = head_x
            state.head_smooth_y = head_y
            state.prev_head_x = head_x
            state.prev_head_y = head_y
        else:
            # Smooth the position
            state.head_smooth_x = state.head_smooth_x * (state.SMOOTH / 100) + head_x * (1 - state.SMOOTH / 100)
            state.head_smooth_y = state.head_smooth_y * (state.SMOOTH / 100) + head_y * (1 - state.SMOOTH / 100)

            # Calculate movement deltas
            dx = state.head_smooth_x - state.prev_head_x
            dy = state.head_smooth_y - state.prev_head_y

            # Apply deadzone
            if abs(dx) > state.DEADZONE:
                state.head_smooth_dx = state.head_smooth_dx * 0.8 + dx * 0.2
            else:
                state.head_smooth_dx *= 0.9

            if abs(dy) > state.DEADZONE:
                state.head_smooth_dy = state.head_smooth_dy * 0.8 + dy * 0.2
            else:
                state.head_smooth_dy *= 0.9

            state.prev_head_x = state.head_smooth_x
            state.prev_head_y = state.head_smooth_y

        return True
    except Exception as e:
        print(f"[FACE] Error: {e}")
        return False


# ── Camera loop ────────────────────────────────────────────────────────────

def run_camera() -> None:
    """Open the webcam and run the main detection loop (blocking)."""
    state.camera_error = None
    cap = None

    state.loading_status = "Opening camera..."
    capture_backends = []
    if sys.platform == "win32":
        capture_backends.append(("DirectShow", cv2.CAP_DSHOW))
    capture_backends.append(("Default", cv2.CAP_ANY))

    for backend_name, backend in capture_backends:
        state.loading_status = f"Opening camera ({backend_name})..."
        candidate = cv2.VideoCapture(0, backend)
        if candidate.isOpened():
            cap = candidate
            break
        candidate.release()

    if cap is None:
        state.camera_error = "Camera not found or blocked by another app."
        state.loading_status = f"ERROR: {state.camera_error}"
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    state.loading_status = "Camera ready"
    state.camera_ready = True

    screenshot_cnt = 0
    dots = 0
    dot_timer = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            state.camera_error = "Camera stopped responding."
            break

        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]

        now = time.time()
        fps_val = 1.0 / max(now - state.prev_time, 1e-6)
        state.fps_buffer.append(fps_val)
        fps_avg = sum(state.fps_buffer) / len(state.fps_buffer)
        state.prev_time = now

        if not state.model_ready:
            if now - dot_timer > 0.05:
                dots += 1
                dot_timer = now
            draw_loading(frame, dots)
            hand_count = 0
        elif state.model_error:
            err = str(state.model_error)
            cv2.putText(frame, "MODEL ERROR:", (20, h // 2 - 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2, cv2.LINE_AA)
            y_pos = h // 2
            for i in range(0, len(err), 50):
                cv2.putText(frame, err[i:i + 50], (20, y_pos),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 255), 1, cv2.LINE_AA)
                y_pos += 30
            cv2.putText(frame, "ESC to exit", (20, y_pos + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            hand_count = 0
        else:
            hand_count = _process_frame(frame, h, w)
            face_detected = _process_face(frame, h, w)
            if state.CONTROL_HAND == "Head" and state.MOUSE_ENABLED and face_detected:
                move_mouse_head()
            draw_ui(frame, fps_avg, hand_count)

        # Recording overlay (drawn on top of everything)
        if state.recording_gesture:
            _draw_recording_overlay(frame, h, w)

        cv2.imshow("Handy", frame)

        key = cv2.waitKeyEx(1)
        if _key_matches(key, "\x1b"):  # ESC
            break
        elif cv2.getWindowProperty("Handy", cv2.WND_PROP_VISIBLE) < 1:
            break
        elif _key_matches(key, "gGע"):
            print(f"[HOTKEY] settings requested ({_key_to_debug(key)})")
            if not state.settings_open:
                state.ui_queue.put("open_settings")
            else:
                print("[HOTKEY] settings already open, request ignored")
        elif _key_matches(key, "tTא"):
            print(f"[HOTKEY] gesture trainer requested ({_key_to_debug(key)})")
            if not state.gesture_trainer_open:
                state.ui_queue.put("open_gesture_trainer")
            else:
                print("[HOTKEY] gesture trainer already open, request ignored")
        elif _key_matches(key, "sS"):
            fname = f"screenshot_{screenshot_cnt:03d}.png"
            cv2.imwrite(fname, frame)
            print(f"Saved: {fname}")
            screenshot_cnt += 1

    cap.release()
    cv2.destroyAllWindows()
    os.kill(os.getpid(), 9)
