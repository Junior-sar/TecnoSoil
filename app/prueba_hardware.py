"""Prueba cada componente conectado al ESP32-S3, uno por uno, e informa si responde.

Ejecutar con el ESP32 conectado (y Thonny / la interfaz cerrados):
    python prueba_hardware.py            (busca el puerto solo)
    python prueba_hardware.py COM13
Para no mover la bomba:  python prueba_hardware.py --sin-bomba
"""
import argparse
import time

from esp32_tecnosoil import ConexionESP32


def esperar_linea(con, despues_de, limite_s=6):
    """Espera una línea del ESP32 más nueva que 'despues_de' (time.monotonic)."""
    fin = time.monotonic() + limite_s
    while time.monotonic() < fin:
        if con._hora > despues_de and con._ultima:
            return con.lectura()
        time.sleep(0.1)
    raise TimeoutError("El ESP32 no envió datos a tiempo")


def resultado(nombre, ok, detalle):
    print(f"  [{'OK ' if ok else 'FALLA'}] {nombre:<22} {detalle}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("puerto", nargs="?", default="auto")
    ap.add_argument("--sin-bomba", action="store_true")
    args = ap.parse_args()

    con = ConexionESP32(args.puerto)
    print(f"ESP32 en {con.puerto}. Probando componentes...\n")
    resultados = []
    try:
        d = esperar_linea(con, 0)

        # LCD 20x4 (I2C, SDA 8 / SCL 9)
        if d.get("lcd"):
            con.lcd(["  PRUEBA DE LCD", "Fila 2: abcdefghij", "Fila 3: 0123456789", "Fila 4: OK"])
        resultados.append(resultado("LCD 20x4 (I2C)", bool(d.get("lcd")),
                                    "responde; revise que se lea el texto de prueba" if d.get("lcd")
                                    else "no responde en 0x27 ni 0x3F (cables, 5 V o contraste)"))

        # DHT22 (GPIO 4)
        t, h = d.get("t"), d.get("h")
        ok = t is not None and h is not None and -10 < t < 60 and 0 < h < 100
        resultados.append(resultado("DHT22", ok, f"T={t if t is None else round(t, 1)} °C  H={h if h is None else round(h, 1)} %" + ("" if ok else "  (fuera de rango)")))

        # HC-SR04 (Trig 5, Echo 6)
        dist = d.get("d")
        resultados.append(resultado("Ultrasonido HC-SR04", dist is not None,
                                    f"{dist:.1f} cm" if dist is not None else "sin eco"))

        # Sensor 7 en 1 (MAX485)
        s = d.get("s")
        resultados.append(resultado("Sensor suelo 7 en 1", s is not None,
                                    f"registros {s}" if s is not None else "no responde por RS485"))

        # Bomba (puente H: IN1 21, IN2 47, ENA 15)
        if args.sin_bomba:
            print("  [ -- ] Bomba                  omitida (--sin-bomba)")
        else:
            con.lcd(["  PRUEBA DE BOMBA", "Encendida al 60 %", "durante 3 s", ""])
            antes = time.monotonic()
            con.bomba(1, 0, 0.6)
            encendida = esperar_linea(con, antes).get("m")
            time.sleep(1)
            antes = time.monotonic()
            con.bomba(0, 0, 0)
            apagada = esperar_linea(con, antes).get("m")
            ok = encendida == [1, 0, 60] and apagada == [0, 0, 0]
            resultados.append(resultado("Bomba (puente H)", ok,
                                        f"encendida={encendida} apagada={apagada}; ¿giró el motor?"))
        con.lcd(["Prueba terminada", f"{sum(resultados)} de {len(resultados)} OK", "", ""])
    finally:
        con.cerrar()
    print(f"\n{sum(resultados)} de {len(resultados)} componentes respondieron.")


if __name__ == "__main__":
    main()
