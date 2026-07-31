# ORION V2 — Movement & Body Control Specification
**For the Hardware Team**  
Version: 1.0 | Project: ORION V2

---

## Overview

ORION's movement is controlled by a **two-layer decision system**:

1. **TinyLlama AI** (running on Pi 3 B) — decides *what* to do based on context
2. **Rule Engine** (instant fallback) — handles safety-critical decisions without AI delay

The Pi 3 B sends serial commands to an **ESP32** over USB. The ESP32 drives the motors.

---

## System Architecture

```
┌─────────────────────┐         ┌──────────────────────┐         ┌─────────────────┐
│     Pi 3 A (Body)   │         │    Pi 3 B (Brain)     │         │     ESP32       │
│                     │         │                       │         │                 │
│  Camera             │──WiFi──►│  Detects face event   │──USB───►│  Motor Driver A │
│  Face Recognition   │         │  TinyLlama decides    │ Serial  │  Motor Driver B │
│  Distance Sensor    │         │  Sends serial command │         │  Head Servo     │
│  Microphone         │         │                       │         │                 │
└─────────────────────┘         └──────────────────────┘         └─────────────────┘
```

---

## Serial Command Protocol

Pi 3 B sends plain text commands over USB Serial at **9600 baud**.  
Each command ends with `\n` (newline).

| Command | Format | Example | Meaning |
|---------|--------|---------|---------|
| Forward | `F:<speed>` | `F:50` | Move forward at 50% speed |
| Backward | `B:<speed>` | `B:30` | Move backward at 30% speed |
| Turn Left | `L:<speed>` | `L:40` | Rotate left at 40% speed |
| Turn Right | `R:<speed>` | `R:40` | Rotate right at 40% speed |
| Stop | `S` | `S` | Stop all motors immediately |
| Greet | `G` | `G` | Wave head servo (greeting gesture) |
| Head Turn | `H:<degrees>` | `H:60` | Turn head servo to angle (0–180°) |

**Speed range:** 0–100 (mapped to PWM 0–255 inside ESP32)  
**Head servo:** 0° = full left, 90° = center, 180° = full right

---

## Movement Decision Logic

### How TinyLlama decides movement

When Pi 3 A detects a face, it sends the person's name and position to Pi 3 B.  
Pi 3 B gives TinyLlama this prompt:

```
You control a robot. Reply with ONE word only.
Commands: FORWARD, BACKWARD, LEFT, RIGHT, STOP, GREET

Situation: Person 'Vaishnavi' detected at 1.2m, greeting mode

Command:
```

TinyLlama replies: `GREET`  
Pi 3 B sends: `G\n` to ESP32.

---

## Behavior Scenarios

### Scenario 1 — Person walks in front of ORION

```
Pi 3 A camera: Face detected (Vaishnavi, distance ~1.5m, center of frame)
    │
    ▼
Pi 3 B TinyLlama: "Person at 1.5m, center" → FORWARD
    │
    ▼
ESP32: F:30   (move forward slowly at 30% speed)
    │
    ▼
[After 1 second — recheck distance]
Distance now 0.8m → FORWARD:20 (slow down)
Distance now 0.4m → STOP (too close)
```

---

### Scenario 2 — Person detected, greeting mode (face just recognized)

```
Face recognized as "Vaishnavi"
    │
    ▼
TinyLlama: "Person detected, greeting mode" → GREET
    │
    ▼
ESP32: G   (head servo waves left → center → right)
    │
    ▼
Pi 3 B speaks: "Good afternoon Vaish! Welcome to ORION."
    │
    ▼
After greeting completes → STOP (wait for voice input)
```

---

### Scenario 3 — Person to the side

```
Camera: Face detected on LEFT side of frame
    │
    ▼
TinyLlama: "Person to the left of frame" → LEFT
    │
    ▼
ESP32: L:35   (turn left to face person)
    │
    ▼
[Recheck — person now centered] → STOP
```

---

### Scenario 4 — Obstacle detected (ultrasonic sensor)

```
Ultrasonic sensor: Object at 20cm
    │
    ▼
IMMEDIATE RULE (no AI) → STOP
    │
    ▼
ESP32: S   (instant stop)
    │
    ▼
TinyLlama: "Obstacle at 20cm ahead" → BACKWARD
    │
    ▼
ESP32: B:30   (reverse slightly)
```

**Note:** Obstacle avoidance uses the rule engine directly — NOT TinyLlama — for instant response.

---

### Scenario 5 — No person visible

```
Camera: No face detected for 5 seconds
    │
    ▼
Rule: "No person" → STOP
    │
    ▼
ESP32: S   (stay still, wait)
```

---

## Speed Guidelines

| Situation | Recommended Speed |
|-----------|-----------------|
| Approaching person (far, >2m) | F:50 |
| Approaching person (medium, 1-2m) | F:30 |
| Approaching person (close, 0.5-1m) | F:15 |
| Person too close (<0.4m) | S (stop) |
| Turning to face person | L:35 or R:35 |
| Reversing from obstacle | B:30 |

---

## ESP32 Wiring

```
ESP32 Pin   →   Component
─────────────────────────────────────
GPIO 12     →   Motor Driver A — IN1
GPIO 13     →   Motor Driver A — IN2
GPIO 14     →   Motor Driver A — ENA (PWM)

GPIO 27     →   Motor Driver B — IN3
GPIO 26     →   Motor Driver B — IN4
GPIO 25     →   Motor Driver B — ENB (PWM)

GPIO 18     →   Head Servo — Signal wire

GND         →   Common ground (ESP32 + Motor Driver + Servo)
5V          →   Servo power
VIN/12V     →   Motor Driver power (depends on motor voltage)
```

**Recommended motor driver:** L298N or L293D  
**Head servo:** Any standard 5V servo (SG90, MG996R)

---

## Arduino Sketch Location

The ESP32 firmware is in the repo at:
```
scripts/orion_esp32/orion_esp32.ino
```

Flash it using Arduino IDE with:
- Board: **ESP32 Dev Module**
- Library: `ESP32Servo` (install from Library Manager)
- Upload speed: 921600

---

## Communication Flow Summary

```
1. Pi 3 A detects face → sends WebSocket message to Pi 3 B
   {"type": "face", "user_id": "Vaishnavi", "distance": 1.2}

2. Pi 3 B receives → TinyLlama decides movement command
   Situation: "Person Vaishnavi at 1.2m, greeting mode"
   Decision: GREET

3. Pi 3 B sends serial to ESP32
   Serial: "G\n"

4. ESP32 executes
   Head servo waves (greeting gesture)

5. ESP32 sends ACK back to Pi 3 B
   Serial: "ACK:GREET"
```

---

## Safety Rules (hardcoded — cannot be overridden by AI)

These always apply regardless of what TinyLlama decides:

1. **Never move if obstacle < 15cm** — ultrasonic sensor triggers immediate STOP
2. **Never move if battery < 10%** — stops to protect hardware
3. **Stop when user is speaking** — don't move while ORION is responding
4. **Max speed 60%** — never go above 60% speed indoors
5. **Stop after 30s of continuous movement** — prevents runaway behavior

---

## What the Hardware Team Needs to Build

| Component | Purpose | Notes |
|-----------|---------|-------|
| 2x DC motors | Wheel drive | 6V or 12V depending on chassis |
| L298N motor driver | PWM motor control | Handles EN/IN pins from ESP32 |
| 1x servo motor | Head turn | SG90 or MG996R |
| ESP32 dev board | Receives Pi commands via USB | Any ESP32 with USB-C or micro USB |
| Ultrasonic sensor (HC-SR04) | Obstacle detection | Connect to ESP32, NOT Pi |
| USB cable | Pi 3 B ↔ ESP32 | Standard USB-A to micro/USB-C |
| 18650 battery pack | Power supply | Separate for motors and Pi |

---

## Questions for Hardware Team

1. What is the chassis wheel base — two wheels (differential drive) or four wheels?
2. What voltage are the DC motors rated for (6V, 9V, 12V)?
3. Is there a planned ultrasonic sensor mount position (front only or all sides)?
4. Will the head servo be on a pan-only or pan-tilt mount?

---

*Document prepared by ORION Software Team*  
*Repo: https://github.com/Darknight4433/OrionV2 — branch: orion-windows-edition*
