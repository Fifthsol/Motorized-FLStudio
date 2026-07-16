# [Motorized FL Studio]

An FL Studio-style, Teenage Engineering-inspired producer board that makes music with stepper motors; servos are used for haptic feedback and accents.

## Overview

A physical beat-making instrument built around stepper motors as pitched voices; six front-panel buttons and a rotary encoder handle composing, while a webcam-based hand-tracking model offers an alternate, touchless way to input tones.

## Input

- 6 buttons and a rotary encoder; 4 of the buttons each control one stepper motor voice
- An AI hand-tracking model that detects thumb-to-finger pinches, usable as an alternate way to input tones without touching the board

## Wiring

### Input Arduino (Nano) : buttons, encoder, and texture servos

| Component | Pin |
|---|---|
| Button 1 | D2 |
| Button 2 | D3 |
| Button 3 | D4 |
| Button 4 | D5 |
| Button 5 | D6 |
| Button 6 | D7 |
| Servo 1 (close left) | D8 |
| Servo 2 (far left) | D9 |
| Servo 3 (close right) | D10 |
| Servo 4 (far right) | D11 |
| Encoder CLK | A3 |
| Encoder DT | A4 |
| Encoder SW (click) | A5 |

Buttons use `INPUT_PULLUP`; one leg to its pin, the other leg to a shared ground rail. Buttons 1-4 also locally drive their matching servo for on-board feedback.

### Output Arduino (Nano) : stepper motors via A4988 drivers

| Motor | STEP | DIR |
|---|---|---|
| Motor 1 | D8 | D7 |
| Motor 2 | D5 | D6 |
| Motor 3 | D9 | D10 |
| Motor 4 | D11 | D12 |

Each A4988 driver's `VDD`/`GND` (logic) connects to the Arduino; `VMOT`/`GND` (power) connects to a separate 12V supply, grounded in common with the Arduino. `RESET` and `SLEEP` are jumpered together on each driver; without this the driver stays disabled.

## Setup

1. Upload the Input Arduino sketch to the Input board; this handles the buttons, encoder, and servos, and sends the ID handshake the serial link looks for.
2. Run the serial link; this connects the Arduino inputs to serial so Godot can read them.
   ```
   python "file path"
   ```
3. Download and run the Godot project; once the serial link is running and the Godot project is open, the integration should function.

## Godot Game Design

- Loop snapping
- BPM control
- Track length control
- The design goal is to keep as much control as possible in the software itself, rather than offloading logic to the hardware
- Run by downloading the GitHub repo folder

## CAD

https://cad.onshape.com/documents/37c8f188255b221d14c71916/w/ac710fb74276f16d4e021b24/e/2ff7e36cea990240b4667b1c

## Images

<img src="https://cdn.hackclub.com/019f6cf1-3cd4-7021-9889-57f47633503f/projectphoto.png">

## Demo Video

https://youtu.be/40AQsFcJLmk
