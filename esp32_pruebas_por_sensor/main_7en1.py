# =====================================================================
# PLANTILLA UNIVERSAL DE LECTURA DE SENSORES - ESP32 + MicroPython
# Adaptada al sensor de suelo 7 en 1 (RS485, Modbus RTU) con MAX485.
# Guardar en el ESP32 como main.py. Solo se cambian las marcas >>> CAMBIAR.
# =====================================================================

from machine import Pin, UART
import time

# ---------------------------------------------------------------------
# 1) CONFIGURACIÓN GENERAL                                >>> CAMBIAR
# ---------------------------------------------------------------------
NOMBRE_SENSOR = "Suelo 7en1"
INTERVALO_S   = 2         # el sensor responde en < 1 s
N_PROMEDIO    = 1
REINTENTOS    = 3
PIN_LED       = None      # LED RGB del S3, None = sin LED

# Pines del MAX485 (UART2 del ESP32)                     >>> CAMBIAR
PIN_TX    = 17            # ESP32 TX2 -> DI del MAX485
PIN_RX    = 16            # ESP32 RX2 <- RO del MAX485
PIN_DE_RE = 7             # DE y RE unidos: 1 = transmitir, 0 = recibir (GPIO4 queda para el DHT11)
BAUDIOS   = 4800          # valor de fábrica del sensor (algunos vienen a 9600)
ID_ESCLAVO = 1
DEPURAR    = True         # muestra los bytes recibidos (False para ocultarlos)

# ---------------------------------------------------------------------
# 2) LIBRERÍA DEL SENSOR                                   >>> CAMBIAR
# No requiere librería externa: Modbus RTU se arma con machine.UART.
# ---------------------------------------------------------------------
REGISTROS = ["hum_%", "temp_C", "EC_uS/cm", "pH", "N_mg/kg", "P_mg/kg", "K_mg/kg"]
ESCALA    = {"hum_%": 10, "temp_C": 10, "pH": 10}   # registro crudo / escala


def crc16(trama):
    crc = 0xFFFF
    for b in trama:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes([crc & 0xFF, crc >> 8])


class Modbus485:
    def __init__(self, uart, de_re, id_esclavo):
        self.uart, self.de_re, self.id = uart, de_re, id_esclavo
        self.de_re.value(0)

    def leer_registros(self, inicio, cantidad):
        trama = bytes([self.id, 0x03, inicio >> 8, inicio & 0xFF, 0, cantidad])
        trama += crc16(trama)
        while self.uart.any():                    # limpia basura previa
            self.uart.read()
        self.de_re.value(1)
        self.uart.write(trama)
        try:
            self.uart.flush()                     # espera fin de transmisión
        except AttributeError:
            time.sleep_us(len(trama) * 11 * 1000000 // BAUDIOS)
        time.sleep_us(200)
        self.de_re.value(0)

        esperado = 5 + 2 * cantidad
        cabecera = bytes([self.id, 0x03, 2 * cantidad])
        buf, limite = b"", time.ticks_add(time.ticks_ms(), 1000)
        resp = None
        while time.ticks_diff(limite, time.ticks_ms()) > 0:
            if self.uart.any():
                buf += self.uart.read()
                i = buf.find(cabecera)            # se sincroniza aunque lleguen bytes basura antes
                if i >= 0 and len(buf) - i >= esperado:
                    resp = buf[i:i + esperado]
                    break
            else:
                time.sleep_ms(5)

        if DEPURAR:
            print("RX crudo:", " ".join("{:02X}".format(b) for b in buf))
        if resp is None:
            raise OSError("sin respuesta válida ({} bytes)".format(len(buf)))
        if crc16(resp[:-2]) != resp[-2:]:
            raise OSError("CRC incorrecto")
        valores = []
        for i in range(cantidad):
            v = (resp[3 + 2 * i] << 8) | resp[4 + 2 * i]
            valores.append(v - 65536 if v > 32767 else v)   # con signo (temperatura)
        return valores


# ---------------------------------------------------------------------
# 3) CREAR EL SENSOR                                      >>> CAMBIAR
# ---------------------------------------------------------------------
def crear_sensor():
    uart = UART(2, baudrate=BAUDIOS, bits=8, parity=None, stop=1,
                tx=PIN_TX, rx=PIN_RX, timeout=100)
    return Modbus485(uart, Pin(PIN_DE_RE, Pin.OUT), ID_ESCLAVO)


# ---------------------------------------------------------------------
# 4) LEER EL SENSOR                                       >>> CAMBIAR
# ---------------------------------------------------------------------
def leer_sensor(sensor):
    crudos = sensor.leer_registros(0x0000, 7)     # 7 registros en una sola trama
    return {k: v / ESCALA.get(k, 1) for k, v in zip(REGISTROS, crudos)}


# ---------------------------------------------------------------------
# 5) PROCESAR / CALIBRAR (opcional)                       >>> CAMBIAR
# ---------------------------------------------------------------------
CALIBRACION = {
    # "pH": (1.0, 0.0),
}

def procesar(datos):
    for clave, (escala, offset) in CALIBRACION.items():
        if clave in datos:
            datos[clave] = datos[clave] * escala + offset
    return datos


# ---------------------------------------------------------------------
# 6) SALIDA                                               >>> CAMBIAR
# Consola + archivo datos.csv en la placa (pregunta 6 de la guía).
# ---------------------------------------------------------------------
GUARDAR_CSV = True

def publicar(datos):
    texto = ", ".join("{}={:.2f}".format(k, v) for k, v in datos.items())
    print("[{}] {}".format(NOMBRE_SENSOR, texto))
    if GUARDAR_CSV:
        try:
            nuevo = "datos.csv" not in __import__("os").listdir()
            with open("datos.csv", "a") as f:
                if nuevo:
                    f.write("t_ms," + ",".join(datos) + "\n")
                f.write("{},{}\n".format(time.ticks_ms(),
                        ",".join("{:.2f}".format(v) for v in datos.values())))
        except OSError as e:
            print("No se pudo guardar CSV:", e)


# =====================================================================
# A PARTIR DE AQUÍ NO HACE FALTA CAMBIAR NADA
# =====================================================================
def leer_con_reintentos(sensor):
    for intento in range(REINTENTOS):
        try:
            return leer_sensor(sensor)
        except OSError as e:
            print("Lectura fallida ({}/{}): {}".format(intento + 1, REINTENTOS, e))
            time.sleep(1)
    return None


def promediar(sensor):
    acumulado, validas = {}, 0
    for _ in range(N_PROMEDIO):
        d = leer_con_reintentos(sensor)
        if d:
            validas += 1
            for k, v in d.items():
                acumulado[k] = acumulado.get(k, 0) + v
        if N_PROMEDIO > 1:
            time.sleep_ms(50)
    if validas == 0:
        return None
    return {k: v / validas for k, v in acumulado.items()}


def main():
    led = Pin(PIN_LED, Pin.OUT) if PIN_LED is not None else None
    print("Iniciando", NOMBRE_SENSOR, "...")
    sensor = crear_sensor()
    time.sleep(1)
    while True:
        if led: led.on()
        datos = promediar(sensor)
        if led: led.off()
        if datos:
            publicar(procesar(datos))
        else:
            print("Sin datos: revisa cableado A/B, alimentación del sensor, baudios e ID")
        time.sleep(INTERVALO_S)


try:
    main()
except KeyboardInterrupt:
    print("Programa detenido")
