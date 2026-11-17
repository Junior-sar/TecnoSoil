# lector_serial.py - capa de comunicación con el ESP32 (se ejecuta en el PC)
# Lee las tramas "DATA:{...}" que envía publicar() y las entrega en una cola.
import json
import queue
import threading
import time

import serial
import serial.tools.list_ports

PREFIJO = "DATA:"            # >>> CAMBIAR solo si cambias el prefijo en el ESP32
BAUDIOS = 115200             # velocidad de la consola de MicroPython


def listar_puertos():
    """Devuelve la lista de puertos serie disponibles (COM3, /dev/ttyUSB0...)."""
    return [p.device for p in serial.tools.list_ports.comports()]


def interpretar(linea):
    """Convierte 'DATA:{"temp_C": 24.3}' en un diccionario. Devuelve None si no es dato."""
    linea = linea.strip()
    if not linea.startswith(PREFIJO):
        return None                     # mensajes de arranque, errores, etc.
    try:
        datos = json.loads(linea[len(PREFIJO):])
    except ValueError:
        return None                     # trama cortada o corrupta
    if not isinstance(datos, dict):
        return None
    return {k: float(v) for k, v in datos.items() if isinstance(v, (int, float))}


class LectorSerial:
    """Abre el puerto y lee en un hilo aparte para no congelar la interfaz."""

    def __init__(self, puerto, baudios=BAUDIOS):
        self.puerto, self.baudios = puerto, baudios
        self.cola = queue.Queue()       # (marca_tiempo, diccionario)
        self.mensajes = queue.Queue()   # líneas que no son datos (para depurar)
        self._ser = None
        self._activo = False

    def conectar(self):
        self._ser = serial.Serial()
        self._ser.port = self.puerto
        self._ser.baudrate = self.baudios
        self._ser.timeout = 1
        self._ser.dtr = False           # evita reiniciar / bloquear el ESP32 al abrir
        self._ser.rts = False
        self._ser.open()
        self._activo = True
        threading.Thread(target=self._bucle, daemon=True).start()

    def _bucle(self):
        while self._activo:
            try:
                crudo = self._ser.readline()
            except Exception as e:          # cable desconectado o puerto cerrado
                if self._activo:
                    self.mensajes.put("Puerto perdido: {}".format(e))
                self._activo = False
                break
            if not crudo:
                continue                    # timeout sin datos
            linea = crudo.decode("utf-8", errors="replace")
            datos = interpretar(linea)
            if datos:
                self.cola.put((time.time(), datos))
            elif linea.strip():
                self.mensajes.put(linea.strip())

    def desconectar(self):
        self._activo = False
        if self._ser and self._ser.is_open:
            self._ser.close()

    @property
    def conectado(self):
        return self._activo


# Prueba en consola:  python lector_serial.py COM3
if __name__ == "__main__":
    import sys
    puerto = sys.argv[1] if len(sys.argv) > 1 else input("Puerto (" + ", ".join(listar_puertos()) + "): ")
    lector = LectorSerial(puerto)
    lector.conectar()
    print("Leyendo", puerto, "- Ctrl+C para salir")
    try:
        while True:
            t, d = lector.cola.get()
            print(time.strftime("%H:%M:%S", time.localtime(t)), d)
    except KeyboardInterrupt:
        lector.desconectar()
