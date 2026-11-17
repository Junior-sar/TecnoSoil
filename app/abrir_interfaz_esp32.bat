@echo off
cd /d "%~dp0"
python interfaz_tecnosoil.py --puerto-esp32 auto
if errorlevel 1 pause
