@echo off
REM Lo que lanza la tarea programada de Windows. No abrir a mano:
REM para eso esta arrancar_espejo.bat, que si enseña ventana.
REM
REM La salida va a espejo.log porque la tarea corre sin ventana y si no
REM no habria forma de saber que ha pasado.
cd /d "%~dp0"
echo. >> espejo.log
echo ===== arranque %DATE% %TIME% ===== >> espejo.log
REM -u: sin almacenar en memoria. Sin esto Python guarda la salida y el
REM registro llega con horas de retraso, justo cuando hace falta mirarlo.
python -u espejo.py --cada 15 --publicar >> espejo.log 2>&1
echo ===== se detuvo %DATE% %TIME% ===== >> espejo.log
