from __future__ import annotations

from dataclasses import dataclass
from math import hypot, sqrt
from time import monotonic
from typing import Iterable, Sequence


Landmark = object


@dataclass(frozen=True)
class HandGesture:
    name: str
    confidence: float
    center_x: float
    center_y: float
    openness: float
    pinch_distance: float
    vertical_velocity: float
    extended_fingers: tuple[str, ...]


class GestureTracker:
    def __init__(self) -> None:
        self._history: dict[str, tuple[float, float]] = {}
        self._stable_gesture: dict[str, str] = {}
        self._candidate_gesture: dict[str, tuple[str, int]] = {}

    def classify(
        self,
        landmarks: Sequence[Landmark],
        handedness: str,
        track_id: str | None = None,
        model_gesture: str | None = None,
        model_confidence: float = 0.0,
        geometry_landmarks: Sequence[Landmark] | None = None,
    ) -> HandGesture:
        now = monotonic()
        center_x = sum(_coord(point, "x") for point in landmarks) / len(landmarks)
        center_y = sum(_coord(point, "y") for point in landmarks) / len(landmarks)
        history_key = track_id or handedness.lower()
        previous = self._history.get(history_key)

        if previous is None:
            vertical_velocity = 0.0
        else:
            last_center_y, last_time = previous
            dt = max(now - last_time, 1e-3)
            vertical_velocity = (last_center_y - center_y) / dt

        self._history[history_key] = (center_y, now)

        geometry = geometry_landmarks or landmarks
        extended = tuple(_extended_fingers(geometry, handedness))
        openness = len(extended) / 5.0
        pinch_distance = _distance(landmarks[4], landmarks[8])
        palm_width = max(_distance(landmarks[5], landmarks[17]), 1e-3)
        pinch_ratio = pinch_distance / palm_width

        model_names = {
            "Closed_Fist": "fist",
            "Open_Palm": "open_palm",
            "Victory": "peace",
            "Thumb_Up": "thumbs_up",
        }

        trusted_model_names = {
            "Closed_Fist": "fist",
            "Open_Palm": "open_palm",
            "Victory": "peace",
        }

        if model_gesture in trusted_model_names and model_confidence >= 0.70:
            name = trusted_model_names[model_gesture]
            confidence = model_confidence
        elif pinch_ratio < 0.20 and "index" in extended:
            name = "pinch"
            confidence = 1.0 - min(pinch_ratio / 0.20, 1.0)
        elif model_gesture in model_names and model_confidence >= 0.60:
            name = model_names[model_gesture]
            confidence = model_confidence
        elif len(extended) == 0:
            name = "fist"
            confidence = 0.9
        elif len(extended) >= 4:
            name = "open_palm"
            confidence = len(extended) / 5.0
        elif extended == ("index", "middle"):
            name = "peace"
            confidence = 0.9
        else:
            name = "unknown"
            confidence = 0.4

        stable_name = self._stable_gesture.get(history_key)
        if stable_name is None:
            self._stable_gesture[history_key] = name
        elif name == stable_name:
            self._candidate_gesture.pop(history_key, None)
        else:
            candidate_name, count = self._candidate_gesture.get(history_key, (name, 0))
            count = count + 1 if candidate_name == name else 1
            self._candidate_gesture[history_key] = (name, count)
            frames_required = 5 if name == "unknown" else 3
            if count >= frames_required:
                self._stable_gesture[history_key] = name
                self._candidate_gesture.pop(history_key, None)
            else:
                name = stable_name

        return HandGesture(
            name=name,
            confidence=confidence,
            center_x=center_x,
            center_y=center_y,
            openness=openness,
            pinch_distance=pinch_distance,
            vertical_velocity=vertical_velocity,
            extended_fingers=extended,
        )


def _extended_fingers(landmarks: Sequence[Landmark], handedness: str) -> Iterable[str]:
    fingers = (
        ("index", (5, 6, 7, 8), 0.76),
        ("middle", (9, 10, 11, 12), 0.80),
        ("ring", (13, 14, 15, 16), 0.80),
        ("pinky", (17, 18, 19, 20), 0.78),
    )
    for name, indices, threshold in fingers:
        if _finger_is_extended(landmarks, indices, threshold):
            yield name

    if _finger_is_extended(landmarks, (1, 2, 3, 4), 0.72):
        yield "thumb"


def _finger_is_extended(
    landmarks: Sequence[Landmark],
    indices: tuple[int, int, int, int],
    straightness_threshold: float,
) -> bool:
    base, first_joint, second_joint, tip = (landmarks[index] for index in indices)
    chain_length = (
        _distance_3d(base, first_joint)
        + _distance_3d(first_joint, second_joint)
        + _distance_3d(second_joint, tip)
    )
    if chain_length < 1e-6:
        return False
    straightness = _distance_3d(base, tip) / chain_length
    wrist = landmarks[0]
    reaches_outward = _distance_3d(tip, wrist) > _distance_3d(first_joint, wrist) * 1.01
    return straightness >= straightness_threshold and reaches_outward


def _vector(origin: Landmark, target: Landmark) -> tuple[float, float, float]:
    return (
        _coord(target, "x") - _coord(origin, "x"),
        _coord(target, "y") - _coord(origin, "y"),
        _coord(target, "z") - _coord(origin, "z"),
    )


def _vector_length(vector: tuple[float, float, float]) -> float:
    return sqrt(sum(component * component for component in vector))


def _distance_3d(a: Landmark, b: Landmark) -> float:
    return _vector_length(_vector(a, b))


def _distance(a: Landmark, b: Landmark) -> float:
    return hypot(_coord(a, "x") - _coord(b, "x"), _coord(a, "y") - _coord(b, "y"))


def _coord(point: Landmark, name: str) -> float:
    return float(getattr(point, name, 0.0) or 0.0)
