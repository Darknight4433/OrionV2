/*
 * ORION V2 — ESP32 Motor Controller
 * ===================================
 * Receives commands from Pi 3 B via Serial (USB or UART).
 * Controls 2 DC motors + 1 head servo.
 *
 * Serial Protocol (9600 baud):
 *   F:<speed>   Forward  (speed 0-100)
 *   B:<speed>   Backward
 *   L:<speed>   Left turn
 *   R:<speed>   Right turn
 *   S           Stop
 *   G           Greet (wave head servo)
 *   H:<deg>     Head servo to angle (0-180)
 *
 * Wiring:
 *   Motor A (Left):  IN1=GPIO12, IN2=GPIO13, ENA=GPIO14 (PWM)
 *   Motor B (Right): IN3=GPIO27, IN4=GPIO26, ENB=GPIO25 (PWM)
 *   Head Servo:      GPIO18
 */

#include <ESP32Servo.h>

// ── Motor A (Left) ──
#define IN1  12
#define IN2  13
#define ENA  14   // PWM

// ── Motor B (Right) ──
#define IN3  27
#define IN4  26
#define ENB  25   // PWM

// ── Head Servo ──
#define SERVO_PIN 18
Servo headServo;

// ── PWM config ──
#define PWM_FREQ    1000
#define PWM_RES     8      // 8-bit = 0-255
#define CH_A        0
#define CH_B        1

String inputBuffer = "";

void setup() {
  Serial.begin(9600);

  // Motor pins
  pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);

  // PWM channels
  ledcSetup(CH_A, PWM_FREQ, PWM_RES);
  ledcSetup(CH_B, PWM_FREQ, PWM_RES);
  ledcAttachPin(ENA, CH_A);
  ledcAttachPin(ENB, CH_B);

  // Head servo
  headServo.attach(SERVO_PIN);
  headServo.write(90);  // center

  stopMotors();
  Serial.println("ORION ESP32 Ready");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      processCommand(inputBuffer);
      inputBuffer = "";
    } else {
      inputBuffer += c;
    }
  }
}

void processCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "S") {
    stopMotors();
    Serial.println("ACK:STOP");

  } else if (cmd == "G") {
    greet();
    Serial.println("ACK:GREET");

  } else if (cmd.startsWith("F:")) {
    int speed = cmd.substring(2).toInt();
    moveForward(map(speed, 0, 100, 0, 255));
    Serial.println("ACK:FORWARD:" + String(speed));

  } else if (cmd.startsWith("B:")) {
    int speed = cmd.substring(2).toInt();
    moveBackward(map(speed, 0, 100, 0, 255));
    Serial.println("ACK:BACKWARD:" + String(speed));

  } else if (cmd.startsWith("L:")) {
    int speed = cmd.substring(2).toInt();
    turnLeft(map(speed, 0, 100, 0, 255));
    Serial.println("ACK:LEFT:" + String(speed));

  } else if (cmd.startsWith("R:")) {
    int speed = cmd.substring(2).toInt();
    turnRight(map(speed, 0, 100, 0, 255));
    Serial.println("ACK:RIGHT:" + String(speed));

  } else if (cmd.startsWith("H:")) {
    int deg = cmd.substring(2).toInt();
    deg = constrain(deg, 0, 180);
    headServo.write(deg);
    Serial.println("ACK:HEAD:" + String(deg));
  }
}

// ── Movement functions ──

void moveForward(int pwm) {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  ledcWrite(CH_A, pwm);
  ledcWrite(CH_B, pwm);
}

void moveBackward(int pwm) {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  ledcWrite(CH_A, pwm);
  ledcWrite(CH_B, pwm);
}

void turnLeft(int pwm) {
  // Left motor backward, right motor forward
  digitalWrite(IN1, LOW);  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  ledcWrite(CH_A, pwm);
  ledcWrite(CH_B, pwm);
}

void turnRight(int pwm) {
  // Left motor forward, right motor backward
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);  digitalWrite(IN4, HIGH);
  ledcWrite(CH_A, pwm);
  ledcWrite(CH_B, pwm);
}

void stopMotors() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  ledcWrite(CH_A, 0);
  ledcWrite(CH_B, 0);
}

void greet() {
  // Wave head servo left-center-right
  headServo.write(60);  delay(400);
  headServo.write(90);  delay(200);
  headServo.write(120); delay(400);
  headServo.write(90);  delay(200);
}
