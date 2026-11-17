# prueba_dht22.py - prueba rápida del sensor de temperatura (sección 5.4)
import dht
from machine import Pin
import time

sensor = dht.DHT22(Pin(4))                # >>> CAMBIAR: pin de datos
while True:
    try:
        sensor.measure()
        print("Temperatura:", sensor.temperature(), "°C",
              " Humedad:", sensor.humidity(), "%")
    except OSError as e:
        print("Error de lectura:", e)
    time.sleep(2)
