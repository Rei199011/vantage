# Vantage EA — Order Blocks en MetaTrader 5

Un robot que opera order blocks en MT5, y una página que enseña lo que está
haciendo, actualizada sola cada quince minutos.

No hay señales de acciones, ni Telegram, ni IA. Eso era el proyecto anterior y
está retirado; vive en el historial de git si alguna vez hace falta.

```
espejo.py             lee MT5 y escribe la pagina
a_tradingview.py      escribe un indicador de Pine con las operaciones
arrancar_espejo.bat   doble clic -> bucle de 15 minutos que publica solo
dashboard.html        la pagina (generada, no editar a mano)
manifest.json         para que se instale como app en el movil
tradingview/          los indicadores generados, uno por simbolo
```

## Las dos piezas

**El robot** vive fuera de este repositorio, en
`Desktop/motor/mt5/`, porque se compila dentro de MetaTrader.
Este repositorio solo lo observa.

**El espejo** lee el terminal de MT5 y genera `dashboard.html`. Cada quince
minutos rehace la página; si algo cambió de verdad, hace commit y lo sube a
GitHub Pages, que es de donde tira la app instalada en el móvil.

## Ponerlo en marcha

```
pip install -r requirements.txt
```

Después, doble clic en `arrancar_espejo.bat`. Hacen falta tres cosas
encendidas: el ordenador, MetaTrader abierto y conectado, y esa ventana sin
cerrar. Si falta cualquiera, la app se queda con la última foto.

Una vuelta suelta, sin bucle y sin publicar:

```
python espejo.py --abrir
```

## Lo que hay que saber para tocarlo

**Filtra por número mágico `20260822`.** La cuenta demo la comparte con otro
robot que usa el mágico `990101` y suele tener posiciones abiertas. Sin ese
filtro el espejo enseñaría las de ese otro robot como si fueran de la EA. Si se
cambia el mágico en el robot, hay que cambiarlo también en `espejo.py`.

**Solo lee.** Todas las llamadas a la API de MT5 son de consulta. El espejo no
envía ninguna orden ni toca ninguna posición.

**Los R salen de dividir entre `RIESGO_POR_OPERACION = 500`**, que es un
parámetro del robot y no se puede deducir del historial de una operación ya
cerrada. Si cambia allí, cambiarlo aquí.

**Agrupa por posición, no por transacción.** Una operación con parcial genera
DOS transacciones de salida. Contarlas sueltas es lo que hace que 16
operaciones aparezcan como 27 en los informes del probador de MT5.

**El resumen se recalcula con los filtros puestos.** Si no, engañaría: enseñaría
trece operaciones de un día con el balance de seis meses. Y una operación que
sale plana cuenta como perdida: con break-even eso pasa a menudo, y meterla en
las ganadas inflaría el acierto.

**MT5 da las horas en hora del servidor**, no en UTC. `a_tradingview.py` mide el
desfase contra el reloj real en cada ejecución en vez de suponerlo; si se
equivoca, las cajas del gráfico salen corridas tres horas.

## TradingView

```
python a_tradingview.py
```

Escribe un fichero `.pine` por símbolo en `tradingview/`. Se copia entero, se
pega en el Pine Editor de TradingView y se pulsa "Añadir al gráfico". Dibuja
cada operación con dos cajas —entrada al stop en rojo, entrada al objetivo en
verde— y una etiqueta con el resultado en R.

Los precios son los del bróker de MT5 y la cotización de TradingView viene de
otra fuente, así que puede haber unos pocos puntos de diferencia. Sirve para ver
dónde y cómo, no para auditar el llenado al tick.
