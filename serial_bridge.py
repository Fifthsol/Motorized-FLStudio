"""
Serial bridge: Input Arduino <-> Godot <-> Output Arduino

- Auto-detects which COM port is which Arduino via a boot-time ID handshake.
  Each Arduino must print its ID once on startup:
      Input Arduino:  Serial.println("ID:INPUT");
      Output Arduino: Serial.println("ID:MOTOR");
- Forwards every line from the Input Arduino to Godot over UDP.
- Listens for commands from Godot over UDP and routes each one to the
  correct board based on a target prefix, since Godot may need to send
  commands to EITHER board (e.g. triggering a servo on the Input Arduino,
  or a motor on the Output Arduino):
      "INPUT:SERVO,1,ON"        -> written to the Input Arduino
      "OUTPUT:MOTOR,2,440"      -> written to the Output Arduino
  The prefix is stripped before writing; only the payload after the colon
  is sent over serial.

Install dependency first:
    pip install pyserial
"""

import serial
import serial.tools.list_ports
import socket
import threading
import time

BAUD_RATE = 9600
HANDSHAKE_TIMEOUT = 3  # seconds to wait for the ID string when identifying a port

REQUIRE_OUTPUT_ARDUINO = False  # set True once the Output Arduino is connected again

GODOT_HOST = "127.0.0.1"
GODOT_LISTEN_PORT = 9001    # Godot listens here for events FROM this bridge
BRIDGE_LISTEN_PORT = 9002   # this bridge listens here for commands FROM Godot


def find_arduino_by_id(target_id, exclude_ports=None):
    """Scan available serial ports, open each briefly, and return the one
    that announces the given ID string on boot."""
    exclude_ports = exclude_ports or set()
    candidate_ports = [p.device for p in serial.tools.list_ports.comports()
                        if p.device not in exclude_ports]

    for port_name in candidate_ports:
        print(f"  Trying {port_name}...")
        try:
            # Short per-read timeout so the while loop below can check elapsed
            # time frequently, instead of blocking for the whole handshake window
            # on a single readline() call.
            ser = serial.Serial(port_name, BAUD_RATE, timeout=0.5)
            time.sleep(2)  # Arduinos reset when the serial port opens; give it time to boot

            # Deliberately NOT clearing the input buffer here - the ID line is
            # printed once at boot and may already be sitting in the buffer
            # from during the sleep above. Clearing it here would throw away
            # the only ID announcement we'll ever get.
            start = time.time()
            while time.time() - start < HANDSHAKE_TIMEOUT:
                line = ser.readline().decode(errors="ignore").strip()
                if line:
                    print(f"    [{port_name}] read: {line!r}")
                if line == target_id:
                    print(f"Found {target_id} on {port_name}")
                    return ser

            print(f"    [{port_name}] no match within {HANDSHAKE_TIMEOUT}s, moving on")
            ser.close()  # didn't identify itself in time, not the one we want
        except (OSError, serial.SerialException) as e:
            print(f"    [{port_name}] error opening port: {e}")
            continue

    return None


def input_arduino_reader(input_ser, udp_socket):
    """Continuously reads lines from the Input Arduino and forwards them to Godot."""
    while True:
        try:
            line = input_ser.readline().decode(errors="ignore").strip()
            if line:
                print(f"[INPUT -> GODOT] {line}")
                udp_socket.sendto(line.encode(), (GODOT_HOST, GODOT_LISTEN_PORT))
        except (OSError, serial.SerialException) as e:
            print(f"Input Arduino read error: {e}")
            break


def godot_command_listener(input_ser, output_ser, udp_socket):
    """Listens for commands from Godot over UDP and routes each one to the
    correct board based on its "INPUT:" or "OUTPUT:" prefix. If the target
    board isn't connected, logs what would have been sent instead."""
    while True:
        try:
            data, _addr = udp_socket.recvfrom(1024)
            message = data.decode(errors="ignore").strip()
            if not message:
                continue

            if ":" not in message:
                print(f"Malformed command (missing target prefix), dropping: {message!r}")
                continue

            target, payload = message.split(":", 1)
            target = target.strip().upper()
            payload = payload.strip()

            if target == "INPUT":
                print(f"[GODOT -> INPUT] {payload}")
                input_ser.write((payload + "\n").encode())
            elif target == "OUTPUT":
                if output_ser is not None:
                    print(f"[GODOT -> OUTPUT] {payload}")
                    output_ser.write((payload + "\n").encode())
                else:
                    print(f"[GODOT -> (no output Arduino connected)] {payload}")
            else:
                print(f"Unknown target {target!r}, dropping: {payload}")
        except OSError as e:
            print(f"UDP receive error: {e}")
            break


def main():
    print("Looking for Input Arduino (ID:INPUT)...")
    input_ser = find_arduino_by_id("ID:INPUT")
    if input_ser is None:
        print("Could not find Input Arduino. Check it's plugged in and flashed with the ID handshake.")
        return

    print("Looking for Output Arduino (ID:MOTOR)...")
    if REQUIRE_OUTPUT_ARDUINO:
        output_ser = find_arduino_by_id("ID:MOTOR", exclude_ports={input_ser.port})
        if output_ser is None:
            print("Could not find Output Arduino. Check it's plugged in and flashed with the ID handshake.")
            input_ser.close()
            return
    else:
        print("Skipping (REQUIRE_OUTPUT_ARDUINO is False) - input-only testing mode.")
        output_ser = None

    # One socket handles both directions: sending TO Godot, and receiving FROM Godot
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind((GODOT_HOST, BRIDGE_LISTEN_PORT))

    print(f"Bridge running. Sending Input events to Godot on port {GODOT_LISTEN_PORT},")
    print(f"listening for Godot commands on port {BRIDGE_LISTEN_PORT}. Ctrl+C to stop.")

    reader_thread = threading.Thread(
        target=input_arduino_reader, args=(input_ser, udp_socket), daemon=True
    )
    listener_thread = threading.Thread(
        target=godot_command_listener, args=(input_ser, output_ser, udp_socket), daemon=True
    )
    reader_thread.start()
    listener_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        input_ser.close()
        if output_ser is not None:
            output_ser.close()
        udp_socket.close()


if __name__ == "__main__":
    main()
