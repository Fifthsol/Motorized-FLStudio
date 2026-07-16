from __future__ import annotations

import math
import unittest
from types import SimpleNamespace

from conductor.hand_kinematics import build_hand_model
from conductor.taps import FingerTapTracker


def _hand_points() -> list[tuple[float, float, float]]:
    return [
        (0.000, -0.045, 0.000), (0.045, -0.025, 0.000),
        (0.055, -0.005, 0.000), (0.060, 0.015, 0.000),
        (0.062, 0.032, 0.000), (0.035, 0.000, 0.000),
        (0.036, 0.030, 0.000), (0.036, 0.055, 0.000),
        (0.036, 0.078, 0.000), (0.012, 0.008, 0.000),
        (0.012, 0.043, 0.000), (0.012, 0.072, 0.000),
        (0.012, 0.098, 0.000), (-0.012, 0.007, 0.000),
        (-0.012, 0.039, 0.000), (-0.012, 0.064, 0.000),
        (-0.012, 0.086, 0.000), (-0.035, 0.000, 0.000),
        (-0.036, 0.026, 0.000), (-0.036, 0.047, 0.000),
        (-0.036, 0.065, 0.000),
    ]


def _transform(
    points: list[tuple[float, float, float]],
    angle_x: float = 0.0,
    angle_y: float = 0.0,
    angle_z: float = 0.0,
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> list[SimpleNamespace]:
    cx, sx = math.cos(angle_x), math.sin(angle_x)
    cy, sy = math.cos(angle_y), math.sin(angle_y)
    cz, sz = math.cos(angle_z), math.sin(angle_z)
    output: list[SimpleNamespace] = []
    for x, y, z in points:
        y, z = y * cx - z * sx, y * sx + z * cx
        x, z = x * cy + z * sy, -x * sy + z * cy
        x, y = x * cz - y * sz, x * sz + y * cz
        output.append(SimpleNamespace(
            x=x + translation[0], y=y + translation[1], z=z + translation[2]
        ))
    return output


def _touch_thumb(
    points: list[tuple[float, float, float]],
    tip_index: int,
    offset: tuple[float, float, float] = (0.004, 0.0, 0.0),
) -> list[tuple[float, float, float]]:
    touched = list(points)
    thumb = points[4]
    touched[tip_index] = tuple(value + delta for value, delta in zip(thumb, offset))
    return touched


def _prime(tracker: FingerTapTracker, points: list[tuple[float, float, float]]) -> None:
    for _ in range(5):
        tracker.update_hand("left", _transform(points))


class HandKinematicsTests(unittest.TestCase):
    def test_local_joint_model_is_rigid_transform_invariant(self) -> None:
        points = _hand_points()
        base = build_hand_model(_transform(points))
        moved = build_hand_model(_transform(
            points, angle_x=0.8, angle_y=-0.6, angle_z=1.1,
            translation=(0.4, -0.2, 0.7),
        ))
        for base_joint, moved_joint in zip(base.joints_local_m, moved.joints_local_m):
            for base_value, moved_value in zip(base_joint, moved_joint):
                self.assertAlmostEqual(base_value, moved_value, places=6)

    def test_index_thumb_contact_fires_only_index(self) -> None:
        points = _hand_points()
        tracker = FingerTapTracker(minimum_interval=0.0)
        _prime(tracker, points)
        touched = _touch_thumb(points, 8)
        active = tracker.update_hand("left", _transform(touched))
        self.assertTrue(active["index"])
        self.assertFalse(any(active[finger] for finger in ("middle", "ring", "pinky")))

    def test_borderline_contact_requires_two_samples(self) -> None:
        points = _hand_points()
        tracker = FingerTapTracker(minimum_interval=0.0)
        _prime(tracker, points)
        borderline = _touch_thumb(points, 8, (0.025, 0.0, 0.0))

        first = tracker.update_hand("left", _transform(borderline))
        second = tracker.update_hand("left", _transform(borderline))

        self.assertFalse(first["index"])
        self.assertTrue(second["index"])

    def test_single_borderline_landmark_jump_does_not_fire(self) -> None:
        points = _hand_points()
        tracker = FingerTapTracker(minimum_interval=0.0)
        _prime(tracker, points)
        borderline = _touch_thumb(points, 8, (0.025, 0.0, 0.0))

        first = tracker.update_hand("left", _transform(borderline))
        second = tracker.update_hand("left", _transform(points))

        self.assertFalse(first["index"])
        self.assertFalse(second["index"])

    def test_fast_2d_contact_fires_when_3d_landmarks_lag(self) -> None:
        points = _hand_points()
        tracker = FingerTapTracker(minimum_interval=0.0)
        _prime(tracker, points)
        image_contact = _touch_thumb(points, 8)

        active = tracker.update_hand(
            "left",
            _transform(points),
            image_landmarks=_transform(image_contact),
        )

        self.assertTrue(active["index"])

    def test_closest_fingertip_wins_when_two_are_near_thumb(self) -> None:
        points = _hand_points()
        tracker = FingerTapTracker(minimum_interval=0.0)
        _prime(tracker, points)
        touched = _touch_thumb(points, 8, (0.003, 0.0, 0.0))
        thumb = points[4]
        touched[12] = (thumb[0] - 0.014, thumb[1], thumb[2])
        for _ in range(4):
            active = tracker.update_hand("left", _transform(touched))
        self.assertTrue(active["index"])
        self.assertFalse(active["middle"])

    def test_contact_must_release_before_firing_again(self) -> None:
        points = _hand_points()
        tracker = FingerTapTracker(minimum_interval=0.0)
        _prime(tracker, points)
        touched = _touch_thumb(points, 8)
        for _ in range(4):
            tracker.update_hand("left", _transform(touched))
        for _ in range(6):
            active = tracker.update_hand("left", _transform(touched))
            self.assertFalse(active["middle"])
        for _ in range(5):
            tracker.update_hand("left", _transform(points))
        for _ in range(4):
            active = tracker.update_hand("left", _transform(touched))
        self.assertTrue(active["index"])

    def test_stationary_landmark_jitter_does_not_trigger(self) -> None:
        points = _hand_points()
        tracker = FingerTapTracker(minimum_interval=0.0)
        for frame in range(120):
            jittered = list(points)
            for number, tip_index in enumerate((4, 8, 12, 16, 20), start=1):
                x, y, z = jittered[tip_index]
                jittered[tip_index] = (
                    x + math.sin(frame * 1.7 + number) * 0.0025,
                    y + math.sin(frame * 1.1 + number) * 0.0020,
                    z + math.cos(frame * 1.4 + number) * 0.0025,
                )
            active = tracker.update_hand("left", _transform(jittered))
            self.assertFalse(any(active.values()))


if __name__ == "__main__":
    unittest.main()
