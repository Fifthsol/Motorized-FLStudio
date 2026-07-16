from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from time import monotonic
from typing import Sequence

from conductor.hand_kinematics import HandKinematicModel, Vector3, build_hand_model


FINGER_TIPS = {
    "index": 8,
    "middle": 12,
    "ring": 16,
    "pinky": 20,
}


@dataclass
class _TapState:
    distance_ratio: float | None = None
    image_distance_ratio: float | None = None
    median_distance_ratio: float | None = None
    distance_history: list[float] = field(default_factory=list)
    active_until: float = 0.0
    last_tap_time: float = 0.0


class FingerTapTracker:
    def __init__(
        self,
        thumb_contact_ratio: float = 0.42,
        thumb_strong_contact_ratio: float = 0.30,
        thumb_release_ratio: float = 0.58,
        active_seconds: float = 0.16,
        minimum_interval: float = 0.18,
        **_legacy_options: float,
    ) -> None:
        self._contact_ratio = thumb_contact_ratio
        self._strong_contact_ratio = thumb_strong_contact_ratio
        self._release_ratio = thumb_release_ratio
        self._active_seconds = active_seconds
        self._minimum_interval = minimum_interval
        self._states: dict[tuple[str, str], _TapState] = {}
        self._models: dict[str, HandKinematicModel] = {}
        self._locked_fingers: dict[str, str | None] = {"left": None, "right": None}
        self._last_seen: dict[str, float] = {}

    def update_hand(
        self,
        handedness: str,
        landmarks: Sequence[object],
        image_landmarks: Sequence[object] | None = None,
    ) -> dict[str, bool]:
        now = monotonic()
        side = handedness.lower()
        try:
            model = build_hand_model(landmarks)
        except ValueError:
            return self._active_for_side(side, now)
        self._models[side] = model

        if now - self._last_seen.get(side, now) > 0.25:
            self._reset_side(side)
        self._last_seen[side] = now

        thumb_tip = model.joints_local_m[4]
        distances = {
            finger: _distance(model.joints_local_m[tip_index], thumb_tip) / model.palm_width_m
            for finger, tip_index in FINGER_TIPS.items()
        }
        if image_landmarks is not None and len(image_landmarks) >= 21:
            image_palm_width = max(_distance_2d(image_landmarks[5], image_landmarks[17]), 1e-4)
            for finger, tip_index in FINGER_TIPS.items():
                image_ratio = _distance_2d(image_landmarks[tip_index], image_landmarks[4]) / image_palm_width
                self._states.setdefault((side, finger), _TapState()).image_distance_ratio = image_ratio
                distances[finger] = distances[finger] * 0.60 + image_ratio * 0.40

        for finger, distance_ratio in distances.items():
            state = self._states.setdefault((side, finger), _TapState())
            state.distance_ratio = distance_ratio
            state.distance_history.append(distance_ratio)
            del state.distance_history[:-3]
            ordered = sorted(state.distance_history)
            state.median_distance_ratio = ordered[len(ordered) // 2]

        locked_finger = self._locked_fingers.get(side)
        if locked_finger is not None:
            locked_state = self._states[(side, locked_finger)]
            if (
                _state_distance(locked_state) >= self._release_ratio
                and _state_median_distance(locked_state) >= self._release_ratio
            ):
                self._locked_fingers[side] = None
            return self._active_for_side(side, now)

        closest_finger = min(
            FINGER_TIPS,
            key=lambda finger: _state_distance(self._states[(side, finger)]),
        )
        candidate = self._states[(side, closest_finger)]
        interval_ok = now - candidate.last_tap_time >= self._minimum_interval
        strong_contact = (
            _state_distance(candidate) <= self._strong_contact_ratio
            or _state_image_distance(candidate) <= self._strong_contact_ratio
        )
        confirmed_contact = (
            len(candidate.distance_history) >= 2
            and _state_median_distance(candidate) <= self._contact_ratio
        )
        if (strong_contact or confirmed_contact) and interval_ok:
            candidate.active_until = now + self._active_seconds
            candidate.last_tap_time = now
            self._locked_fingers[side] = closest_finger

        return self._active_for_side(side, now)

    def active_taps(self) -> dict[str, dict[str, bool]]:
        now = monotonic()
        return {side: self._active_for_side(side, now) for side in ("left", "right")}

    def model_snapshot(self, handedness: str) -> dict[str, object]:
        side = handedness.lower()
        model = self._models.get(side)
        if model is None:
            return {}
        return {
            "origin_world_m": _rounded_vector(model.origin_world_m),
            "axes_world": [_rounded_vector(axis) for axis in model.axes_world],
            "palm_width_m": round(model.palm_width_m, 5),
            "tap_mode": "thumb_contact",
            "fingers": {
                finger: {
                    "tip_local_m": _rounded_vector(data.tip_local_m),
                    "thumb_distance_ratio": round(
                        _state_distance(self._states.get((side, finger), _TapState())),
                        4,
                    ),
                    "thumb_median_distance_ratio": round(
                        _state_median_distance(self._states.get((side, finger), _TapState())),
                        4,
                    ),
                    "contact": _state_distance(
                        self._states.get((side, finger), _TapState())
                    ) <= self._contact_ratio,
                }
                for finger, data in model.fingers.items()
            },
        }

    def _active_for_side(self, side: str, now: float) -> dict[str, bool]:
        return {
            finger: now < self._states.get((side, finger), _TapState()).active_until
            for finger in FINGER_TIPS
        }

    def _reset_side(self, side: str) -> None:
        for finger in FINGER_TIPS:
            self._states.pop((side, finger), None)
        self._locked_fingers[side] = None


def _distance(a: Vector3, b: Vector3) -> float:
    return sqrt(sum((first - second) ** 2 for first, second in zip(a, b)))


def _state_distance(state: _TapState) -> float:
    return state.distance_ratio if state.distance_ratio is not None else float("inf")


def _state_median_distance(state: _TapState) -> float:
    return (
        state.median_distance_ratio
        if state.median_distance_ratio is not None
        else float("inf")
    )


def _state_image_distance(state: _TapState) -> float:
    return (
        state.image_distance_ratio
        if state.image_distance_ratio is not None
        else float("inf")
    )


def _distance_2d(first: object, second: object) -> float:
    x = float(getattr(first, "x", 0.0)) - float(getattr(second, "x", 0.0))
    y = float(getattr(first, "y", 0.0)) - float(getattr(second, "y", 0.0))
    return sqrt(x * x + y * y)


def _rounded_vector(vector: Vector3) -> list[float]:
    return [round(component, 5) for component in vector]
