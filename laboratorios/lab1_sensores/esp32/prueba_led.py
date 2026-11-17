# prueba_led.py - prueba inicial de la placa (sección 5.2)
# El DevKit de la guía tiene el LED en el GPIO 2. Nuestro ESP32-S3 trae un LED RGB
# direccionable (WS2812) en el GPIO 48, por eso se maneja con la librería integrada neopixel.
from machine import Pin
import neopixel
import time

led = neopixel.NeoPixel(Pin(48), 1)       # >>> CAMBIAR: GPIO del LED RGB de la placa
encendido = False
for _ in range(10):
    encendido = not encendido
    led[0] = (0, 40, 0) if encendido else (0, 0, 0)   # verde suave / apagado
    led.write()
    time.sleep(0.5)
led[0] = (0, 0, 0)
led.write()
print("ESP32 funcionando")
