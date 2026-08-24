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

# El mágico del EA. Si se cambia en el robot, hay que cambiarlo aquí.
MAGICO = 20260822

# Lo que el robot arriesga por operación, para poder expresar los resultados
# en R. Es un parámetro suyo, no algo que se pueda deducir del historial de
# una operación ya cerrada.
RIESGO_POR_OPERACION = 500.0

DIAS_HISTORIAL = 180
SALIDA = "dashboard.html"

TIPOS_ORDEN = {
    mt5.ORDER_TYPE_BUY_LIMIT: "compra limitada",
    mt5.ORDER_TYPE_SELL_LIMIT: "venta limitada",
    mt5.ORDER_TYPE_BUY_STOP: "compra parada",
    mt5.ORDER_TYPE_SELL_STOP: "venta parada",
}


# ---------------------------------------------------------------- lectura


def leer_terminal():
    """Todo lo que hay que saber del terminal, en un diccionario."""
    if not mt5.initialize():
        return {"error": f"no se pudo conectar con MetaTrader 5: {mt5.last_error()}"}

    try:
        ti = mt5.terminal_info()
        ai = mt5.account_info()
        return {
            "generado": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "conectado": bool(ti and ti.connected),
            "magico": MAGICO,
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
        if p.magic != MAGICO:
            continue
        venta = p.type == mt5.POSITION_TYPE_SELL
        riesgo = _riesgo_de(venta, p.symbol, p.volume, p.price_open, p.sl)
        n = _dig(p.symbol)
        abierta = dt.datetime.fromtimestamp(p.time)
        filas.append({
            "simbolo": p.symbol,
            "lado": "VENTA" if venta else "COMPRA",
            "lotes": p.volume,
            "entrada": round(p.price_open, n),
            "stop": round(p.sl, n),
            "objetivo": round(p.tp, n),
            "flotante": round(p.profit, 2),
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
        if o.magic != MAGICO:
            continue
        n = _dig(o.symbol)
        puesta = dt.datetime.fromtimestamp(o.time_setup)
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
        if o.magic == MAGICO and o.position_id and (o.sl or o.tp):
            niveles.setdefault(o.position_id, (o.sl, o.tp))

    por_posicion = {}
    for d in deals:
        if d.magic != MAGICO:
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
        else:
            p["beneficio"] += d.profit + d.swap + d.commission
            p["cerrada"] = d.time
            p["salidas"] += 1
            p["puntos"].append((d.time, d.price))

    filas = []
    for pid, p in por_posicion.items():
        if p["abierta"] is None or p["cerrada"] is None:
            continue          # todavía viva: sale en las abiertas
        a = dt.datetime.fromtimestamp(p["abierta"])
        c = dt.datetime.fromtimestamp(p["cerrada"])
        sl, tp = niveles.get(pid, (0.0, 0.0))
        n = _dig(p["simbolo"])
        filas.append({
            "grafico": _svg(p["simbolo"], p["entrada"], sl, tp,
                            p["abierta"], p["puntos"], n),
            "stop": round(sl, n),
            "objetivo": round(tp, n),
            "simbolo": p["simbolo"],
            "lado": p["lado"],
            "beneficio": round(p["beneficio"], 2),
            "r": round(p["beneficio"] / RIESGO_POR_OPERACION, 2),
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
        dt.datetime.fromtimestamp(t_in - VELAS_ANTES * 900),
        dt.datetime.fromtimestamp(t_fin + VELAS_DESPUES * 900))
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
        ts = dt.datetime.fromtimestamp(int(velas["time"][k]))
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
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Vantage EA</title>
<!-- Sin esto la pagina se abre como una web normal, no como app instalada. -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Vantage EA">
<meta name="theme-color" content="#F4E8DA">
<link rel="apple-touch-icon" href="icon.png">
<link rel="manifest" href="manifest.json">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:wght@500;700&family=IBM+Plex+Mono:wght@400;500&family=Newsreader:ital,wght@0,400;0,600;1,400&display=swap">
<style>
  :root{
    --paper:#F4E8DA; --ink:#17120D; --rule:#C4AE95; --muted:#7C6B58;
    --bull:#1B5E43; --bear:#9E2B21; --mark:#1F3A5F; --tarjeta:#FBF4EA;
  }
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]){
      --paper:#14110D; --ink:#EDE3D6; --rule:#4A3F33; --muted:#9C8A76;
      --bull:#5FBE93; --bear:#E0705F; --mark:#7FA8D4; --tarjeta:#1D1913;
    }
  }
  :root[data-theme="dark"]{
    --paper:#14110D; --ink:#EDE3D6; --rule:#4A3F33; --muted:#9C8A76;
    --bull:#5FBE93; --bear:#E0705F; --mark:#7FA8D4; --tarjeta:#1D1913;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);
       font-family:'Newsreader',Georgia,serif;line-height:1.5}
  .hoja{max-width:1140px;margin:0 auto;padding:2rem 1.1rem 4rem}
  .mono{font-family:'IBM Plex Mono',ui-monospace,monospace;
        font-variant-numeric:tabular-nums}

  header{border-bottom:3px double var(--rule);padding-bottom:1rem}
  h1{font-family:'Bodoni Moda','Didot',serif;font-weight:700;
     font-size:clamp(1.9rem,5vw,3rem);margin:0;letter-spacing:-0.01em;
     text-wrap:balance}
  .cintillo{display:flex;flex-wrap:wrap;gap:.4rem 1.4rem;margin-top:.9rem;
            font-size:.82rem;color:var(--muted)}
  .cintillo b{color:var(--ink);font-weight:600}

  /* --- pestanas --- */
  .pestanas{display:flex;margin-top:1.6rem;border-bottom:1px solid var(--rule)}
  .pestanas button{font-family:'Newsreader',serif;font-size:.95rem;
    background:transparent;color:var(--muted);border:0;cursor:pointer;
    padding:.65rem 1.15rem;border-bottom:2px solid transparent;
    margin-bottom:-1px;display:flex;align-items:baseline;gap:.5rem}
  .pestanas button .n{font-family:'IBM Plex Mono',monospace;font-size:.78rem;
    background:var(--tarjeta);border:1px solid var(--rule);padding:0 .35rem}
  .pestanas button.on{color:var(--ink);border-bottom-color:var(--mark);
    font-weight:600}
  .pestanas button:hover{color:var(--ink)}
  .pestanas button:focus-visible{outline:2px solid var(--mark);outline-offset:-2px}
  .hoja-pestana{display:none}
  .hoja-pestana.on{display:block}

  h2{font-size:.76rem;text-transform:uppercase;letter-spacing:.14em;
     color:var(--muted);font-weight:600;margin:1.7rem 0 0;
     border-bottom:1px solid var(--rule);padding-bottom:.35rem;
     display:flex;gap:.7rem;align-items:baseline}
  h2 .cuenta{margin-left:auto;letter-spacing:0}

  /* --- cifras --- */
  .cifras{display:grid;gap:.7rem;margin-top:1rem;
          grid-template-columns:repeat(auto-fit,minmax(138px,1fr))}
  .cifra{background:var(--tarjeta);border:1px solid var(--rule);padding:.8rem .9rem}
  .cifra .n{display:block;font-family:'Bodoni Moda',serif;font-size:1.7rem;
            font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums}
  .cifra .e{font-size:.7rem;text-transform:uppercase;letter-spacing:.09em;
            color:var(--muted)}

  /* --- filtros --- */
  .filtros{background:var(--tarjeta);border:1px solid var(--rule);
           padding:.9rem 1rem;margin-top:1.4rem;display:flex;flex-wrap:wrap;
           gap:.8rem 1.4rem;align-items:flex-end}
  .campo{display:flex;flex-direction:column;gap:.25rem}
  .campo label{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;
               color:var(--muted);font-weight:600}
  .filtros input[type=date],.filtros select{
    font-family:'IBM Plex Mono',monospace;font-size:.84rem;
    background:var(--paper);color:var(--ink);
    border:1px solid var(--rule);border-radius:0;padding:.35rem .5rem}
  .filtros input:focus-visible,.filtros select:focus-visible,
  .filtros button:focus-visible{
    outline:2px solid var(--mark);outline-offset:1px}
  .filtros>button{font-family:'Newsreader',serif;font-size:.85rem;
    background:transparent;color:var(--mark);border:1px solid var(--mark);
    padding:.4rem .9rem;cursor:pointer}
  .filtros>button:hover{background:var(--mark);color:var(--paper)}
  .conmutador{display:flex;border:1px solid var(--rule)}
  .conmutador button{border:0;border-right:1px solid var(--rule);cursor:pointer;
    background:transparent;color:var(--muted);padding:.4rem .8rem;
    font-size:.8rem;font-family:'Newsreader',serif}
  .conmutador button:last-child{border-right:0}
  .conmutador button.on{background:var(--mark);color:var(--paper)}

  /* --- tarjetas --- */
  .mazo{display:grid;gap:.8rem;margin-top:1rem;
        grid-template-columns:repeat(auto-fill,minmax(258px,1fr))}
  #listaCerradas .mazo{grid-template-columns:repeat(auto-fill,minmax(420px,1fr))}
  .t{background:var(--tarjeta);border:1px solid var(--rule);
     border-left:4px solid var(--rule);padding:.85rem .95rem;
     display:flex;flex-direction:column;gap:.5rem}
  .t.gana{border-left-color:var(--bull)}
  .t.pierde{border-left-color:var(--bear)}
  .t .alto{display:flex;align-items:baseline;gap:.45rem;flex-wrap:wrap}
  .t .sim{font-family:'Bodoni Moda',serif;font-size:1.15rem;font-weight:700}
  .t .r{margin-left:auto;font-family:'IBM Plex Mono',monospace;
        font-size:1.2rem;font-weight:500;font-variant-numeric:tabular-nums}
  .t .dinero{font-family:'IBM Plex Mono',monospace;font-size:.9rem}
  .t .linea{display:flex;justify-content:space-between;gap:.6rem;
            font-size:.78rem;color:var(--muted);
            border-top:1px solid color-mix(in srgb,var(--rule) 50%,transparent);
            padding-top:.4rem}
  .t .linea .mono{color:var(--ink)}
  .sube{color:var(--bull)} .baja{color:var(--bear)}
  .venta,.compra{font-size:.66rem;letter-spacing:.07em;padding:.1rem .4rem;
        border:1px solid currentColor;white-space:nowrap}
  .venta{color:var(--bear)} .compra{color:var(--bull)}
  .marca{font-size:.64rem;letter-spacing:.05em;color:var(--mark);
         border:1px solid var(--mark);padding:.05rem .3rem;white-space:nowrap}
  /* --- el grafico de cada operacion --- */
  .gr{width:100%;height:auto;display:block;margin:.15rem 0 .1rem;
      background:color-mix(in srgb,var(--paper) 55%,transparent);
      border:1px solid color-mix(in srgb,var(--rule) 55%,transparent)}
  .cuerpo.alcista,.mecha.alcista{fill:var(--bull);stroke:var(--bull)}
  .cuerpo.bajista,.mecha.bajista{fill:var(--bear);stroke:var(--bear)}
  .mecha{stroke-width:1}
  .riesgo{fill:var(--bear);opacity:.12}
  .premio{fill:var(--bull);opacity:.12}
  .lent{stroke:var(--ink);stroke-width:1.2;stroke-dasharray:3 2}
  .lries{stroke:var(--bear);stroke-width:1;stroke-dasharray:4 3}
  .lprem{stroke:var(--bull);stroke-width:1;stroke-dasharray:4 3}
  .etq{font-family:'IBM Plex Mono',monospace;font-size:8.5px;stroke:none}
  text.lent{fill:var(--ink)}
  text.lries{fill:var(--bear)}
  text.lprem{fill:var(--bull)}
  .marcaent{fill:var(--paper);stroke:var(--ink);stroke-width:1.6}
  .salida.parcial{fill:var(--mark);stroke:var(--paper);stroke-width:1}
  .salida.final{fill:var(--ink);stroke:var(--paper);stroke-width:1}
  .eje{font-family:'IBM Plex Mono',monospace;font-size:8px;fill:var(--muted)}

  .vacio{background:var(--tarjeta);border:1px dashed var(--rule);
         padding:1.1rem;color:var(--muted);font-style:italic;margin-top:1rem}
  .nota{color:var(--muted);font-style:italic;margin:.7rem 0 0;font-size:.88rem}
  footer{margin-top:3rem;border-top:1px solid var(--rule);padding-top:.9rem;
         font-size:.76rem;color:var(--muted)}
</style>
</head>
<body>
<div class="hoja">
  <header>
    <h1>Vantage EA</h1>
    <div class="cintillo" id="cintillo"></div>
  </header>

  <nav class="pestanas">
    <button data-hoja="curso" class="on">En curso <span class="n" id="nCurso">0</span></button>
    <button data-hoja="cerradas">Operaciones cerradas <span class="n" id="nCerradas">0</span></button>
  </nav>

  <div class="hoja-pestana on" id="curso">
    <h2>Posiciones abiertas<span class="cuenta mono" id="nAbiertas">0</span></h2>
    <div id="abiertas"></div>
    <h2>Órdenes esperando<span class="cuenta mono" id="nPendientes">0</span></h2>
    <div id="pendientes"></div>
  </div>

  <div class="hoja-pestana" id="cerradas">
    <div class="filtros">
      <div class="campo">
        <label>Filtrar por</label>
        <div class="conmutador" id="porQue">
          <button data-campo="cerrada_dia" class="on">Fecha de cierre</button>
          <button data-campo="abierta_dia">Fecha de entrada</button>
        </div>
      </div>
      <div class="campo">
        <label for="desde">Desde</label>
        <input type="date" id="desde">
      </div>
      <div class="campo">
        <label for="hasta">Hasta</label>
        <input type="date" id="hasta">
      </div>
      <div class="campo">
        <label for="par">Par</label>
        <select id="par"><option value="">Todos</option></select>
      </div>
      <div class="campo">
        <label>Resultado</label>
        <div class="conmutador" id="resultado">
          <button data-r="" class="on">Todas</button>
          <button data-r="gana">Ganadas</button>
          <button data-r="pierde">Perdidas</button>
        </div>
      </div>
      <button id="limpiar">Ver todo</button>
    </div>
    <div id="resumen"></div>
    <div id="listaCerradas"></div>
  </div>

  <footer id="pie"></footer>
</div>

<script>
const D = __DATOS__;
const DIV = D.cuenta.divisa || "";

const esc = s => String(s).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const eur = n => (n >= 0 ? "+" : "") + n.toLocaleString("es-ES",
  {minimumFractionDigits:2, maximumFractionDigits:2}) + " " + DIV;
const signo = n => n > 0 ? "sube" : (n < 0 ? "baja" : "");
const lado  = l => `<span class="${l === "VENTA" ? "venta" : "compra"}">${l}</span>`;
const conR  = n => (n > 0 ? "+" : "") + n.toFixed(2);

function mazo(id, tarjetas, vacio) {
  document.getElementById(id).innerHTML = tarjetas.length
    ? `<div class="mazo">${tarjetas.join("")}</div>`
    : `<div class="vacio">${vacio}</div>`;
}

document.getElementById("cintillo").innerHTML = [
  `Balance <b class="mono">${D.cuenta.balance.toLocaleString("es-ES")}</b>`,
  `Equidad <b class="mono">${D.cuenta.equidad.toLocaleString("es-ES")}</b>`,
].filter(Boolean).join("<span>·</span>");

// --- pestanas -----------------------------------------------------------
document.querySelectorAll(".pestanas button").forEach(b => {
  b.addEventListener("click", () => {
    document.querySelectorAll(".pestanas button").forEach(x => x.classList.remove("on"));
    document.querySelectorAll(".hoja-pestana").forEach(x => x.classList.remove("on"));
    b.classList.add("on");
    document.getElementById(b.dataset.hoja).classList.add("on");
  });
});

// --- en curso -----------------------------------------------------------
document.getElementById("nCurso").textContent = D.abiertas.length + D.pendientes.length;
document.getElementById("nAbiertas").textContent = D.abiertas.length;
document.getElementById("nPendientes").textContent = D.pendientes.length;

mazo("abiertas", D.abiertas.map(p => `
  <article class="t ${p.flotante > 0 ? "gana" : (p.flotante < 0 ? "pierde" : "")}">
    <div class="alto">
      <span class="sim">${esc(p.simbolo)}</span>
      ${lado(p.lado)}
      ${p.en_breakeven ? '<span class="marca">break-even</span>' : ""}
      <span class="r ${signo(p.flotante)}">${eur(p.flotante)}</span>
    </div>
    <div class="linea"><span>Entrada</span><span class="mono">${p.entrada}</span></div>
    <div class="linea"><span>Stop</span><span class="mono">${p.stop || "—"}</span></div>
    <div class="linea"><span>Objetivo</span><span class="mono">${p.objetivo || "—"}</span></div>
    <div class="linea"><span>${p.lotes} lotes · desde</span><span class="mono">${esc(p.abierta_desde)}</span></div>
  </article>`),
  "Ninguna posición abierta ahora mismo.");

mazo("pendientes", D.pendientes.map(o => `
  <article class="t">
    <div class="alto">
      <span class="sim">${esc(o.simbolo)}</span>
      <span class="marca">${esc(o.tipo)}</span>
      <span class="r mono">${o.nivel}</span>
    </div>
    <div class="linea"><span>Stop</span><span class="mono">${o.stop || "—"}</span></div>
    <div class="linea"><span>Objetivo</span><span class="mono">${o.objetivo || "—"}</span></div>
    <div class="linea"><span>${o.lotes} lotes · puesta</span><span class="mono">${esc(o.puesta)}</span></div>
  </article>`),
  "Ninguna orden puesta. El robot solo coloca una cuando hay un order block vivo y el precio está del lado que toca.");

// --- cerradas, con filtros ----------------------------------------------
let campoFecha = "cerrada_dia";
let resultado = "";

// El desplegable de pares se llena con los que REALMENTE hay en el historial,
// no con una lista fija: así nunca ofrece un par sin operaciones ni se deja
// fuera uno nuevo.
const selPar = document.getElementById("par");
[...new Set(D.cerradas.map(c => c.simbolo))].sort().forEach(s => {
  const o = document.createElement("option");
  o.value = s; o.textContent = s;
  selPar.appendChild(o);
});

function pintarCerradas() {
  const desde = document.getElementById("desde").value;
  const hasta = document.getElementById("hasta").value;
  const par = selPar.value;

  const filas = D.cerradas.filter(c => {
    const d = c[campoFecha];
    if (desde && d < desde) return false;
    if (hasta && d > hasta) return false;
    if (par && c.simbolo !== par) return false;
    // El cero cuenta como perdida: una operacion que sale plana no ha ganado.
    if (resultado === "gana" && !(c.r > 0)) return false;
    if (resultado === "pierde" && c.r > 0) return false;
    return true;
  });

  document.getElementById("nCerradas").textContent =
    filas.length === D.cerradas.length
      ? filas.length : filas.length + "/" + D.cerradas.length;

  // El resumen se recalcula SOBRE LO FILTRADO. Si no, el filtro engañaría:
  // enseñaría cinco operaciones de un mes y el balance de seis meses.
  const res = document.getElementById("resumen");
  if (filas.length) {
    const r = filas.map(x => x.r);
    const suma = r.reduce((a, b) => a + b, 0);
    const gana = r.filter(x => x > 0).length;
    const euros = filas.reduce((a, b) => a + b.beneficio, 0);
    res.innerHTML = `<div class="cifras">
      <div class="cifra"><span class="n mono">${filas.length}</span><span class="e">operaciones</span></div>
      <div class="cifra"><span class="n mono">${(100 * gana / filas.length).toFixed(1)}%</span><span class="e">acierto</span></div>
      <div class="cifra"><span class="n mono ${signo(suma)}">${conR(suma)}</span><span class="e">R acumulados</span></div>
      <div class="cifra"><span class="n mono ${signo(suma)}">${conR(suma / filas.length)}</span><span class="e">R por operación</span></div>
      <div class="cifra"><span class="n mono ${signo(euros)}">${eur(euros)}</span><span class="e">resultado</span></div>
    </div>
    <p class="nota">Los R salen de dividir el resultado entre los ${D.riesgo} ${DIV}
      que el robot arriesga por operación.</p>`;
  } else {
    res.innerHTML = "";
  }

  mazo("listaCerradas", filas.map(c => `
    <article class="t ${c.r > 0 ? "gana" : (c.r < 0 ? "pierde" : "")}">
      <div class="alto">
        <span class="sim">${esc(c.simbolo)}</span>
        ${lado(c.lado)}
        ${c.parcial ? '<span class="marca">con parcial</span>' : ""}
        <span class="r ${signo(c.r)}">${conR(c.r)} R</span>
      </div>
      ${c.grafico || ""}
      <div class="dinero ${signo(c.beneficio)}">${eur(c.beneficio)}</div>
      <div class="linea"><span>Entrada</span><span class="mono">${c.entrada}</span></div>
      <div class="linea"><span>Abierta</span><span class="mono">${esc(c.abierta)}</span></div>
      <div class="linea"><span>Cierre</span><span class="mono">${esc(c.cerrada)}</span></div>
      <div class="linea"><span>Duración</span><span class="mono">${c.horas} h</span></div>
    </article>`),
    D.cerradas.length
      ? "Ninguna operación con esos filtros."
      : "Todavía no ha cerrado ninguna operación.");
}

document.querySelectorAll("#porQue button").forEach(b => {
  b.addEventListener("click", () => {
    document.querySelectorAll("#porQue button").forEach(x => x.classList.remove("on"));
    b.classList.add("on");
    campoFecha = b.dataset.campo;
    pintarCerradas();
  });
});
document.querySelectorAll("#resultado button").forEach(b => {
  b.addEventListener("click", () => {
    document.querySelectorAll("#resultado button").forEach(x => x.classList.remove("on"));
    b.classList.add("on");
    resultado = b.dataset.r;
    pintarCerradas();
  });
});
["desde", "hasta"].forEach(id =>
  document.getElementById(id).addEventListener("change", pintarCerradas));
selPar.addEventListener("change", pintarCerradas);
document.getElementById("limpiar").addEventListener("click", () => {
  document.getElementById("desde").value = "";
  document.getElementById("hasta").value = "";
  selPar.value = "";
  resultado = "";
  document.querySelectorAll("#resultado button").forEach((x, i) =>
    x.classList.toggle("on", i === 0));
  pintarCerradas();
});

pintarCerradas();

document.getElementById("pie").textContent =
  "Página estática. La genera espejo.py leyendo el terminal; no calcula nada " +
  "ni decide nada.";
</script>
</body>
</html>
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
