from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from conductor.partner_serial import PartnerSerialDriver


@dataclass(frozen=True)
class MotorCommand:
    gesture: str
    confidence: float
    servo_angles: list[float] = field(default_factory=lambda: [90.0, 90.0, 90.0, 90.0])
    stepper_speeds: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    metadata: dict[str, Any] = field(default_factory=dict)


class HardwareDriver(Protocol):
    def send(self, command: MotorCommand) -> None:
        ...

    def close(self) -> None:
        ...


class ConsoleHardwareDriver:
    def send(self, command: MotorCommand) -> None:
        tap_events = command.metadata.get("tap_events", [])
        tap_text = ",".join(
            f"{event['hand']}:{event['finger']}->{event['actuator']}{event['channel']}"
            for event in tap_events
        ) or "none"
        print(
            "gesture={gesture} confidence={confidence:.2f} taps={taps} servos={servos} steppers={steppers}".format(
                gesture=command.gesture,
                confidence=command.confidence,
                taps=tap_text,
                servos=[round(value, 1) for value in command.servo_angles],
                steppers=[round(value, 1) for value in command.stepper_speeds],
            )
        )

    def close(self) -> None:
        pass


class SerialJsonHardwareDriver(PartnerSerialDriver):
    """Compatibility name used by the app; implementation is partner_serial.py."""
