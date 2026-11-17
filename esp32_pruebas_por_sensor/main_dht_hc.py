# =====================================================================
# PLANTILLA UNIVERSAL DE LECTURA DE SENSORES - ESP32-S3 + MicroPython
# Sensor 1: DHT11 (temperatura y humedad, 1 cable, librería dht integrada)
# Sensor 2: HC-SR04 (distancia por ultrasonido, digital, sin librería)
# Guardar en el ESP32 como main.py. Solo se cambian las marcas >>> CAMBIAR.
# =====================================================================

from machine import Pin, time_pulse_us
import time

# ---------------------------------------------------------------------
# 1) CONFIGURACIÓN GENERAL                                >>> CAMBIAR
# ---------------------------------------------------------------------
NOMBRE_SENSOR = "DHT11 + HC-SR04"
INTERVALO_S   = 2         # DHT11: mínimo 1 s entre lecturas
N_PROMEDIO    = 1         # >>> CAMBIAR: lecturas a promediar (1 = sin filtro)
REINTENTOS    = 3
PIN_LED       = None      # ESP32-S3: el LED es RGB (GPIO48/38); None = sin LED

# Pines                                                 >>> CAMBIAR
PIN_DHT  = 4              # DATA del DHT11
PIN_TRIG = 5              # Trig del HC-SR04 (salida del ESP32)
PIN_ECHO = 6              # Echo del HC-SR04 (entrada, ¡con divisor si el sensor va a 5 V!)

# ---------------------------------------------------------------------
# 2) LIBRERÍA DEL SENSOR                                   >>> CAMBIAR
# ---------------------------------------------------------------------
import dht                # integrada en el firmware
# HC-SR04: no requiere librería (machine.time_pulse_us)

VEL_SONIDO_CM_US = 0.0343  # 343 m/s a ~20 °C


# ---------------------------------------------------------------------
# 3) CREAR EL SENSOR                                      >>> CAMBIAR
#    Devuelve un diccionario con los dos sensores.
# ---------------------------------------------------------------------
def crear_sensor():
    trig = Pin(PIN_TRIG, Pin.OUT, value=0)
    echo = Pin(PIN_ECHO, Pin.IN)
    return {"dht": dht.DHT11(Pin(PIN_DHT)), "trig": trig, "echo": echo}


def medir_distancia_cm(trig, echo):
    trig.value(0); time.sleep_us(2)
    trig.value(1); time.sleep_us(10)          # pulso de disparo de 10 µs
    trig.value(0)
    t = time_pulse_us(echo, 1, 30000)         # máx. 30 ms (~5 m)
    if t < 0:
        raise OSError("ultrasonido sin eco ({})".format(t))
    return t * VEL_SONIDO_CM_US / 2           # ida y vuelta


# ---------------------------------------------------------------------
# 4) LEER EL SENSOR                                       >>> CAMBIAR
#    Debe devolver un diccionario {nombre_variable: valor_numérico}
# ---------------------------------------------------------------------
def leer_sensor(sensor):
    datos, errores = {}, []
    try:                                      # si un sensor falla, el otro sigue
        sensor["dht"].measure()
        datos["temp_C"] = sensor["dht"].temperature()
        datos["hum_%"] = sensor["dht"].humidity()
    except OSError as e:
        errores.append("DHT11: {}".format(e))
    try:
        datos["dist_cm"] = medir_distancia_cm(sensor["trig"], sensor["echo"])
    except OSError as e:
        errores.append("HC-SR04: {}".format(e))
    if errores:
        print("Aviso:", "; ".join(errores))
    if not datos:
        raise OSError("ningún sensor respondió")
    return datos


# ---------------------------------------------------------------------
# 5) PROCESAR / CALIBRAR (opcional)                       >>> CAMBIAR
#    valor_real = valor * ESCALA + OFFSET
# ---------------------------------------------------------------------
CALIBRACION = {
    # "dist_cm": (1.0, 0.0),
}

def procesar(datos):
    for clave, (escala, offset) in CALIBRACION.items():
        if clave in datos:
            datos[clave] = datos[clave] * escala + offset
    return datos


# ---------------------------------------------------------------------
# 6) SALIDA                                               >>> CAMBIAR
#    Consola + archivo datos.csv en la placa (pregunta 6 de la guía).
# ---------------------------------------------------------------------
GUARDAR_CSV = True
COLUMNAS    = ["temp_C", "hum_%", "dist_cm"]   # columnas fijas del CSV

def publicar(datos):
    texto = ", ".join("{}={:.2f}".format(k, v) for k, v in datos.items())
    print("[{}] {}".format(NOMBRE_SENSOR, texto))
    if GUARDAR_CSV:
        try:
            nuevo = "datos.csv" not in __import__("os").listdir()
            with open("datos.csv", "a") as f:
                if nuevo:
                    f.write("t_ms," + ",".join(COLUMNAS) + "\n")
                f.write("{},{}\n".format(time.ticks_ms(), ",".join(
                    "{:.2f}".format(datos[c]) if c in datos else "" for c in COLUMNAS)))
        except OSError as e:
            print("No se pudo guardar CSV:", e)


# =====================================================================
# A PARTIR DE AQUÍ NO HACE FALTA CAMBIAR NADA
# =====================================================================
def leer_con_reintentos(sensor):
    for intento in range(REINTENTOS):
        try:
            return leer_sensor(sensor)
        except OSError as e:              # típico: cable suelto / sensor ocupado
            print("Lectura fallida ({}/{}): {}".format(intento + 1, REINTENTOS, e))
            time.sleep(1)
    return None


def promediar(sensor):
    acumulado, cuentas = {}, {}
    for _ in range(N_PROMEDIO):
        d = leer_con_reintentos(sensor)
        if d:
            for k, v in d.items():
                acumulado[k] = acumulado.get(k, 0) + v
                cuentas[k] = cuentas.get(k, 0) + 1
        if N_PROMEDIO > 1:
            time.sleep(1)                 # el DHT11 necesita 1 s entre lecturas
    if not acumulado:
        return None
    return {k: v / cuentas[k] for k, v in acumulado.items()}


def main():
    led = Pin(PIN_LED, Pin.OUT) if PIN_LED is not None else None
    print("Iniciando", NOMBRE_SENSOR, "...")
    sensor = crear_sensor()
    time.sleep(1)                        # tiempo de arranque del sensor
    while True:
        if led: led.on()
        datos = promediar(sensor)
        if led: led.off()
        if datos:
            publicar(procesar(datos))
        else:
            print("Sin datos: revisa cableado, pines y alimentación")
        time.sleep(INTERVALO_S)


try:
    main()
except KeyboardInterrupt:                   # Ctrl+C en Thonny detiene el programa
    print("Programa detenido")
