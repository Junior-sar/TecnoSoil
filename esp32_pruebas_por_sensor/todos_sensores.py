# DHT22 + HC-SR04 + sensor de suelo 7 en 1 (RS485) - ESP32-S3 + MicroPython
from machine import Pin, UART, time_pulse_us
import dht, time

DHT  = dht.DHT22(Pin(4))
TRIG = Pin(5, Pin.OUT, value=0)
ECHO = Pin(6, Pin.IN)

BAUDIOS = 4800
ID_ESCLAVO = 1
DE_RE = Pin(7, Pin.OUT, value=0)          # 1 = transmitir, 0 = recibir
UART2 = UART(2, baudrate=BAUDIOS, bits=8, parity=None, stop=1, tx=17, rx=16, timeout=100)

REGISTROS = ["hum_%", "temp_C", "EC_uS/cm", "pH", "N_mg/kg", "P_mg/kg", "K_mg/kg"]
ESCALA    = {"hum_%": 10, "temp_C": 10, "pH": 10}


def crc16(trama):
    crc = 0xFFFF
    for b in trama:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes([crc & 0xFF, crc >> 8])


def leer_suelo():
    trama = bytes([ID_ESCLAVO, 0x03, 0, 0, 0, 7])
    trama += crc16(trama)
    while UART2.any():
        UART2.read()
    DE_RE.value(1)
    UART2.write(trama)
    time.sleep_us(len(trama) * 11 * 1000000 // BAUDIOS)   # espera fin de transmisión
    time.sleep_us(200)
    DE_RE.value(0)

    cabecera, esperado = bytes([ID_ESCLAVO, 0x03, 14]), 19
    buf, limite = b"", time.ticks_add(time.ticks_ms(), 1000)
    while time.ticks_diff(limite, time.ticks_ms()) > 0:
        if UART2.any():
            buf += UART2.read()
            i = buf.find(cabecera)            # se sincroniza aunque lleguen bytes basura antes
            if i >= 0 and len(buf) - i >= esperado:
                resp = buf[i:i + esperado]
                if crc16(resp[:-2]) != resp[-2:]:
                    raise OSError("CRC incorrecto")
                datos = []
                for n, nombre in enumerate(REGISTROS):
                    v = (resp[3 + 2 * n] << 8) | resp[4 + 2 * n]
                    v = v - 65536 if v > 32767 else v
                    datos.append("{}={}".format(nombre, v / ESCALA.get(nombre, 1)))
                return " ".join(datos)
        else:
            time.sleep_ms(5)
    raise OSError("sin respuesta ({} bytes)".format(len(buf)))


while True:
    try:
        DHT.measure()
        aire = "Temp: {:.1f} °C  Hum: {:.1f} %".format(DHT.temperature(), DHT.humidity())
    except OSError:
        aire = "DHT22 sin respuesta"

    TRIG.value(0); time.sleep_us(2)
    TRIG.value(1); time.sleep_us(10)
    TRIG.value(0)
    t = time_pulse_us(ECHO, 1, 30000)
    dist = "Sin eco" if t < 117 else "Distancia: {:.1f} cm".format(t * 0.0343 / 2)   # < 2 cm: pulso falso

    try:
        suelo = leer_suelo()
    except OSError as e:
        suelo = "7 en 1: {}".format(e)

    print(aire, "|", dist, "|", suelo)
    time.sleep(3)
