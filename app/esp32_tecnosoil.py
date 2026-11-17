import json
import os
import threading
import time

from compu_int import MotorPuenteH, Pantalla, SensorDHT11, SensorNivel, SensorSuelo

PUENTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "esp32_puente.py")
VIDS_ESP32 = (0x303A, 0x1A86)  # USB nativo del ESP32-S3 y conversor CH343 (conector UART)


def buscar_puerto_esp32():
    """Devuelve el primer puerto COM que parezca un ESP32-S3, o None."""
    from serial.tools import list_ports
    for p in list_ports.comports():
        if p.vid in VIDS_ESP32:
            return p.device
    return None


class ConexionESP32:
    """Envía esp32_puente.py a la placa por el REPL y guarda la última lectura que reporta."""

    SIN_DATOS_S = 12  # sin líneas nuevas durante este tiempo se considera perdida la conexión
    REPETIR_BOMBA_S = 3  # la placa apaga la bomba si pasan 10 s sin órdenes

    def __init__(self, puerto, al_recibir=None):
        import serial
        if puerto in (None, "", "auto"):
            puerto = buscar_puerto_esp32()
            if not puerto:
                raise OSError("No se encontró ningún ESP32 conectado por USB.")
        self.puerto = puerto
        self._lock = threading.Lock()
        self._bomba = [0, 0, 0]
        self._ser = serial.Serial()
        self._ser.port, self._ser.baudrate = puerto, 115200
        self._ser.timeout, self._ser.write_timeout = 0.2, 3
        self._ser.dtr, self._ser.rts = False, False  # en el conector UART reiniciarían la placa
        self._ser.open()
        self._al_recibir = al_recibir
        self._ultima, self._hora, self._error = {}, time.monotonic(), None
        self._activa = True
        try:
            self._enviar_programa()
        except Exception:
            self._ser.close()
            raise
        threading.Thread(target=self._escuchar, daemon=True).start()

    def _enviar_programa(self):
        leido, inicio = b"", time.monotonic()
        while not leido.rstrip().endswith(b">>>"):
            if time.monotonic() - inicio > 5:
                raise OSError("El ESP32 no responde en el REPL. Reinícielo y cierre Thonny.")
            # Ctrl+C detiene lo que corra; Ctrl+B sale del REPL "crudo" si quedó así de una sesión anterior
            self._ser.write(b"\x03\x02\r")
            leido += self._ser.read(500)
        self._ser.write(b"\r\x01")
        time.sleep(0.3)
        self._ser.read(500)
        with open(PUENTE, "rb") as f:
            codigo = f.read()
        for i in range(0, len(codigo), 128):
            self._ser.write(codigo[i:i + 128])
            time.sleep(0.02)
        self._ser.write(b"\x04")

    def enviar(self, orden: dict):
        """Manda una orden JSON a esp32_puente.py (una por línea)."""
        if not self._activa:
            return
        linea = (json.dumps(orden, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
        try:
            with self._lock:
                self._ser.write(linea)
        except Exception as e:  # cable desconectado: lo reporta lectura() en el siguiente paso
            self._error = self._error or str(e)

    def bomba(self, in1, in2, fraccion):
        self._bomba = [int(in1), int(in2), round(max(0.0, min(1.0, fraccion)) * 100)]
        self.enviar({"m": self._bomba})

    def lcd(self, lineas):
        self.enviar({"l": [str(t)[:20] for t in (list(lineas) + [""] * 4)[:4]]})

    def _escuchar(self):
        resto, repetido = b"", time.monotonic()
        try:
            while self._activa:
                if time.monotonic() - repetido > self.REPETIR_BOMBA_S:
                    repetido = time.monotonic()
                    self.enviar({"m": self._bomba})  # mantiene viva la orden de la bomba
                resto += self._ser.read(500)
                *lineas, resto = resto.split(b"\n")
                for linea in lineas:
                    self._procesar(linea.decode("utf-8", "replace"))
        except Exception as e:  # p. ej. se desconecta el cable USB
            if self._activa:
                self._error = str(e)

    def _procesar(self, linea):
        if "Error:" in linea or "Traceback" in linea:
            self._error = linea.strip()
        i = linea.find("{")  # la primera línea llega como OK{...}
        if i < 0:
            return
        try:
            datos = json.loads(linea[i:])
        except ValueError:
            return
        self._ultima, self._hora = datos, time.monotonic()
        if self._al_recibir:
            self._al_recibir(datos)

    def lectura(self):
        if self._error:
            raise ConnectionError(f"ESP32: {self._error}")
        if time.monotonic() - self._hora > self.SIN_DATOS_S:
            raise ConnectionError(f"El ESP32 lleva más de {self.SIN_DATOS_S} s sin enviar datos.")
        return self._ultima

    def cerrar(self):
        if not self._activa:
            return
        try:
            self.bomba(0, 0, 0)
        except Exception:
            pass
        self._activa = False
        time.sleep(0.3)
        try:
            self._ser.write(b"\x03\x03")
            time.sleep(0.3)
            self._ser.write(b"\x02")
        except Exception:
            pass
        self._ser.close()


class SensorDHT22ESP32(SensorDHT11):
    """Misma validación de SensorDHT11; el dato viene del DHT22 conectado al ESP32."""

    def __init__(self, conexion: ConexionESP32):
        super().__init__()
        self._conexion = conexion

    def _leer_crudo(self):
        d = self._conexion.lectura()
        return round(d.get("t") or 0, 1), round(d.get("h") or 0, 1)


class SensorNivelESP32(SensorNivel):
    """Convierte a % de llenado la distancia medida por el HC-SR04 conectado al ESP32."""

    def __init__(self, conexion: ConexionESP32, altura_tanque_cm=7.0, altura_lleno_cm=0.0):
        super().__init__(altura_tanque_cm, altura_lleno_cm)
        self._conexion = conexion

    def _medir_cm(self):
        d = self._conexion.lectura().get("d")
        return self._alto if d is None else d  # sin eco: se reporta 0 %


class SensorSueloESP32(SensorSuelo):
    """Sensor 7-en-1 leído por el ESP32 a través del MAX485."""

    def __init__(self, conexion: ConexionESP32):
        self._conexion = conexion

    def _leer_registro(self, direccion):
        s = self._conexion.lectura().get("s")
        return None if s is None else s[direccion]


class MotorESP32(MotorPuenteH):
    """Puente H real: además de guardar IN1/IN2/PWM, los manda al ESP32 (GPIO 21, 47 y 15).
    Sin conexión (None) se comporta igual que MotorPuenteH, es decir, simulado."""

    def __init__(self, conexion: ConexionESP32 = None, pwm_max=20000):
        super().__init__(pwm_max)
        self._conexion = conexion

    def _reportar(self):
        super()._reportar()
        if self._conexion:
            self._conexion.bomba(self._in1, self._in2, self._pwm / self._pwm_max)


class PantallaLCDESP32(Pantalla):
    """LCD 20x4 física conectada al ESP32 por I2C (GPIO 8 y 9)."""

    def __init__(self, conexion: ConexionESP32):
        self._conexion = conexion

    def mostrar(self, *lineas):
        self._conexion.lcd(lineas)
