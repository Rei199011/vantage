@echo off
REM El parte del dia. Lo lanza la tarea programada a las 23:30, media hora
REM despues de que cierre la sesion de Nueva York para el robot.
cd /d "%~dp0"
echo ===== resumen %DATE% %TIME% ===== >> avisos.log
python -u avisos.py --resumen >> avisos.log 2>&1
