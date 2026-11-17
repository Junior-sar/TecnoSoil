@echo off
cd /d "%~dp0"
echo Subiendo main.py (DHT11 + HC-SR04) al ESP32 en COM17...
mpremote connect COM17 cp main.py :main.py + cp main_7en1.py :main_7en1.py
if errorlevel 1 (echo ERROR: no se pudo usar COM17. Conecta la placa y cierra Thonny. & pause & exit /b 1)
mpremote connect COM17 rm :datos.csv >nul 2>&1
echo Listo. Ahora ejecuta 2_leer_sensor.bat
pause
