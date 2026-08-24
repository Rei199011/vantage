"""
Vantage — Las operaciones de la EA, para verlas en TradingView
--------------------------------------------------------------
Lee el historial de MetaTrader 5 y escribe un indicador de Pine Script que
dibuja cada operación en el gráfico: la caja de la entrada al stop, la caja de
la entrada al objetivo, y una etiqueta con el resultado en R.

    python a_tradingview.py                 # todos los símbolos, uno por fichero
    python a_tradingview.py --simbolo GBPJPY

Los ficheros salen en `tradingview/`. Se copian y se pegan en el editor de Pine
de TradingView (Pine Editor -> Añadir al gráfico).

SOLO LEE MT5. No envía ninguna orden.

LA HORA. MT5 devuelve las marcas en hora del SERVIDOR, y Pine trabaja en UTC.
El desfase se mide contra el reloj real en cada ejecución en lugar de
suponerlo: si se equivoca, las cajas salen corridas tres horas y el dibujo no
se parece a nada.
"""

import argparse
import datetime as dt
import io
import os
import sys

try:
    import MetaTrader5 as mt5
except ImportError:
    print("Falta el paquete MetaTrader5:  pip install MetaTrader5")
    sys.exit(1)

MAGICO = 20260822
RIESGO_POR_OPERACION = 500.0
DIAS = 180
CARPETA = "tradingview"


def desfase_servidor():
    """Segundos que el reloj del servidor lleva por delante de UTC."""
    t = mt5.symbol_info_tick("EURUSD")
    if t is None or not t.time:
        return 0
    servidor = dt.datetime.fromtimestamp(t.time, dt.timezone.utc)
    ahora = dt.datetime.now(dt.timezone.utc)
    return round((servidor - ahora).total_seconds() / 3600) * 3600


def operaciones():
    """Cada operación con su entrada, su stop, su objetivo y su salida."""
    desde = dt.datetime.now() - dt.timedelta(days=DIAS)
    deals = mt5.history_deals_get(desde, dt.datetime.now() + dt.timedelta(days=1)) or []
    ords = mt5.history_orders_get(desde, dt.datetime.now() + dt.timedelta(days=1)) or []

    # El stop y el objetivo no viven en la transacción: viven en la ORDEN que
    # abrió la posición. Sin esto no se puede dibujar la geometría, solo el
    # resultado.
    niveles = {}
    for o in ords:
        if o.magic == MAGICO and o.position_id:
            if o.sl or o.tp:
                niveles.setdefault(o.position_id, (o.sl, o.tp))

    por_pos = {}
    for d in deals:
        if d.magic != MAGICO:
            continue
        p = por_pos.setdefault(d.position_id, {
            "simbolo": d.symbol, "venta": False, "beneficio": 0.0,
            "entrada": 0.0, "t_in": None, "t_out": None, "salida": 0.0,
        })
        if d.entry == mt5.DEAL_ENTRY_IN:
            p["venta"] = d.type == mt5.DEAL_TYPE_SELL
            p["entrada"] = d.price
            p["t_in"] = d.time
        else:
            p["beneficio"] += d.profit + d.swap + d.commission
            p["t_out"] = d.time
            p["salida"] = d.price

    fuera = []
    for pid, p in por_pos.items():
        if p["t_in"] is None:
            continue
        sl, tp = niveles.get(pid, (0.0, 0.0))
        fuera.append({
            "simbolo": p["simbolo"],
            "venta": p["venta"],
            "entrada": p["entrada"],
            "stop": sl,
            "objetivo": tp,
            "salida": p["salida"] or p["entrada"],
            "t_in": p["t_in"],
            # Una posición todavía viva no tiene salida: se dibuja hasta ahora.
            "t_out": p["t_out"] or int(dt.datetime.now().timestamp()),
            "viva": p["t_out"] is None,
            "r": round(p["beneficio"] / RIESGO_POR_OPERACION, 2),
        })
    return sorted(fuera, key=lambda x: x["t_in"])


def pine(simbolo, ops, desfase):
    """El indicador, con las operaciones metidas dentro como listas."""
    def ms(t):
        return (t - desfase) * 1000

    lin = lambda xs: ", ".join(str(x) for x in xs)

    return f'''//@version=6
// =====================================================================
//  Vantage EA — operaciones en {simbolo}
//
//  Generado por a_tradingview.py a partir del historial de MetaTrader 5.
//  Copiar entero, pegar en el Pine Editor y pulsar "Añadir al gráfico".
//
//  Cada operación se dibuja con dos cajas desde la vela de entrada hasta
//  la de salida: la ROJA va de la entrada al stop y la VERDE de la entrada
//  al objetivo. La etiqueta lleva el resultado en R.
//
//  Las marcas de tiempo vienen de MT5, que las da en hora del SERVIDOR
//  (UTC+{desfase // 3600}). Ya están pasadas a UTC, que es lo que usa Pine.
//
//  Los precios son los del bróker de MT5. La cotización de TradingView es
//  de otra fuente, así que puede haber unos pocos puntos de diferencia:
//  sirve para ver DÓNDE y CÓMO, no para auditar el llenado al tick.
// =====================================================================
indicator("Vantage EA — {simbolo}", overlay = true, max_boxes_count = 500, max_labels_count = 500)

mostrarStop     = input.bool(true,  "Caja del stop")
mostrarObjetivo = input.bool(true,  "Caja del objetivo")
mostrarEtiqueta = input.bool(true,  "Etiqueta con el resultado")

var int[]    tIn      = array.from({lin(ms(o["t_in"]) for o in ops)})
var int[]    tOut     = array.from({lin(ms(o["t_out"]) for o in ops)})
var float[]  entrada  = array.from({lin(o["entrada"] for o in ops)})
var float[]  stop     = array.from({lin(o["stop"] for o in ops)})
var float[]  objetivo = array.from({lin(o["objetivo"] for o in ops)})
var float[]  erre     = array.from({lin(o["r"] for o in ops)})
var bool[]   esVenta  = array.from({lin(str(o["venta"]).lower() for o in ops)})

var bool pintado = false

if not pintado and barstate.islast
    pintado := true
    for i = 0 to array.size(tIn) - 1
        int  t1 = array.get(tIn, i)
        int  t2 = array.get(tOut, i)
        float e = array.get(entrada, i)
        float s = array.get(stop, i)
        float o = array.get(objetivo, i)
        float r = array.get(erre, i)
        bool  v = array.get(esVenta, i)

        color tono = r > 0 ? color.new(color.teal, 82) : color.new(color.red, 82)

        if mostrarStop and s > 0
            box.new(t1, math.max(e, s), t2, math.min(e, s),
                 xloc = xloc.bar_time, border_color = color.new(color.red, 45),
                 bgcolor = color.new(color.red, 90))

        if mostrarObjetivo and o > 0
            box.new(t1, math.max(e, o), t2, math.min(e, o),
                 xloc = xloc.bar_time, border_color = color.new(color.teal, 45),
                 bgcolor = color.new(color.teal, 90))

        line.new(t1, e, t2, e, xloc = xloc.bar_time,
                 color = color.new(color.gray, 20), width = 2)

        if mostrarEtiqueta
            label.new(t1, e, xloc = xloc.bar_time,
                 text = (v ? "VENTA" : "COMPRA") + "  " +
                        (r > 0 ? "+" : "") + str.tostring(r, "#.00") + " R",
                 style = v ? label.style_label_down : label.style_label_up,
                 color = tono, textcolor = chart.fg_color, size = size.small)
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simbolo", default=None,
                    help="solo este símbolo; por defecto, todos")
    ap.add_argument("--carpeta", default=CARPETA)
    args = ap.parse_args()

    if not mt5.initialize():
        print("  no se pudo conectar con MetaTrader 5:", mt5.last_error())
        return 1
    try:
        desfase = desfase_servidor()
        ops = operaciones()
    finally:
        mt5.shutdown()

    if not ops:
        print("  la EA todavía no tiene ninguna operación en el historial")
        return 0

    os.makedirs(args.carpeta, exist_ok=True)
    simbolos = sorted({o["simbolo"] for o in ops})
    if args.simbolo:
        simbolos = [s for s in simbolos if s.upper() == args.simbolo.upper()]
        if not simbolos:
            print(f"  no hay operaciones de {args.simbolo}")
            return 1

    print()
    print(f"  desfase del servidor: +{desfase // 3600} h  (ya descontado)")
    print()
    for s in simbolos:
        de_este = [o for o in ops if o["simbolo"] == s]
        ruta = os.path.join(args.carpeta, f"vantage_ea_{s}.pine")
        io.open(ruta, "w", encoding="utf-8").write(pine(s, de_este, desfase))
        vivas = sum(1 for o in de_este if o["viva"])
        r = sum(o["r"] for o in de_este)
        print(f"  {ruta:44} {len(de_este):3} operaciones"
              f"{f' ({vivas} viva)' if vivas else '':10}  {r:+.2f} R")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
