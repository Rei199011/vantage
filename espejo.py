"""
Vantage — Espejo de la EA
-------------------------
Genera `dashboard.html` como reflejo de lo que hace el robot de order blocks
en MetaTrader 5. No calcula señales ni decide nada: lee el terminal y lo pinta.

    python espejo.py              # escribe dashboard.html una vez
    python espejo.py --abrir      # y lo abre en el navegador
    python espejo.py --cada 15    # lo rehace cada 15 minutos, sin parar

SOLO LEE. No envía ninguna orden ni toca ninguna posición. Todas las funciones
que se usan de la API de MT5 son de consulta.

Filtra por NUMERO MAGICO, así que en una cuenta compartida con otros robots
—como la demo donde también corre Ariel— solo enseña lo nuestro.
"""

import argparse
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
import time

try:
    import MetaTrader5 as mt5
except ImportError:
    print("Falta el paquete MetaTrader5:  pip install MetaTrader5")
    sys.exit(1)

# Los mágicos de los EA. Si se cambia en un robot, hay que cambiarlo aquí.
#
# SON TRES, desde el 30/09/2026:
#
#   20260822  OB 1_1      EURJPY, con EMA
#   20260930  OB_sin_EMA  EURUSD, GBPJPY, USDCAD y XAUUSD, sin EMA
#   20260921  OB_5min     el oro de antes, en M5 y a 1:2. Ya no opera, pero sus
#                         operaciones cerradas son parte del historial y tienen
#                         que seguir contando.
#
# Mientras esto fue un escalar, los cuatro pares del segundo robot NO salían en
# el panel, y nadie lo habría notado: la pestaña enseñaba menos operaciones de
# las que había. Al ampliarlo se me olvidó el 20260921 y se perdieron las dos
# del oro; el aviso vino de Reinaldo, no del programa.
#
# LO QUE NO ENTRA, Y ES A PROPÓSITO. En esta misma cuenta demo corre Ariel con
# el mágico 990101 y tiene 58 operaciones de oro suyas. El 0 son los cierres a
# mano. Ni uno ni otro son de este robot y no deben aparecer aquí: ese filtrado
# es justo para lo que existe este fichero.
MAGICOS = {20260822, 20260921, 20260930}

# Se conserva para lo que aún espera un número suelto.
MAGICO = 20260822

# Lo que el robot arriesga por operación, para poder expresar los resultados
# en R. Es un parámetro suyo, no algo que se pueda deducir del historial de
# una operación ya cerrada.
RIESGO_POR_OPERACION = 150.0

DIAS_HISTORIAL = 180
SALIDA = "dashboard.html"

TIPOS_ORDEN = {
    mt5.ORDER_TYPE_BUY_LIMIT: "compra limitada",
    mt5.ORDER_TYPE_SELL_LIMIT: "venta limitada",
    mt5.ORDER_TYPE_BUY_STOP: "compra parada",
    mt5.ORDER_TYPE_SELL_STOP: "venta parada",
}


# ---------------------------------------------------------------- lectura


# La hora. MetaTrader sella TODO en hora del SERVIDOR y lo entrega como un
# epoch que hay que leer COMO SI fuera UTC. Pasarlo por datetime.fromtimestamp()
# le suma encima el huso de este ordenador, y lo que sale no es ni la hora del
# servidor ni la de aqui: son las dos sumadas. Eso enseñaba las entradas tres
# horas tarde.
#
# El desfase se MIDE contra el reloj real en cada vuelta en lugar de suponerlo,
# porque cambia solo con el horario de verano.

_DESFASE = 0


def _desfase_servidor():
    """Horas que el reloj del servidor lleva por delante de UTC."""
    t = mt5.symbol_info_tick("EURUSD")
    if t is None or not t.time:
        return 0
    servidor = dt.datetime.fromtimestamp(t.time, dt.timezone.utc)
    return round((servidor - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600)


def _servidor(ts):
    """La marca tal cual la escribe el servidor. Es lo que espera copy_rates."""
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).replace(tzinfo=None)


def _local(ts):
    """La marca de MT5 pasada al reloj de quien mira la pagina."""
    utc = dt.datetime.fromtimestamp(ts, dt.timezone.utc) - dt.timedelta(hours=_DESFASE)
    return utc.astimezone().replace(tzinfo=None)


def _parcial_cobrado(pid):
    """Lo ya realizado en una posicion que SIGUE viva: el parcial del 1:1."""
    ds = mt5.history_deals_get(position=pid) or []
    return round(sum(d.profit + d.swap + d.commission
                     for d in ds if d.entry != mt5.DEAL_ENTRY_IN), 2)


def _terminal():
    """
    A QUE terminal hay que conectarse, cuando hay mas de uno abierto.

    Con el MetaTrader de MetaQuotes y el de FTMO a la vez, una initialize() a
    secas coge el que le parece. El 29/09 el espejo se cambio de cuenta EL
    SOLO: la app paso a enseñar los 50.000 de FTMO y todo el historial de la
    demo desaparecio de la vista sin que nadie tocara nada.

    Se fija en .env, no en el codigo, para poder cambiar de cuenta sin tocar
    nada mas:

        MT5_TERMINAL=C:/Program Files/MetaTrader 5/terminal64.exe

    Sin esa linea se comporta como antes: el que encuentre.
    """
    ruta = os.getenv("MT5_TERMINAL")
    if not ruta and os.path.exists(".env"):
        for linea in io.open(".env", encoding="utf-8", errors="ignore"):
            if linea.strip().startswith("MT5_TERMINAL="):
                ruta = linea.split("=", 1)[1].strip().strip('"').strip("'")
                break
    return ruta or None


def _abrir():
    """initialize() apuntando al terminal que toca."""
    ruta = _terminal()
    return mt5.initialize(ruta) if ruta else mt5.initialize()


def leer_terminal():
    """Todo lo que hay que saber del terminal, en un diccionario."""
    if not _abrir():
        return {"error": f"no se pudo conectar con MetaTrader 5: {mt5.last_error()}"}

    try:
        global _DESFASE
        _DESFASE = _desfase_servidor()
        ti = mt5.terminal_info()
        ai = mt5.account_info()
        return {
            "generado": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "conectado": bool(ti and ti.connected),
            "magico": sorted(MAGICOS),
            "riesgo": RIESGO_POR_OPERACION,
            "cuenta": {
                "login": ai.login if ai else None,
                "servidor": ai.server if ai else "",
                "divisa": ai.currency if ai else "",
                "balance": round(ai.balance, 2) if ai else 0.0,
                "equidad": round(ai.equity, 2) if ai else 0.0,
            },
            "abiertas": _abiertas(),
            "pendientes": _pendientes(),
            "cerradas": _cerradas(),
        }
    finally:
        mt5.shutdown()


def _dig(simbolo):
    """
    Decimales del símbolo.

    Sin esto, 1,16396 se imprime como 1.1639599999999999: ruido de coma
    flotante que ensucia la tabla entera.
    """
    s = mt5.symbol_info(simbolo)
    return s.digits if s else 5


def _abiertas():
    filas = []
    for p in (mt5.positions_get() or []):
        if p.magic not in MAGICOS:
            continue
        venta = p.type == mt5.POSITION_TYPE_SELL
        riesgo = _riesgo_de(venta, p.symbol, p.volume, p.price_open, p.sl)
        n = _dig(p.symbol)
        abierta = _local(p.time)
        filas.append({
            "simbolo": p.symbol,
            "lado": "VENTA" if venta else "COMPRA",
            "lotes": p.volume,
            "entrada": round(p.price_open, n),
            "stop": round(p.sl, n),
            "objetivo": round(p.tp, n),
            "flotante": round(p.profit, 2),
            # Lo YA cobrado aqui dentro. Ese dinero esta en la cuenta aunque la
            # operacion siga viva, y si no se enseñara desapareceria de la app
            # al dejar de contarse entre las cerradas.
            "parcial_cobrado": _parcial_cobrado(p.ticket),
            "abierta_desde": abierta.strftime("%d/%m %H:%M"),
            "abierta_dia": abierta.strftime("%Y-%m-%d"),
            # Un stop ya movido a la entrada no arriesga nada. Se marca aparte
            # porque es la señal de que el parcial ya se cobró.
            "en_breakeven": riesgo is not None and riesgo <= 0.01,
            "riesgo": round(riesgo, 2) if riesgo else 0.0,
        })
    return sorted(filas, key=lambda x: x["simbolo"])


def _pendientes():
    filas = []
    for o in (mt5.orders_get() or []):
        if o.magic not in MAGICOS:
            continue
        n = _dig(o.symbol)
        puesta = _local(o.time_setup)
        filas.append({
            "simbolo": o.symbol,
            "tipo": TIPOS_ORDEN.get(o.type, str(o.type)),
            "lotes": o.volume_current,
            "nivel": round(o.price_open, n),
            "stop": round(o.sl, n),
            "objetivo": round(o.tp, n),
            "puesta": puesta.strftime("%d/%m %H:%M"),
            "puesta_dia": puesta.strftime("%Y-%m-%d"),
        })
    return sorted(filas, key=lambda x: x["simbolo"])


def _cerradas():
    """
    Reconstruye las operaciones a partir de las transacciones.

    Una operación con parcial genera DOS transacciones de salida, así que
    contarlas sin agrupar infla la cuenta: es el error que hace que 16
    operaciones aparezcan como 27 en los informes del probador.
    """
    desde = dt.datetime.now() - dt.timedelta(days=DIAS_HISTORIAL)
    hasta = dt.datetime.now() + dt.timedelta(days=1)
    deals = mt5.history_deals_get(desde, hasta) or []

    # El stop y el objetivo no viven en la transacción: viven en la ORDEN que
    # abrió la posición. Sin ellos no se puede dibujar la geometría.
    niveles = {}
    for o in (mt5.history_orders_get(desde, hasta) or []):
        if o.magic in MAGICOS and o.position_id and (o.sl or o.tp):
            niveles.setdefault(o.position_id, (o.sl, o.tp))

    por_posicion = {}
    for d in deals:
        if d.magic not in MAGICOS:
            continue
        p = por_posicion.setdefault(d.position_id, {
            "simbolo": d.symbol, "lado": "", "beneficio": 0.0,
            "abierta": None, "cerrada": None, "entrada": 0.0, "salidas": 0,
            "puntos": [],
        })
        if d.entry == mt5.DEAL_ENTRY_IN:
            p["lado"] = "VENTA" if d.type == mt5.DEAL_TYPE_SELL else "COMPRA"
            p["abierta"] = d.time
            p["entrada"] = d.price
            p["lotes"] = d.volume
        else:
            p["beneficio"] += d.profit + d.swap + d.commission
            p["cerrada"] = d.time
            p["salidas"] += 1
            p["puntos"].append((d.time, d.price))

    # Una posicion con parcial YA tiene una salida, asi que "tiene salidas" no
    # sirve para saber si esta cerrada: hay que preguntarselo al terminal. Sin
    # esto una operacion a medias sale en las DOS pestañas, y su parcial se
    # cuenta como si fuera el resultado final de la operacion.
    vivas = {x.ticket for x in (mt5.positions_get() or [])
             if x.magic in MAGICOS}

    filas = []
    for pid, p in por_posicion.items():
        if p["abierta"] is None or p["cerrada"] is None or pid in vivas:
            continue          # todavía viva: sale en las abiertas
        a = _local(p["abierta"])
        c = _local(p["cerrada"])
        sl, tp = niveles.get(pid, (0.0, 0.0))
        riesgo_real = _riesgo_de(p["lado"] == "VENTA", p["simbolo"],
                                 p.get("lotes", 0.0), p["entrada"], sl) or 0.0
        n = _dig(p["simbolo"])
        filas.append({
            "grafico": _svg(p["simbolo"], p["entrada"], sl, tp,
                            p["abierta"], p["puntos"], n),
            "stop": round(sl, n),
            "objetivo": round(tp, n),
            "simbolo": p["simbolo"],
            "lado": p["lado"],
            "beneficio": round(p["beneficio"], 2),
            # La R sale del riesgo REAL de esta operación, no de un 500 fijo.
            #
            # Con el techo por margen el lote se recorta cuando no cabe, así
            # que una operación puede arriesgar 97 EUR en vez de 500. Dividir
            # siempre entre 500 enseñaría esa operación como +0,19 R cuando
            # ganó su 1R entero, y aplastaría todas las métricas hacia cero.
            #
            # Si el terminal no da el riesgo -sin stop, o ya movido a la
            # entrada- se recurre al parámetro, que es lo que había antes.
            "r": round(p["beneficio"] / (riesgo_real or RIESGO_POR_OPERACION), 2),
            "riesgo": round(riesgo_real, 2) if riesgo_real else None,
            "entrada": round(p["entrada"], _dig(p["simbolo"])),
            "abierta": a.strftime("%d/%m %H:%M"),
            "cerrada": c.strftime("%d/%m %H:%M"),
            # Día en formato ordenable, que es lo que usan los filtros. El
            # formato bonito no vale: "31/12" ordena antes que "01/01".
            "abierta_dia": a.strftime("%Y-%m-%d"),
            "cerrada_dia": c.strftime("%Y-%m-%d"),
            "horas": round((p["cerrada"] - p["abierta"]) / 3600.0, 1),
            "parcial": p["salidas"] > 1,
        })
    return sorted(filas, key=lambda x: x["cerrada_dia"], reverse=True)


# --- el gráfico de cada operación --------------------------------------
#
# Se dibuja aquí, en el servidor, como SVG plano. Ni librerías ni peticiones:
# la página sigue siendo un fichero suelto que se abre sin nada más.

ANCHO, ALTO = 560, 250
IZQ, DER, ARR, ABA = 8, 62, 12, 22
VELAS_ANTES, VELAS_DESPUES = 30, 20


def _svg(simbolo, entrada, stop, objetivo, t_in, salidas, digitos):
    """Las velas de la operación con su geometría encima."""
    if not salidas:
        return ""
    t_fin = max(t for t, _ in salidas)
    velas = mt5.copy_rates_range(
        simbolo, mt5.TIMEFRAME_M15,
        _servidor(t_in - VELAS_ANTES * 900),
        _servidor(t_fin + VELAS_DESPUES * 900))
    if velas is None or len(velas) < 5:
        return ""

    n = len(velas)
    niveles = [entrada] + [v for v in (stop, objetivo) if v]
    lo = min(float(velas["low"].min()), *niveles)
    hi = max(float(velas["high"].max()), *niveles)
    pad = (hi - lo) * 0.07 or 0.01
    lo, hi = lo - pad, hi + pad

    util = ANCHO - IZQ - DER
    x = lambda k: IZQ + util * (k + 0.5) / n
    y = lambda pr: ARR + (ALTO - ARR - ABA) * (hi - float(pr)) / (hi - lo)
    grosor = max(1.6, util / n * 0.62)

    P = []
    k_in = max(0, int((t_in - velas["time"][0]) // 900))
    k_out = min(n - 1, int((t_fin - velas["time"][0]) // 900))
    x1, x2 = x(k_in), max(x(k_out), x(k_in) + 6)

    for nivel, clase in ((stop, "riesgo"), (objetivo, "premio")):
        if not nivel:
            continue
        ya, yb = sorted((y(entrada), y(nivel)))
        P.append(f'<rect x="{x1:.1f}" y="{ya:.1f}" width="{x2 - x1:.1f}" '
                 f'height="{yb - ya:.1f}" class="{clase}"/>')

    for k in range(n):
        v = velas[k]
        cx = x(k)
        c = "alcista" if v["close"] >= v["open"] else "bajista"
        P.append(f'<line x1="{cx:.1f}" y1="{y(v["high"]):.1f}" x2="{cx:.1f}" '
                 f'y2="{y(v["low"]):.1f}" class="mecha {c}"/>')
        ya, yb = sorted((y(v["open"]), y(v["close"])))
        P.append(f'<rect x="{cx - grosor / 2:.1f}" y="{ya:.1f}" '
                 f'width="{grosor:.1f}" height="{max(1.0, yb - ya):.1f}" '
                 f'class="cuerpo {c}"/>')

    for nivel, clase in ((objetivo, "lprem"), (entrada, "lent"), (stop, "lries")):
        if not nivel:
            continue
        yy = y(nivel)
        P.append(f'<line x1="{x1:.1f}" y1="{yy:.1f}" x2="{ANCHO - DER}" '
                 f'y2="{yy:.1f}" class="{clase}"/>')
        P.append(f'<text x="{ANCHO - DER + 4}" y="{yy + 3.5:.1f}" '
                 f'class="etq {clase}">{nivel:.{digitos}f}</text>')

    for i, (t, precio) in enumerate(sorted(salidas)):
        k = int((t - velas["time"][0]) // 900)
        if 0 <= k < n:
            cual = "parcial" if i == 0 and len(salidas) > 1 else "final"
            P.append(f'<circle cx="{x(k):.1f}" cy="{y(precio):.1f}" r="3.4" '
                     f'class="salida {cual}"/>')
    P.append(f'<circle cx="{x1:.1f}" cy="{y(entrada):.1f}" r="3.8" class="marcaent"/>')

    for k in (0, n // 2, n - 1):
        ts = _local(int(velas["time"][k]))
        anc = "start" if k == 0 else ("end" if k == n - 1 else "middle")
        P.append(f'<text x="{x(k):.1f}" y="{ALTO - 6}" class="eje" '
                 f'text-anchor="{anc}">{ts.strftime("%d/%m %H:%M")}</text>')

    return (f'<svg viewBox="0 0 {ANCHO} {ALTO}" class="gr" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(P)}</svg>')


def _riesgo_de(venta, simbolo, lotes, entrada, stop):
    """Lo que se pierde si salta el stop. Se lo pregunta al terminal."""
    if not stop or stop <= 0.0:
        return None
    if (venta and stop <= entrada) or (not venta and stop >= entrada):
        return 0.0                       # el stop ya está a favor
    tipo = mt5.ORDER_TYPE_SELL if venta else mt5.ORDER_TYPE_BUY
    p = mt5.order_calc_profit(tipo, simbolo, lotes, entrada, stop)
    return abs(p) if p is not None else None


# ---------------------------------------------------------------- pintado


def render(d):
    return PLANTILLA.replace("__DATOS__", json.dumps(d, ensure_ascii=False))


PLANTILLA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Vantage EA</title>
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Vantage EA">
<meta name="theme-color" content="#0B1017">
<link rel="apple-touch-icon" href="icon.png">
<link rel="manifest" href="manifest.json">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap">
<style>
/* Sala de control, primero en vertical. Una pizarra azulada, una tinta de
   acento y las cifras en monoespaciada para que las columnas cuadren. */
:root{
  --fondo:#0B1017; --panel:#121A24; --hueco:#0E151E; --linea:#1F2B39;
  --tinta:#E6EDF5; --media:#A3B2C2; --apagada:#7D8FA3;
  --acento:#38BDF8; --sube:#34D399; --baja:#F87171; --aviso:#FBBF24;
  --texto:'Archivo',system-ui,-apple-system,sans-serif;
  --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,monospace;
  color-scheme:dark;
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--fondo);color:var(--tinta);font-family:var(--texto);
     font-size:14px;line-height:1.45;-webkit-font-smoothing:antialiased;
     -webkit-text-size-adjust:100%}
.envoltorio{max-width:1180px;margin:0 auto;padding:0 14px 32px}
@media(min-width:760px){.envoltorio{padding:0 20px 40px}}

/* ---- cabecera pegada arriba, con el hueco de la barra del movil ---- */
.alto{position:sticky;top:0;z-index:20;background:var(--fondo);
      padding-top:calc(12px + env(safe-area-inset-top,0px));padding-bottom:10px;
      border-bottom:1px solid var(--linea);
      display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.marca{font-weight:700;font-size:1rem;letter-spacing:-.01em;white-space:nowrap}
.marca span{color:var(--acento)}
.pulso{display:inline-flex;align-items:center;gap:6px;font-size:.66rem;
       letter-spacing:.08em;text-transform:uppercase;color:var(--sube)}
.pulso i{width:7px;height:7px;border-radius:50%;background:currentColor;
         box-shadow:0 0 0 3px color-mix(in srgb,currentColor 20%,transparent)}
.sello{margin-left:auto;font-family:var(--mono);font-size:.68rem;
       color:var(--apagada);text-align:right;min-width:0}

/* ---- las cifras de cabecera ---- */
.cifras{display:grid;gap:1px;background:var(--linea);
        border:1px solid var(--linea);margin:14px 0;
        grid-template-columns:repeat(2,1fr)}
@media(min-width:520px){.cifras{grid-template-columns:repeat(3,1fr)}}
@media(min-width:900px){.cifras{grid-template-columns:repeat(6,1fr)}}
.celda{background:var(--panel);padding:11px 13px;min-width:0}
.celda small{display:block;font-size:.64rem;letter-spacing:.09em;
             text-transform:uppercase;color:var(--apagada);margin-bottom:3px}
.celda b{display:block;font-family:var(--mono);font-size:1.3rem;font-weight:500;
         letter-spacing:-.02em;font-variant-numeric:tabular-nums;
         line-height:1.15;overflow-wrap:anywhere}
.celda em{font-style:normal;display:block;margin-top:2px;font-family:var(--mono);
          font-size:.68rem;color:var(--apagada)}
@media(min-width:900px){.celda b{font-size:1.45rem}}
.sube{color:var(--sube)} .baja{color:var(--baja)} .av{color:var(--aviso)}

/* ---- los mandos: chips que ruedan y el interruptor ---- */
.mandos{position:sticky;top:calc(45px + env(safe-area-inset-top,0px));z-index:15;
        background:var(--fondo);padding:9px 0 11px;
        display:flex;gap:9px;align-items:center}
.chips{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;
       -webkit-overflow-scrolling:touch;padding:2px 0;min-width:0;flex:1}
.chips::-webkit-scrollbar{display:none}
button{font:inherit;cursor:pointer;color:var(--media);background:var(--panel);
       border:1px solid var(--linea);padding:8px 14px;font-size:.78rem;
       white-space:nowrap;transition:background .14s,color .14s,border-color .14s;
       min-height:38px;border-radius:2px}
button:hover{color:var(--tinta);border-color:var(--apagada)}
button[aria-pressed="true"]{background:var(--acento);border-color:var(--acento);
       color:#06131C;font-weight:600}
button:focus-visible{outline:2px solid var(--acento);outline-offset:2px}
.palanca{display:flex;flex:0 0 auto;border:1px solid var(--linea)}
.palanca button{border:none;border-radius:0;padding:8px 13px}
.palanca button+button{border-left:1px solid var(--linea)}

/* ---- paneles ---- */
.caja{background:var(--panel);border:1px solid var(--linea);margin-bottom:12px;
      min-width:0}
.caja>header{display:flex;align-items:center;gap:9px;padding:10px 13px;
             border-bottom:1px solid var(--linea)}
.caja>header h2{margin:0;font-size:.7rem;letter-spacing:.1em;
                text-transform:uppercase;color:var(--apagada);font-weight:600}
.caja>header .ind{margin-left:auto;font-family:var(--mono);font-size:.8rem;
                  font-variant-numeric:tabular-nums}
.cuerpo{padding:12px 13px}
.par2{display:grid;gap:12px;grid-template-columns:1fr}
@media(min-width:900px){.par2{grid-template-columns:1fr 292px}}

/* ---- la curva ---- */
.curva{width:100%;height:auto;display:block}
.rej{stroke:var(--linea);stroke-width:1}
.relleno{fill:color-mix(in srgb,var(--acento) 13%,transparent);stroke:none}
.trazo{fill:none;stroke:var(--acento);stroke-width:2;stroke-linejoin:round;
       stroke-linecap:round}
.punta{fill:var(--acento);stroke:var(--panel);stroke-width:2}
.ejeY,.ejeX{font-family:var(--mono);font-size:10px;fill:var(--apagada)}
.ejeY{text-anchor:end}

/* ---- reparto por instrumento ---- */
.pares{display:flex;flex-direction:column;gap:11px}
.par{display:grid;grid-template-columns:66px 1fr auto;gap:8px;
     align-items:center}
.par b{font-family:var(--mono);font-size:.78rem;font-weight:500}
.riel{height:7px;background:var(--hueco);border:1px solid var(--linea);
      position:relative;overflow:hidden}
.riel i{position:absolute;inset:0 auto 0 0}
.par .val{font-family:var(--mono);font-size:.76rem;
          font-variant-numeric:tabular-nums}
.par .sub{grid-column:2/4;margin-top:-6px;font-family:var(--mono);
          font-size:.69rem;color:var(--apagada)}

/* ---- las operaciones: fichas en vertical, tabla en ancho ---- */
.lista{display:flex;flex-direction:column;gap:1px;background:var(--linea)}
.op{background:var(--panel);border-left:3px solid var(--linea);padding:0}
.op.g{border-left-color:var(--sube)} .op.p{border-left-color:var(--baja)}
.op>summary{list-style:none;cursor:pointer;padding:11px 13px;
            display:grid;grid-template-columns:auto 1fr auto;gap:4px 10px;
            align-items:center}
.op>summary::-webkit-details-marker{display:none}
.op>summary:focus-visible{outline:2px solid var(--acento);outline-offset:-2px}
.op .sim{font-size:.88rem;font-weight:600}
.op .r{font-family:var(--mono);font-size:1.05rem;font-weight:500;
       font-variant-numeric:tabular-nums;text-align:right}
.op .meta{grid-column:1/3;font-family:var(--mono);font-size:.69rem;
          color:var(--apagada);min-width:0;overflow-wrap:anywhere}
.op .din{font-family:var(--mono);font-size:.78rem;text-align:right;
         font-variant-numeric:tabular-nums}
.detalle{padding:0 13px 13px}
.detalle .gr{width:100%;height:auto;display:block;background:var(--hueco);
             border:1px solid var(--linea)}
.detalle dl{display:grid;grid-template-columns:auto 1fr;gap:3px 12px;
            margin:10px 0 0;font-family:var(--mono);font-size:.72rem}
.detalle dt{color:var(--apagada)} .detalle dd{margin:0;text-align:right}
.lado{display:inline-block;font-family:var(--mono);font-size:.62rem;
      letter-spacing:.06em;padding:1px 5px;border:1px solid currentColor}
.marca2{display:inline-block;font-family:var(--mono);font-size:.62rem;
        color:var(--aviso);border:1px solid var(--aviso);padding:1px 4px}
.tabla{display:none}
@media(min-width:760px){
  .lista{display:none}
  .tabla{display:block;overflow-x:auto}
  table{width:100%;border-collapse:collapse;font-size:.82rem}
  th{text-align:left;font-size:.65rem;letter-spacing:.1em;text-transform:uppercase;
     color:var(--apagada);font-weight:600;padding:9px 12px;
     border-bottom:1px solid var(--linea);white-space:nowrap}
  td{padding:9px 12px;border-bottom:1px solid var(--hueco);white-space:nowrap}
  tbody tr:hover{background:var(--hueco)}
  .num{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right}
  .franja{display:inline-block;width:3px;height:14px;vertical-align:-2px;
          margin-right:8px}
}
.vacio{padding:18px 13px;color:var(--apagada);font-size:.8rem}
/* los colores del grafico por operacion que genera el espejo */
.cuerpo.alcista,.mecha.alcista{fill:var(--sube);stroke:var(--sube)}
.cuerpo.bajista,.mecha.bajista{fill:var(--baja);stroke:var(--baja)}
.mecha{stroke-width:1}
.riesgo{fill:var(--baja);opacity:.13}
.premio{fill:var(--sube);opacity:.13}
.lent{stroke:var(--tinta);stroke-width:1.2;stroke-dasharray:3 2}
.lries{stroke:var(--baja);stroke-width:1;stroke-dasharray:4 3}
.lprem{stroke:var(--sube);stroke-width:1;stroke-dasharray:4 3}
.etq{font-family:var(--mono);font-size:8.5px;stroke:none}
text.lent{fill:var(--tinta)} text.lries{fill:var(--baja)}
text.lprem{fill:var(--sube)}
.marcaent{fill:var(--panel);stroke:var(--tinta);stroke-width:1.6}
.salida.parcial{fill:var(--aviso);stroke:var(--panel);stroke-width:1}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head><body>
<div class="envoltorio">
  <div class="alto">
    <div class="marca">VANTAGE <span>OB</span></div>
    <div class="pulso" id="pulso"><i></i><span>en linea</span></div>
    <div class="sello" id="sello"></div>
  </div>

  <div class="cifras" id="cifras"></div>

  <div class="mandos">
    <div class="chips" id="chips"></div>
    <div class="palanca">
      <button id="bEur" aria-pressed="true">€</button>
      <button id="bR" aria-pressed="false">R</button>
    </div>
  </div>

  <div class="par2">
    <div class="caja">
      <header><h2>Resultado acumulado</h2><div class="ind" id="indCurva"></div></header>
      <div class="cuerpo" id="grafico"></div>
    </div>
    <div class="caja">
      <header><h2>Por instrumento</h2></header>
      <div class="cuerpo"><div class="pares" id="pares"></div></div>
    </div>
  </div>

  <div class="caja">
    <header><h2>En espera</h2><div class="ind" id="indEsp"></div></header>
    <div id="espera"></div>
  </div>

  <div class="caja">
    <header><h2>Cerradas</h2><div class="ind" id="indOps"></div></header>
    <div class="lista" id="lista"></div>
    <div class="tabla" id="tabla"></div>
  </div>
</div>
<script>
const D = __DATOS__;
const fmt = (n, d = 2) => n.toLocaleString("es-ES",
      {minimumFractionDigits: d, maximumFractionDigits: d});
const eur = n => (n < 0 ? "−" : "+") + fmt(Math.abs(n), 0) + " €";
const rr  = n => (n < 0 ? "−" : "+") + fmt(Math.abs(n), 2);

// El orden es por CIERRE: el dinero entra en la cuenta al cerrar, no al abrir,
// y una curva ordenada por apertura ensena un recorrido que nunca ocurrio.
const cuando = s => {
  const [f, h] = s.split(" ");
  const [d, m] = f.split("/");
  const [H, M] = (h || "0:0").split(":");
  return new Date(2026, m - 1, d, H, M).getTime();
};
const cer = [...D.cerradas].sort((a, b) => cuando(a.cerrada) - cuando(b.cerrada));
const gana = cer.filter(o => o.beneficio > 0).length;
const acierto = cer.length ? 100 * gana / cer.length : 0;
const totalR = cer.reduce((s, o) => s + (o.r ?? 0), 0);
const totalE = cer.reduce((s, o) => s + o.beneficio, 0);

// La racha de perdidas mas cara. Es la cifra que dice si la cuenta aguanta, y
// en el panel viejo no estaba en ningun sitio.
let peor = 0, corre = 0;
for (const o of cer) { corre = o.beneficio < 0 ? corre + o.beneficio : 0;
                       peor = Math.min(peor, corre); }

// OJO CON EL NOMBRE. Esto se llamaba `pares`, igual que el id del <div> que
// lo pinta, y una `const` con el nombre de un elemento lo tapa: el
// `pares.innerHTML = ...` de mas abajo escribia sobre este objeto y el panel
// "Por instrumento" salia vacio sin dar ningun error.
const porPar = {};
for (const o of cer) {
  const p = porPar[o.simbolo] ??= {n: 0, g: 0, e: 0, r: 0};
  p.n++; p.e += o.beneficio; p.r += o.r ?? 0; if (o.beneficio > 0) p.g++;
}
const listaPares = Object.entries(porPar).sort((a, b) => b[1].e - a[1].e);

// LA HORA, EN RELATIVO. En el movil lo primero que uno quiere saber no es a
// que hora se genero, sino si lo que esta mirando es de ahora o de hace dos
// horas porque el ordenador se apago.
function haceCuanto(gen) {
  const [f, h] = gen.split(" ");
  const [d, m, a] = f.split("/");
  const [H, M] = h.split(":");
  const t = new Date(+a, m - 1, +d, +H, +M);
  const min = Math.round((Date.now() - t) / 60000);
  if (min < 1) return "ahora mismo";
  if (min < 60) return `hace ${min} min`;
  const hrs = Math.floor(min / 60);
  return hrs < 24 ? `hace ${hrs} h ${min % 60} min` : `hace ${Math.floor(hrs / 24)} d`;
}
function pintaSello() {
  const viejo = (Date.now() - new Date(D.generado.split(" ")[0]
    .split("/").reverse().join("-") + "T" + D.generado.split(" ")[1])) > 25 * 60000;
  sello.innerHTML = `${D.cuenta.login} · <span${viejo ?
    ' style="color:var(--aviso)"' : ""}>${haceCuanto(D.generado)}</span>`;
}
pintaSello();
setInterval(pintaSello, 30000);

// SE RECARGA SOLA cada 10 minutos, que es lo que tarda el espejo en volver a
// publicar. Solo cuando la pestana esta A LA VISTA: recargar una pestana de
// fondo gasta datos del movil y no la ve nadie. Al volver a ella se comprueba
// si toca y se recarga en el momento.
const CADA = 10 * 60 * 1000;
let ultima = Date.now();
function quizaRecargar() {
  if (document.visibilityState !== "visible") return;
  if (Date.now() - ultima >= CADA) location.reload();
}
setInterval(quizaRecargar, 20000);
document.addEventListener("visibilitychange", quizaRecargar);
if (!D.conectado) {
  pulso.innerHTML = "<i></i><span>sin conexion</span>";
  pulso.style.color = "var(--baja)";
}

cifras.innerHTML = [
  ["Balance", fmt(D.cuenta.balance, 0) + " €", "",
   `equidad ${fmt(D.cuenta.equidad, 0)}`],
  ["Resultado", eur(totalE), totalE >= 0 ? "sube" : "baja",
   `${rr(totalR)} R`],
  ["Acierto", fmt(acierto, 1) + " %", acierto >= 50 ? "sube" : "baja",
   `${gana} de ${cer.length}`],
  ["Peor racha", eur(peor), "baja", "seguidas"],
  ["Riesgo / op", fmt(D.riesgo, 0) + " €",
   "", `${fmt(100 * D.riesgo / D.cuenta.balance, 2)} %`],
  ["En juego", `${D.abiertas.length} / ${D.pendientes.length}`,
   D.abiertas.length ? "av" : "", "abiertas / espera"],
].map(([t, v, c, s]) =>
  `<div class="celda"><small>${t}</small><b class="${c}">${v}</b>` +
  `<em>${s}</em></div>`).join("");

const maxAbs = Math.max(...listaPares.map(([, p]) => Math.abs(p.e)), 1);
pares.innerHTML = listaPares.map(([s, p]) => `
  <div class="par"><b>${s}</b>
    <div class="riel"><i style="width:${(100 * Math.abs(p.e) / maxAbs).toFixed(1)}%;
      background:${p.e >= 0 ? "var(--sube)" : "var(--baja)"}"></i></div>
    <span class="val ${p.e >= 0 ? "sube" : "baja"}">${eur(p.e)}</span>
    <span class="sub">${p.n} ops · ${fmt(100 * p.g / p.n, 0)} % · ${rr(p.r)} R</span>
  </div>`).join("");

indEsp.textContent = D.pendientes.length || "";
espera.innerHTML = D.pendientes.length ? `<div class="lista">` +
  D.pendientes.map(o => `<div class="op" style="border-left-color:var(--acento)">
    <div style="padding:11px 13px;display:grid;
         grid-template-columns:auto 1fr auto;gap:4px 10px;align-items:center">
      <span class="sim">${o.simbolo}</span>
      <span class="r av" style="grid-column:3">${fmt(o.lotes, 2)} lotes</span>
      <span class="meta">${o.tipo} · nivel ${o.nivel} · stop ${o.stop}
        · objetivo ${o.objetivo} · puesta ${o.puesta}</span>
    </div></div>`).join("") + `</div>`
  : `<div class="vacio">Ninguna orden en espera.</div>`;

// ------------------------------------------------- filtro, escala y dibujo
let filtro = null, modo = "e";
const simbolos = [...new Set(cer.map(o => o.simbolo))].sort();
chips.innerHTML = `<button data-s="" aria-pressed="true">Todos</button>` +
  simbolos.map(s => `<button data-s="${s}" aria-pressed="false">${s}</button>`).join("");

function curvaSVG(sub) {
  const v = sub.map(o => o.v);
  const W = 720, H = 180, mI = 52, mD = 12, mT = 14, mB = 24;
  const lo = Math.min(0, ...v), hi = Math.max(0, ...v), ra = (hi - lo) || 1;
  const x = i => mI + (W - mI - mD) * (v.length === 1 ? .5 : i / (v.length - 1));
  const y = t => mT + (H - mT - mB) * (1 - (t - lo) / ra);
  const pts = v.map((t, i) => [x(i), y(t)]);
  const li = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " +
             p[1].toFixed(1)).join(" ");
  const ar = `${li} L${x(v.length - 1).toFixed(1)} ${y(0).toFixed(1)}` +
             ` L${x(0).toFixed(1)} ${y(0).toFixed(1)} Z`;
  let rej = "", etq = "";
  for (let k = 0; k <= 4; k++) {
    const t = lo + ra * k / 4, yy = y(t);
    rej += `<line x1="${mI}" y1="${yy.toFixed(1)}" x2="${W - mD}"` +
           ` y2="${yy.toFixed(1)}" class="rej"/>`;
    etq += `<text x="${mI - 8}" y="${(yy + 3.5).toFixed(1)}" class="ejeY">` +
           (modo === "e" ? fmt(t, 0) : fmt(t, 1)) + `</text>`;
  }
  const f = pts[pts.length - 1];
  return `<svg viewBox="0 0 ${W} ${H}" class="curva" role="img"
    aria-label="Acumulado de ${v.length} operaciones cerradas">${rej}${etq}
    <path d="${ar}" class="relleno"/><path d="${li}" class="trazo"/>
    <circle cx="${f[0].toFixed(1)}" cy="${f[1].toFixed(1)}" r="4" class="punta"/>
    <text x="${mI}" y="${H - 7}" class="ejeX">${sub[0].cerrada}</text>
    <text x="${W - mD}" y="${H - 7}" class="ejeX" text-anchor="end"
      >${sub[sub.length - 1].cerrada}</text></svg>`;
}

function ficha(o) {
  const sig = o.beneficio >= 0;
  return `<details class="op ${sig ? "g" : "p"}">
    <summary>
      <span class="sim">${o.simbolo}</span>
      <span class="r ${sig ? "sube" : "baja"}" style="grid-column:3"
        >${rr(o.r ?? 0)}</span>
      <span class="meta"><span class="lado" style="color:${
        o.lado === "VENTA" ? "var(--baja)" : "var(--sube)"}">${o.lado}</span>
        ${o.entrada} · ${fmt(o.horas, 1)} h · ${o.cerrada}${
        o.parcial ? ' <span class="marca2">parcial</span>' : ""}</span>
      <span class="din ${sig ? "sube" : "baja"}" style="grid-column:3"
        >${eur(o.beneficio)}</span>
    </summary>
    <div class="detalle">
      ${o.grafico || ""}
      <dl><dt>Entrada</dt><dd>${o.entrada}</dd>
        <dt>Stop</dt><dd class="baja">${o.stop}</dd>
        <dt>Objetivo</dt><dd class="sube">${o.objetivo}</dd>
        <dt>Riesgo</dt><dd>${fmt(o.riesgo, 2)} €</dd>
        <dt>Abierta</dt><dd>${o.abierta}</dd>
        <dt>Cerrada</dt><dd>${o.cerrada}</dd></dl>
    </div></details>`;
}

function pinta() {
  const vis = filtro ? cer.filter(o => o.simbolo === filtro) : cer;
  let a = 0;
  const sub = vis.map(o => ({...o,
    v: (a += modo === "e" ? o.beneficio : (o.r ?? 0))}));

  grafico.innerHTML = sub.length ? curvaSVG(sub)
    : `<div class="vacio">Sin operaciones.</div>`;
  const tot = sub.length ? sub[sub.length - 1].v : 0;
  indCurva.innerHTML = `<span class="${tot >= 0 ? "sube" : "baja"}">` +
    (modo === "e" ? eur(tot) : rr(tot) + " R") + `</span>`;
  indOps.textContent = filtro ? `${vis.length} de ${cer.length}` : vis.length;

  const rev = [...vis].reverse();
  lista.innerHTML = rev.length ? rev.map(ficha).join("")
    : `<div class="vacio">Sin operaciones para ese filtro.</div>`;
  tabla.innerHTML = rev.length ? `<table><thead><tr>
    <th>Instrumento</th><th>Lado</th><th class="num">Entrada</th>
    <th class="num">R</th><th class="num">Resultado</th>
    <th class="num">Horas</th><th>Cerrada</th></tr></thead><tbody>` +
    rev.map(o => `<tr>
      <td><i class="franja" style="background:${o.beneficio >= 0 ?
        "var(--sube)" : "var(--baja)"}"></i>${o.simbolo}</td>
      <td><span class="lado" style="color:${o.lado === "VENTA" ?
        "var(--baja)" : "var(--sube)"}">${o.lado}</span></td>
      <td class="num">${o.entrada}</td>
      <td class="num ${o.r >= 0 ? "sube" : "baja"}">${rr(o.r ?? 0)}</td>
      <td class="num ${o.beneficio >= 0 ? "sube" : "baja"}">${eur(o.beneficio)}</td>
      <td class="num">${fmt(o.horas, 1)}</td>
      <td style="color:var(--apagada)">${o.cerrada}</td></tr>`).join("") +
    `</tbody></table>` : "";
}

chips.addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  filtro = b.dataset.s || null;
  chips.querySelectorAll("button").forEach(o =>
    o.setAttribute("aria-pressed", String(o === b)));
  pinta();
});
function escala(nuevo, si, no) {
  modo = nuevo;
  si.setAttribute("aria-pressed", "true");
  no.setAttribute("aria-pressed", "false");
  pinta();
}
bEur.onclick = () => escala("e", bEur, bR);
bR.onclick   = () => escala("r", bR, bEur);
pinta();
</script></body></html>
"""


# ---------------------------------------------------------------- principal


def publicar(salida):
    """
    Sube la página a GitHub para que la app la vea.

    Rebasa antes de empujar. Ya no hay nada más publicando en este repositorio
    —el bot de acciones se retiró—, pero el rebase se queda: cuesta nada y
    cubre el caso de haber tocado el repositorio desde otro sitio.
    """
    def git(*args, **kw):
        return subprocess.run(["git", *args], capture_output=True, text=True, **kw)

    # El orden importa: primero el commit, DESPUES el rebase. Al reves git se
    # niega -- "cannot pull with rebase: you have unstaged changes" -- porque
    # la pagina acaba de reescribirse.
    git("add", salida)
    marca = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    r = git("commit", "-m", f"Espejo de la EA — {marca}")
    if "nothing to commit" in (r.stdout + r.stderr):
        return "sin cambios que subir"

    # autoStash: cualquier otro fichero del repositorio que este a medias no
    # tiene por que bloquear la publicacion. Git lo guarda, rebasa, y lo
    # devuelve tal cual estaba.
    r = git("-c", "rebase.autoStash=true", "pull", "--rebase", "origin", "main")
    if r.returncode:
        return f"no se pudo rebasar: {(r.stderr or r.stdout).strip()[:90]}"

    r = git("push", "origin", "main")
    if r.returncode:
        return f"no se pudo subir: {(r.stderr or r.stdout).strip()[:90]}"
    return "publicado"


def _sin_marca(html):
    """El contenido sin la hora de generación, para comparar dos versiones."""
    return re.sub(r'"generado": *"[^"]*"', "", html)


def una_vuelta(salida):
    """
    Lee el terminal y reescribe la página. Devuelve (datos, resumen, cambió).

    `cambió` compara ignorando la hora de generación: sin eso, la página sería
    distinta en cada vuelta aunque no hubiera pasado nada, y publicarla
    dejaría noventa y seis commits al día sin ninguna información dentro.
    """
    d = leer_terminal()
    if "error" in d:
        return None, d["error"], False

    nuevo = render(d)
    antes = ""
    if os.path.exists(salida):
        antes = io.open(salida, encoding="utf-8").read()
    cambio = _sin_marca(antes) != _sin_marca(nuevo)

    io.open(salida, "w", encoding="utf-8").write(nuevo)

    texto = (f"abiertas {len(d['abiertas'])}  pendientes {len(d['pendientes'])}"
             f"  cerradas {len(d['cerradas'])}")
    if d["cerradas"]:
        r = [x["r"] for x in d["cerradas"]]
        gana = sum(1 for x in r if x > 0)
        texto += f"  |  {100.0 * gana / len(r):.0f}% acierto  {sum(r):+.2f} R"
    return d, texto, cambio


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=SALIDA)
    ap.add_argument("--abrir", action="store_true")
    ap.add_argument("--cada", type=int, default=0, metavar="MINUTOS",
                    help="rehacer la página cada N minutos, sin parar")
    ap.add_argument("--publicar", action="store_true",
                    help="subirla a GitHub cuando cambie, para que la app la vea")
    args = ap.parse_args()

    # --- una sola vez ------------------------------------------------
    if args.cada <= 0:
        d, texto, _ = una_vuelta(args.salida)
        print()
        if d is None:
            print(" ", texto)
            print("  ¿Está MetaTrader 5 abierto?")
            return 1
        print(f"  {args.salida} escrito.")
        print(f"  {texto}")
        print()
        if args.abrir:
            os.startfile(os.path.abspath(args.salida))
        return 0

    # --- en bucle ----------------------------------------------------
    #
    # Se reconecta al terminal en cada vuelta y suelta la conexión al
    # terminar: si MetaTrader se cierra o se reinicia, la vuelta siguiente
    # vuelve a engancharse sola en vez de quedarse colgada para siempre.
    print()
    print(f"  Rehaciendo {args.salida} cada {args.cada} minutos.")
    print("  Para parar: Ctrl+C")
    print()
    if args.abrir:
        una_vuelta(args.salida)
        os.startfile(os.path.abspath(args.salida))
    if args.publicar:
        print("  Se publicará en GitHub cada vez que cambie algo.")
        print()

    fallos = 0
    try:
        while True:
            marca = dt.datetime.now().strftime("%H:%M:%S")
            try:
                d, texto, cambio = una_vuelta(args.salida)
            except Exception as e:               # noqa: BLE001
                d, texto, cambio = None, f"error inesperado: {e}", False

            if d is None:
                fallos += 1
                print(f"  {marca}  sin datos ({texto})")
                # Un aviso cada cuatro fallos seguidos, no en cada vuelta:
                # con MetaTrader cerrado esto llenaría la pantalla.
                if fallos % 4 == 1:
                    print("            ¿Está MetaTrader 5 abierto y conectado?")
            else:
                if fallos:
                    print(f"  {marca}  recuperado")
                fallos = 0
                print(f"  {marca}  {texto}")
                if args.publicar and cambio:
                    print(f"            {publicar(args.salida)}")

            time.sleep(args.cada * 60)
    except KeyboardInterrupt:
        print()
        print("  Parado.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
