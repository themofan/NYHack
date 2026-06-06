#include "Arduino.h"
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Servo.h>
#include <Wire.h>

namespace {
constexpr float kGravityAlpha = 0.02f;
constexpr float kSwingStartThresholdG = 2.0f;
constexpr float kSwingEndThresholdG = 0.5f;
constexpr float kMetersPerSecondSquaredPerG = 9.80665f;
constexpr uint32_t kSampleIntervalMs = 0;
constexpr uint32_t kSameDirectionCooldownMs = 200;
constexpr int kServoPin = D6;
constexpr int kServoShakeAngleA = 10;
constexpr int kServoShakeAngleB = 170;
constexpr int kServoIdleAngle = 90;
constexpr uint32_t kServoShakeIntervalMs = 200;
constexpr uint32_t kBoardLedToggleMs = 250;
constexpr uint32_t kRoundDelayMs = 5000;
constexpr int kSequenceLength = 5;
}

enum class GameState {
  WaitingToStart,
  WaitingForInput,
};

Adafruit_MPU6050 mpu;
Servo swingServo;

bool swingActive = false;
bool swingArmed = false;
float swingPeakMagnitudeG = 0.0f;
float swingPeakXG = 0.0f;
float swingPeakYG = 0.0f;
float swingPeakZG = 0.0f;
float gravityX = 0.0f;
float gravityY = 0.0f;
float gravityZ = 0.0f;
int lastAcceptedDirection = -1;
uint32_t lastAcceptedDirectionMs = 0;

GameState gameState = GameState::WaitingToStart;
uint32_t roundStateStartMs = 0;
uint32_t lastServoToggleMs = 0;
uint32_t lastBoardLedToggleMs = 0;
bool boardLedsOn = false;
int servoAngle = kServoIdleAngle;
int targetDirections[kSequenceLength] = {0};
int sequenceProgress = 0;

void SetupBoardLeds() {
#if defined(LED_BUILTIN)
  pinMode(LED_BUILTIN, OUTPUT);
#endif
}

void SetBoardLeds(bool on) {
  const uint8_t level = on ? HIGH : LOW;
#if defined(LED_BUILTIN)
  digitalWrite(LED_BUILTIN, level);
#endif
}

void PrintProgressCircles(int progressCount) {
  for (int i = 0; i < kSequenceLength; ++i) {
    if (i < progressCount) {
      Serial.print('o');
    } else {
      Serial.print('.');
    }
    if (i < (kSequenceLength - 1)) {
      Serial.print(' ');
    }
  }
  Serial.println();
}

const char* DirectionToString(int directionIndex) {
  switch (directionIndex) {
    case 0: return "X";
    case 1: return "Y";
    default: return "Z";
  }
}

int ComputeDirectionIndex(float xG, float yG, float zG) {
  int directionIndex = 0;
  float dominantAbsG = fabsf(xG);

  if (fabsf(yG) > dominantAbsG) {
    directionIndex = 1;
    dominantAbsG = fabsf(yG);
  }

  if (fabsf(zG) > dominantAbsG) {
    directionIndex = 2;
  }

  return directionIndex;
}

void GenerateAndPrintSequence() {
  for (int i = 0; i < kSequenceLength; ++i) {
    targetDirections[i] = random(3);
    Serial.print(DirectionToString(targetDirections[i]));
    if (i < (kSequenceLength - 1)) {
      Serial.print(' ');
    }
  }
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);

  Serial.println("MPU6050 Init...");

  if (!mpu.begin()) {
    Serial.println("ERROR: MPU6050 not found. Check wiring and I2C address.");
    while (1) delay(10);
  }
  Serial.println("MPU6050 found!");

  swingServo.attach(kServoPin);
  swingServo.write(servoAngle);
  randomSeed(micros());
  SetupBoardLeds();
  SetBoardLeds(false);

  // Use a higher range so peaks above 3G do not clip.
  mpu.setAccelerometerRange(MPU6050_RANGE_16_G);

  // Gyro range: 250 deg/s is most sensitive
  mpu.setGyroRange(MPU6050_RANGE_250_DEG);

  // Higher bandwidth preserves shorter acceleration spikes.
  mpu.setFilterBandwidth(MPU6050_BAND_184_HZ);

  roundStateStartMs = millis();
  Serial.println("Ready. Wait 5s, then match 5 swing directions in order.\n");
  delay(100);
}

void loop() {
  static uint32_t lastSampleMs = 0;
  const uint32_t now = millis();

  if (gameState == GameState::WaitingToStart) {
    swingServo.write(kServoIdleAngle);
    SetBoardLeds(false);
    boardLedsOn = false;
    if ((now - roundStateStartMs) >= kRoundDelayMs) {
      gameState = GameState::WaitingForInput;
      sequenceProgress = 0;
      swingArmed = false;
      swingActive = false;
      lastAcceptedDirection = -1;
      lastAcceptedDirectionMs = 0;
      servoAngle = kServoShakeAngleA;
      swingServo.write(servoAngle);
      lastServoToggleMs = now;
      lastBoardLedToggleMs = now;
      GenerateAndPrintSequence();
    }
  } else {
    if ((now - lastBoardLedToggleMs) >= kBoardLedToggleMs) {
      lastBoardLedToggleMs = now;
      boardLedsOn = !boardLedsOn;
      SetBoardLeds(boardLedsOn);
    }

    if ((now - lastServoToggleMs) >= kServoShakeIntervalMs) {
      lastServoToggleMs = now;
      servoAngle = (servoAngle == kServoShakeAngleA) ? kServoShakeAngleB : kServoShakeAngleA;
      swingServo.write(servoAngle);
    }
  }

  if ((now - lastSampleMs) < kSampleIntervalMs) {
    return;
  }
  lastSampleMs = now;

  sensors_event_t accel, gyro, temp;
  mpu.getEvent(&accel, &gyro, &temp);

  gravityX += kGravityAlpha * (accel.acceleration.x - gravityX);
  gravityY += kGravityAlpha * (accel.acceleration.y - gravityY);
  gravityZ += kGravityAlpha * (accel.acceleration.z - gravityZ);

  const float linearAccelXG = (accel.acceleration.x - gravityX) / kMetersPerSecondSquaredPerG;
  const float linearAccelYG = (accel.acceleration.y - gravityY) / kMetersPerSecondSquaredPerG;
  const float linearAccelZG = (accel.acceleration.z - gravityZ) / kMetersPerSecondSquaredPerG;
  const float linearAccelMagnitudeG = sqrtf(
      linearAccelXG * linearAccelXG +
      linearAccelYG * linearAccelYG +
      linearAccelZG * linearAccelZG);

  if (gameState != GameState::WaitingForInput) {
    return;
  }

  if (!swingActive && linearAccelMagnitudeG < kSwingEndThresholdG) {
    swingArmed = true;
  }

  if (!swingActive && swingArmed && linearAccelMagnitudeG >= kSwingStartThresholdG) {
    swingActive = true;
    swingArmed = false;
    swingPeakMagnitudeG = linearAccelMagnitudeG;
    swingPeakXG = linearAccelXG;
    swingPeakYG = linearAccelYG;
    swingPeakZG = linearAccelZG;
  } else if (swingActive && linearAccelMagnitudeG > swingPeakMagnitudeG) {
    swingPeakMagnitudeG = linearAccelMagnitudeG;
    swingPeakXG = linearAccelXG;
    swingPeakYG = linearAccelYG;
    swingPeakZG = linearAccelZG;
  }

  if (swingActive && linearAccelMagnitudeG < kSwingEndThresholdG) {
    const int detectedDirection = ComputeDirectionIndex(swingPeakXG, swingPeakYG, swingPeakZG);
    const bool sameDirectionCooldown =
        (detectedDirection == lastAcceptedDirection) &&
        ((now - lastAcceptedDirectionMs) < kSameDirectionCooldownMs);

    if (!sameDirectionCooldown) {
      lastAcceptedDirection = detectedDirection;
      lastAcceptedDirectionMs = now;

      if (detectedDirection == targetDirections[sequenceProgress]) {
        sequenceProgress++;
        PrintProgressCircles(sequenceProgress);

        if (sequenceProgress >= kSequenceLength) {
          Serial.println("Spells completed!\n");
          gameState = GameState::WaitingToStart;
          roundStateStartMs = now;
          swingServo.write(kServoIdleAngle);
          SetBoardLeds(false);
          boardLedsOn = false;
          sequenceProgress = 0;
        }
      }
    }

    swingActive = false;
    swingPeakMagnitudeG = 0.0f;
    swingPeakXG = 0.0f;
    swingPeakYG = 0.0f;
    swingPeakZG = 0.0f;
  }
}