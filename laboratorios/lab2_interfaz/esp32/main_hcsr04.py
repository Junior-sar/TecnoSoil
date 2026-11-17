# =====================================================================
# PLANTILLA UNIVERSAL DE LECTURA DE SENSORES - ESP32 + MicroPython
# Versión 2: envía las lecturas al PC (trama DATA:{json})
# Segundo sensor (Etapa G): ultrasonido HC-SR04. El bloque 6 no cambia.
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
NOMBRE_SENSOR = "HC-SR04"  # >>> CAMBIAR: solo informativo
INTERVALO_S   = 1          # >>> CAMBIAR: segundos entre lecturas
N_PROMEDIO    = 3          # >>> CAMBIAR: nº de lecturas a promediar
REINTENTOS    = 3          # nº de intentos si una lectura falla
PIN_LED       = 2          # LED integrado (en muchas placas es el GPIO 2)

PIN_DATOS = 4              # sensores de 1 cable: DHT, DS18B20, digitales
PIN_TRIG  = 5              # HC-SR04: disparo
PIN_ECHO  = 6              # HC-SR04: eco
PIN_SDA   = 21             # bus I2C por defecto del ESP32
PIN_SCL   = 22
PIN_ADC   = 34             # analógico: usar GPIO 32-39 (ADC1)

# ---------------------------------------------------------------------
# 2) LIBRERÍA DEL SENSOR                                   >>> CAMBIAR
# ---------------------------------------------------------------------
from machine import time_pulse_us          # HC-SR04 (no necesita librería externa)
# import dht                                # DHT11 / DHT22
# import onewire, ds18x20                   # DS18B20
# import bme280_float as bme280             # BME280 (copiar a /lib)

# ---------------------------------------------------------------------
# 3) CREAR EL SENSOR                                       >>> CAMBIAR
# ---------------------------------------------------------------------
def crear_sensor():
    return (Pin(PIN_TRIG, Pin.OUT, value=0), Pin(PIN_ECHO, Pin.IN))

# ---------------------------------------------------------------------
# 4) LEER EL SENSOR                                        >>> CAMBIAR
#    Debe devolver un diccionario {nombre_variable: valor_numérico}
# ---------------------------------------------------------------------
def leer_sensor(sensor):
    trig, echo = sensor
    trig.value(0); time.sleep_us(2)
    trig.value(1); time.sleep_us(10)        # pulso de disparo de 10 us
    trig.value(0)
    t = time_pulse_us(echo, 1, 30000)       # duración del eco en us (máx. ~5 m)
    if t < 117:                             # sin eco (-1/-2) o < 2 cm: lectura inválida
        raise OSError("sin eco")
    return {"dist_cm": t * 0.0343 / 2}      # velocidad del sonido 343 m/s, ida y vuelta

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
