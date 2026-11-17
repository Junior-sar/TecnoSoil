# prueba_intervalo_dht22.py - pregunta 3: ¿qué pasa si se lee el DHT22 más rápido que cada 2 s?
# Hace 10 lecturas con cada intervalo y muestra cuánto tarda measure() y el valor leído.
import dht
import time
from machine import Pin

sensor = dht.DHT22(Pin(4))
for intervalo in (2.0, 1.0, 0.5, 0.2):
    for n in range(10):
        t = time.ticks_ms()
        try:
            sensor.measure()
            valor = (sensor.temperature(), sensor.humidity())
        except OSError as e:
            valor = "ERROR " + str(e)
        print(intervalo, n, time.ticks_diff(time.ticks_ms(), t), valor)
        time.sleep(intervalo)
