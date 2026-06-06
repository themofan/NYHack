// Move Mirror — STM32 Nucleo G474RE firmware
// Streams raw MPU-6050 motion as CSV so the localhost server can classify
// Up/Down/Left/Right gestures. One line per sample at ~100 Hz:
//
//     A,<ax>,<ay>,<az>,<gx>,<gy>,<gz>
//
// accel in g, gyro in deg/s. 115200 baud. Pairs with server.py's SerialSampleSource.
//
// PlatformIO: same env as themofan/NYHack —
//   [env:nucleo_g474re] platform=ststm32 board=nucleo_g474re framework=arduino
//   lib_deps = adafruit/Adafruit MPU6050, adafruit/Adafruit Unified Sensor, adafruit/Adafruit BusIO

#include <Arduino.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>

namespace {
constexpr float kG = 9.80665f;            // m/s^2 per g
constexpr float kRadToDeg = 57.29578f;
}

Adafruit_MPU6050 mpu;

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);

  if (!mpu.begin()) {
    Serial.println("ERROR: MPU6050 not found. Check wiring / I2C address.");
    while (1) delay(10);
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_16_G);   // headroom for sharp gestures
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_94_HZ);
  delay(100);
}

void loop() {
  sensors_event_t a, g, t;
  mpu.getEvent(&a, &g, &t);

  Serial.print("A,");
  Serial.print(a.acceleration.x / kG, 3); Serial.print(',');
  Serial.print(a.acceleration.y / kG, 3); Serial.print(',');
  Serial.print(a.acceleration.z / kG, 3); Serial.print(',');
  Serial.print(g.gyro.x * kRadToDeg, 2);  Serial.print(',');
  Serial.print(g.gyro.y * kRadToDeg, 2);  Serial.print(',');
  Serial.println(g.gyro.z * kRadToDeg, 2);

  delay(10);   // ~100 Hz
}
