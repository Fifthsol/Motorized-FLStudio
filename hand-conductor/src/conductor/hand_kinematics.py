from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable, Sequence


Vector3 = tuple[float, float, float]

FINGER_JOINTS = {
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}


@dataclass(frozen=True)
class FingerKinematics:
    tip_local_m: Vector3
    tip_from_mcp_m: Vector3
    curl: float


@dataclass(frozen=True)
class HandKinematicModel:
    origin_world_m: Vector3
    axes_world: tuple[Vector3, Vector3, Vector3]
    palm_width_m: float
    joints_local_m: tuple[Vector3, ...]
    fingers: dict[str, FingerKinematics]


def build_hand_model(landmarks: Sequence[object]) -> HandKinematicModel:
    world = tuple(_point(landmark) for landmark in landmarks)
    if len(world) < 21:
        raise ValueError("A hand model requires all 21 MediaPipe landmarks")

    palm_indices = (0, 5, 9, 13, 17)
    origin = _average(world[index] for index in palm_indices)
    across = _normalize(_subtract(world[5], world[17]))
    knuckle_center = _average(world[index] for index in (5, 9, 13, 17))
    forward_seed = _subtract(knuckle_center, world[0])
    forward = _normalize(_subtract(forward_seed, _scale(across, _dot(forward_seed, across))))
    normal = _normalize(_cross(across, forward))
    forward = _normalize(_cross(normal, across))

    joints_local = tuple(_to_local(point, origin, across, forward, normal) for point in world)
    palm_width = max(_distance(world[5], world[17]), 1e-4)
    fingers: dict[str, FingerKinematics] = {}
    for finger, indices in FINGER_JOINTS.items():
        mcp, pip, dip, tip = (joints_local[index] for index in indices)
        chain_length = _distance(mcp, pip) + _distance(pip, dip) + _distance(dip, tip)
        direct_length = _distance(mcp, tip)
        curl = 1.0 - min(direct_length / max(chain_length, 1e-6), 1.0)
        fingers[finger] = FingerKinematics(
            tip_local_m=tip,
            tip_from_mcp_m=_subtract(tip, mcp),
            curl=curl,
        )

    return HandKinematicModel(
        origin_world_m=origin,
        axes_world=(across, forward, normal),
        palm_width_m=palm_width,
        joints_local_m=joints_local,
        fingers=fingers,
    )


def _to_local(point: Vector3, origin: Vector3, across: Vector3, forward: Vector3, normal: Vector3) -> Vector3:
    relative = _subtract(point, origin)
    return (_dot(relative, across), _dot(relative, forward), _dot(relative, normal))


def _point(landmark: object) -> Vector3:
    return (
        float(getattr(landmark, "x", 0.0) or 0.0),
        float(getattr(landmark, "y", 0.0) or 0.0),
        float(getattr(landmark, "z", 0.0) or 0.0),
    )


def _average(points: Iterable[Vector3]) -> Vector3:
    values = tuple(points)
    return tuple(sum(point[index] for point in values) / len(values) for index in range(3))


def _subtract(a: Vector3, b: Vector3) -> Vector3:
    return tuple(first - second for first, second in zip(a, b))


def _scale(vector: Vector3, amount: float) -> Vector3:
    return tuple(component * amount for component in vector)


def _dot(a: Vector3, b: Vector3) -> float:
    return sum(first * second for first, second in zip(a, b))


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(vector: Vector3) -> float:
    return sqrt(_dot(vector, vector))


def _normalize(vector: Vector3) -> Vector3:
    length = _length(vector)
    if length < 1e-7:
        raise ValueError("Degenerate palm landmarks cannot define a hand orientation")
    return tuple(component / length for component in vector)


def _distance(a: Vector3, b: Vector3) -> float:
    return _length(_subtract(a, b))
