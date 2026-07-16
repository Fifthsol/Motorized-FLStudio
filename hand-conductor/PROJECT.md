# Hand Conductor Project Guide

## Project Goal

Hand Conductor uses a webcam to control a music device containing four stepper
motors and four servo motors. MediaPipe tracks up to two hands. Hand gestures
produce general placeholder motor values, while touching each non-thumb finger
to the thumb produces a specific motor-channel event.

The computer-vision side is functional. The hardware protocol is intentionally
a placeholder because it must match the final microcontroller firmware.

## Quick Start

Use Python 3.10-3.13 on Windows.

```powershell
cd C:\Users\aptcs\Documents\conductor
python -m pip install -r requirements.txt
python run_conductor.py
```

The default camera is camera `0`, and two-hand tracking is enabled by default.

```powershell
python run_conductor.py --camera 1
python run_conductor.py --max-hands 1
```

Press `Q` in the camera preview to stop the program.

## Thumb-Tap Controls

Touch a fingertip to the thumb tip. The blue dot is the thumb target. Tracked
fingertips are yellow and turn red when a tap fires.

| Hand | Finger | Hardware | Channel |
| --- | --- | --- | ---: |
| Left | Index | Stepper | 0 |
| Left | Middle | Stepper | 1 |
| Left | Ring | Stepper | 2 |
| Left | Pinky | Stepper | 3 |
| Right | Index | Servo | 0 |
| Right | Middle | Servo | 1 |
| Right | Ring | Servo | 2 |
| Right | Pinky | Servo | 3 |

Every active tap is included in `command.metadata.tap_events`:

```json
{
  "hand": "left",
  "finger": "index",
  "actuator": "stepper",
  "channel": 0
}
```

The terminal prints the same event as:

```text
taps=left:index->stepper0
```

## Serial Hardware Integration

This has been rewired from the original serial placeholder to talk to the
project's existing Python bridge instead of opening its own COM port
(the bridge already owns both Arduino connections, so a second process
grabbing the same port directly would just fail).

```text
src/conductor/partner_serial.py
```

Run with the bridge already running, connected to both Arduinos:

```powershell
python run_conductor.py --bridge
```

`PartnerSerialDriver` tracks each of the 8 channels' active state frame to
frame and sends edge-triggered commands over UDP to `127.0.0.1:9002`
(override with `--bridge-host`/`--bridge-port`):

- Tap starts on a left-hand finger -> `OUTPUT:MOTOR,<1-4>,<freq>`
- Tap releases on a left-hand finger -> `OUTPUT:MOTOR,<1-4>,0`
- Tap starts on a right-hand finger -> `INPUT:SERVO,<1-4>,ON`
- Tap releases on a right-hand finger -> `INPUT:SERVO,<1-4>,OFF`

The 4 stepper pitches come from `tap_stepper_frequencies` in `config.json`
(defaults to the same C4/D4/F4/G4 pentatonic set used elsewhere in the
project, for musical consistency). `build_serial_payload()` is kept around
for reference/debugging but is no longer what actually gets sent — see
`PartnerSerialDriver.send()` for the real logic.

The general gesture-driven `servo_angles`/`stepper_speeds` placeholder
(pan/pitch/openness/accent from hand position) is intentionally left
un-wired to real hardware for now — there's no obvious equivalent on this
project's fixed-position servos/steppers. Only the crisp per-channel tap
events, which map cleanly onto real motor channels, are wired through.

Do not put motor pin control in the computer-vision loop. The computer
sends commands; the Arduino firmware generates the actual step pulses and
servo PWM (already true of this project's existing Arduino firmware).

## Placeholder Output Values

The current thumb-tap output values are configured in `config.json`:

```json
{
  "tap_stepper_speed": 450,
  "tap_servo_angle": 150
}
```

A left-hand tap temporarily sets the matching stepper speed to `450`. A
right-hand tap temporarily sets the matching servo angle to `150`. Change these
values or replace the behavior in `_tap_outputs()` inside
`src/conductor/app.py` when the hardware requirements are known.

## Tracking Details

- MediaPipe Gesture Recognizer tracks two hands and 21 landmarks per hand.
- The program keeps at most one detected left hand and one detected right hand.
- Thumb contact combines hand-relative 3D distance with current 2D image distance.
- Strong contact fires in one frame.
- Borderline contact must appear in two of the last three samples.
- A finger must separate from the thumb before it can fire again.
- Only the closest fingertip to the thumb can fire at a time on each hand.

Contact sensitivity is controlled in `config.json`:

```json
{
  "tap_thumb_strong_contact_ratio": 0.3,
  "tap_thumb_contact_ratio": 0.42,
  "tap_thumb_release_ratio": 0.58
}
```

These values are distances divided by palm width. Increasing a contact ratio
makes tapping easier but increases false contacts.

## Gestures and 67 Feature

The app also recognizes open palm, fist, peace, pinch, pointing, and thumbs-up.
The gesture-to-motor behavior is placeholder logic in `src/conductor/app.py`.

The hidden `67` popup requires two open palms moving up and down. Controls:

- `T`: enable or disable the feature.
- `Y`: toggle easy activation mode.
- `R`: reset the 60-second cooldown.
- `Q`: quit the conductor app.
- `Esc`, `Q`, or the close button: close the popup.

## Important Files

| File | Purpose |
| --- | --- |
| `run_conductor.py` | Program entry point |
| `src/conductor/app.py` | Camera loop, mappings, preview, and command creation |
| `src/conductor/taps.py` | Thumb-contact detector |
| `src/conductor/gestures.py` | Gesture classification and smoothing |
| `src/conductor/hand_kinematics.py` | Internal 3D hand coordinate model |
| `src/conductor/hardware.py` | Command data model and driver selection |
| `src/conductor/partner_serial.py` | Hardware serial protocol placeholder to edit |
| `config.json` | Tracking sensitivity and placeholder output values |
| `tests/` | Tracking and channel-mapping regression tests |

## Testing

Run all automated tests before changing the protocol or mappings:

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

Then test each finger manually and verify these terminal labels:

```text
left:index->stepper0
left:middle->stepper1
left:ring->stepper2
left:pinky->stepper3
right:index->servo0
right:middle->servo1
right:ring->servo2
right:pinky->servo3
```

Finally, run with the real serial port and verify one motor channel at a time at
low speed before connecting the complete mechanism.

## Known Limitations

- Webcam 3D landmarks are estimates, not depth-camera measurements.
- Fast motion blur can cause MediaPipe to temporarily lose fingertips.
- Actual motor limits, acceleration, step pulse timing, and emergency stopping
  must be enforced by the microcontroller firmware.
- The placeholder values are not safe assumptions for unknown hardware.
