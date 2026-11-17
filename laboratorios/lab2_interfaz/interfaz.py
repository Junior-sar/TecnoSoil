# interfaz.py - interfaz gráfica: visualiza las señales del ESP32 y las guarda en CSV
# Requiere: pip install pyserial matplotlib      Ejecutar: python interfaz.py
import csv
import time
import tkinter as tk
from collections import deque
from tkinter import ttk, filedialog, messagebox

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from lector_serial import LectorSerial, listar_puertos

# ---------------------------------------------------------------------
# CONFIGURACIÓN                                            >>> CAMBIAR
# ---------------------------------------------------------------------
TITULO      = "Monitor de sensores ESP32"
VENTANA_S   = 120          # segundos visibles en la gráfica
REFRESCO_MS = 250          # cada cuánto se actualiza la pantalla
MAX_PUNTOS  = 2000         # puntos guardados en memoria por variable


class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(TITULO)
        self.geometry("1000x650")
        self.lector = None
        self.t0 = None                      # instante de la primera lectura
        self.series = {}                    # {variable: deque de (t, valor)}
        self.archivo = None                 # archivo CSV abierto
        self.escritor = None
        self.columnas = None                # orden fijo de columnas del CSV
        self.n_filas = 0
        self._armar_controles()
        self._armar_grafica()
        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.after(REFRESCO_MS, self.actualizar)

    # ---------- construcción de la ventana ---------------------------
    def _armar_controles(self):
        barra = ttk.Frame(self, padding=8)
        barra.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(barra, text="Puerto:").pack(side=tk.LEFT)
        self.cb_puerto = ttk.Combobox(barra, width=16, values=listar_puertos())
        self.cb_puerto.pack(side=tk.LEFT, padx=4)
        if self.cb_puerto["values"]:
            self.cb_puerto.current(0)
        ttk.Button(barra, text="↻", width=3, command=self.refrescar_puertos).pack(side=tk.LEFT)

        self.bt_conectar = ttk.Button(barra, text="Conectar", command=self.conectar)
        self.bt_conectar.pack(side=tk.LEFT, padx=8)
        self.bt_grabar = ttk.Button(barra, text="Iniciar grabación", command=self.grabar, state=tk.DISABLED)
        self.bt_grabar.pack(side=tk.LEFT)
        ttk.Button(barra, text="Limpiar gráfica", command=self.limpiar).pack(side=tk.LEFT, padx=8)

        self.lb_estado = ttk.Label(barra, text="Desconectado", foreground="gray")
        self.lb_estado.pack(side=tk.RIGHT)

        # Panel de valores actuales (se llena al llegar el primer dato)
        self.panel = ttk.Frame(self, padding=(8, 0))
        self.panel.pack(side=tk.TOP, fill=tk.X)
        self.etiquetas = {}

    def _armar_grafica(self):
        self.fig = Figure(figsize=(9, 5), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.ejes = {}

    def _crear_ejes(self):
        """Una subgráfica por variable recibida (se adapta a cualquier sensor)."""
        self.fig.clear()
        nombres = list(self.series)
        self.ejes = {}
        for i, nombre in enumerate(nombres):
            ax = self.fig.add_subplot(len(nombres), 1, i + 1)
            ax.set_ylabel(nombre)
            ax.grid(True, alpha=0.3)
            linea, = ax.plot([], [], lw=1.5)
            self.ejes[nombre] = (ax, linea)
        if nombres:
            self.ejes[nombres[-1]][0].set_xlabel("Tiempo (s)")
        self.fig.tight_layout()

    # ---------- acciones de los botones -----------------------------
    def refrescar_puertos(self):
        self.cb_puerto["values"] = listar_puertos()

    def conectar(self):
        if self.lector and self.lector.conectado:
            self.detener_grabacion()
            self.lector.desconectar()
            self.bt_conectar.config(text="Conectar")
            self.bt_grabar.config(state=tk.DISABLED)
            self.lb_estado.config(text="Desconectado", foreground="gray")
            return
        puerto = self.cb_puerto.get()
        if not puerto:
            messagebox.showwarning(TITULO, "Seleccione un puerto")
            return
        try:
            self.lector = LectorSerial(puerto)
            self.lector.conectar()
        except Exception as e:                          # puerto ocupado (Thonny), sin permisos...
            messagebox.showerror(TITULO, "No se pudo abrir {}:\n{}".format(puerto, e))
            return
        self.bt_conectar.config(text="Desconectar")
        self.bt_grabar.config(state=tk.NORMAL)
        self.lb_estado.config(text="Conectado a " + puerto, foreground="green")

    def grabar(self):
        if self.archivo:
            self.detener_grabacion()
            return
        nombre = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=time.strftime("lecturas_%Y%m%d_%H%M%S.csv"))
        if not nombre:
            return
        self.archivo = open(nombre, "w", newline="", encoding="utf-8")
        self.escritor = csv.writer(self.archivo)
        self.columnas = None                            # se fijan con el primer dato
        self.n_filas = 0
        self.bt_grabar.config(text="Detener grabación")

    def detener_grabacion(self):
        if self.archivo:
            self.archivo.close()
            self.archivo = None
            self.bt_grabar.config(text="Iniciar grabación")
            self.lb_estado.config(text="Archivo guardado ({} filas)".format(self.n_filas))

    def limpiar(self):
        self.series.clear()
        self.t0 = None
        for w in self.panel.winfo_children():
            w.destroy()
        self.etiquetas.clear()
        self.fig.clear()
        self.canvas.draw_idle()

    # ---------- guardado --------------------------------------------
    def guardar_fila(self, t, datos):
        if self.columnas is None:
            self.columnas = list(datos)
            self.escritor.writerow(["fecha_hora", "t_s"] + self.columnas)
        fila = [time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)),
                "{:.2f}".format(t - self.t0)]
        fila += [round(datos[c], 3) if c in datos else "" for c in self.columnas]
        self.escritor.writerow(fila)
        self.archivo.flush()                            # no se pierde nada si se cierra mal
        self.n_filas += 1

    # ---------- bucle de actualización ------------------------------
    def actualizar(self):
        nuevas = False
        if self.lector:
            while not self.lector.cola.empty():
                t, datos = self.lector.cola.get()
                if self.t0 is None:
                    self.t0 = t
                for k, v in datos.items():
                    if k not in self.series:
                        self.series[k] = deque(maxlen=MAX_PUNTOS)
                        self._crear_etiqueta(k)
                        self.ejes = {}                  # obliga a redibujar los ejes
                    self.series[k].append((t - self.t0, v))
                    self.etiquetas[k].config(text="{}: {:.2f}".format(k, v))
                if self.archivo:
                    self.guardar_fila(t, datos)
                nuevas = True
            while not self.lector.mensajes.empty():
                print("[ESP32]", self.lector.mensajes.get())
            if self.archivo:
                self.lb_estado.config(text="Grabando… {} filas".format(self.n_filas), foreground="red")
        if nuevas:
            self.redibujar()
        self.after(REFRESCO_MS, self.actualizar)

    def _crear_etiqueta(self, nombre):
        lb = ttk.Label(self.panel, text=nombre, font=("Segoe UI", 14, "bold"), padding=(0, 0, 24, 0))
        lb.pack(side=tk.LEFT)
        self.etiquetas[nombre] = lb

    def redibujar(self):
        if set(self.ejes) != set(self.series):
            self._crear_ejes()
        for nombre, (ax, linea) in self.ejes.items():
            puntos = self.series[nombre]
            ts = [p[0] for p in puntos]
            vs = [p[1] for p in puntos]
            linea.set_data(ts, vs)
            fin = ts[-1] if ts else 0
            ax.set_xlim(max(0, fin - VENTANA_S), max(VENTANA_S, fin))
            ax.relim()
            ax.autoscale_view(scalex=False)
        self.canvas.draw_idle()

    def cerrar(self):
        self.detener_grabacion()
        if self.lector:
            self.lector.desconectar()
        self.destroy()


if __name__ == "__main__":
    Aplicacion().mainloop()
