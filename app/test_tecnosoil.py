"""Pruebas unitarias de TecnoSoil (no necesitan el ESP32 conectado).

Ejecutar en esta carpeta:   python -m unittest -v test_tecnosoil
"""
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

import compu_int as ci
from esp32_tecnosoil import (ConexionESP32, MotorESP32, PantallaLCDESP32, SensorDHT22ESP32,
                             SensorNivelESP32, SensorSueloESP32)


def silencio():
    """Oculta los print de [MOTOR] y del LCD de consola durante una prueba."""
    return redirect_stdout(io.StringIO())


class ConexionFalsa:
    """Reemplaza al ESP32: guarda lo que se le manda y devuelve una lectura fija."""

    def __init__(self, lectura=None):
        self.datos = lectura or {}
        self.bombas, self.lcds = [], []

    def lectura(self):
        return self.datos

    def bomba(self, in1, in2, fraccion):
        self.bombas.append((in1, in2, fraccion))

    def lcd(self, lineas):
        self.lcds.append(list(lineas))


class SerialFalso:
    def __init__(self):
        self.escrito = b""

    def write(self, b):
        self.escrito += b


def conexion_sin_puerto():
    """ConexionESP32 sin abrir un puerto real, para probar su lógica."""
    c = ConexionESP32.__new__(ConexionESP32)
    import threading, time
    c._ser, c._lock, c._activa = SerialFalso(), threading.Lock(), True
    c._ultima, c._hora, c._error, c._al_recibir, c._bomba = {}, time.monotonic(), None, None, [0, 0, 0]
    return c


# ============================ MODELOS ============================
class TestModelos(unittest.TestCase):
    def test_rango_incluye_bordes(self):
        r = ci.Rango(6.0, 7.5)
        self.assertTrue(r.contiene(6.0))
        self.assertTrue(r.contiene(7.5))
        self.assertFalse(r.contiene(7.6))

    def test_lectura_con_error_no_es_valida(self):
        self.assertFalse(ci.LecturaSuelo.con_error().es_valida)
        self.assertTrue(ci.LecturaSuelo(humedad=40).es_valida)

    def test_tomate_compatible(self):
        s = ci.LecturaSuelo(humedad=70, temp_suelo=25, ph=6.5, conductividad=500,
                            nitrogeno=40, fosforo=25, potasio=200)
        tomate = next(p for p in ci.BaseDatosPlantas().plantas if p.nombre == "Tomate")
        self.assertTrue(tomate.es_compatible(s))
        s.potasio = 100  # por debajo del mínimo (156)
        self.assertFalse(tomate.es_compatible(s))

    def test_buscar_compatibles_respeta_maximo(self):
        s = ci.LecturaSuelo(humedad=65, temp_suelo=25, ph=6.5, nitrogeno=500, fosforo=500, potasio=500)
        bd = ci.BaseDatosPlantas()
        self.assertGreater(len(bd.buscar_compatibles(s, maximo=99)), 3)
        self.assertEqual(len(bd.buscar_compatibles(s)), 3)

    def test_suelo_sin_compatibles(self):
        s = ci.LecturaSuelo(humedad=65, temp_suelo=25, ph=3.0, nitrogeno=0, fosforo=0, potasio=0)
        self.assertEqual(ci.BaseDatosPlantas().buscar_compatibles(s), [])


# ============================ SENSORES ============================
class TestSensores(unittest.TestCase):
    def test_dht_descarta_datos_fuera_de_rango(self):
        dht = SensorDHT22ESP32(ConexionFalsa({"t": 25.04, "h": 60.0}))
        self.assertEqual(dht.leer(), (25.0, 60.0))
        dht._conexion.datos = {"t": 125.0, "h": 100.0}  # lectura corrupta del DHT22
        dht._ultima = None
        self.assertEqual(dht.leer(), (25.0, 60.0))  # conserva la última buena

    def test_dht_sin_dato(self):
        dht = SensorDHT22ESP32(ConexionFalsa({"t": None, "h": None}))
        self.assertEqual(dht.leer(), (0, 0))

    def test_nivel_porcentaje(self):
        nivel = SensorNivelESP32(ConexionFalsa({"d": 3.5}), altura_tanque_cm=7.0)
        self.assertAlmostEqual(nivel.leer(), 50.0)
        nivel._conexion.datos = {"d": 0.0}
        self.assertAlmostEqual(nivel.leer(), 100.0)
        nivel._conexion.datos = {"d": 20.0}  # más lejos que el fondo
        self.assertAlmostEqual(nivel.leer(), 0.0)

    def test_nivel_sin_eco_es_cero(self):
        self.assertEqual(SensorNivelESP32(ConexionFalsa({"d": None})).leer(), 0.0)

    def test_suelo_escala_registros(self):
        crudos = [453, 251, 812, 65, 40, 25, 200]  # hum, temp, ec, ph, N, P, K
        s = SensorSueloESP32(ConexionFalsa({"s": crudos})).leer()
        self.assertAlmostEqual(s.humedad, 45.3)
        self.assertAlmostEqual(s.temp_suelo, 25.1)
        self.assertAlmostEqual(s.ph, 6.5)
        self.assertEqual((s.conductividad, s.nitrogeno, s.fosforo, s.potasio), (812, 40, 25, 200))

    def test_suelo_sin_respuesta(self):
        s = SensorSueloESP32(ConexionFalsa({"s": None})).leer()
        self.assertFalse(s.es_valida)

    def test_crc16_modbus(self):
        # Trama de ejemplo estándar: 01 03 00 00 00 01 -> CRC 84 0A
        self.assertEqual(ci.SensorSueloModbus.crc16(bytes([1, 3, 0, 0, 0, 1])), bytes([0x84, 0x0A]))


# ============================ ACTUADORES ============================
class TestMotorYBomba(unittest.TestCase):
    def test_pwm_se_limita(self):
        m = ci.MotorPuenteH(pwm_max=1000)
        m.pwm = 5000
        self.assertEqual(m.pwm, 1000)
        m.pwm = -3
        self.assertEqual(m.pwm, 0)

    def test_adelante_y_detener(self):
        m = ci.MotorPuenteH()
        with silencio():
            m.adelante(8000)
            self.assertEqual((m._in1, m._in2, m.pwm), (1, 0, 8000))
            m.detener()
        self.assertEqual((m._in1, m._in2, m.pwm), (0, 0, 0))

    def test_bomba_usa_potencia(self):
        m = ci.MotorPuenteH(pwm_max=20000)
        with silencio():
            ci.Bomba(m, potencia=0.5).encender()
        self.assertEqual(m.pwm, 10000)

    def test_procesador_comandos(self):
        m = ci.MotorPuenteH()
        p = ci.ProcesadorComandos(m)
        with silencio():
            p.procesar("vel=1500/")
            self.assertEqual((m._in1, m.pwm), (1, 1500))
            p.procesar("vel=300/")  # < 500 apaga
            self.assertEqual((m._in1, m.pwm), (0, 0))
            p.procesar("vel=abc/")  # basura: apaga
            self.assertEqual(m.pwm, 0)
            p.procesar("hola")  # sin vel=: lo ignora
        self.assertEqual(m.pwm, 0)

    def test_motor_esp32_envia_a_la_placa(self):
        c = ConexionFalsa()
        m = MotorESP32(c, pwm_max=20000)
        with silencio():
            m.adelante(15000)
            m.detener()
        self.assertEqual(c.bombas, [(1, 0, 0.75), (0, 0, 0.0)])

    def test_motor_esp32_sin_conexion_es_simulado(self):
        with silencio():
            MotorESP32(None).adelante(5000)  # no debe fallar


# ============================ PANTALLA ============================
class TestPantalla(unittest.TestCase):
    def test_lcd_esp32_reenvia_lineas(self):
        c = ConexionFalsa()
        PantallaLCDESP32(c).mostrar("Hola", "Mundo")
        self.assertEqual(c.lcds, [["Hola", "Mundo"]])

    def test_lcd_consola_recorta_a_20(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ci.PantallaConsola().mostrar("X" * 30)
        self.assertIn("|" + "X" * 20 + "|", buf.getvalue())


# ============================ CONEXIÓN ESP32 ============================
class TestConexionESP32(unittest.TestCase):
    def test_orden_de_bomba(self):
        c = conexion_sin_puerto()
        c.bomba(1, 0, 0.6)
        self.assertEqual(json.loads(c._ser.escrito), {"m": [1, 0, 60]})
        self.assertTrue(c._ser.escrito.endswith(b"\n"))

    def test_bomba_limita_porcentaje(self):
        c = conexion_sin_puerto()
        c.bomba(1, 0, 3.0)
        self.assertEqual(json.loads(c._ser.escrito)["m"], [1, 0, 100])

    def test_orden_lcd_rellena_y_recorta(self):
        c = conexion_sin_puerto()
        c.lcd(["A" * 25, "Temp 25°C"])
        filas = json.loads(c._ser.escrito)["l"]
        self.assertEqual(len(filas), 4)
        self.assertEqual(filas[0], "A" * 20)
        self.assertEqual(filas[2:], ["", ""])
        self.assertTrue(c._ser.escrito.isascii())  # el ESP32 recibe solo ASCII

    def test_procesa_primera_linea_ok(self):
        c = conexion_sin_puerto()
        recibidos = []
        c._al_recibir = recibidos.append
        c._procesar('OK{"t": 24.5, "h": 61.0, "d": 3.2, "s": null}')
        self.assertEqual(c.lectura()["t"], 24.5)
        self.assertEqual(len(recibidos), 1)

    def test_detecta_error_de_la_placa(self):
        c = conexion_sin_puerto()
        c._procesar("Traceback (most recent call last):")
        with self.assertRaises(ConnectionError):
            c.lectura()

    def test_sin_datos_mucho_tiempo(self):
        c = conexion_sin_puerto()
        c._hora -= ConexionESP32.SIN_DATOS_S + 1
        with self.assertRaises(ConnectionError):
            c.lectura()


# ============================ RIEGO ============================
class TestControladorRiego(unittest.TestCase):
    def setUp(self):
        self.motor = ci.MotorPuenteH()
        self.sensor = mock.Mock()
        self.sensor.leer.return_value = ci.LecturaSuelo(humedad=45)
        self.riego = ci.ControladorRiego(ci.Bomba(self.motor), self.sensor, ci.PantallaConsola(),
                                         umbral_bajo=30, riego_s=5)

    @mock.patch("compu_int.time.sleep")
    def test_riega_si_humedad_baja_y_apaga(self, _sleep):
        estados = []
        self.motor._reportar = lambda: estados.append((self.motor._in1, self.motor.pwm))
        with silencio():
            nueva = self.riego.verificar(ci.LecturaSuelo(humedad=20))
        self.assertEqual(estados, [(1, 20000), (0, 20000)])  # encendió y luego apagó
        self.assertEqual(nueva.humedad, 45)  # vuelve a leer después de regar

    @mock.patch("compu_int.time.sleep")
    def test_no_riega_si_humedad_ok(self, _sleep):
        with silencio():
            self.riego.verificar(ci.LecturaSuelo(humedad=60))
        self.assertEqual(self.motor._in1, 0)
        self.sensor.leer.assert_not_called()

    @mock.patch("compu_int.time.sleep")
    def test_no_riega_con_sensor_en_error(self, _sleep):
        with silencio():
            self.riego.verificar(ci.LecturaSuelo.con_error())
        self.assertEqual(self.motor._in1, 0)


try:
    from PySide6.QtCore import QCoreApplication
    import interfaz_tecnosoil as gui
except ImportError:  # sin PySide6 se saltan solo estas pruebas
    gui = None


@unittest.skipIf(gui is None, "PySide6 no está instalado")
class TestInterfaz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_pantalla_gui_tambien_escribe_lcd_fisica(self):
        ev, c, filas = gui.Eventos(), ConexionFalsa(), []
        ev.lcd.connect(filas.append)
        gui.PantallaGUI(ev, PantallaLCDESP32(c)).mostrar("AMBIENTE", "T: 25 C")
        self.assertEqual(filas, [["AMBIENTE", "T: 25 C", "", ""]])
        self.assertEqual(c.lcds, [["AMBIENTE", "T: 25 C", "", ""]])

    def test_motor_gui_mueve_bomba_real(self):
        ev, c, señales = gui.Eventos(), ConexionFalsa(), []
        ev.motor.connect(lambda *a: señales.append(a))
        m = gui.MotorGUI(ev, conexion=c)
        with silencio():
            m.adelante(20000)
        self.assertEqual(c.bombas, [(1, 0, 1.0)])
        self.assertEqual(señales, [(1, 0, 20000, 20000)])
        self.assertTrue(m.encendido)

    @mock.patch("compu_int.time.sleep")
    @mock.patch("interfaz_tecnosoil.time.sleep")
    def test_riego_pausado_con_poca_agua(self, *_):
        ev, c, estados = gui.Eventos(), ConexionFalsa(), []
        ev.estado.connect(estados.append)
        motor = gui.MotorGUI(ev, conexion=c)
        r = gui.ControladorRiegoGUI(ci.Bomba(motor), mock.Mock(), gui.PantallaGUI(ev), ev, lambda: 5.0)
        r.verificar(ci.LecturaSuelo(humedad=10))
        self.assertEqual(estados, ["Pausada"])
        self.assertEqual(c.bombas, [])  # la bomba nunca se encendió


if __name__ == "__main__":
    unittest.main(verbosity=2)
