# HC-SR04 simple - ESP32-S3 + MicroPython
# Mide la distancia cada 0.5 s. Si no hay eco, prueba TRIG y ECHO al revés.
from machine import Pin, time_pulse_us
import time

PIN_A = 5   # TRIG
PIN_B = 6   # ECHO


def medir(trig, echo):
    trig.value(0); time.sleep_us(2)
    trig.value(1); time.sleep_us(10)
    trig.value(0)
    t = time_pulse_us(echo, 1, 30000)
    return t * 0.0343 / 2 if t > 0 else None


def pines(t, e):
    return Pin(t, Pin.OUT, value=0), Pin(e, Pin.IN)


trig_n, echo_n = PIN_A, PIN_B
trig, echo = pines(trig_n, echo_n)
fallos = 0
print("HC-SR04: TRIG=GPIO{} ECHO=GPIO{}".format(trig_n, echo_n))

while True:
    d = medir(trig, echo)
    if d is not None:
        fallos = 0
        print("Distancia: {:.1f} cm".format(d))
    else:
        fallos += 1
        print("sin eco")
        if fallos == 5:                     # 5 fallos seguidos: invierte los pines
            fallos = 0
            trig_n, echo_n = echo_n, trig_n
            trig, echo = pines(trig_n, echo_n)
            print("Probando al revés: TRIG=GPIO{} ECHO=GPIO{}".format(trig_n, echo_n))
    time.sleep_ms(500)
