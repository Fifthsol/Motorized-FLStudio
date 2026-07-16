// Input Arduino: 6 buttons (D2-D7), buttons 1-4 also locally drive texture servos (D8-D11),
// and a rotary encoder with click (CLK A3, DT A4, SW A5)
//
// Sends an ID handshake on boot so the Python bridge can identify this board,
// then streams every button/encoder event in the bridge's expected format.
//
// Requires the Bounce2 and Servo libraries:
// Arduino IDE -> Tools -> Manage Libraries -> search "Bounce2" -> install
// (Servo library is built in, no install needed)

#include <Bounce2.h>
#include <Servo.h>

// --- Buttons ---
const uint8_t NUM_BUTTONS = 6;
const uint8_t BUTTON_PINS[NUM_BUTTONS] = {2, 3, 4, 5, 6, 7};
Bounce buttons[NUM_BUTTONS];

// --- Servos (buttons 1-4 also drive these directly, for on-board testing) ---
const uint8_t NUM_SERVOS = 4;
const uint8_t SERVO_PINS[NUM_SERVOS] = {8, 9, 10, 11};
Servo servos[NUM_SERVOS];
const int SERVO_REST_ANGLE = 0;
const int SERVO_PRESSED_ANGLE = 180;
const unsigned long SERVO_PULSE_DEFAULT_MS = 150;

// --- Rotary encoder ---
const uint8_t ENCODER_CLK = A3;
const uint8_t ENCODER_DT  = A4;
const uint8_t ENCODER_SW  = A5;

Bounce encoderSwitch;
int lastClkState;
long encoderPosition = 0;

void setup() {
  Serial.begin(9600);
  while (!Serial) { }

  Serial.println("ID:INPUT");

  for (uint8_t i = 0; i < NUM_BUTTONS; i++) {
    buttons[i].attach(BUTTON_PINS[i], INPUT_PULLUP);
    buttons[i].interval(10);
  }

  for (uint8_t i = 0; i < NUM_SERVOS; i++) {
    servos[i].attach(SERVO_PINS[i]);
    servos[i].write(SERVO_REST_ANGLE);
  }

  pinMode(ENCODER_CLK, INPUT_PULLUP);
  pinMode(ENCODER_DT, INPUT_PULLUP);
  lastClkState = digitalRead(ENCODER_CLK);

  encoderSwitch.attach(ENCODER_SW, INPUT_PULLUP);
  encoderSwitch.interval(10);
}

void handleIncomingSerial() {
  if (!Serial.available()) return;

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  // Expected formats: "SERVO,<id>,ON" / "SERVO,<id>,OFF" / "SERVO,<id>,PULSE,<ms>"
  if (line.startsWith("SERVO,")) {
    int firstComma = line.indexOf(',', 6);
    if (firstComma == -1) return;

    int servoId = line.substring(6, firstComma).toInt();
    String action = line.substring(firstComma + 1);

    if (servoId < 1 || servoId > NUM_SERVOS) return;
    uint8_t idx = servoId - 1;

    if (action.startsWith("ON")) {
      servos[idx].write(SERVO_PRESSED_ANGLE);
    } else if (action.startsWith("OFF")) {
      servos[idx].write(SERVO_REST_ANGLE);
    } else if (action.startsWith("PULSE")) {
      int secondComma = action.indexOf(',');
      unsigned long pulseMs = (secondComma == -1)
          ? SERVO_PULSE_DEFAULT_MS
          : action.substring(secondComma + 1).toInt();
      servos[idx].write(SERVO_PRESSED_ANGLE);
      delay(pulseMs);
      servos[idx].write(SERVO_REST_ANGLE);
    }
  }
}

void loop() {
  handleIncomingSerial();

  // --- Buttons ---
  for (uint8_t i = 0; i < NUM_BUTTONS; i++) {
    buttons[i].update();

    if (buttons[i].fell()) {
      Serial.print("BTN,");
      Serial.print(i + 1);
      Serial.println(",1");

      if (i < NUM_SERVOS) {
        servos[i].write(SERVO_PRESSED_ANGLE);
      }
    }

    if (buttons[i].rose()) {
      Serial.print("BTN,");
      Serial.print(i + 1);
      Serial.println(",0");

      if (i < NUM_SERVOS) {
        servos[i].write(SERVO_REST_ANGLE);
      }
    }
  }

  // --- Encoder rotation ---
  int currentClkState = digitalRead(ENCODER_CLK);
  if (currentClkState != lastClkState && currentClkState == LOW) {
    if (digitalRead(ENCODER_DT) != currentClkState) {
      encoderPosition++;
      Serial.println("ENC,+1");
    } else {
      encoderPosition--;
      Serial.println("ENC,-1");
    }
  }
  lastClkState = currentClkState;

  // --- Encoder push switch ---
  encoderSwitch.update();
  if (encoderSwitch.fell()) {
    Serial.println("SW,1");
  }
  if (encoderSwitch.rose()) {
    Serial.println("SW,0");
  }
}