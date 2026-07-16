from __future__ import annotations

import unittest

from conductor.app import _tap_events, _tap_outputs


class TapMappingTests(unittest.TestCase):
    def test_each_left_finger_maps_to_matching_stepper(self) -> None:
        config = {"tap_stepper_speed": 450, "tap_servo_angle": 150}
        fingers = ("index", "middle", "ring", "pinky")
        for channel, finger in enumerate(fingers):
            taps = {"left": {finger: True}, "right": {}}
            servos, steppers = _tap_outputs([90.0] * 4, [0.0] * 4, taps, config)
            self.assertEqual(steppers[channel], 450)
            self.assertEqual(servos, [90.0] * 4)
            self.assertEqual(_tap_events(taps), [{
                "hand": "left", "finger": finger,
                "actuator": "stepper", "channel": channel,
            }])

    def test_each_right_finger_maps_to_matching_servo(self) -> None:
        config = {"tap_stepper_speed": 450, "tap_servo_angle": 150}
        fingers = ("index", "middle", "ring", "pinky")
        for channel, finger in enumerate(fingers):
            taps = {"left": {}, "right": {finger: True}}
            servos, steppers = _tap_outputs([90.0] * 4, [0.0] * 4, taps, config)
            self.assertEqual(servos[channel], 150)
            self.assertEqual(steppers, [0.0] * 4)
            self.assertEqual(_tap_events(taps), [{
                "hand": "right", "finger": finger,
                "actuator": "servo", "channel": channel,
            }])


if __name__ == "__main__":
    unittest.main()
