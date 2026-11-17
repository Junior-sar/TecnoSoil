# registro_referencia.py - sección 6: 5 lecturas del DHT22 junto a la temperatura del
# sensor 7 en 1 (RS485, Modbus), que se usa como referencia ("otro sensor").
import dht, time
from machine import Pin, UART

DHT = dht.DHT22(Pin(4))
DE_RE = Pin(7, Pin.OUT, value=0)
UART2 = UART(2, baudrate=4800, tx=17, rx=16, timeout=100)


def crc16(t):
    c = 0xFFFF
    for b in t:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ 0xA001 if c & 1 else c >> 1
    return bytes([c & 0xFF, c >> 8])


def temp_referencia():
    trama = bytes([1, 3, 0, 1, 0, 1])          # registro 1 = temperatura x10
    trama += crc16(trama)
    while UART2.any():
        UART2.read()
    DE_RE.value(1); UART2.write(trama)
    time.sleep_us(len(trama) * 11 * 1000000 // 4800 + 200)
    DE_RE.value(0)
    time.sleep_ms(200)
    r = UART2.read() or b""
    i = r.find(bytes([1, 3, 2]))
    if i < 0 or len(r) - i < 7 or crc16(r[i:i + 5]) != r[i + 5:i + 7]:
        return None
    v = (r[i + 3] << 8) | r[i + 4]
    return (v - 65536 if v > 32767 else v) / 10


for n in range(1, 6):
    DHT.measure()
    print("{};{:.1f};{:.1f};{}".format(n, DHT.temperature(), DHT.humidity(), temp_referencia()))
    time.sleep(2.5)
