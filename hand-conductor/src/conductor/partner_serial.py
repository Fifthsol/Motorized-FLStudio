"""Sends motor commands to the project's existing Python serial bridge over UDP.

Rewritten from the original direct-pyserial placeholder: rather than opening
its own COM port (which would conflict with the bridge script that already
owns both Arduino connections), this sends the same "INPUT:"/"OUTPUT:"
prefixed text commands the bridge already accepts from Godot on port 9002.
The bridge itself needs no changes - it doesn't care which process sent the
UDP packet.

Channel mapping (from the tap_events the vision side already produces):
  Left hand taps  (stepper channels 0-3) -> motors 1-4 on the Output Arduino
  Right hand taps (servo channels 0-3)   -> servos 1-4 on the Input Arduino

Each channel's rising edge (tap starts) sends a "note on" command; the
falling edge (finger separates) sends "note off". This means a quick tap
plays a short note, and holding contact sustains it - matches how the
tracker already reports tap state per frame.
"""

from __future__ import annotations

import socket
from typing import Any, Protocol


# Musical mapping for the 4 stepper channels - reuses the same pentatonic
# set as the rest of the instrument (C4, D4, F4, G4) so this stays in tune
# with everything else. Override per-channel in config.json under
# "tap_stepper_frequencies" if you want different notes.
DEFAULT_STEPPER_FREQUENCIES = [261.63, 293.66, 349.23, 392.00]

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 9002

# Godot's HardwareInput listener already understands "BTN,<id>,1/0" packets -
# that's the same format the physical Input Arduino's buttons send. Sending
# it straight to Godot here means a hand tap shows up in Godot's on-screen
# visualization exactly like a physical button press, with no new Godot-side
# parsing needed.
GODOT_HOST = "127.0.0.1"
GODOT_PORT = 9001


class MotorCommandLike(Protocol):
    gesture: str
    confidence: float
    servo_angles: list[float]
    stepper_speeds: list[float]
    metadata: dict[str, Any]


def build_serial_payload(command: MotorCommandLike) -> dict[str, Any]:
    """Kept for debug/logging purposes - not what actually gets sent anymore.
    See PartnerSerialDriver.send() for the real bridge commands."""
    return {
        "type": "motor_command",
        "servos": [round(value, 1) for value in command.servo_angles],
        "steppers": [round(value, 1) for value in command.stepper_speeds],
        "tap_events": command.metadata.get("tap_events", []),
        "gesture": command.gesture,
    }


def encode_serial_command(command: MotorCommandLike) -> bytes:
    """Kept for debug/logging and test compatibility - not what actually
    gets sent to hardware anymore. See PartnerSerialDriver.send()."""
    import json

    payload = build_serial_payload(command)
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


class PartnerSerialDriver:
    """Sends tap-triggered motor/servo commands to the local bridge over UDP.

    Tracks each channel's previous active state so it can detect rising
    edges (tap started -> note/servo on) and falling edges (tap released
    -> note/servo off) from the tap_events metadata each frame provides.
    """

    def __init__(
        self,
        bridge_host: str = BRIDGE_HOST,
        bridge_port: int = BRIDGE_PORT,
        stepper_frequencies: list[float] | None = None,
    ) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._bridge_address = (bridge_host, bridge_port)
        self._stepper_frequencies = stepper_frequencies or DEFAULT_STEPPER_FREQUENCIES

        # Tracks which channels were active on the previous frame, so we can
        # detect edges rather than re-sending the same command every frame.
        self._stepper_active = [False, False, False, False]
        self._servo_active = [False, False, False, False]

    def _send_bridge_command(self, target: str, payload: str) -> None:
        message = f"{target}:{payload}".encode("utf-8")
        self._socket.sendto(message, self._bridge_address)

    def _notify_godot(self, payload: str) -> None:
        # No target prefix here - this goes straight to Godot's listener,
        # not through the bridge's routing.
        self._socket.sendto(payload.encode("utf-8"), (GODOT_HOST, GODOT_PORT))

    def send(self, command: MotorCommandLike) -> None:
        tap_events = command.metadata.get("tap_events", [])

        # Figure out which channels are active THIS frame from the tap events.
        stepper_now = [False, False, False, False]
        servo_now = [False, False, False, False]
        for event in tap_events:
            channel = event["channel"]
            if event["actuator"] == "stepper":
                stepper_now[channel] = True
            elif event["actuator"] == "servo":
                servo_now[channel] = True

        # Steppers (left hand -> motors 1-4 on the Output Arduino)
        for channel in range(4):
            was_active = self._stepper_active[channel]
            is_active = stepper_now[channel]
            motor_id = channel + 1  # bridge/motor IDs are 1-indexed

            if is_active and not was_active:
                freq = self._stepper_frequencies[channel]
                self._send_bridge_command("OUTPUT", f"MOTOR,{motor_id},{freq}")
                self._notify_godot(f"BTN,{motor_id},1")
            elif was_active and not is_active:
                self._send_bridge_command("OUTPUT", f"MOTOR,{motor_id},0")
                self._notify_godot(f"BTN,{motor_id},0")

        self._stepper_active = stepper_now

        # Servos (right hand -> servos 1-4 on the Input Arduino)
        for channel in range(4):
            was_active = self._servo_active[channel]
            is_active = servo_now[channel]
            servo_id = channel + 1

            if is_active and not was_active:
                self._send_bridge_command("INPUT", f"SERVO,{servo_id},ON")
            elif was_active and not is_active:
                self._send_bridge_command("INPUT", f"SERVO,{servo_id},OFF")

        self._servo_active = servo_now

    def close(self) -> None:
        # All-notes-off / all-servos-off on shutdown, so nothing gets left
        # stuck on if the app closes mid-tap.
        for channel in range(4):
            if self._stepper_active[channel]:
                self._send_bridge_command("OUTPUT", f"MOTOR,{channel + 1},0")
                self._notify_godot(f"BTN,{channel + 1},0")
            if self._servo_active[channel]:
                self._send_bridge_command("INPUT", f"SERVO,{channel + 1},OFF")
        self._socket.close()
