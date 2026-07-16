from __future__ import annotations

import argparse
import json
import ssl
import subprocess
import sys
import time
from collections import deque
from math import ceil
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import cv2
import mediapipe as mp

from conductor.gestures import GestureTracker, HandGesture
from conductor.hardware import ConsoleHardwareDriver, HardwareDriver, MotorCommand, SerialJsonHardwareDriver
from conductor.taps import FINGER_TIPS, FingerTapTracker


MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
    "gesture_recognizer/float16/latest/gesture_recognizer.task"
)
HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
)

FINGER_CHANNELS = {
    "index": 0,
    "middle": 1,
    "ring": 2,
    "pinky": 3,
}


class SixSevenDetector:
    def __init__(
        self,
        velocity_threshold: float = 0.25,
        display_seconds: float = 1.5,
        cooldown_seconds: float = 60.0,
        open_palm_window_frames: int = 24,
        open_palm_ratio: float = 0.70,
        easy_velocity_threshold: float = 0.10,
    ) -> None:
        self._velocity_threshold = velocity_threshold
        self._display_seconds = display_seconds
        self._cooldown_seconds = cooldown_seconds
        self._open_palm_window_frames = open_palm_window_frames
        self._open_palm_ratio = open_palm_ratio
        self._easy_velocity_threshold = easy_velocity_threshold
        self._visible_until = 0.0
        self._cooldown_until = 0.0
        self._was_active = False
        self._triggered = False
        self._enabled = True
        self._easy_mode = False
        self._open_palm_history = {
            "left": deque(maxlen=open_palm_window_frames),
            "right": deque(maxlen=open_palm_window_frames),
        }
        self._motion_directions = {"left": set(), "right": set()}

    def update(self, command: MotorCommand | None) -> bool:
        now = time.monotonic()
        if not self._enabled:
            self._was_active = False
            return False
        hands = command.metadata.get("hands", []) if command else []
        hands_by_side = {
            str(hand.get("handedness", "")).lower(): hand
            for hand in hands
            if str(hand.get("handedness", "")).lower() in ("left", "right")
        }
        for side in ("left", "right"):
            hand = hands_by_side.get(side)
            self._open_palm_history[side].append(bool(hand and hand.get("gesture") == "open_palm"))

        if self._easy_mode:
            both_open = all(
                hands_by_side.get(side, {}).get("gesture") == "open_palm"
                for side in ("left", "right")
            )
            both_moving = all(
                abs(float(hands_by_side.get(side, {}).get("vertical_velocity", 0.0)))
                >= self._easy_velocity_threshold
                for side in ("left", "right")
            )
            active = both_open and both_moving
            if active and not self._was_active and now >= self._cooldown_until:
                self._triggered = True
                self._visible_until = now + self._display_seconds
                self._cooldown_until = now + self._cooldown_seconds
            self._was_active = active
            return now < self._visible_until

        minimum_samples = max(8, self._open_palm_window_frames // 2)
        palms_qualified = all(
            len(self._open_palm_history[side]) >= minimum_samples
            and sum(self._open_palm_history[side]) / len(self._open_palm_history[side]) >= self._open_palm_ratio
            for side in ("left", "right")
        )

        active = False
        if palms_qualified:
            for side in ("left", "right"):
                hand = hands_by_side.get(side)
                if not hand or hand.get("gesture") != "open_palm":
                    continue
                velocity = float(hand.get("vertical_velocity", 0.0))
                if velocity >= self._velocity_threshold:
                    self._motion_directions[side].add("up")
                elif velocity <= -self._velocity_threshold:
                    self._motion_directions[side].add("down")
            active = all(
                self._motion_directions[side] == {"up", "down"}
                for side in ("left", "right")
            )
        else:
            self._clear_motion()
        if active and not self._was_active and now >= self._cooldown_until:
            self._triggered = True
            self._visible_until = now + self._display_seconds
            self._cooldown_until = now + self._cooldown_seconds
        self._was_active = active
        return now < self._visible_until

    def consume_trigger(self) -> bool:
        triggered = self._triggered
        self._triggered = False
        return triggered

    def reset_cooldown(self) -> None:
        self._cooldown_until = 0.0
        self._was_active = False
        self._clear_motion()

    def toggle(self) -> bool:
        self._enabled = not self._enabled
        self._was_active = False
        self._clear_motion()
        if not self._enabled:
            for history in self._open_palm_history.values():
                history.clear()
        return self._enabled

    def toggle_easy_mode(self) -> bool:
        self._easy_mode = not self._easy_mode
        self._was_active = False
        self._clear_motion()
        return self._easy_mode

    @property
    def enabled(self) -> bool:
        return self._enabled

    def cooldown_remaining(self) -> int:
        return max(0, ceil(self._cooldown_until - time.monotonic()))

    def _clear_motion(self) -> None:
        for directions in self._motion_directions.values():
            directions.clear()


class SixSevenPopupController:
    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None

    def show(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        popup_path = Path(__file__).with_name("six_seven_popup.py")
        self._process = subprocess.Popen([sys.executable, str(popup_path)])

    def close(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
        self._process = None


def main() -> None:
    args = _parse_args()
    config = _load_config(args.config)
    model_path = Path(args.model)
    _ensure_model(model_path)

    driver = _make_driver(args, config)
    capture = cv2.VideoCapture(args.camera)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open camera index {args.camera}")
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    capture.set(cv2.CAP_PROP_FPS, 60)

    tracker = GestureTracker()
    tap_tracker = FingerTapTracker(
        thumb_contact_ratio=float(config["tap_thumb_contact_ratio"]),
        thumb_strong_contact_ratio=float(config["tap_thumb_strong_contact_ratio"]),
        thumb_release_ratio=float(config["tap_thumb_release_ratio"]),
        active_seconds=float(config["tap_active_seconds"]),
        minimum_interval=float(config["tap_minimum_interval"]),
    )
    six_seven_detector = SixSevenDetector(
        velocity_threshold=float(config["six_seven_velocity_threshold"]),
        display_seconds=float(config["six_seven_display_seconds"]),
        cooldown_seconds=float(config["six_seven_cooldown_seconds"]),
        open_palm_window_frames=int(config["six_seven_open_palm_window_frames"]),
        open_palm_ratio=float(config["six_seven_open_palm_ratio"]),
        easy_velocity_threshold=float(config["six_seven_easy_velocity_threshold"]),
    )
    six_seven_popup = SixSevenPopupController()
    last_command_time = 0.0

    BaseOptions = mp.tasks.BaseOptions
    GestureRecognizer = mp.tasks.vision.GestureRecognizer
    GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    options = GestureRecognizerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        running_mode=VisionRunningMode.VIDEO,
        num_hands=args.max_hands,
        min_hand_detection_confidence=args.min_detection_confidence,
        min_hand_presence_confidence=args.min_presence_confidence,
        min_tracking_confidence=args.min_tracking_confidence,
    )

    try:
        with GestureRecognizer.create_from_options(options) as recognizer:
            while True:
                ok, frame_bgr = capture.read()
                if not ok:
                    break

                frame_bgr = cv2.flip(frame_bgr, 1)
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                timestamp_ms = int(time.monotonic() * 1000)
                result = recognizer.recognize_for_video(mp_image, timestamp_ms)

                command = _command_from_result(result, tracker, tap_tracker, config)
                show_six_seven = six_seven_detector.update(command)
                if six_seven_detector.consume_trigger():
                    six_seven_popup.show()
                now = time.monotonic()
                if command and now - last_command_time >= float(config["min_command_interval_s"]):
                    driver.send(command)
                    last_command_time = now

                if not args.no_preview:
                    _draw_result(
                        frame_bgr,
                        result,
                        command,
                        show_six_seven,
                        six_seven_detector.enabled,
                        six_seven_detector.cooldown_remaining(),
                    )
                    cv2.imshow("Hand Conductor - press q to quit", frame_bgr)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
                    if key in (ord("r"), ord("R")):
                        six_seven_detector.reset_cooldown()
                        print("67 popup cooldown reset")
                    if key in (ord("t"), ord("T")):
                        enabled = six_seven_detector.toggle()
                        if not enabled:
                            six_seven_popup.close()
                    if key in (ord("y"), ord("Y")):
                        easy_mode = six_seven_detector.toggle_easy_mode()
                        print(f"67 easy mode {'enabled' if easy_mode else 'disabled'}")
    finally:
        capture.release()
        driver.close()
        six_seven_popup.close()
        cv2.destroyAllWindows()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hand tracking conductor for 4 servos and 4 steppers.")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--model", default="models/gesture_recognizer.task")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--max-hands", type=int, default=2)
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument(
        "--bridge",
        action="store_true",
        help="Send tap events to the project's Python serial bridge over UDP instead of printing to console.",
    )
    parser.add_argument("--bridge-host", default="127.0.0.1")
    parser.add_argument("--bridge-port", type=int, default=9002)
    parser.add_argument("--min-detection-confidence", type=float, default=0.50)
    parser.add_argument("--min-presence-confidence", type=float, default=0.50)
    parser.add_argument("--min-tracking-confidence", type=float, default=0.40)
    return parser.parse_args()


def _load_config(path: str) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "min_command_interval_s": 0.08,
        "servo_min_angle": 0,
        "servo_max_angle": 180,
        "stepper_max_speed": 600,
        "six_seven_velocity_threshold": 0.25,
        "six_seven_display_seconds": 1.5,
        "six_seven_cooldown_seconds": 60,
        "six_seven_open_palm_window_frames": 24,
        "six_seven_open_palm_ratio": 0.70,
        "six_seven_easy_velocity_threshold": 0.10,
        "tap_thumb_contact_ratio": 0.42,
        "tap_thumb_strong_contact_ratio": 0.30,
        "tap_thumb_release_ratio": 0.58,
        "tap_active_seconds": 0.16,
        "tap_minimum_interval": 0.18,
        "tap_stepper_speed": 450,
        "tap_servo_angle": 150,
    }
    config_path = Path(path)
    if not config_path.exists():
        return defaults
    with config_path.open("r", encoding="utf-8") as file:
        loaded = json.load(file)
    return {**defaults, **loaded}


def _ensure_model(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading MediaPipe model to {path}...")
    _download_file(MODEL_URL, path)


def _download_file(url: str, path: Path) -> None:
    try:
        _download_file_with_context(url, path, context=None)
    except URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        print("Python SSL certificate verification failed; retrying model download without cert verification.")
        _download_file_with_context(url, path, context=ssl._create_unverified_context())


def _download_file_with_context(url: str, path: Path, context: ssl.SSLContext | None) -> None:
    with urlopen(url, context=context) as response:
        path.write_bytes(response.read())


def _make_driver(args: argparse.Namespace, config: dict[str, Any]) -> HardwareDriver:
    if args.bridge:
        frequencies = config.get("tap_stepper_frequencies")
        return SerialJsonHardwareDriver(args.bridge_host, args.bridge_port, frequencies)
    return ConsoleHardwareDriver()


def _command_from_result(
    result: Any,
    tracker: GestureTracker,
    tap_tracker: FingerTapTracker,
    config: dict[str, Any],
) -> MotorCommand | None:
    if not result.hand_landmarks:
        taps = tap_tracker.active_taps()
        servo_angles, stepper_speeds = _tap_outputs(
            [90.0, 90.0, 90.0, 90.0],
            [0.0, 0.0, 0.0, 0.0],
            taps,
            config,
        )
        return MotorCommand(
            gesture="none",
            confidence=0.0,
            servo_angles=servo_angles,
            stepper_speeds=stepper_speeds,
            metadata={"hands": [], "finger_taps": taps, "tap_events": _tap_events(taps)},
        )

    servo_angles = [90.0, 90.0, 90.0, 90.0]
    stepper_speeds = [0.0, 0.0, 0.0, 0.0]
    hands: list[dict[str, Any]] = []
    gestures: list[HandGesture] = []

    selected_by_side: dict[str, tuple[int, Any, str, float]] = {}
    for index, landmarks in enumerate(result.hand_landmarks):
        handedness = (
            result.handedness[index][0].category_name
            if result.handedness and index < len(result.handedness) and result.handedness[index]
            else ("Left" if index == 0 else "Right")
        )
        side = handedness.lower()
        if side not in ("left", "right"):
            continue
        handedness_score = (
            float(getattr(result.handedness[index][0], "score", 0.0))
            if result.handedness and index < len(result.handedness) and result.handedness[index]
            else 0.0
        )
        current = selected_by_side.get(side)
        if current is None or handedness_score > current[3]:
            selected_by_side[side] = (index, landmarks, handedness, handedness_score)

    for index, landmarks, handedness, _ in sorted(selected_by_side.values(), key=lambda item: item[0]):
        model_gesture_name = None
        model_gesture_confidence = 0.0
        model_gestures = getattr(result, "gestures", [])
        if index < len(model_gestures) and model_gestures[index]:
            model_gesture = model_gestures[index][0]
            model_gesture_name = model_gesture.category_name
            model_gesture_confidence = float(model_gesture.score)
        geometry_landmarks = (
            result.hand_world_landmarks[index]
            if getattr(result, "hand_world_landmarks", None)
            and index < len(result.hand_world_landmarks)
            else landmarks
        )
        gesture = tracker.classify(
            landmarks,
            handedness,
            track_id=handedness.lower(),
            model_gesture=model_gesture_name,
            model_confidence=model_gesture_confidence,
            geometry_landmarks=geometry_landmarks,
        )
        hand_taps = tap_tracker.update_hand(
            handedness,
            geometry_landmarks,
            image_landmarks=landmarks,
        )
        gestures.append(gesture)
        pair_start = 0 if handedness.lower() == "left" else 2
        hand_servos = _servo_targets(gesture, config)
        hand_steppers = _stepper_targets(gesture, config)

        if gesture.name != "fist":
            servo_angles[pair_start:pair_start + 2] = hand_servos[:2]
            stepper_speeds[pair_start:pair_start + 2] = hand_steppers[:2]

        hands.append({
            "landmark_index": index,
            "handedness": handedness,
            "gesture": gesture.name,
            "confidence": round(gesture.confidence, 4),
            "center_x": round(gesture.center_x, 4),
            "center_y": round(gesture.center_y, 4),
            "openness": round(gesture.openness, 4),
            "pinch_distance": round(gesture.pinch_distance, 4),
            "vertical_velocity": round(gesture.vertical_velocity, 4),
            "extended_fingers": list(gesture.extended_fingers),
            "taps": hand_taps,
            "kinematics": tap_tracker.model_snapshot(handedness),
        })

    if not gestures:
        taps = tap_tracker.active_taps()
        servo_angles, stepper_speeds = _tap_outputs(servo_angles, stepper_speeds, taps, config)
        return MotorCommand(
            gesture="none",
            confidence=0.0,
            servo_angles=servo_angles,
            stepper_speeds=stepper_speeds,
            metadata={"hands": [], "finger_taps": taps, "tap_events": _tap_events(taps)},
        )

    taps = tap_tracker.active_taps()
    servo_angles, stepper_speeds = _tap_outputs(servo_angles, stepper_speeds, taps, config)
    gesture_label = " + ".join(f"{hand['handedness']}:{hand['gesture']}" for hand in hands)

    return MotorCommand(
        gesture=gesture_label,
        confidence=sum(gesture.confidence for gesture in gestures) / len(gestures),
        servo_angles=servo_angles,
        stepper_speeds=stepper_speeds,
        metadata={"hands": hands, "finger_taps": taps, "tap_events": _tap_events(taps)},
    )


def _tap_outputs(
    servo_angles: list[float],
    stepper_speeds: list[float],
    taps: dict[str, dict[str, bool]],
    config: dict[str, Any],
) -> tuple[list[float], list[float]]:
    stepper_speed = float(config["tap_stepper_speed"])
    servo_angle = float(config["tap_servo_angle"])
    for finger, channel in FINGER_CHANNELS.items():
        if taps.get("left", {}).get(finger, False):
            stepper_speeds[channel] = stepper_speed
        if taps.get("right", {}).get(finger, False):
            servo_angles[channel] = servo_angle
    return servo_angles, stepper_speeds


def _tap_events(taps: dict[str, dict[str, bool]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for handedness, actuator in (("left", "stepper"), ("right", "servo")):
        for finger, channel in FINGER_CHANNELS.items():
            if taps.get(handedness, {}).get(finger, False):
                events.append({
                    "hand": handedness,
                    "finger": finger,
                    "actuator": actuator,
                    "channel": channel,
                })
    return events


def _servo_targets(gesture: HandGesture, config: dict[str, Any]) -> list[float]:
    low = float(config["servo_min_angle"])
    high = float(config["servo_max_angle"])
    pitch = _map_range(1.0 - gesture.center_y, 0.0, 1.0, low, high)
    pan = _map_range(gesture.center_x, 0.0, 1.0, low, high)
    openness = _map_range(gesture.openness, 0.0, 1.0, low, high)
    accent = high if gesture.name == "pinch" else low
    return [_clamp(pitch, low, high), _clamp(pan, low, high), _clamp(openness, low, high), accent]


def _stepper_targets(gesture: HandGesture, config: dict[str, Any]) -> list[float]:
    max_speed = float(config["stepper_max_speed"])
    tempo_motion = _clamp(gesture.vertical_velocity * max_speed, -max_speed, max_speed)

    if gesture.name == "peace":
        return [max_speed * 0.25, -max_speed * 0.25, max_speed * 0.25, -max_speed * 0.25]
    if gesture.name == "open_palm":
        speed = _map_range(gesture.center_x, 0.0, 1.0, -max_speed * 0.5, max_speed * 0.5)
        return [speed, speed, speed, speed]
    if gesture.name == "pinch":
        return [max_speed * 0.5, 0.0, max_speed * 0.5, 0.0]
    if gesture.name == "thumbs_up":
        return [max_speed * 0.35, max_speed * 0.35, max_speed * 0.35, max_speed * 0.35]
    return [0.0, 0.0, 0.0, 0.0]


def _draw_result(
    frame_bgr: Any,
    result: Any,
    command: MotorCommand | None,
    show_six_seven: bool = False,
    feature_enabled: bool = True,
    cooldown_remaining: int = 0,
) -> None:
    height, width = frame_bgr.shape[:2]
    hands_metadata = command.metadata.get("hands", []) if command else []
    hands_by_landmark_index = {
        int(hand.get("landmark_index", index)): hand
        for index, hand in enumerate(hands_metadata)
    }
    for index, landmarks in enumerate(result.hand_landmarks):
        if index not in hands_by_landmark_index:
            continue
        points = [(int(point.x * width), int(point.y * height)) for point in landmarks]
        for start, end in HAND_CONNECTIONS:
            cv2.line(frame_bgr, points[start], points[end], (50, 220, 120), 2)
        for point in points:
            cv2.circle(frame_bgr, point, 4, (40, 140, 255), -1)

        hand = hands_by_landmark_index.get(index)
        if hand:
            hand_label = f"{hand['handedness']}: {hand['gesture']}"
            label_y = max(24, min(point[1] for point in points) - 12)
            label_x = max(8, min(point[0] for point in points))
            cv2.putText(frame_bgr, hand_label, (label_x, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
            cv2.circle(frame_bgr, points[4], 10, (255, 180, 0), -1, cv2.LINE_AA)
            cv2.circle(frame_bgr, points[4], 12, (255, 255, 255), 2, cv2.LINE_AA)
            for finger, tip_index in FINGER_TIPS.items():
                tip = points[tip_index]
                if hand.get("taps", {}).get(finger, False):
                    cv2.circle(frame_bgr, tip, 12, (0, 0, 255), -1, cv2.LINE_AA)
                    cv2.circle(frame_bgr, tip, 14, (255, 255, 255), 2, cv2.LINE_AA)
                else:
                    cv2.circle(frame_bgr, tip, 8, (0, 255, 255), -1, cv2.LINE_AA)
                    cv2.circle(frame_bgr, tip, 10, (0, 0, 0), 2, cv2.LINE_AA)

    label = "gesture=none"
    if command:
        label = f"{command.gesture}  servos={','.join(str(round(v)) for v in command.servo_angles)}"
    cv2.putText(frame_bgr, label, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)

    status = "ENABLED" if feature_enabled else "DISABLED"
    status_color = (80, 220, 120) if feature_enabled else (120, 120, 255)
    cv2.putText(frame_bgr, status, (width - 150, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)
    if cooldown_remaining > 0:
        timer = str(cooldown_remaining)
        cv2.putText(frame_bgr, timer, (width - 58, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    if show_six_seven:
        text = "67"
        font = cv2.FONT_HERSHEY_DUPLEX
        scale = max(3.0, min(width, height) / 150.0)
        thickness = max(6, int(scale * 2))
        (text_width, text_height), _ = cv2.getTextSize(text, font, scale, thickness)
        origin = ((width - text_width) // 2, (height + text_height) // 2)
        cv2.putText(frame_bgr, text, origin, font, scale, (0, 0, 0), thickness + 6, cv2.LINE_AA)
        cv2.putText(frame_bgr, text, origin, font, scale, (0, 255, 255), thickness, cv2.LINE_AA)


def _map_range(value: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
    value = _clamp(value, in_min, in_max)
    return out_min + (value - in_min) * (out_max - out_min) / (in_max - in_min)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


if __name__ == "__main__":
    main()
