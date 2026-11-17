from machine import Pin, time_pulse_us
import dht, time

DHT  = dht.DHT22(Pin(4))
TRIG = Pin(5, Pin.OUT)
ECHO = Pin(6, Pin.IN)

while True:
    try:
        DHT.measure()
        print("Temp: {} °C  Hum: {} %".format(DHT.temperature(), DHT.humidity()), end="  |  ")
    except OSError:
        print("DHT22 sin respuesta", end="  |  ")

    TRIG.value(0); time.sleep_us(2)
    TRIG.value(1); time.sleep_us(10)
    TRIG.value(0)
    t = time_pulse_us(ECHO, 1, 30000)
    print("Sin eco" if t < 117 else "Distancia: {:.1f} cm".format(t * 0.0343 / 2))   # < 2 cm: pulso falso
    time.sleep(2)
