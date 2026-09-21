@echo off
REM Lo que lanza la tarea programada de Windows. No abrir a mano:
REM para eso esta "python avisos.py --cada 60", que si enseña ventana.
REM
REM -u: sin almacenar en memoria. Sin esto Python guarda la salida y el
REM registro llega con horas de retraso, justo cuando hace falta mirarlo.
cd /d "%~dp0"
echo. >> avisos.log
echo ===== arranque %DATE% %TIME% ===== >> avisos.log
python -u avisos.py --cada 60 >> avisos.log 2>&1
echo ===== se detuvo %DATE% %TIME% ===== >> avisos.log
