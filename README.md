# [Motorized FL Studio]

FL Studio-style producer board that makes music with stepper motors, servos are also used for haptic feedback and accents.

## Overview

Beat-making board built with 4 stepper motors that run at different frequencies for sounds. 

Six front-panel buttons and a rotary encoder are used for input. You can also use a webcam-based hand-tracking model as a touchless alternative

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

### Output Arduino (Nano) : stepper motors via A4988 drivers

| Motor | STEP | DIR |
|---|---|---|
| Motor 1 | D8 | D7 |
| Motor 2 | D5 | D6 |
| Motor 3 | D9 | D10 |
| Motor 4 | D11 | D12 |

## Setup

1. Upload the input Arduino sketch to the input board arduino nano, this script lets buttons be connected to servos and then to serial link which is used by godot.
2. Run the serial link so Godot can read them.
   ```
   python "file path"
   ```
3. Download and run the Godot project, when serial link is running and the Godot project is open, integration should function.
4. If you want to use the hand model install the hand conductor file and its dependancies (should auto install), then CD into the folder and run
   ```
   python run_conductor.py --bridge
   ```
   no extra integration should work with the godot project!

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

<img src="https://cdn.hackclub.com/019f6d06-9ddc-7116-b20f-14ccb0f49b43/Screenshot%202026-07-16%20182233.png">
## Demo Video

https://youtu.be/40AQsFcJLmk
