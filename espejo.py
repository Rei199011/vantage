"""
Vantage — Espejo de la EA
-------------------------
Genera `dashboard.html` como reflejo de lo que hace el robot de order blocks
en MetaTrader 5. No calcula señales ni decide nada: lee el terminal y lo pinta.

    python espejo.py            # escribe dashboard.html
    python espejo.py --abrir    # y lo abre en el navegador

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
import sys

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
    deals = mt5.history_deals_get(desde, dt.datetime.now() + dt.timedelta(days=1)) or []

    por_posicion = {}
    for d in deals:
        if d.magic != MAGICO:
            continue
        p = por_posicion.setdefault(d.position_id, {
            "simbolo": d.symbol, "lado": "", "beneficio": 0.0,
            "abierta": None, "cerrada": None, "entrada": 0.0, "salidas": 0,
        })
        if d.entry == mt5.DEAL_ENTRY_IN:
            p["lado"] = "VENTA" if d.type == mt5.DEAL_TYPE_SELL else "COMPRA"
            p["abierta"] = d.time
            p["entrada"] = d.price
        else:
            p["beneficio"] += d.profit + d.swap + d.commission
            p["cerrada"] = d.time
            p["salidas"] += 1

    filas = []
    for p in por_posicion.values():
        if p["abierta"] is None or p["cerrada"] is None:
            continue          # todavía viva: sale en las abiertas
        a = dt.datetime.fromtimestamp(p["abierta"])
        c = dt.datetime.fromtimestamp(p["cerrada"])
        filas.append({
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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vantage EA</title>
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
      <div class="dinero ${signo(c.beneficio)}">${eur(c.beneficio)}</div>
      <div class="linea"><span>Entrada</span><span class="mono">${esc(c.abierta)}</span></div>
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=SALIDA)
    ap.add_argument("--abrir", action="store_true")
    args = ap.parse_args()

    d = leer_terminal()
    if "error" in d:
        print(" ", d["error"])
        print("  ¿Está MetaTrader 5 abierto?")
        return 1

    io.open(args.salida, "w", encoding="utf-8").write(render(d))

    print()
    print(f"  {args.salida} escrito.")
    print(f"  abiertas {len(d['abiertas'])}   pendientes {len(d['pendientes'])}"
          f"   cerradas {len(d['cerradas'])}")
    if d["cerradas"]:
        r = [x["r"] for x in d["cerradas"]]
        gana = sum(1 for x in r if x > 0)
        print(f"  {len(r)} operaciones, {100.0 * gana / len(r):.1f}% de acierto, "
              f"{sum(r):+.2f} R")
    else:
        print("  el robot todavía no ha cerrado ninguna operación")
    print()

    if args.abrir:
        os.startfile(os.path.abspath(args.salida))
    return 0


if __name__ == "__main__":
    sys.exit(main())
