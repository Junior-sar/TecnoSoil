# Busca el sensor 7 en 1 probando baudios e IDs Modbus. Ejecutar una vez con Thonny o mpremote run.
from machine import Pin, UART
import time

PIN_TX, PIN_RX, PIN_DE_RE = 17, 16, 7

def crc16(t):
    c = 0xFFFF
    for b in t:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ 0xA001 if c & 1 else c >> 1
    return bytes([c & 0xFF, c >> 8])

de = Pin(PIN_DE_RE, Pin.OUT, value=0)
for baud in (4800, 9600, 2400, 19200):
    u = UART(2, baudrate=baud, tx=PIN_TX, rx=PIN_RX, timeout=100)
    for ident in (1, 2, 3, 255):
        t = bytes([ident, 3, 0, 0, 0, 1]); t += crc16(t)
        while u.any(): u.read()
        de.value(1); u.write(t)
        try: u.flush()
        except AttributeError: time.sleep_ms(30)
        de.value(0)
        time.sleep_ms(300)
        r = u.read()
        print("baud", baud, "id", ident, "->", r)
        if r and len(r) >= 7 and crc16(r[:5]) == r[5:7]:
            print(">>> SENSOR ENCONTRADO: baudios", baud, "ID", r[0])
print("Fin de la búsqueda")
