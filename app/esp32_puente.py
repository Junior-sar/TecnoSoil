# Corre en el ESP32-S3 (MicroPython). La interfaz lo envía al conectarse; no hace falta guardarlo en la placa.
# Cada 2 s imprime una línea JSON: t y h (DHT22), d (distancia en cm), s (7 registros crudos del suelo),
# lcd (True si la pantalla responde) y m (estado de la bomba: [IN1, IN2, % PWM]).
# Recibe de la PC una línea JSON por comando:
#   {"m": [1, 0, 60]}            bomba: IN1, IN2 y % de PWM (0-100)
#   {"l": ["fila1", ..., "fila4"]}  texto de la LCD 20x4
from machine import Pin, PWM, UART, I2C, time_pulse_us
import dht, json, time, sys, select

DHT  = dht.DHT22(Pin(4))
TRIG = Pin(5, Pin.OUT, value=0)
ECHO = Pin(6, Pin.IN)

BAUDIOS, ID_ESCLAVO = 4800, 1
DE_RE = Pin(7, Pin.OUT, value=0)          # 1 = transmitir, 0 = recibir
UART2 = UART(2, baudrate=BAUDIOS, bits=8, parity=None, stop=1, tx=17, rx=16, timeout=100)

# Puente H (L298N): IN1 y IN2 dan el sentido, ENA la velocidad por PWM.
IN1 = Pin(21, Pin.OUT, value=0)
IN2 = Pin(47, Pin.OUT, value=0)
ENA = PWM(Pin(15), freq=1000, duty_u16=0)
SIN_ORDENES_MS = 10000                     # si la PC deja de hablar, la bomba se apaga sola
INVERTIR_GIRO = True   # la bomba tiene polaridad: con el cableado actual bombea con IN1=0, IN2=1


class LCD20x4:
    """LCD HD44780 por I2C con el módulo PCF8574 (P0=RS, P2=E, P3=luz, P4-P7=datos)."""
    FILAS = (0x00, 0x40, 0x14, 0x54)

    def __init__(self, i2c, direccion=0x27):
        self.i2c, self.dir = i2c, direccion
        time.sleep_ms(50)
        self._sincronizar()
        self._enviar(0x01, 0)                # borrar
        time.sleep_ms(2)

    def _sincronizar(self):
        """Vuelve a poner la LCD en modo 4 bits. Si un ruido (p. ej. al arrancar la bomba) le hizo
        perder medio byte, sin esto mostraría caracteres raros hasta reiniciarla."""
        for n in (0x30, 0x30, 0x30, 0x20):
            self._nibble(n)
            time.sleep_ms(5)
        for c in (0x28, 0x0C, 0x06):         # 4 bits 2 líneas, display on, avance
            self._enviar(c, 0)

    def _nibble(self, b):
        self.i2c.writeto(self.dir, bytes([b | 0x0C, (b | 0x08) & ~0x04]))   # pulso en E, luz encendida

    def _enviar(self, b, rs):
        self._nibble((b & 0xF0) | rs)
        self._nibble(((b << 4) & 0xF0) | rs)

    def mostrar(self, lineas):
        self._sincronizar()
        for f in range(4):
            texto = (lineas[f] if f < len(lineas) else "")[:20]
            self._enviar(0x80 | self.FILAS[f], 0)
            for ch in texto + " " * (20 - len(texto)):
                self._enviar(ord(ch) if 32 <= ord(ch) < 127 else 0x3F, 1)   # fuera de ASCII: '?'


def iniciar_lcd():
    i2c = I2C(0, sda=Pin(8), scl=Pin(9), freq=100000)
    for direccion in (0x27, 0x3F):
        if direccion in i2c.scan():
            try:
                return LCD20x4(i2c, direccion)
            except OSError:
                pass
    return None


LCD = iniciar_lcd()
estado_bomba = [0, 0, 0]
ultima_orden = time.ticks_ms()


def bomba(in1, in2, pct):
    pct = max(0, min(100, int(pct)))
    if INVERTIR_GIRO:
        in1, in2 = in2, in1
    IN1.value(1 if in1 else 0)
    IN2.value(1 if in2 else 0)
    ENA.duty_u16(pct * 65535 // 100 if (in1 or in2) else 0)
    estado_bomba[:] = [in2, in1, pct] if INVERTIR_GIRO else [in1, in2, pct]   # tal como lo pidió la PC


def mostrar_lcd(lineas):
    global LCD
    if LCD is None:
        return
    try:
        LCD.mostrar(lineas)
    except OSError:   # se soltó un cable: deja de intentarlo
        LCD = None


def crc16(trama):
    crc = 0xFFFF
    for b in trama:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes([crc & 0xFF, crc >> 8])


def leer_dht():
    try:
        DHT.measure()
        return DHT.temperature(), DHT.humidity()
    except OSError:
        return None, None


def leer_distancia():
    TRIG.value(0); time.sleep_us(2)
    TRIG.value(1); time.sleep_us(10)
    TRIG.value(0)
    t = time_pulse_us(ECHO, 1, 30000)
    return None if t < 117 else t * 0.0343 / 2   # < 2 cm: pulso falso


def leer_suelo():
    trama = bytes([ID_ESCLAVO, 0x03, 0, 0, 0, 7])
    trama += crc16(trama)
    while UART2.any():
        UART2.read()
    DE_RE.value(1)
    UART2.write(trama)
    time.sleep_us(len(trama) * 11 * 1000000 // BAUDIOS + 200)   # espera fin de transmisión
    DE_RE.value(0)

    cabecera, buf = bytes([ID_ESCLAVO, 0x03, 14]), b""
    limite = time.ticks_add(time.ticks_ms(), 1000)
    while time.ticks_diff(limite, time.ticks_ms()) > 0:
        if UART2.any():
            buf += UART2.read()
            i = buf.find(cabecera)            # se sincroniza aunque lleguen bytes basura antes
            if i >= 0 and len(buf) - i >= 19:
                resp = buf[i:i + 19]
                if crc16(resp[:-2]) != resp[-2:]:
                    return None
                valores = []
                for n in range(7):
                    v = (resp[3 + 2 * n] << 8) | resp[4 + 2 * n]
                    valores.append(v - 65536 if v > 32767 else v)
                return valores
        else:
            time.sleep_ms(5)
    return None


def procesar(linea):
    global ultima_orden
    try:
        orden = json.loads(linea)
    except ValueError:
        return
    ultima_orden = time.ticks_ms()
    if "m" in orden:
        bomba(*orden["m"])
    if "l" in orden:
        mostrar_lcd(orden["l"])


ENTRADA = select.poll()
ENTRADA.register(sys.stdin, select.POLLIN)


def atender_ordenes(espera_ms):
    """Espera espera_ms atendiendo las órdenes de la PC que lleguen mientras tanto."""
    fin = time.ticks_add(time.ticks_ms(), espera_ms)
    while True:
        resto = time.ticks_diff(fin, time.ticks_ms())
        if ENTRADA.poll(max(0, min(resto, 50))):
            procesar(sys.stdin.readline())
        if estado_bomba[2] and time.ticks_diff(time.ticks_ms(), ultima_orden) > SIN_ORDENES_MS:
            bomba(0, 0, 0)
        if resto <= 0:
            return


try:
    mostrar_lcd(["      TecnoSoil", "ESP32 conectado", "", ""])
    while True:
        t, h = leer_dht()
        atender_ordenes(0)
        datos = {"t": t, "h": h, "d": leer_distancia(), "s": leer_suelo(),
                 "lcd": LCD is not None, "m": estado_bomba}
        print(json.dumps(datos))
        atender_ordenes(2000)
finally:   # Ctrl+C de la PC o cualquier error: la bomba nunca queda encendida
    bomba(0, 0, 0)
