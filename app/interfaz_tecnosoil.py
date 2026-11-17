
import argparse
import csv
import sys
import time
from collections import deque
from datetime import datetime

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPen, QTextOption
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSlider, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from compu_int import (
    BaseDatosPlantas, Bomba, Canal, CanalConsola, ControladorRiego, LecturaAmbiente,
    LecturaSuelo, MotorPuenteH, Pantalla, ProcesadorComandos, SensorDHT11, SensorNivel,
    SensorSueloModbus, SensorSueloSimulado, SistemaTecnoSoil,
)
from esp32_tecnosoil import (
    ConexionESP32, MotorESP32, PantallaLCDESP32, SensorDHT22ESP32, SensorNivelESP32, SensorSueloESP32,
)

SIMULADO = "Simulado"
POR_ESP32 = "Lo lee el ESP32"


# ============================ PUENTE HILO -> GUI ============================
class Eventos(QObject):
    """Señales que el hilo de lectura emite y la ventana recibe (signal/slot)."""

    lcd = Signal(list)
    motor = Signal(int, int, int, int)  # in1, in2, pwm, pwm_max
    tx = Signal(str)
    rx = Signal(str)
    estado = Signal(str)
    ambiente = Signal(object)
    suelo = Signal(object)
    cultivos = Signal(list)
    error = Signal(str)
    esp32 = Signal(dict)  # última línea recibida del ESP32

class PantallaGUI(Pantalla):
    """Dibuja el LCD en la ventana y, si hay una pantalla física (LCD del ESP32), también en ella."""

    def __init__(self, eventos: Eventos, fisica: Pantalla = None):
        self._ev, self._fisica = eventos, fisica

    def mostrar(self, *lineas):
        filas = [(lineas[i] if i < len(lineas) else "")[:20] for i in range(4)]
        self._ev.lcd.emit(filas)
        if self._fisica:
            self._fisica.mostrar(*filas)


class MotorGUI(MotorESP32):
    """Informa a la GUI el estado del puente H; con conexión, además mueve la bomba real."""

    def __init__(self, eventos: Eventos, pwm_max=20000, conexion: ConexionESP32 = None):
        super().__init__(conexion, pwm_max)
        self._ev = eventos

    @property
    def encendido(self):
        return self._in1 == 1 and self._pwm > 0

    def _reportar(self):
        super()._reportar()
        self._ev.motor.emit(self._in1, self._in2, self._pwm, self._pwm_max)


class CanalGUI(Canal):
    """Decorador: envía por el canal real (consola o serial) y además lo muestra en la GUI."""

    def __init__(self, interno: Canal, eventos: Eventos):
        super().__init__()
        self._interno, self._ev = interno, eventos
        interno.al_recibir(self._recibido)

    def _recibido(self, trama):
        self._ev.rx.emit(trama.strip())
        self._notificar(trama)

    def enviar(self, texto):
        self._interno.enviar(texto)
        self._ev.tx.emit(texto.strip())


class ControladorRiegoGUI(ControladorRiego):
    """Igual al original, más el estado 'Pausada' del diagrama de estados (nivel de agua bajo)."""

    def __init__(self, bomba, sensor, pantalla, eventos: Eventos, nivel_agua):
        super().__init__(bomba, sensor, pantalla)
        self._ev, self._nivel_agua = eventos, nivel_agua
        self.riego_automatico, self.nivel_minimo = True, 15.0

    def necesita_riego(self, s: LecturaSuelo):
        return self.umbral_sensor < s.humedad < self.umbral_bajo

    def verificar(self, s: LecturaSuelo):
        if not s.es_valida:
            return s
        if self.necesita_riego(s) and self.riego_automatico:
            if self._nivel_agua() < self.nivel_minimo:
                self._ev.estado.emit("Pausada")
                self._pantalla.mostrar("Riego PAUSADO", "Nivel de agua bajo",
                                       f"Agua: {self._nivel_agua():.0f}%")
                time.sleep(1.5)
                return s
            self._ev.estado.emit("Regando")
            s = super().verificar(s)
            self._ev.estado.emit("Leyendo propiedades")
            return s
        if self.necesita_riego(s):  # riego automático desactivado
            self._pantalla.mostrar("Humedad BAJA", "Riego auto: OFF")
            time.sleep(0.5)
            return s
        return super().verificar(s)


class SistemaGUI(SistemaTecnoSoil):
    """Mismo ciclo de SistemaTecnoSoil, con pantalla, motor y canal inyectados para la GUI."""

    def __init__(self, sensor_suelo, canal: Canal, eventos: Eventos, dht=None, nivel=None, conexion=None):
        # No se llama a super().__init__ porque ese crea PantallaConsola y MotorPuenteH fijos.
        # Con conexion (ESP32) la bomba y el LCD son los reales; sin ella, simulados en la ventana.
        self._ev = eventos
        self._dht, self._nivel, self._suelo = dht or SensorDHT11(), nivel or SensorNivel(), sensor_suelo
        self._motor = MotorGUI(eventos, conexion=conexion)
        self._pantalla = PantallaGUI(eventos, PantallaLCDESP32(conexion) if conexion else None)
        self._canal = CanalGUI(canal, eventos)
        self._plantas = BaseDatosPlantas()
        self.riego = ControladorRiegoGUI(Bomba(self._motor), sensor_suelo, self._pantalla, eventos,
                                         lambda: self.ambiente.nivel_agua_pct)
        self._riego = self.riego
        self.comandos = ProcesadorComandos(self._motor)
        self._canal.al_recibir(self.comandos.procesar)
        self.ambiente, self.suelo = LecturaAmbiente(), LecturaSuelo()

    @property
    def plantas(self):
        return self._plantas

    @property
    def motor(self):
        return self._motor

    # Se reescriben para avisar a la GUI antes de la pausa de 3 s (así tarjetas y LCD coinciden).
    def mostrar_ambiente(self):
        t, h = self._dht.leer()
        a = self.ambiente = LecturaAmbiente(t, h, self._nivel.leer())
        self._ev.ambiente.emit(a)
        self._pantalla.mostrar("  AMBIENTE Y AGUA", f"T.Aire: {a.temperatura or '--'} C",
                               f"H.Aire: {a.humedad or '--'} %", f"N.Agua: {a.nivel_agua_pct:.0f} %")
        time.sleep(3)

    def mostrar_suelo(self):
        s = self.suelo = self._riego.verificar(self._suelo.leer())
        self._ev.suelo.emit(s)
        a = self.ambiente
        if not s.es_valida:  # no se envían ni se muestran los -99 de error como si fueran datos
            self._pantalla.mostrar("SUELO - SIN DATOS", "7-en-1 no responde")
            self._canal.enviar_json({"t_aire": a.temperatura, "h_aire": a.humedad,
                                     "nivel_agua": round(a.nivel_agua_pct)})
            time.sleep(3)
            return
        self._pantalla.mostrar("SUELO - FISICO", f"T:{s.temp_suelo:.1f}C  H:{s.humedad:.1f}%",
                               f"pH: {s.ph:.1f}", f"EC: {s.conductividad:.0f} us/cm")
        self._canal.enviar_json({
            "t_aire": a.temperatura, "h_aire": a.humedad, "nivel_agua": round(a.nivel_agua_pct),
            "h_suelo": round(s.humedad, 1), "t_suelo": round(s.temp_suelo, 1), "ec": round(s.conductividad),
            "ph": round(s.ph, 1), "n": round(s.nitrogeno), "p": round(s.fosforo), "k": round(s.potasio)})
        time.sleep(3)

    def mostrar_npk(self):
        if self.suelo.es_valida:
            super().mostrar_npk()

    def sugerir_cultivos(self):
        if self.suelo.es_valida:
            self._ev.cultivos.emit([p.nombre for p in self._plantas.buscar_compatibles(self.suelo)])
        super().sugerir_cultivos()

    def pasos(self):
        return [self.mostrar_ambiente, self.mostrar_suelo, self.mostrar_npk, self.sugerir_cultivos]


class HiloLectura(QThread):
    """Ejecuta el ciclo de SistemaTecnoSoil paso a paso hasta que se pida detener."""

    def __init__(self, sistema: SistemaGUI, eventos: Eventos):
        super().__init__()
        self._sistema, self._ev = sistema, eventos

    def run(self):
        try:
            self._sistema.motor.detener()
            self._sistema._pantalla.mostrar("Iniciando...", "TecnoSoil")
            time.sleep(0.5)
            while not self.isInterruptionRequested():
                self._ev.estado.emit("Leyendo propiedades")
                for paso in self._sistema.pasos():
                    if self.isInterruptionRequested():
                        break
                    paso()
        except Exception as e:  # p. ej. se desconecta el adaptador serial
            self._ev.error.emit(str(e))
        finally:
            self._sistema.motor.detener()
            self._sistema._pantalla.mostrar("Sistema detenido", "TecnoSoil")
            self._ev.estado.emit("Inactiva")


# ============================ WIDGETS ============================
COLORES_ESTADO = {
    "Inactiva": "#7a7f87", "Leyendo propiedades": "#2f7dd1",
    "Regando": "#1f9d55", "Pausada": "#d9822b",
}


class LCD20x4(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("lcd")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(0)
        fuente = QFont("Consolas")
        fuente.setStyleHint(QFont.Monospace)
        fuente.setPointSize(15)
        fuente.setBold(True)
        self._filas = []
        for _ in range(4):
            lbl = QLabel(" " * 20)
            lbl.setFont(fuente)
            lbl.setObjectName("lcdTexto")
            lay.addWidget(lbl)
            self._filas.append(lbl)

    def mostrar(self, lineas):
        for lbl, txt in zip(self._filas, lineas):
            lbl.setText(txt.ljust(20))


class Tarjeta(QFrame):
    """Muestra una variable: título, valor grande y unidad."""

    def __init__(self, titulo, unidad, decimales=1):
        super().__init__()
        self.setObjectName("tarjeta")
        self._dec, self._unidad = decimales, unidad
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        t = QLabel(titulo)
        t.setObjectName("tarjetaTitulo")
        self._valor = QLabel("--")
        self._valor.setObjectName("tarjetaValor")
        lay.addWidget(t)
        lay.addWidget(self._valor)

    def set_valor(self, v, alerta=False):
        texto = "--" if v is None else f"{v:.{self._dec}f} {self._unidad}"
        self._valor.setText(texto)
        self._valor.setProperty("alerta", alerta)
        self._valor.style().unpolish(self._valor)
        self._valor.style().polish(self._valor)


class GraficaTendencia(QWidget):
    """Gráfica de líneas simple con QPainter (sin dependencias extra)."""

    SERIES = [("Humedad suelo %", "#2f7dd1"), ("Temp. suelo °C", "#d9534f"),
              ("Nivel agua %", "#17a2b8"), ("Humedad aire %", "#8e6cc2")]

    def __init__(self, puntos=60):
        super().__init__()
        self.setMinimumHeight(220)
        self._datos = [deque(maxlen=puntos) for _ in self.SERIES]
        self._umbral = None

    def agregar(self, valores, umbral):
        for d, v in zip(self._datos, valores):
            d.append(v)
        self._umbral = umbral
        self.update()

    def limpiar(self):
        for d in self._datos:
            d.clear()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        area = QRectF(44, 12, self.width() - 56, self.height() - 44)
        p.setPen(QPen(pal.mid().color(), 1))
        p.setFont(QFont(self.font().family(), 8))
        for v in range(0, 101, 25):
            y = area.bottom() - v / 100 * area.height()
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.drawText(QRectF(0, y - 8, 38, 16), Qt.AlignRight | Qt.AlignVCenter, str(v))
        if self._umbral is not None:
            y = area.bottom() - self._umbral / 100 * area.height()
            p.setPen(QPen(QColor("#2f7dd1"), 1, Qt.DashLine))
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
        for (nombre, color), d in zip(self.SERIES, self._datos):
            if len(d) < 2:
                continue
            paso = area.width() / (d.maxlen - 1)
            camino = QPainterPath()
            nuevo = True
            for i, v in enumerate(d):
                if v is None:  # sin dato: la línea se corta
                    nuevo = True
                    continue
                pt = QPointF(area.left() + i * paso, area.bottom() - max(0, min(v, 100)) / 100 * area.height())
                camino.moveTo(pt) if nuevo else camino.lineTo(pt)
                nuevo = False
            p.setPen(QPen(QColor(color), 2))
            p.drawPath(camino)
        x = area.left()
        for nombre, color in self.SERIES:
            p.setPen(QPen(QColor(color), 3))
            p.drawLine(QPointF(x, self.height() - 14), QPointF(x + 16, self.height() - 14))
            p.setPen(pal.text().color())
            p.drawText(QPointF(x + 20, self.height() - 10), nombre)
            x += 130
        p.setPen(pal.text().color())
        p.drawText(QPointF(area.right() - 150, area.top() + 12), "- - umbral de riego")


# ============================ VENTANA PRINCIPAL ============================
class VentanaTecnoSoil(QMainWindow):
    def __init__(self, puerto_suelo=None, puerto_esp32=None):
        super().__init__()
        self.setWindowTitle("TecnoSoil · AgroControl")
        self.resize(1280, 820)
        self.ev = Eventos()
        self.sistema, self.hilo, self.conexion = None, None, None
        self._ultima_dist = None
        self.registros = []  # filas para CSV
        self._ultimo_ambiente = LecturaAmbiente()
        self._plantas = BaseDatosPlantas()

        self._construir()
        self._conectar_senales()
        self._refrescar_puertos(puerto_suelo, puerto_esp32)
        self._cambiar_estado("Inactiva")
        self.lcd.mostrar(["   TecnoSoil", "Presione Iniciar", "", ""])

    # ---------- construcción ----------
    def _construir(self):
        central = QWidget()
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)

        # Barra superior
        barra = QHBoxLayout()
        titulo = QLabel("TecnoSoil · AgroControl")
        titulo.setObjectName("titulo")
        self.lbl_estado = QLabel()
        self.lbl_estado.setObjectName("estado")
        self.btn_iniciar = QPushButton("▶ Iniciar")
        self.btn_detener = QPushButton("■ Detener")
        self.btn_detener.setEnabled(False)
        barra.addWidget(titulo)
        barra.addStretch()
        barra.addWidget(QLabel("Estado:"))
        barra.addWidget(self.lbl_estado)
        barra.addSpacing(16)
        barra.addWidget(self.btn_iniciar)
        barra.addWidget(self.btn_detener)
        raiz.addLayout(barra)

        cuerpo = QHBoxLayout()
        raiz.addLayout(cuerpo, 1)

        # Columna izquierda: configuración y control
        izq = QVBoxLayout()
        cuerpo.addLayout(izq, 0)

        g_con = QGroupBox("Conexión")
        f = QGridLayout(g_con)
        self.cb_esp32, self.cb_suelo = QComboBox(), QComboBox()
        self.cb_esp32.setEditable(True)
        self.cb_suelo.setEditable(True)
        self.sp_tanque = QDoubleSpinBox(suffix=" cm", minimum=1, maximum=400, value=7.0, decimals=1)
        self.btn_puertos = QPushButton("Actualizar puertos")
        f.addWidget(QLabel("ESP32 (todos los sensores):"), 0, 0)
        f.addWidget(self.cb_esp32, 0, 1)
        f.addWidget(QLabel("Altura del tanque:"), 1, 0)
        f.addWidget(self.sp_tanque, 1, 1)
        f.addWidget(QLabel("Sensor 7-en-1 (RS485):"), 2, 0)
        f.addWidget(self.cb_suelo, 2, 1)
        f.addWidget(self.btn_puertos, 3, 0, 1, 2)
        izq.addWidget(g_con)

        g_riego = QGroupBox("Riego automático")
        f = QGridLayout(g_riego)
        self.chk_auto = QCheckBox("Activar riego automático")
        self.chk_auto.setChecked(True)
        self.sp_umbral = QDoubleSpinBox(suffix=" %", minimum=1, maximum=99, value=30.0, decimals=1)
        self.sp_tiempo = QSpinBox(suffix=" s", minimum=1, maximum=60, value=5)
        self.sp_nivel = QDoubleSpinBox(suffix=" %", minimum=0, maximum=100, value=15.0, decimals=0)
        f.addWidget(self.chk_auto, 0, 0, 1, 2)
        f.addWidget(QLabel("Regar si humedad <"), 1, 0)
        f.addWidget(self.sp_umbral, 1, 1)
        f.addWidget(QLabel("Tiempo de riego"), 2, 0)
        f.addWidget(self.sp_tiempo, 2, 1)
        f.addWidget(QLabel("Pausar si agua <"), 3, 0)
        f.addWidget(self.sp_nivel, 3, 1)
        izq.addWidget(g_riego)

        g_bomba = QGroupBox("Bomba (puente H)")
        f = QGridLayout(g_bomba)
        self.sl_pwm = QSlider(Qt.Horizontal, minimum=0, maximum=20000, value=10000, singleStep=500)
        self.lbl_pwm = QLabel("10000")
        self.btn_on = QPushButton("Encender")
        self.btn_off = QPushButton("Apagar")
        self.lbl_motor = QLabel("IN1=0  IN2=0  PWM=0")
        self.lbl_motor.setObjectName("motor")
        f.addWidget(QLabel("PWM manual:"), 0, 0)
        f.addWidget(self.lbl_pwm, 0, 1, Qt.AlignRight)
        f.addWidget(self.sl_pwm, 1, 0, 1, 2)
        f.addWidget(self.btn_on, 2, 0)
        f.addWidget(self.btn_off, 2, 1)
        f.addWidget(self.lbl_motor, 3, 0, 1, 2)
        nota = QLabel("Envía el comando vel=XXXX/ (< 500 apaga). "
                      "Con el ESP32 mueve la bomba real (IN1=21, IN2=47, ENA=15).")
        nota.setWordWrap(True)
        nota.setObjectName("nota")
        f.addWidget(nota, 4, 0, 1, 2)
        izq.addWidget(g_bomba)

        self.btn_csv = QPushButton("Guardar lecturas en CSV")
        izq.addWidget(self.btn_csv)
        izq.addStretch()

        # Columna central: tarjetas
        centro = QVBoxLayout()
        cuerpo.addLayout(centro, 1)

        g_amb = QGroupBox("Ambiente y agua (DHT + ultrasonido)")
        f = QGridLayout(g_amb)
        self.t_taire = Tarjeta("Temperatura aire", "°C")
        self.t_haire = Tarjeta("Humedad aire", "%")
        self.t_nivel = Tarjeta("Nivel de agua", "%", 0)
        self.t_dist = Tarjeta("Distancia (ultrasonido)", "cm")
        self.pb_nivel = QProgressBar(maximum=100, textVisible=False)
        f.addWidget(self.t_taire, 0, 0)
        f.addWidget(self.t_haire, 0, 1)
        f.addWidget(self.t_nivel, 0, 2)
        f.addWidget(self.t_dist, 0, 3)
        f.addWidget(self.pb_nivel, 1, 2)
        centro.addWidget(g_amb)

        g_suelo = QGroupBox("Suelo (sensor 7-en-1)")
        f = QGridLayout(g_suelo)
        self.t_hsuelo = Tarjeta("Humedad suelo", "%")
        self.t_tsuelo = Tarjeta("Temperatura suelo", "°C")
        self.t_ph = Tarjeta("pH", "")
        self.t_ec = Tarjeta("Conductividad", "µS/cm", 0)
        self.t_n = Tarjeta("Nitrógeno (N)", "mg/kg", 0)
        self.t_p = Tarjeta("Fósforo (P)", "mg/kg", 0)
        self.t_k = Tarjeta("Potasio (K)", "mg/kg", 0)
        for i, t in enumerate([self.t_hsuelo, self.t_tsuelo, self.t_ph, self.t_ec,
                               self.t_n, self.t_p, self.t_k]):
            f.addWidget(t, i // 4, i % 4)
        centro.addWidget(g_suelo)

        g_cult = QGroupBox("Cultivos sugeridos")
        h = QHBoxLayout(g_cult)
        self.lbl_cultivos = QLabel("Sin lecturas todavía")
        self.lbl_cultivos.setObjectName("cultivos")
        self.lbl_cultivos.setWordWrap(True)
        h.addWidget(self.lbl_cultivos)
        centro.addWidget(g_cult)

        self.tabs = QTabWidget()
        self.grafica = GraficaTendencia()
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setMaximumBlockCount(500)
        self.log.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.tabla = QTableWidget(0, 8)
        self.tabla.setHorizontalHeaderLabels(["Cultivo", "T. suelo °C", "Humedad %", "pH",
                                              "N mín", "P mín", "K mín", "¿Compatible?"])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabs.addTab(self.grafica, "Tendencias")
        self.tabs.addTab(self.log, "Comunicación")
        self.tabs.addTab(self.tabla, "Base de cultivos")
        centro.addWidget(self.tabs, 1)
        self._llenar_tabla(None)

        # Columna derecha: LCD
        der = QVBoxLayout()
        cuerpo.addLayout(der, 0)
        g_lcd = QGroupBox("LCD 20x4")
        v = QVBoxLayout(g_lcd)
        self.lcd = LCD20x4()
        v.addWidget(self.lcd)
        der.addWidget(g_lcd)
        g_est = QGroupBox("Diagrama de estados")
        v = QVBoxLayout(g_est)
        self.lbl_estados = {}
        for nombre in COLORES_ESTADO:
            lbl = QLabel(nombre)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setObjectName("nodoEstado")
            v.addWidget(lbl)
            self.lbl_estados[nombre] = lbl
        der.addWidget(g_est)
        der.addStretch()

        self.statusBar().showMessage("Listo")
        salir = QAction("Salir", self)
        salir.triggered.connect(self.close)
        self.menuBar().addMenu("Archivo").addAction(salir)

    def _conectar_senales(self):
        self.btn_iniciar.clicked.connect(self.iniciar)
        self.btn_detener.clicked.connect(self.detener)
        self.btn_puertos.clicked.connect(lambda: self._refrescar_puertos())
        self.cb_esp32.currentTextChanged.connect(lambda _: self._sincronizar_suelo())
        self.btn_on.clicked.connect(lambda: self._comando_bomba(self.sl_pwm.value()))
        self.btn_off.clicked.connect(lambda: self._comando_bomba(0))
        self.sl_pwm.valueChanged.connect(lambda v: self.lbl_pwm.setText(str(v)))
        self.btn_csv.clicked.connect(self.guardar_csv)
        for w in (self.sp_umbral, self.sp_tiempo, self.sp_nivel):
            w.valueChanged.connect(self._aplicar_parametros)
        self.chk_auto.toggled.connect(self._aplicar_parametros)

        self.ev.lcd.connect(self.lcd.mostrar)
        self.ev.motor.connect(self._on_motor)
        self.ev.tx.connect(lambda t: self._log("TX →", t))
        self.ev.rx.connect(lambda t: self._log("RX ←", t))
        self.ev.estado.connect(self._cambiar_estado)
        self.ev.ambiente.connect(self._on_ambiente)
        self.ev.suelo.connect(self._on_suelo)
        self.ev.cultivos.connect(self._on_cultivos)
        self.ev.esp32.connect(self._on_esp32)
        self.ev.error.connect(lambda m: QMessageBox.critical(self, "Error de comunicación", m))

    # ---------- puertos ----------
    def _refrescar_puertos(self, suelo=None, esp32=None):
        try:
            from serial.tools import list_ports
            puertos = [p.device for p in list_ports.comports()]
        except ImportError:
            puertos = []
        for cb, elegido in ((self.cb_esp32, esp32), (self.cb_suelo, suelo)):
            actual = elegido or cb.currentText() or SIMULADO
            cb.clear()
            cb.addItems([SIMULADO] + (["auto"] if cb is self.cb_esp32 else []) + puertos)
            cb.setCurrentText(actual)
        self._sincronizar_suelo()

    def _usa_esp32(self):
        return self.cb_esp32.currentText().strip() not in ("", SIMULADO)

    def _sincronizar_suelo(self):
        """Con ESP32, el 7-en-1 se lee por su módulo RS485: la casilla del adaptador USB no aplica."""
        if self._usa_esp32():
            self.cb_suelo.setCurrentText(POR_ESP32)
            self.cb_suelo.setEnabled(False)
        else:
            if self.cb_suelo.currentText() == POR_ESP32:
                self.cb_suelo.setCurrentText(SIMULADO)
            self.cb_suelo.setEnabled(self.btn_iniciar.isEnabled())

    # ---------- ciclo ----------
    def iniciar(self):
        p_suelo = self.cb_suelo.currentText().strip()
        p_esp32 = self.cb_esp32.currentText().strip()
        dht, nivel = None, None
        try:
            canal = CanalConsola()  # los datos solo se registran en la pestaña Comunicación
            if p_esp32 in ("", SIMULADO):
                sensor = SensorSueloSimulado() if p_suelo in ("", SIMULADO) else SensorSueloModbus(p_suelo)
            else:
                self.conexion = ConexionESP32(p_esp32, self.ev.esp32.emit)
                p_esp32 = self.conexion.puerto  # "auto" ya resuelto al COM real
                dht = SensorDHT22ESP32(self.conexion)
                nivel = SensorNivelESP32(self.conexion, self.sp_tanque.value())
                sensor = SensorSueloESP32(self.conexion)
                p_suelo = f"ESP32 en {p_esp32}"
                time.sleep(2.5)  # da tiempo a la primera línea de datos
        except ImportError:
            QMessageBox.critical(self, "Falta pyserial", "Instale pyserial: pip install pyserial")
            return
        except Exception as e:
            QMessageBox.critical(self, "No se pudo abrir el puerto", str(e))
            return
        self.sistema = SistemaGUI(sensor, canal, self.ev, dht, nivel, self.conexion)
        self._aplicar_parametros()
        self.hilo = HiloLectura(self.sistema, self.ev)
        self.hilo.finished.connect(self._hilo_terminado)
        self.hilo.start()
        self.btn_iniciar.setEnabled(False)
        self.btn_detener.setEnabled(True)
        for w in (self.cb_esp32, self.sp_tanque, self.cb_suelo, self.btn_puertos):
            w.setEnabled(False)
        modo = f"suelo: {p_suelo or SIMULADO}"
        self.statusBar().showMessage(f"Leyendo ({modo})")
        self._log("INFO", f"Sistema iniciado ({modo})")

    def detener(self):
        if self.hilo and self.hilo.isRunning():
            self.hilo.requestInterruption()
            self.btn_detener.setEnabled(False)
            self.statusBar().showMessage("Deteniendo al terminar el paso actual...")

    def _cerrar_conexion(self):
        if self.conexion:
            self.conexion.cerrar()
            self.conexion = None

    def _hilo_terminado(self):
        self._cerrar_conexion()
        self.btn_iniciar.setEnabled(True)
        self.btn_detener.setEnabled(False)
        for w in (self.cb_esp32, self.sp_tanque, self.cb_suelo, self.btn_puertos):
            w.setEnabled(True)
        self._sincronizar_suelo()
        self.statusBar().showMessage("Detenido")
        self._log("INFO", "Sistema detenido")

    def _aplicar_parametros(self):
        if not self.sistema:
            return
        r = self.sistema.riego
        r.umbral_bajo, r.riego_s = self.sp_umbral.value(), self.sp_tiempo.value()
        r.nivel_minimo, r.riego_automatico = self.sp_nivel.value(), self.chk_auto.isChecked()

    def _comando_bomba(self, pwm):
        if not self.sistema:
            QMessageBox.information(self, "Sistema detenido", "Inicie el sistema para controlar la bomba.")
            return
        trama = f"vel={pwm}/"
        self._log("GUI", trama)
        self.sistema.comandos.procesar(trama)

    # ---------- slots de datos ----------
    def _on_motor(self, in1, in2, pwm, pwm_max):
        on = in1 == 1 and pwm > 0
        self.lbl_motor.setText(f"IN1={in1}  IN2={in2}  PWM={pwm}/{pwm_max}  {'● ENCENDIDA' if on else '○ apagada'}")
        self.lbl_motor.setProperty("on", on)
        self.lbl_motor.style().unpolish(self.lbl_motor)
        self.lbl_motor.style().polish(self.lbl_motor)

    def _on_esp32(self, datos):
        self._ultima_dist = datos.get("d")
        self.t_dist.set_valor(self._ultima_dist)
        d = "sin eco" if self._ultima_dist is None else f"{self._ultima_dist:.1f} cm"
        m = datos.get("m") or [0, 0, 0]
        self._log("ESP32", f"T={datos.get('t')} °C  H={datos.get('h')} %  distancia={d}  "
                           f"suelo={'sin respuesta' if datos.get('s') is None else datos.get('s')}  "
                           f"LCD={'OK' if datos.get('lcd') else 'no responde'}  "
                           f"bomba=IN1 {m[0]} IN2 {m[1]} {m[2]} %")

    def _on_ambiente(self, a: LecturaAmbiente):
        self._ultimo_ambiente = a
        self.t_taire.set_valor(a.temperatura or None)
        self.t_haire.set_valor(a.humedad or None)
        self.t_nivel.set_valor(a.nivel_agua_pct, alerta=a.nivel_agua_pct < self.sp_nivel.value())
        self.pb_nivel.setValue(round(a.nivel_agua_pct))

    def _on_suelo(self, s: LecturaSuelo):
        if not s.es_valida:
            for t in (self.t_hsuelo, self.t_tsuelo, self.t_ph, self.t_ec, self.t_n, self.t_p, self.t_k):
                t.set_valor(None)
            self.lbl_cultivos.setText("Error de lectura del sensor de suelo")
            a = self._ultimo_ambiente
            self.grafica.agregar([None, None, a.nivel_agua_pct, a.humedad], self.sp_umbral.value())
            self.registros.append({
                "fecha": datetime.now().isoformat(timespec="seconds"),
                "t_aire": a.temperatura, "h_aire": a.humedad, "nivel_agua": round(a.nivel_agua_pct),
                "dist_cm": self._ultima_dist,
            })
            return
        self.t_hsuelo.set_valor(s.humedad, alerta=s.humedad < self.sp_umbral.value())
        self.t_tsuelo.set_valor(s.temp_suelo)
        self.t_ph.set_valor(s.ph)
        self.t_ec.set_valor(s.conductividad)
        self.t_n.set_valor(s.nitrogeno)
        self.t_p.set_valor(s.fosforo)
        self.t_k.set_valor(s.potasio)
        a = self._ultimo_ambiente
        self.grafica.agregar([s.humedad, s.temp_suelo, a.nivel_agua_pct, a.humedad], self.sp_umbral.value())
        self._llenar_tabla(s)
        self.registros.append({
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "t_aire": a.temperatura, "h_aire": a.humedad, "nivel_agua": round(a.nivel_agua_pct),
            "dist_cm": self._ultima_dist,
            "h_suelo": round(s.humedad, 1), "t_suelo": round(s.temp_suelo, 1), "ec": round(s.conductividad),
            "ph": round(s.ph, 1), "n": round(s.nitrogeno), "p": round(s.fosforo), "k": round(s.potasio),
        })

    def _on_cultivos(self, nombres):
        self.lbl_cultivos.setText("  ·  ".join(nombres) if nombres else "Ninguno es compatible con este suelo")
        if self.registros:
            self.registros[-1]["cultivos"] = ", ".join(nombres) or "Ninguno"

    def _llenar_tabla(self, s):
        plantas = self._plantas.plantas
        self.tabla.setRowCount(len(plantas))
        verde = QColor(46, 160, 67, 70)
        for fila, pl in enumerate(plantas):
            ok = s is not None and pl.es_compatible(s)
            celdas = [pl.nombre, f"{pl.temp_suelo.minimo}–{pl.temp_suelo.maximo}",
                      f"{pl.humedad.minimo}–{pl.humedad.maximo}", f"{pl.ph.minimo}–{pl.ph.maximo}",
                      str(pl.nitrogeno_min), str(pl.fosforo_min), str(pl.potasio_min),
                      "—" if s is None else ("Sí" if ok else "No")]
            for col, txt in enumerate(celdas):
                item = QTableWidgetItem(txt)
                if ok:
                    item.setBackground(verde)
                self.tabla.setItem(fila, col, item)

    def _cambiar_estado(self, estado):
        color = COLORES_ESTADO.get(estado, "#7a7f87")
        self.lbl_estado.setText(estado)
        self.lbl_estado.setStyleSheet(f"background:{color};")
        for nombre, lbl in self.lbl_estados.items():
            activo = nombre == estado
            lbl.setStyleSheet(f"background:{COLORES_ESTADO[nombre]}; color:white; font-weight:bold;"
                              if activo else "")

    def _log(self, origen, texto):
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {origen}  {texto}")

    def guardar_csv(self):
        if not self.registros:
            QMessageBox.information(self, "Sin datos", "Aún no hay lecturas para guardar.")
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar lecturas",
                                              f"tecnosoil_{datetime.now():%Y%m%d_%H%M}.csv", "CSV (*.csv)")
        if not ruta:
            return
        campos = ["fecha", "t_aire", "h_aire", "nivel_agua", "dist_cm", "h_suelo", "t_suelo", "ec",
                  "ph", "n", "p", "k", "cultivos"]
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(self.registros)
        self.statusBar().showMessage(f"Guardadas {len(self.registros)} lecturas en {ruta}")

    def closeEvent(self, evento):
        if self.hilo and self.hilo.isRunning():
            self.hilo.requestInterruption()
            self.hide()
            self.hilo.wait(15000)
        self._cerrar_conexion()
        evento.accept()


ESTILO = """
QLabel#titulo { font-size: 22px; font-weight: bold; color: #2e7d32; }
QLabel#estado { color: white; font-weight: bold; padding: 4px 12px; border-radius: 10px; }
QFrame#tarjeta { border: 1px solid palette(mid); border-radius: 8px; background: palette(base); }
QLabel#tarjetaTitulo { color: palette(placeholder-text); font-size: 11px; }
QLabel#tarjetaValor { font-size: 20px; font-weight: bold; }
QLabel#tarjetaValor[alerta="true"] { color: #d9534f; }
QLabel#cultivos { font-size: 18px; font-weight: bold; color: #2e7d32; padding: 4px; }
QLabel#motor { font-family: Consolas, monospace; padding: 4px; }
QLabel#motor[on="true"] { color: #1f9d55; font-weight: bold; }
QLabel#nota { color: palette(placeholder-text); font-size: 11px; }
QLabel#nodoEstado { border: 1px solid palette(mid); border-radius: 12px; padding: 8px; margin: 2px; }
QFrame#lcd { background: #3c6e1f; border: 6px solid #1d2b12; border-radius: 6px; }
QLabel#lcdTexto { color: #d8f5b0; background: transparent; }
QPushButton { padding: 6px 12px; }
QGroupBox { font-weight: bold; }
"""


def main():
    parser = argparse.ArgumentParser(description="Interfaz gráfica de TecnoSoil")
    parser.add_argument("--puerto-suelo", help="Adaptador USB-RS485 del sensor 7-en-1 (ej. COM5)")
    parser.add_argument("--puerto-esp32", help="ESP32 con todos los sensores (ej. COM17); arranca la lectura")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(ESTILO)
    ventana = VentanaTecnoSoil(args.puerto_suelo, args.puerto_esp32)
    ventana.show()
    if args.puerto_esp32:
        QTimer.singleShot(300, ventana.iniciar)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
