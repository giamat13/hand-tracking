"""Background thread that loads the MediaPipe hand-landmarker and face-landmarker models."""

import os
import sys
import urllib.request

import mediapipe as mp

import handy.state as state
from .config import MODEL_FILENAME, MODEL_URL, FACE_MODEL_FILENAME, FACE_MODEL_URL


def _model_path() -> str:
    """Resolve model file path — works for both script and frozen EXE."""
    if getattr(sys, "frozen", False):
        app_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(app_dir, MODEL_FILENAME)


def _face_model_path() -> str:
    """Resolve face model file path — works for both script and frozen EXE."""
    if getattr(sys, "frozen", False):
        app_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(app_dir, FACE_MODEL_FILENAME)


def _set_status(msg: str) -> None:
    state.loading_status = msg
    print(msg)


def load_model() -> None:
    """Load (or download) the model. Sets state.model_ready when finished."""
    try:
        _set_status("Importing mediapipe...")
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions

        model_path = _model_path()
        if not os.path.exists(model_path):
            _set_status("Downloading hand model (~9 MB)...")
            try:
                urllib.request.urlretrieve(MODEL_URL, model_path)
            except Exception as dl_err:
                state.model_error = f"Download failed: {dl_err}"
                _set_status(f"ERROR: {dl_err}")
                return

        _set_status("Loading hand model...")
        base_options = mp_python.BaseOptions(model_asset_path=model_path)
        options = HandLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.7,
            min_tracking_confidence=0.6,
        )
        state.detector = HandLandmarker.create_from_options(options)
        state.USE_NEW_API = True
        _set_status("Model ready (new API)")

        # Load face detector
        _set_status("Loading face model...")
        from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions

        face_model_path = _face_model_path()
        if not os.path.exists(face_model_path):
            _set_status("Downloading face model (~5 MB)...")
            try:
                urllib.request.urlretrieve(FACE_MODEL_URL, face_model_path)
            except Exception as dl_err:
                print(f"[model] Face download failed: {dl_err}")
                # Continue without face detection

        try:
            face_base_options = mp_python.BaseOptions(model_asset_path=face_model_path)
            face_options = FaceLandmarkerOptions(
                base_options=face_base_options,
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=0.7,
                min_tracking_confidence=0.6,
            )
            state.face_detector = FaceLandmarker.create_from_options(face_options)
            _set_status("Face model ready")
        except Exception as face_err:
            print(f"[model] Face model failed: {face_err}")
            # Continue without face detection

    except Exception as new_api_err:
        print(f"[model] New API failed: {new_api_err}")
        try:
            _set_status("Trying legacy mediapipe API...")
            import mediapipe as _mp

            if hasattr(_mp, "solutions") and hasattr(_mp.solutions, "hands"):
                state.mp_hands = _mp.solutions.hands
                state.mp_draw = _mp.solutions.drawing_utils
            else:
                try:
                    from mediapipe.python.solutions import drawing_utils as _d
                    from mediapipe.python.solutions import hands as _h
                except ImportError:
                    import mediapipe.python.solutions.drawing_utils as _d
                    import mediapipe.python.solutions.hands as _h
                state.mp_hands = _h
                state.mp_draw = _d

            state.hands_old = state.mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.6,
            )
            _set_status("Model ready (legacy API)")

        except Exception as legacy_err:
            state.model_error = str(legacy_err)
            _set_status(f"ERROR: {legacy_err}")

    # Always mark finished so the loading screen unblocks
    state.model_ready = True
