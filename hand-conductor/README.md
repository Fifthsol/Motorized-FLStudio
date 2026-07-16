# Hand Conductor

Webcam hand tracking for a hackathon music device with 4 servos and 4 steppers.

See `PROJECT.md` for the complete teammate handoff and serial integration guide.

This uses Google's published MediaPipe Hand Landmarker model. The app detects hand landmarks, classifies a few simple hand shapes, and turns them into placeholder motor commands. Your teammate should only need to edit `src/conductor/hardware.py` or swap in a serial protocol.

## What It Tracks

- `open_palm`: all fingers open
- `fist`: closed hand
- `peace`: index and middle fingers
- `pinch`: thumb tip close to index tip

## Setup

Use Python 3.10-3.12. MediaPipe may not have wheels for the newest Python releases.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run

```powershell
python run_conductor.py
```

The program tracks two hands by default. A trained MediaPipe Gesture Recognizer
classifies fist, open-palm, pointing, peace, and thumbs-up gestures; pinch uses landmark geometry.
Five-frame voting reduces label flicker. The detected left hand controls servo and
stepper channels `0-1`; the detected right hand controls channels `2-3`. The detected hand gets
its own gesture label and motion tracking. Pass `--max-hands 1` for single-hand mode.
Duplicate handedness results are discarded, so the app processes at most one left hand and
one right hand at a time.

Finger tapping uses thumb contact. MediaPipe's 21 world-space joints are converted into a 3D
hand-local model, and each non-thumb fingertip's distance to the thumb tip is divided by palm
width. This makes the contact threshold independent of camera distance and hand orientation.
The closest fingertip fires immediately when its fused 3D and 2D coordinate is clearly equal
to the thumb-tip coordinate. Borderline contact must appear in two of three samples, while
strong contact still fires in one frame. It cannot fire again until that finger separates.

Left-hand index/middle/ring/pinky thumb taps map to stepper channels `0-3`; right-hand taps map
to servo channels `0-3`. Yellow dots mark tracked fingertips, the blue dot marks the thumb
target, and a fingertip turns red when its tap fires. Tune contact and release thresholds using the `tap_*` settings in
`config.json`. The calculated origin, orientation axes, local fingertip coordinates, and curl
values are also included under `metadata.hands[].kinematics` in every motor command.
Every command also includes `metadata.tap_events`, with explicit `hand`, `finger`, `actuator`,
and `channel` fields. The same mapping is printed in the terminal when a tap is active.

When two open palms move vertically at the same time, a full-screen animated `67` swarm opens.
Both hands must be open palms for at least 70% of the recent 24-frame window before motion
tracking starts. Each hand must then register both upward and downward movement.
Close it with the visible `CLOSE X` button, `Esc`, or `Q`.
The popup has a 60-second cooldown. Press `R` in the camera preview to reset it immediately.
Press `T` to enable or disable the feature. The preview intentionally shows only
`ENABLED`/`DISABLED` and the remaining cooldown number.
Press `Y` to toggle hidden easy mode. Easy mode requires two current open palms moving
vertically past the lower `six_seven_easy_velocity_threshold`, but skips majority qualification
and the full up/down sequence. Its state is intentionally not shown in the preview.
Sensitivity is controlled by `six_seven_velocity_threshold` in `config.json`.

The first run downloads the MediaPipe model into `models/gesture_recognizer.task`.

Useful options:

```powershell
python run_conductor.py --camera 1
python run_conductor.py --no-preview
python run_conductor.py --bridge
```

`--bridge` sends tap events to the project's existing Python serial bridge
over UDP (127.0.0.1:9002 by default — override with `--bridge-host`/
`--bridge-port`) instead of printing to console. The bridge must already be
running and connected to both Arduinos. See `PROJECT.md` for the full
mapping.

## Hardware Hook

Without `--bridge`, the default output just prints commands:

```text
gesture=open_palm servos=[92.0, 48.5, 144.0, 0.0] steppers=[0.0, 0.0, 0.0, 0.0]
```

With `--bridge`, `src/conductor/partner_serial.py` sends real tap events to
the project's Python serial bridge over UDP:

- Left-hand taps (stepper channels 0-3) -> `OUTPUT:MOTOR,<1-4>,<freq>` /
  `OUTPUT:MOTOR,<1-4>,0` on tap start/release, playing one of 4 fixed
  pitches (tunable via `tap_stepper_frequencies` in `config.json`) on the
  4 NEMA motors.
- Right-hand taps (servo channels 0-3) -> `INPUT:SERVO,<1-4>,ON` /
  `INPUT:SERVO,<1-4>,OFF` on tap start/release, driving the 4 servos.

The bridge itself needs no changes — it already accepts these commands from
any UDP sender, Godot included.

## Gesture-to-Motor Placeholder Mapping

- Hand X controls servo pan.
- Hand Y controls servo pitch.
- Finger openness controls one servo.
- Pinch triggers an accent servo.
- Left index/middle/ring/pinky taps pulse steppers `0-3`.
- Right index/middle/ring/pinky taps pulse servos `0-3`.
- Fist sends zeroed stop commands.

The mapping is intentionally simple. Replace it with the real motor behavior once the stepper/servo firmware protocol is known.
