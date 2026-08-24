@echo off
REM Doble clic aqui para tener el espejo al dia y publicado en la app.
REM Se situa solo en la carpeta donde este este archivo.
cd /d "%~dp0"
title Vantage EA - espejo
echo.
echo  Rehaciendo el espejo cada 15 minutos y publicandolo cuando cambie.
echo  Para parar: Ctrl+C
echo.
echo  MetaTrader 5 tiene que estar abierto: el espejo lee del terminal.
echo.
python espejo.py --cada 15 --publicar
echo.
echo  El espejo se ha detenido.
pause
