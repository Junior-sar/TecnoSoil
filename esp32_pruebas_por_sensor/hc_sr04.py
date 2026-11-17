# Lectura simple del HC-SR04 con ESP32-S3 + MicroPython
from machine import Pin, time_pulse_us
import time

TRIG = Pin(5, Pin.OUT)   # si no mide, intercambia 5 y 6
ECHO = Pin(6, Pin.IN)

while True:
    TRIG.value(0); time.sleep_us(2)
    TRIG.value(1); time.sleep_us(10)
    TRIG.value(0)
    t = time_pulse_us(ECHO, 1, 30000)
    if t < 117:                # < 2 cm: pulso falso, fuera del rango del sensor
        print("Sin eco")
    else:
        print("Distancia: {:.1f} cm".format(t * 0.0343 / 2))
    time.sleep(0.5)
