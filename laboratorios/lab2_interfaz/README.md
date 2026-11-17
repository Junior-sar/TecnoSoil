# Laboratorio 2: del ESP32 a la interfaz gráfica en Python

Cadena completa **sensor → ESP32 → USB → Python → interfaz (Tkinter + Matplotlib) → CSV**.

| Archivo | Dónde corre | Función |
|---|---|---|
| `esp32/main.py` | ESP32 | Plantilla con la trama `DATA:{json}` (DHT22 en GPIO 4) |
| `esp32/main_hcsr04.py` | ESP32 | Misma plantilla con el segundo sensor (HC-SR04, Trig 5 / Echo 6) |
| `lector_serial.py` | PC | Lee el puerto en un hilo y separa las tramas `DATA:` |
| `interfaz.py` | PC | Valores actuales, una gráfica por variable y grabación en CSV |
| `resultados/` | — | CSV de 3 minutos de cada sensor, capturas de la interfaz y gráficas |
| `Informe_Laboratorio_2.pdf` | — | Informe con resultados, preguntas de análisis y conclusiones |

```
pip install pyserial matplotlib
python lector_serial.py COM13   # prueba sin interfaz
python interfaz.py              # interfaz gráfica
```
