"""
Custom gesture definitions, recording sessions, and matching.

Each gesture can contain multiple training sessions. Static sessions store
normalized landmark snapshots. Motion sessions store a normalized palm path.
Matching picks the closest trained session instead of collapsing everything
into one template, which keeps bad recordings isolated and removable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import time

import numpy as np


# ── Matching sensitivity ───────────────────────────────────────────────────
MATCH_THRESHOLD: float = 0.20
MIN_SAMPLES: int = 15
RECORD_SAMPLES: int = 60
MOTION_MIN_FRAMES: int = 15
MOTION_RECORD_FRAMES: int = 90
MOTION_RESAMPLE_POINTS: int = 24
MOTION_MATCH_THRESHOLD: float = 0.34
MOTION_MIN_TRAVEL: float = 0.08


# ── Built-in gestures (produced by gesture.classify_gesture) ──────────────
BUILTIN_ENTRIES: list[str] = [
    "Fist",
    "Open Hand",
    "One Finger",
    "Victory",
    "Hang Loose",
    "Thumbs Up",
    "1 Fingers",
    "2 Fingers",
    "3 Fingers",
    "4 Fingers",
    "5 Fingers",
]


def _new_session_id() -> str:
    return f"s{time.time_ns()}"


@dataclass
class GestureSession:
    """One training session for a gesture."""

    id: str = field(default_factory=_new_session_id)
    kind: str = "static"
    samples: list = field(default_factory=list)   # list[np.ndarray (21,2)]
    motion_path: Optional[np.ndarray] = None
    motion_frame_count: int = 0
    target_frames: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "samples": [s.tolist() for s in self.samples],
            "motion_path": self.motion_path.tolist() if self.motion_path is not None else [],
            "motion_frame_count": self.motion_frame_count,
            "target_frames": self.target_frames,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "GestureSession":
        kind = d.get("kind", "static")
        if kind not in {"static", "motion"}:
            kind = "static"
        motion_path_data = d.get("motion_path", [])
        return GestureSession(
            id=str(d.get("id") or _new_session_id()),
            kind=kind,
            samples=[np.array(s, dtype=np.float32) for s in d.get("samples", [])],
            motion_path=(
                np.array(motion_path_data, dtype=np.float32)
                if motion_path_data else None
            ),
            motion_frame_count=int(
                d.get("motion_frame_count")
                or (len(motion_path_data) if motion_path_data else 0)
            ),
            target_frames=int(d.get("target_frames", 0)),
            created_at=float(d.get("created_at", time.time())),
        )

    def sample_count(self) -> int:
        return self.motion_frame_count if self.kind == "motion" else len(self.samples)

    def is_trained(self) -> bool:
        if self.kind == "motion":
            return self.motion_path is not None and self.motion_frame_count >= MOTION_MIN_FRAMES
        return len(self.samples) >= MIN_SAMPLES

    def mean_template(self) -> Optional[np.ndarray]:
        if self.kind != "static" or not self.samples:
            return None
        return np.mean(np.stack(self.samples), axis=0)


@dataclass
class GestureTemplate:
    """One named gesture with one or more training sessions."""

    name: str
    kind: str = "static"
    sessions: list[GestureSession] = field(default_factory=list)
    builtin: bool = False
    deleted: bool = False
    motion_tolerance: float = 1.25

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "builtin": self.builtin,
            "deleted": self.deleted,
            "motion_tolerance": self.motion_tolerance,
            "sessions": [s.to_dict() for s in self.sessions],
        }

    @staticmethod
    def from_dict(d: dict) -> "GestureTemplate":
        kind = d.get("kind", "static")
        if kind not in {"static", "motion"}:
            kind = "static"

        sessions_data = d.get("sessions")
        if isinstance(sessions_data, list):
            sessions = [GestureSession.from_dict(s) for s in sessions_data if isinstance(s, dict)]
        else:
            # Legacy migration: old files stored one flattened template only.
            sessions = []
            legacy_samples = d.get("samples", [])
            legacy_motion_path = d.get("motion_path", [])
            legacy_motion_frame_count = int(d.get("motion_frame_count", 0))
            if legacy_samples:
                sessions.append(
                    GestureSession(
                        kind="static",
                        samples=[np.array(s, dtype=np.float32) for s in legacy_samples],
                        target_frames=max(len(legacy_samples), RECORD_SAMPLES),
                    )
                )
            elif legacy_motion_path:
                sessions.append(
                    GestureSession(
                        kind="motion",
                        motion_path=np.array(legacy_motion_path, dtype=np.float32),
                        motion_frame_count=legacy_motion_frame_count or len(legacy_motion_path),
                        target_frames=legacy_motion_frame_count or MOTION_RECORD_FRAMES,
                    )
                )

        template = GestureTemplate(
            name=d["name"],
            kind=kind,
            sessions=sessions,
            builtin=bool(d.get("builtin", False)),
            deleted=bool(d.get("deleted", False)),
            motion_tolerance=float(d.get("motion_tolerance", 1.25)),
        )
        template.normalize_sessions()
        return template

    def normalize_sessions(self) -> None:
        cleaned: list[GestureSession] = []
        for session in self.sessions:
            if session.kind not in {"static", "motion"}:
                continue
            if session.kind == "motion" and session.target_frames <= 0:
                session.target_frames = session.motion_frame_count or MOTION_RECORD_FRAMES
            if session.kind == "static" and session.target_frames <= 0:
                session.target_frames = max(len(session.samples), RECORD_SAMPLES)
            cleaned.append(session)
        self.sessions = cleaned
        if self.kind not in {"static", "motion"}:
            self.kind = "static"
        self.motion_tolerance = min(max(float(self.motion_tolerance or 1.25), 0.7), 2.0)

    def is_trained(self) -> bool:
        return not self.deleted and any(session.is_trained() for session in self.sessions)

    def session_count(self) -> int:
        return len(self.sessions)

    def trained_session_count(self) -> int:
        return sum(1 for session in self.sessions if session.is_trained())

    def sample_count(self) -> int:
        return sum(session.sample_count() for session in self.sessions)

    def clear_sessions(self) -> None:
        self.sessions.clear()

    def add_static_session(self, samples: list, target_frames: int = RECORD_SAMPLES) -> Optional[GestureSession]:
        if not samples:
            return None
        session = GestureSession(
            kind="static",
            samples=list(samples),
            target_frames=max(target_frames, len(samples), MIN_SAMPLES),
        )
        self.kind = "static"
        self.deleted = False
        self.sessions.append(session)
        return session

    def add_motion_session(self, points: list, target_frames: int = MOTION_RECORD_FRAMES) -> Optional[GestureSession]:
        session = build_motion_session(points, target_frames=target_frames)
        if session is None:
            return None
        self.kind = "motion"
        self.deleted = False
        self.sessions.append(session)
        return session

    def delete_session(self, session_id: str) -> bool:
        original = len(self.sessions)
        self.sessions = [session for session in self.sessions if session.id != session_id]
        return len(self.sessions) != original


def normalize_landmarks(lm_list: list) -> Optional[np.ndarray]:
    """Convert raw landmarks to a scale/position-invariant (21, 2) array."""
    pts = np.array([[lm[0], lm[1]] for lm in lm_list], dtype=np.float32)
    pts -= pts[0]
    hand_size = float(np.linalg.norm(pts[9]))
    if hand_size < 1e-4:
        return None
    pts /= hand_size
    return pts


def extract_motion_point(lm_list: list) -> tuple[float, float]:
    """Return a stable palm-center point for motion tracking."""
    palm_ids = (0, 5, 9, 13, 17)
    x = sum(lm_list[i][0] for i in palm_ids) / len(palm_ids)
    y = sum(lm_list[i][1] for i in palm_ids) / len(palm_ids)
    return (x, y)


def _resample_motion_path(points: np.ndarray, target_count: int) -> Optional[np.ndarray]:
    if len(points) < 2:
        return None

    segment_lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    total_length = float(np.sum(segment_lengths))
    if total_length < 1e-6:
        return None

    cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths)))
    targets = np.linspace(0.0, total_length, target_count, dtype=np.float32)
    resampled = []
    seg_idx = 0

    for target in targets:
        while seg_idx < len(segment_lengths) - 1 and cumulative[seg_idx + 1] < target:
            seg_idx += 1
        start = points[seg_idx]
        end = points[seg_idx + 1]
        span = cumulative[seg_idx + 1] - cumulative[seg_idx]
        if span < 1e-6:
            resampled.append(start.copy())
            continue
        ratio = (target - cumulative[seg_idx]) / span
        resampled.append(start + (end - start) * ratio)

    return np.array(resampled, dtype=np.float32)


def normalize_motion_path(points: list) -> Optional[np.ndarray]:
    """
    Convert a recorded motion path into a translation/scale-invariant curve.

    The path is anchored to its first point, lightly smoothed, and resampled
    to a fixed number of points so speed differences still match.
    """
    if len(points) < MOTION_MIN_FRAMES:
        return None

    pts = np.array(points, dtype=np.float32)
    if pts.ndim != 2 or pts.shape[1] != 2:
        return None

    if len(pts) >= 3:
        smooth = pts.copy()
        smooth[1:-1] = (pts[:-2] + pts[1:-1] * 2.0 + pts[2:]) / 4.0
        pts = smooth

    pts -= pts[0]
    travel = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
    span = np.ptp(pts, axis=0)
    scale = float(max(span[0], span[1], np.linalg.norm(span)))
    if travel < MOTION_MIN_TRAVEL or scale < (MOTION_MIN_TRAVEL * 0.5):
        return None

    pts /= max(scale, 1e-6)
    return _resample_motion_path(pts, MOTION_RESAMPLE_POINTS)


def build_motion_session(points: list, target_frames: int = MOTION_RECORD_FRAMES) -> Optional[GestureSession]:
    path = normalize_motion_path(points)
    session = GestureSession(
        kind="motion",
        motion_path=path,
        motion_frame_count=len(points),
        target_frames=max(target_frames, MOTION_MIN_FRAMES),
    )
    return session if session.motion_frame_count else None


def _candidate_motion_sizes(expected: int) -> list[int]:
    sizes = {
        max(MOTION_MIN_FRAMES, int(round(expected * factor)))
        for factor in (0.5, 0.65, 0.8, 1.0, 1.2, 1.4, 1.6)
    }
    return sorted(sizes)


def _iter_motion_candidates(motion_points: list, expected: int):
    history_len = len(motion_points)
    if history_len < MOTION_MIN_FRAMES:
        return
    max_offset = min(18, history_len - MOTION_MIN_FRAMES)
    for candidate_size in _candidate_motion_sizes(expected):
        if history_len < candidate_size:
            continue
        for offset in range(0, max_offset + 1, 3):
            end = history_len - offset
            start = end - candidate_size
            if start < 0:
                continue
            candidate = normalize_motion_path(motion_points[start:end])
            if candidate is not None:
                yield candidate


def is_deleted_builtin(name: str, templates: list) -> bool:
    for tmpl in templates:
        if tmpl.name == name and tmpl.builtin and tmpl.deleted:
            return True
    return False


def match_custom_gesture(
    lm_list: list,
    templates: list,          # list[GestureTemplate]
    motion_points: Optional[list] = None,
) -> Optional[str]:
    """Return the closest trained custom gesture, or None if no match."""
    best_name: Optional[str] = None
    best_dist: float

    if motion_points:
        best_dist = MOTION_MATCH_THRESHOLD
        for tmpl in templates:
            if tmpl.deleted or tmpl.kind != "motion":
                continue
            threshold = MOTION_MATCH_THRESHOLD * tmpl.motion_tolerance
            for session in tmpl.sessions:
                if session.kind != "motion" or session.motion_path is None or not session.is_trained():
                    continue
                expected = max(session.motion_frame_count, session.target_frames, MOTION_MIN_FRAMES)
                for candidate in _iter_motion_candidates(motion_points, expected):
                    dist = float(np.mean(np.linalg.norm(candidate - session.motion_path, axis=1)))
                    if dist < min(best_dist, threshold):
                        best_dist = dist
                        best_name = tmpl.name
        if best_name:
            return best_name

    norm = normalize_landmarks(lm_list)
    if norm is None:
        return None

    best_dist = MATCH_THRESHOLD
    for tmpl in templates:
        if tmpl.deleted or tmpl.kind != "static":
            continue
        for session in tmpl.sessions:
            if session.kind != "static" or not session.is_trained():
                continue
            mean = session.mean_template()
            if mean is None:
                continue
            dist = float(np.mean(np.linalg.norm(norm - mean, axis=1)))
            if dist < best_dist:
                best_dist = dist
                best_name = tmpl.name

    return best_name
