from __future__ import annotations

import json
import unittest

from conductor.hardware import MotorCommand
from conductor.partner_serial import encode_serial_command


class PartnerSerialTests(unittest.TestCase):
    def test_serial_packet_contains_motor_values_and_tap_identity(self) -> None:
        command = MotorCommand(
            gesture="right:open_palm",
            confidence=0.9,
            servo_angles=[90.0, 90.0, 150.0, 90.0],
            stepper_speeds=[0.0, 0.0, 0.0, 0.0],
            metadata={"tap_events": [{
                "hand": "right",
                "finger": "ring",
                "actuator": "servo",
                "channel": 2,
            }]},
        )

        encoded = encode_serial_command(command)
        payload = json.loads(encoded.decode("utf-8"))

        self.assertTrue(encoded.endswith(b"\n"))
        self.assertEqual(payload["servos"], [90.0, 90.0, 150.0, 90.0])
        self.assertEqual(payload["steppers"], [0.0, 0.0, 0.0, 0.0])
        self.assertEqual(payload["tap_events"][0]["finger"], "ring")
        self.assertEqual(payload["tap_events"][0]["channel"], 2)


if __name__ == "__main__":
    unittest.main()
