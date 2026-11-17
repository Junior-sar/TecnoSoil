import argparse
import json
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass


# ============================ MODELOS ============================
@dataclass
class LecturaSuelo:
    humedad: float = 0.0
    temp_suelo: float = 0.0
    ph: float = 0.0
    conductividad: float = 0.0
    nitrogeno: float = 0.0
    fosforo: float = 0.0
    potasio: float = 0.0

    @classmethod
    def con_error(cls):
        return cls(*([-99.0] * 7))

    @property
    def es_valida(self):
        return self.humedad >= 0.0


@dataclass
class LecturaAmbiente:
    temperatura: int = 0
    humedad: int = 0
    nivel_agua_pct: float = 0.0


@dataclass(frozen=True)
class Rango:
    minimo: float
    maximo: float

    def contiene(self, valor):
        return self.minimo <= valor <= self.maximo


@dataclass(frozen=True)
class Planta:
    nombre: str
    temp_suelo: Rango
    humedad: Rango
    ph: Rango
    nitrogeno_min: int
    fosforo_min: int
    potasio_min: int

    def es_compatible(self, s: LecturaSuelo):
        return (self.temp_suelo.contiene(s.temp_suelo) and self.humedad.contiene(s.humedad)
                and self.ph.contiene(s.ph) and s.nitrogeno >= self.nitrogeno_min
                and s.fosforo >= self.fosforo_min and s.potasio >= self.potasio_min)


class BaseDatosPlantas:
    # Nombre, T_Suelo(min,max), Hum(min,max), pH(min,max), N_min, P_min, K_min (mg/kg)
    # P y K de Tomate, Frijol, Maiz, Pimiento, Name, Berenjena y Calabaza: nivel adecuado segun Cenicafe
    # (P 20-30 mg/kg; K 0,4 cmol/kg = 156 mg/kg). Antes pedian 300-420 mg/kg, valores no reales.
    DATOS = [
        ("Tomate", 20, 30, 60, 80, 6.0, 7.5, 30, 20, 156), ("Frijol", 20, 30, 50, 70, 6.0, 7.5, 30, 20, 156),
        ("Maiz", 20, 34, 55, 75, 5.8, 7.0, 160, 20, 156), ("Pimiento", 21, 32, 55, 75, 6.0, 7.0, 155, 20, 156),
        ("Albahaca", 18, 28, 60, 80, 6.0, 7.5, 90, 35, 75), ("Zanahoria", 10, 24, 50, 70, 5.8, 6.8, 70, 50, 90),
        ("Pepino", 21, 30, 60, 80, 6.0, 7.0, 110, 250, 280), ("Menta", 15, 25, 75, 90, 6.0, 7.5, 70, 20, 60),
        ("Ñame", 25, 35, 85, 99, 5.0, 7.0, 150, 20, 156), ("Mani", 25, 35, 50, 70, 6.0, 7.5, 80, 200, 200),
        ("Yuca", 20, 35, 40, 70, 5.0, 7.0, 60, 40, 80), ("Batata", 20, 30, 50, 70, 5.5, 6.5, 70, 60, 150),
        ("Berenjena", 22, 32, 60, 80, 6.0, 7.0, 140, 20, 156), ("Sandia", 20, 30, 40, 70, 6.0, 7.0, 90, 60, 120),
        ("Melon", 20, 30, 50, 75, 6.0, 7.5, 100, 70, 140), ("Espinaca", 10, 24, 60, 80, 6.0, 7.5, 120, 40, 100),
        ("Cebolla", 12, 25, 50, 70, 6.0, 7.5, 80, 50, 90), ("Calabaza", 20, 32, 60, 80, 6.0, 7.5, 130, 20, 156),
        ("Acelga", 12, 25, 60, 85, 6.0, 7.5, 110, 50, 150), ("Cafe", 18, 25, 60, 80, 5.0, 6.5, 150, 200, 250),
        ("Arandano", 15, 25, 50, 85, 4.0, 5.5, 50, 20, 40), ("Piña", 20, 35, 40, 80, 4.5, 5.5, 80, 40, 80),
        ("Camelia", 10, 25, 50, 80, 4.5, 6.0, 40, 30, 60), ("Esparrago", 15, 30, 50, 80, 6.5, 8.5, 80, 40, 80),
        ("Lavanda", 15, 35, 20, 50, 6.5, 8.5, 20, 20, 40), ("Remolacha", 10, 25, 50, 75, 6.5, 8.0, 100, 50, 150),
        ("Ajo", 5, 20, 40, 70, 5.5, 7.5, 70, 30, 50), ("Col Kale", 5, 20, 50, 85, 6.0, 7.5, 100, 40, 80),
        ("Haba", 5, 18, 50, 75, 6.0, 7.5, 40, 40, 80), ("Rabano", 5, 25, 50, 85, 5.5, 7.0, 40, 30, 40),
        ("AloeVera", 15, 40, 5, 40, 6.0, 8.0, 10, 10, 10), ("Nopal", 10, 45, 5, 35, 5.5, 8.5, 20, 20, 20),
        ("Agave", 15, 40, 5, 30, 6.0, 8.0, 15, 15, 15), ("Malanga", 20, 35, 70, 100, 5.5, 7.0, 100, 50, 100),
        ("Arroz", 15, 35, 90, 100, 6.0, 8.0, 50, 40, 50), ("Girasol", 15, 35, 30, 70, 5.5, 7.8, 40, 30, 50),
        ("Tuberculos", 10, 30, 40, 80, 5.0, 7.5, 60, 40, 80),
    ]

    def __init__(self):
        self._plantas = [Planta(n, Rango(a, b), Rango(c, d), Rango(e, f), N, P, K)
                         for n, a, b, c, d, e, f, N, P, K in self.DATOS]

    @property
    def plantas(self):
        return tuple(self._plantas)

    def buscar_compatibles(self, lectura, maximo=3):
        return [p for p in self._plantas if p.es_compatible(lectura)][:maximo]


class Sensor(ABC):
    @abstractmethod
    def leer(self): ...


class SensorDHT11(Sensor):
    """Lee cada 2 s y descarta datos corruptos (conserva la última lectura buena)."""

    def __init__(self, intervalo_s=2.0):
        self._intervalo, self._ultima, self._valor = intervalo_s, None, (0, 0)

    def leer(self):
        ahora = time.monotonic()
        if self._ultima is None or ahora - self._ultima > self._intervalo:
            self._ultima = ahora
            t, h = self._leer_crudo()
            if 0 < t < 60 and 0 < h < 100:
                self._valor = (t, h)
        return self._valor

    def _leer_crudo(self):  # simulado
        return random.randint(24, 34), random.randint(45, 85)


class SensorNivel(Sensor):
    """Ultrasonido SRF04: convierte distancia a % de llenado del tanque."""

    def __init__(self, altura_tanque_cm=7.0, altura_lleno_cm=0.0):
        self._alto, self._lleno = altura_tanque_cm, altura_lleno_cm

    def leer(self):
        d = min(self._medir_cm(), self._alto)
        return max(0.0, min(100.0, (self._alto - d) / (self._alto - self._lleno) * 100))

    def _medir_cm(self):  # simulado
        return random.uniform(0.5, 8.0)


class SensorSuelo(Sensor):
    """Sensor 7-en-1. Las subclases solo implementan _leer_registro()."""

    REGISTROS = ["humedad", "temp_suelo", "conductividad", "ph", "nitrogeno", "fosforo", "potasio"]
    ESCALA = {"humedad": 10, "temp_suelo": 10, "ph": 10}

    def leer(self):
        valores = {}
        for direccion, campo in enumerate(self.REGISTROS):
            crudo = self._leer_registro(direccion)
            if crudo is None:
                return LecturaSuelo.con_error()
            valores[campo] = crudo / self.ESCALA.get(campo, 1)
        return LecturaSuelo(**valores)

    @abstractmethod
    def _leer_registro(self, direccion): ...


class SensorSueloSimulado(SensorSuelo):
    RANGOS = [(150, 750), (200, 300), (500, 900), (55, 72), (30, 160), (20, 420), (40, 410)]

    def _leer_registro(self, direccion):
        return random.randint(*self.RANGOS[direccion])


class SensorSueloSimuladoEstable(SensorSuelo):
    """Suelo simulado con valores de un suelo agrícola típico que cambian poco entre lecturas
    (paseo aleatorio acotado), para demostraciones sin tierra. Se muestra como "Simulado"."""

    BASE = [452, 262, 480, 65, 48, 26, 182]      # hum 45.2 %, 26.2 °C, 480 uS/cm, pH 6.5, N, P, K
    PASO = [4, 2, 6, 1, 1, 1, 2]                 # cambio máximo por lectura (en unidades crudas)
    MARGEN = [25, 12, 40, 3, 5, 3, 12]           # cuánto se puede alejar de la base

    def __init__(self):
        self._actual = list(self.BASE)

    def _leer_registro(self, direccion):
        if direccion == 0:                       # una lectura completa empieza en el registro 0
            for i, base in enumerate(self.BASE):
                v = self._actual[i] + random.randint(-self.PASO[i], self.PASO[i])
                self._actual[i] = max(base - self.MARGEN[i], min(base + self.MARGEN[i], v))
        return self._actual[direccion]


class SensorSueloModbus(SensorSuelo):
    """Modbus RTU por adaptador USB-RS485 (4800 baudios, ID 1, función 0x03)."""

    def __init__(self, puerto, id_esclavo=1):
        import serial
        self._ser = serial.Serial(puerto, 4800, timeout=2.0)
        self._id = id_esclavo

    @staticmethod
    def crc16(trama):
        crc = 0xFFFF
        for b in trama:
            crc ^= b
            for _ in range(8):
                crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        return crc.to_bytes(2, "little")

    def _leer_registro(self, direccion):
        trama = bytes([self._id, 0x03, 0, direccion, 0, 1])
        self._ser.reset_input_buffer()
        self._ser.write(trama + self.crc16(trama))
        resp = self._ser.read(7)
        time.sleep(0.05)
        if len(resp) != 7 or resp[:3] != bytes([self._id, 0x03, 0x02]):
            return None
        if self.crc16(resp[:5]) != resp[5:]:  # trama dañada por ruido
            return None
        return int.from_bytes(resp[3:5], "big", signed=True)


# ============================ ACTUADORES ============================
class MotorPuenteH:
    def __init__(self, pwm_max=20000):
        self._pwm_max, self._pwm, self._in1, self._in2 = pwm_max, 0, 0, 0

    @property
    def pwm(self):
        return self._pwm

    @pwm.setter
    def pwm(self, valor):
        self._pwm = max(0, min(int(valor), self._pwm_max))

    @property
    def pwm_max(self):
        return self._pwm_max

    def adelante(self, pwm=None):
        self._in1, self._in2 = 1, 0
        if pwm is not None:
            self.pwm = pwm
        self._reportar()

    def detener(self, cortar_pwm=True):
        self._in1, self._in2 = 0, 0
        if cortar_pwm:
            self.pwm = 0
        self._reportar()

    def _reportar(self):
        print(f"[MOTOR] IN1={self._in1} IN2={self._in2} PWM={self._pwm}/{self._pwm_max}")


class Bomba:
    """potencia: fracción del PWM máximo usada al regar (1.0 = 100 %)."""

    def __init__(self, motor: MotorPuenteH, potencia=1.0):
        self._motor, self.potencia = motor, potencia

    def encender(self):
        self._motor.adelante(round(self._motor.pwm_max * self.potencia))

    def apagar(self):
        self._motor.detener(cortar_pwm=False)


# ============================ PANTALLA ============================
class Pantalla(ABC):
    @abstractmethod
    def mostrar(self, *lineas): ...


class PantallaConsola(Pantalla):
    """LCD 20x4 dibujado en consola."""

    def mostrar(self, *lineas):
        print("\n+" + "-" * 20 + "+")
        for i in range(4):
            texto = lineas[i] if i < len(lineas) else ""
            print("|" + texto[:20].ljust(20) + "|")
        print("+" + "-" * 20 + "+")


# ============================ COMUNICACIÓN ============================
class Canal(ABC):
    def __init__(self):
        self._oyentes = []

    def al_recibir(self, funcion):
        self._oyentes.append(funcion)

    def _notificar(self, trama):
        for f in self._oyentes:
            f(trama)

    def enviar_json(self, objeto):
        self.enviar(json.dumps(objeto, ensure_ascii=False, separators=(",", ":")) + "\r\n")

    @abstractmethod
    def enviar(self, texto): ...


class CanalConsola(Canal):
    def enviar(self, texto):
        print(f"[DATOS] {texto.strip()}")


class ProcesadorComandos:
    """Interpreta 'vel=XXXX/': < 500 apaga el motor, si no lo enciende con ese PWM."""

    def __init__(self, motor: MotorPuenteH):
        self._motor = motor

    def procesar(self, trama):
        if "vel=" not in trama:
            return
        try:
            ancho = int(trama.split("=", 1)[1].split("/", 1)[0])
        except ValueError:
            ancho = 0
        self._motor.detener() if ancho < 500 else self._motor.adelante(ancho)


# ============================ SISTEMA ============================
class ControladorRiego:
    def __init__(self, bomba, sensor, pantalla, umbral_bajo=30.0, umbral_sensor=1.0, riego_s=5):
        self._bomba, self._sensor, self._pantalla = bomba, sensor, pantalla
        self.umbral_bajo, self.umbral_sensor, self.riego_s = umbral_bajo, umbral_sensor, riego_s

    def verificar(self, s: LecturaSuelo):
        if not (self.umbral_sensor < s.humedad < self.umbral_bajo):
            self._pantalla.mostrar("Humedad Optima", f"Actual: {s.humedad:.1f}%")
            time.sleep(0.5)
            return s
        self._pantalla.mostrar("Humedad BAJA", f"Cur:{s.humedad:.1f}% < Min:{self.umbral_bajo:.1f}%")
        time.sleep(0.5)
        self._pantalla.mostrar("Activando Bomba", f"Regando {self.riego_s}s...")
        self._bomba.encender()
        try:
            time.sleep(self.riego_s)
        finally:  # la bomba se apaga aunque se interrumpa el programa (Ctrl+C)
            self._bomba.apagar()
        self._pantalla.mostrar("Riego Completo", "Re-Leyendo...")
        time.sleep(0.5)
        return self._sensor.leer()


class SistemaTecnoSoil:
    def __init__(self, sensor_suelo: SensorSuelo, canal: Canal):
        self._dht, self._nivel, self._suelo = SensorDHT11(), SensorNivel(), sensor_suelo
        self._motor, self._pantalla, self._canal = MotorPuenteH(), PantallaConsola(), canal
        self._plantas = BaseDatosPlantas()
        self._riego = ControladorRiego(Bomba(self._motor), sensor_suelo, self._pantalla)
        self._canal.al_recibir(ProcesadorComandos(self._motor).procesar)
        self.ambiente, self.suelo = LecturaAmbiente(), LecturaSuelo()

    def mostrar_ambiente(self):
        t, h = self._dht.leer()
        a = self.ambiente = LecturaAmbiente(t, h, self._nivel.leer())
        self._pantalla.mostrar("  AMBIENTE Y AGUA", f"T.Aire: {a.temperatura or '--'} C",
                               f"H.Aire: {a.humedad or '--'} %", f"N.Agua: {a.nivel_agua_pct:.0f} %")
        time.sleep(3)

    def mostrar_suelo(self):
        s = self.suelo = self._riego.verificar(self._suelo.leer())
        self._pantalla.mostrar("SUELO - FISICO", f"T:{s.temp_suelo:.1f}C  H:{s.humedad:.1f}%",
                               f"pH: {s.ph:.1f}", f"EC: {s.conductividad:.0f} us/cm")
        a = self.ambiente
        self._canal.enviar_json({
            "t_aire": a.temperatura, "h_aire": a.humedad, "nivel_agua": round(a.nivel_agua_pct),
            "h_suelo": round(s.humedad, 1), "t_suelo": round(s.temp_suelo, 1), "ec": round(s.conductividad),
            "ph": round(s.ph, 1), "n": round(s.nitrogeno), "p": round(s.fosforo), "k": round(s.potasio)})
        time.sleep(3)

    def mostrar_npk(self):
        s = self.suelo
        self._pantalla.mostrar(f"N:{s.nitrogeno:.0f}   P:{s.fosforo:.0f}", f"K:{s.potasio:.0f}   (mg/kg)", "-" * 20)
        time.sleep(2)

    def sugerir_cultivos(self):
        if not self.suelo.es_valida:
            return
        compatibles = [p.nombre for p in self._plantas.buscar_compatibles(self.suelo)]
        nombres = ", ".join(compatibles) or "Ninguno"
        self._pantalla.mostrar("Sugerencias:", *(compatibles or ["Ninguno"]))  # un cultivo por fila del LCD
        time.sleep(2)
        self._canal.enviar_json({"cultivo": nombres})
        time.sleep(0.5)

    def ejecutar(self):
        self._motor.detener()
        self._pantalla.mostrar("Iniciando...", "TecnoSoil")
        time.sleep(0.5)
        while True:
            self.mostrar_ambiente()
            self.mostrar_suelo()
            self.mostrar_npk()
            self.sugerir_cultivos()


# ============================ MAIN ============================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TecnoSoil en Python (POO)")
    parser.add_argument("--puerto-suelo", help="Adaptador USB-RS485 del sensor 7-en-1 (ej. COM5)")
    args = parser.parse_args()

    sensor = SensorSueloModbus(args.puerto_suelo) if args.puerto_suelo else SensorSueloSimulado()
    canal = CanalConsola()
    try:
        SistemaTecnoSoil(sensor, canal).ejecutar()
    except KeyboardInterrupt:
        print("\nDetenido.")