#include "Arduino.h"
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>

namespace {
constexpr float kMetersPerSecondSquaredPerG = 9.80665f;
constexpr float kSwingThresholdG = 1.5f;
constexpr uint32_t kSwingEndDebounceMs = 40;
}

Adafruit_MPU6050 mpu;

bool swingActive = false;
float swingPeakG = 0.0f;
uint32_t lastAboveThresholdMs = 0;
uint32_t swingCount = 0;

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);

  Serial.println("MPU6050 Init...");

  if (!mpu.begin()) {
    Serial.println("ERROR: MPU6050 not found. Check wiring and I2C address.");
    while (1) delay(10);
  }
  Serial.println("MPU6050 found!");

  // Use a higher range so peaks above 3G do not clip.
  mpu.setAccelerometerRange(MPU6050_RANGE_16_G);

  // Gyro range: 250 deg/s is most sensitive
  mpu.setGyroRange(MPU6050_RANGE_250_DEG);

  // Higher bandwidth preserves shorter acceleration spikes.
  mpu.setFilterBandwidth(MPU6050_BAND_184_HZ);

  Serial.println("Ready. Reporting peak accel for each swing above 3.0G.\n");
  delay(100);
}

void loop() {
  sensors_event_t accel, gyro, temp;
  mpu.getEvent(&accel, &gyro, &temp);

  const float accelMagnitude = sqrtf(
      accel.acceleration.x * accel.acceleration.x +
      accel.acceleration.y * accel.acceleration.y +
      accel.acceleration.z * accel.acceleration.z);
  const float accelMagnitudeG = accelMagnitude / kMetersPerSecondSquaredPerG;
  const uint32_t now = millis();

  if (accelMagnitudeG >= kSwingThresholdG) {
    if (!swingActive) {
      swingActive = true;
      swingPeakG = accelMagnitudeG;
      swingCount++;
    } else if (accelMagnitudeG > swingPeakG) {
      swingPeakG = accelMagnitudeG;
    }

    lastAboveThresholdMs = now;
  }

  if (swingActive && (now - lastAboveThresholdMs) >= kSwingEndDebounceMs) {
    Serial.print("Swing ");
    Serial.print(swingCount);
    Serial.print(" peak: ");
    Serial.print(swingPeakG, 2);
    Serial.println(" g");

    swingActive = false;
    swingPeakG = 0.0f;
  }
}