# Interfaz gráfica TecnoSoil / AgroControl

Aplicación de escritorio (PySide6, la librería vista en la clase 7 de GUI/HMI) que corre en tu PC
y reutiliza las clases de `compu_int.py` sin modificarlas.

## Cómo ejecutarla

1. Instala Python 3.10 o superior.
2. En esta carpeta, instala las dependencias (una sola vez):

   ```
   pip install -r requirements.txt
   ```

3. Ejecuta:

   ```
   python interfaz_tecnosoil.py
   ```

   Por defecto usa los sensores simulados. Para hardware real puedes elegir los puertos en el
   panel "Conexión" o pasarlos igual que en el programa de consola:

   ```
   python interfaz_tecnosoil.py --puerto-suelo COM5
   ```

`compu_int.py` debe estar en la misma carpeta. Sigue funcionando solo, por consola, como antes.

Con el ESP32-S3 conectado (DHT22 en GPIO4, HC-SR04 en GPIO5/6, MAX485 en GPIO17/16/7), cierra Thonny y ejecuta
`abrir_interfaz_esp32.bat` o:

```
python interfaz_tecnosoil.py --puerto-esp32 auto
```

La interfaz envía `esp32_puente.py` a la placa al conectarse y recibe de ella una línea JSON cada 2 s
(`esp32_tecnosoil.py`). Ajusta "Altura del tanque" antes de Iniciar para que el nivel de agua sea correcto.
Con el ESP32 la **bomba es real** (puente H L298N: IN1 en GPIO 21, IN2 en GPIO 47, ENA/PWM en GPIO 15) y la
**LCD 20x4 física** (I2C con PCF8574, dirección 0x27, SDA en GPIO 8 y SCL en GPIO 9) muestra lo mismo que la
LCD de la ventana. La PC le manda a la placa una línea JSON por orden (`{"m": [IN1, IN2, %PWM]}` y
`{"l": [4 filas]}`). Por seguridad la placa apaga la bomba si pasan 10 s sin órdenes de la PC o si se
detiene el programa. La bomba tiene polaridad; si con tu cableado no bombea, cambia `INVERTIR_GIRO` en `esp32_puente.py`. En "ESP32" puedes elegir `auto` para que busque el puerto solo (el `.bat` ya lo hace).

## Pruebas

- **Pruebas unitarias** (no necesitan la placa): `python -m unittest -v test_tecnosoil`
- **Prueba del hardware, componente por componente** (LCD, DHT22, ultrasonido, 7-en-1 y bomba 3 s):
  `python prueba_hardware.py` (agrega `--sin-bomba` para no mover el motor). Cierra antes la interfaz y Thonny.

## Qué muestra y controla

- **Iniciar / Detener** el ciclo de lectura (el mismo de `SistemaTecnoSoil.ejecutar`).
- **Ambiente y agua**: temperatura y humedad del aire (DHT11) y nivel del tanque (ultrasonido).
- **Suelo**: humedad, temperatura, pH, conductividad y NPK del sensor 7-en-1.
- **Cultivos sugeridos** y pestaña **Base de cultivos** con los compatibles resaltados en verde.
- **LCD 20x4** virtual con los mismos mensajes que la pantalla física.
- **Diagrama de estados** en vivo: Inactiva, Leyendo propiedades, Regando y Pausada
  (el riego se pausa si el nivel de agua está por debajo del mínimo).
- **Riego automático**: umbral de humedad, tiempo de riego y nivel mínimo de agua, ajustables en vivo.
- **Bomba manual**: PWM y botones Encender/Apagar, que envían el comando `vel=XXXX/`.
- **Comunicación**: registro de los datos del ESP32, los JSON generados y los comandos de la bomba.
- **Tendencias**: gráfica de humedad del suelo, temperatura, nivel de agua y humedad del aire.
- **Guardar lecturas en CSV**.

## Cómo está organizada (POO)

| Clase nueva | Hereda de | Para qué |
|---|---|---|
| `PantallaGUI` | `Pantalla` | Dibuja el LCD en la ventana y, con ESP32, también en la LCD física |
| `MotorESP32` | `MotorPuenteH` | Manda IN1/IN2/PWM al puente H real del ESP32 |
| `PantallaLCDESP32` | `Pantalla` | Escribe en la LCD 20x4 física del ESP32 |
| `MotorGUI` | `MotorESP32` | Informa a la GUI el estado IN1/IN2/PWM (y mueve la bomba real si hay ESP32) |
| `CanalGUI` | `Canal` | Decora el canal real (consola o serial) y muestra lo enviado/recibido |
| `ControladorRiegoGUI` | `ControladorRiego` | Agrega el estado "Pausada" por nivel de agua bajo |
| `SistemaGUI` | `SistemaTecnoSoil` | Mismo ciclo, con las dependencias anteriores inyectadas |
| `HiloLectura` | `QThread` | Corre el ciclo sin congelar la ventana |
| `VentanaTecnoSoil` | `QMainWindow` | La interfaz (widgets, layouts, señales/slots) |

La lógica sigue en `compu_int.py`, la presentación en `interfaz_tecnosoil.py`, y se comunican por
señales de Qt (`Eventos`), como recomienda la clase: separar presentación, lógica y comunicación.
