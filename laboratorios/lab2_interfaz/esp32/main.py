# =====================================================================
# PLANTILLA UNIVERSAL DE LECTURA DE SENSORES - ESP32 + MicroPython
# Versión 2: envía las lecturas al PC (trama DATA:{json})
# ---------------------------------------------------------------------
# Guarda este archivo en el ESP32 como main.py (se ejecuta al encender)
# Busca las marcas >>> CAMBIAR : son los únicos puntos a adaptar.
# =====================================================================
from machine import Pin, I2C, ADC, SoftI2C
import time
import json                                 # NUEVO: para la trama al PC

# ---------------------------------------------------------------------
# 1) CONFIGURACIÓN GENERAL                                 >>> CAMBIAR
# ---------------------------------------------------------------------
NOMBRE_SENSOR = "DHT22"    # >>> CAMBIAR: solo informativo
INTERVALO_S   = 2          # >>> CAMBIAR: segundos entre lecturas
N_PROMEDIO    = 1          # >>> CAMBIAR: nº de lecturas a promediar
REINTENTOS    = 3          # nº de intentos si una lectura falla
PIN_LED       = 2          # LED integrado (en muchas placas es el GPIO 2)

PIN_DATOS = 4              # sensores de 1 cable: DHT, DS18B20, digitales
PIN_SDA   = 21             # bus I2C por defecto del ESP32
PIN_SCL   = 22
PIN_ADC   = 34             # analógico: usar GPIO 32-39 (ADC1)

# ---------------------------------------------------------------------
# 2) LIBRERÍA DEL SENSOR                                   >>> CAMBIAR
# ---------------------------------------------------------------------
import dht                                  # DHT11 / DHT22
# import onewire, ds18x20                   # DS18B20
# import bme280_float as bme280             # BME280 (copiar a /lib)

# ---------------------------------------------------------------------
# 3) CREAR EL SENSOR                                       >>> CAMBIAR
# ---------------------------------------------------------------------
def crear_sensor():
    return dht.DHT22(Pin(PIN_DATOS))        # DHT11 -> dht.DHT11(...)

# ---------------------------------------------------------------------
# 4) LEER EL SENSOR                                        >>> CAMBIAR
#    Debe devolver un diccionario {nombre_variable: valor_numérico}
# ---------------------------------------------------------------------
def leer_sensor(sensor):
    sensor.measure()
    return {"temp_C": sensor.temperature(),
            "hum_%": sensor.humidity()}

# ---------------------------------------------------------------------
# 5) PROCESAR / CALIBRAR (opcional)                        >>> CAMBIAR
# ---------------------------------------------------------------------
CALIBRACION = {
    # "temp_C": (1.0, -0.5),   # (escala, offset) por variable
}

def procesar(datos):
    for clave, (escala, offset) in CALIBRACION.items():
        if clave in datos:
            datos[clave] = datos[clave] * escala + offset
    return datos

# ---------------------------------------------------------------------
# 6) SALIDA                                                >>> CAMBIAR
#    MODO_PC = True  -> trama DATA:{json} para la interfaz del PC
#    MODO_PC = False -> texto legible en la consola de Thonny
# ---------------------------------------------------------------------
MODO_PC = True

def publicar(datos):
    if MODO_PC:
        print("DATA:" + json.dumps(datos))
    else:
        texto = ", ".join("{}={:.2f}".format(k, v) for k, v in datos.items())
        print("[{}] {}".format(NOMBRE_SENSOR, texto))

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
    led = Pin(PIN_LED, Pin.OUT)
    print("Iniciando", NOMBRE_SENSOR, "...")
    sensor = crear_sensor()
    time.sleep(1)
    while True:
        led.on()
        datos = promediar(sensor)
        led.off()
        if datos:
            publicar(procesar(datos))
        else:
            print("Sin datos: revisa cableado, pines y alimentación")
        time.sleep(INTERVALO_S)


try:
    main()
except KeyboardInterrupt:
    print("Programa detenido")
