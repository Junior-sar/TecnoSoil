@echo off
cd /d "%~dp0"
echo Leyendo DHT11 + ultrasonido (Ctrl+C para detener, luego Ctrl+X para salir)
mpremote connect COM17 reset
timeout /t 2 >nul
mpremote connect COM17 repl
