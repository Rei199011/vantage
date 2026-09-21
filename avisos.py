"""
Vantage EA — avisos por Telegram de lo que hace el robot.

    python avisos.py --probar          comprueba las credenciales y manda una prueba
    python avisos.py --una-vez         mira una vez y avisa de lo nuevo
    python avisos.py --cada 60         en bucle, cada 60 segundos

Va en PARALELO al espejo, no dentro. El espejo rehace la página cada quince
minutos y eso está bien para mirar, pero quince minutos es mucho para
enterarse de una entrada. Aquí se mira cada minuto.

SOLO LEE MT5. No envía ninguna orden ni toca ninguna posición.

LAS CREDENCIALES NO ESTÁN AQUÍ. Se leen de `.env`, que no se sube al
repositorio. Hacen falta dos líneas:

    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...

El token lo da @BotFather. El chat es donde se publica: puede ser tu chat
privado con el bot, un grupo o un canal.
"""

import argparse
import datetime as dt
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

try:
    import MetaTrader5 as mt5
except ImportError:
    print("Falta el paquete MetaTrader5:  pip install MetaTrader5")
    sys.exit(1)

# Los dos robots que corren ahora, con su etiqueta. Sin esto, un día con las
# dos operando sería ilegible: son experimentos distintos y sus resultados no
# se suman.
#
# Solo el marco, no la proporción: la proporción se calcula de la orden real y
# ponerla aquí además la duplicaba en el mensaje ("M15 · 1:1 · 1:1.0"). Y si
# algún día se cambia ObjetivoVecesR en el gráfico, la etiqueta escrita a mano
# mentiría mientras la calculada diría la verdad.
ROBOTS = {
    20260822: "M15",
    20260921: "M5",
}

ESTADO = "avisos_estado.json"
DIAS_HISTORIAL = 30


# ------------------------------------------------------------------ envío


def _credenciales():
    """Del entorno o de .env, en ese orden. Nunca se escriben en el código."""
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if tok and chat:
        return tok, chat
    if os.path.exists(".env"):
        for linea in io.open(".env", encoding="utf-8", errors="ignore"):
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if k.strip() == "TELEGRAM_BOT_TOKEN" and not tok:
                tok = v
            elif k.strip() == "TELEGRAM_CHAT_ID" and not chat:
                chat = v
    return tok, chat


def enviar(texto):
    """
    Manda el mensaje. Devuelve None si fue bien, o el motivo del fallo.

    Se usa urllib y no `requests` a propósito: es de la biblioteca estándar, y
    así los avisos no dependen de instalar nada. Un aviso que no sale porque
    falta un paquete es peor que no tener avisos.
    """
    tok, chat = _credenciales()
    if not tok or not chat:
        return ("faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID; "
                "ponlos en .env o en el entorno")
    datos = urllib.parse.urlencode({
        "chat_id": chat,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    url = "https://api.telegram.org/bot" + tok + "/sendMessage"
    try:
        with urllib.request.urlopen(url, data=datos, timeout=20) as r:
            j = json.loads(r.read().decode())
        return None if j.get("ok") else str(j.get("description", j))[:160]
    except Exception as e:                                   # noqa: BLE001
        return f"{type(e).__name__}: {e}"[:160]


# ------------------------------------------------------------------ estado


def _leer_estado():
    if not os.path.exists(ESTADO):
        return {"abiertas": [], "cerradas": []}
    try:
        d = json.load(io.open(ESTADO, encoding="utf-8"))
        return {"abiertas": list(d.get("abiertas", [])),
                "cerradas": list(d.get("cerradas", []))}
    except Exception:                                        # noqa: BLE001
        return {"abiertas": [], "cerradas": []}


def _guardar_estado(d):
    io.open(ESTADO, "w", encoding="utf-8").write(
        json.dumps(d, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ lectura


def _dig(simbolo):
    i = mt5.symbol_info(simbolo)
    return i.digits if i else 5


def _riesgo(venta, simbolo, lotes, entrada, stop):
    """Lo que se pierde si salta el stop. Se lo pregunta al terminal."""
    if not stop or stop <= 0:
        return None
    if (venta and stop <= entrada) or (not venta and stop >= entrada):
        return 0.0
    p = mt5.order_calc_profit(
        mt5.ORDER_TYPE_SELL if venta else mt5.ORDER_TYPE_BUY,
        simbolo, lotes, entrada, stop)
    return abs(p) if p is not None else None


def _posiciones():
    """Lo que está abierto ahora, de cualquiera de los dos robots."""
    fuera = {}
    for p in (mt5.positions_get() or []):
        if p.magic not in ROBOTS:
            continue
        venta = p.type == mt5.POSITION_TYPE_SELL
        n = _dig(p.symbol)
        fuera[p.ticket] = {
            "simbolo": p.symbol, "magico": p.magic,
            "lado": "VENTA" if venta else "COMPRA",
            "lotes": p.volume, "entrada": round(p.price_open, n),
            "stop": round(p.sl, n), "objetivo": round(p.tp, n),
            "riesgo": _riesgo(venta, p.symbol, p.volume, p.price_open, p.sl),
            "abierta": p.time,
        }
    return fuera


def _cerradas():
    """
    Operaciones ya terminadas, con su R calculada con el riesgo REAL.

    Se agrupa por POSICIÓN y no por transacción: un parcial genera dos
    salidas, y contarlas sueltas infla la cuenta. Y una posición que sigue
    viva NO cuenta como cerrada aunque tenga una salida — eso es justo lo que
    pasa tras cobrar un parcial.
    """
    desde = dt.datetime.now() - dt.timedelta(days=DIAS_HISTORIAL)
    hasta = dt.datetime.now() + dt.timedelta(days=1)
    vivas = {p.ticket for p in (mt5.positions_get() or []) if p.magic in ROBOTS}

    niveles = {}
    for o in (mt5.history_orders_get(desde, hasta) or []):
        if o.magic in ROBOTS and o.position_id and o.sl:
            niveles.setdefault(o.position_id, o.sl)

    por_pos = {}
    for d in (mt5.history_deals_get(desde, hasta) or []):
        if d.magic not in ROBOTS:
            continue
        p = por_pos.setdefault(d.position_id, {
            "simbolo": d.symbol, "magico": d.magic, "lado": "",
            "beneficio": 0.0, "abierta": None, "cerrada": None,
            "entrada": 0.0, "lotes": 0.0, "salida": 0.0,
        })
        if d.entry == mt5.DEAL_ENTRY_IN:
            p["lado"] = "VENTA" if d.type == mt5.DEAL_TYPE_SELL else "COMPRA"
            p["abierta"] = d.time
            p["entrada"] = d.price
            p["lotes"] = d.volume
        else:
            p["beneficio"] += d.profit + d.swap + d.commission
            p["cerrada"] = d.time
            p["salida"] = d.price

    fuera = {}
    for pid, p in por_pos.items():
        if p["abierta"] is None or p["cerrada"] is None or pid in vivas:
            continue
        r = _riesgo(p["lado"] == "VENTA", p["simbolo"], p["lotes"],
                    p["entrada"], niveles.get(pid, 0.0))
        p["riesgo"] = r
        p["r"] = round(p["beneficio"] / r, 2) if r else None
        fuera[pid] = p
    return fuera


# ------------------------------------------------------------------ mensajes


def _dur(a, b):
    m = int((b - a) / 60)
    return f"{m} min" if m < 60 else f"{m // 60}h {m % 60:02d}m"


def msg_entrada(p):
    n = _dig(p["simbolo"])
    marca = "\U0001F7E2" if p["lado"] == "COMPRA" else "\U0001F534"
    riesgo = f"{p['riesgo']:,.0f} €" if p["riesgo"] else "?"
    rb = ""
    if p["stop"] and p["objetivo"]:
        d = abs(p["entrada"] - p["stop"])
        if d:
            rb = f" · 1:{abs(p['objetivo'] - p['entrada']) / d:.1f}"
    etiqueta = ROBOTS.get(p["magico"], str(p["magico"]))
    return (f"{marca} <b>{p['lado']} {p['simbolo']}</b>\n"
            f"<i>{etiqueta}{rb}</i>\n\n"
            f"entrada  <code>{p['entrada']:.{n}f}</code>\n"
            f"stop     <code>{p['stop']:.{n}f}</code>\n"
            f"objetivo <code>{p['objetivo']:.{n}f}</code>\n\n"
            f"{p['lotes']} lotes · arriesga {riesgo}")


def msg_cierre(p, acum):
    n = _dig(p["simbolo"])
    r = p.get("r")
    if r is None:
        marca, texto = "⚪", "sin riesgo calculable"
    elif r > 0.05:
        marca, texto = "✅", f"<b>{r:+.2f} R</b>"
    elif r < -0.05:
        marca, texto = "❌", f"<b>{r:+.2f} R</b>"
    else:
        marca, texto = "⚪", f"<b>{r:+.2f} R</b> (plana)"
    etiqueta = ROBOTS.get(p["magico"], str(p["magico"]))
    return (f"{marca} <b>{p['simbolo']}</b>  {texto}  "
            f"({p['beneficio']:+,.2f} €)\n"
            f"<i>{etiqueta}</i>\n\n"
            f"{p['lado']} {p['lotes']} lotes · "
            f"{_dur(p['abierta'], p['cerrada'])}\n"
            f"<code>{p['entrada']:.{n}f}</code> → "
            f"<code>{p['salida']:.{n}f}</code>\n\n"
            f"<i>{acum}</i>")


def _acumulado(cerradas, magico):
    """El balance del robot al que pertenece la operación, no de los dos."""
    mias = [p for p in cerradas.values()
            if p["magico"] == magico and p.get("r") is not None]
    if not mias:
        return ""
    n = len(mias)
    g = sum(1 for p in mias if p["r"] > 0)
    tot = sum(p["r"] for p in mias)
    etiqueta = ROBOTS.get(magico, str(magico))
    return (f"{etiqueta}: {n} ops · {g} ganadas "
            f"({100.0 * g / n:.0f}%) · {tot:+.2f} R")


# ------------------------------------------------------------------ resumen


def _dia_de_sesion():
    """
    Qué día hay que resumir, en hora del servidor.

    La sesión del robot cierra a las 21:00 UTC, que en el servidor (UTC+3) son
    las 00:00 del día SIGUIENTE. Si el resumen se lanza justo después y mira
    "hoy", mira un día recién nacido y sale vacío. Por eso, de madrugada, el
    día que interesa es el anterior.
    """
    t = mt5.symbol_info_tick("EURUSD")
    ahora = (dt.datetime.fromtimestamp(t.time, dt.timezone.utc).replace(tzinfo=None)
             if t and t.time else dt.datetime.utcnow())
    dia = ahora.date()
    if ahora.hour < 6:
        dia = dia - dt.timedelta(days=1)
    a = dt.datetime.combine(dia, dt.time.min)
    return a, a + dt.timedelta(days=1)


ESTADOS = {1: "puesta", 2: "cancelada", 3: "parcial",
           4: "se llenó", 5: "RECHAZADA", 6: "caducada"}


def resumen_diario():
    """El parte del día: lo que se colocó, lo que cerró y cómo va la cuenta."""
    if not mt5.initialize():
        return None, f"no se pudo conectar con MetaTrader 5: {mt5.last_error()}"
    try:
        a, b = _dia_de_sesion()
        ats = a.replace(tzinfo=dt.timezone.utc).timestamp()
        bts = b.replace(tzinfo=dt.timezone.utc).timestamp()

        ords = [o for o in (mt5.history_orders_get(
                    a - dt.timedelta(days=2), b + dt.timedelta(days=1)) or [])
                if o.magic in ROBOTS and ats <= o.time_setup < bts]
        abiertas = _posiciones()
        cerradas = _cerradas()
        pendientes = [o for o in (mt5.orders_get() or []) if o.magic in ROBOTS]
        hoy = {k: p for k, p in cerradas.items() if ats <= p["cerrada"] < bts}
    finally:
        mt5.shutdown()

    L = [f"\U0001F4CA <b>Resumen del {a:%d/%m}</b>", ""]

    L.append(f"<b>Órdenes colocadas: {len(ords)}</b>")
    for o in sorted(ords, key=lambda x: x.time_setup):
        etiqueta = ROBOTS.get(o.magic, str(o.magic))
        L.append(f"  {o.symbol} {o.volume_initial} · {etiqueta} · "
                 f"{ESTADOS.get(o.state, o.state)}")
    if not ords:
        L.append("  <i>ninguna</i>")
    L.append("")

    L.append(f"<b>Cerradas hoy: {len(hoy)}</b>")
    suma = 0.0
    for p in sorted(hoy.values(), key=lambda x: x["cerrada"]):
        r = p.get("r")
        marca = "✅" if (r or 0) > 0.05 else ("❌" if (r or 0) < -0.05 else "⚪")
        suma += r or 0.0
        L.append(f"  {marca} {p['simbolo']} "
                 f"{'?' if r is None else f'{r:+.2f}'} R "
                 f"({p['beneficio']:+,.0f} €)")
    if hoy:
        L.append(f"  <b>del día: {suma:+.2f} R</b>")
    else:
        L.append("  <i>ninguna</i>")
    L.append("")

    L.append(f"<b>Abiertas ahora: {len(abiertas)}</b>")
    for p in abiertas.values():
        L.append(f"  {p['simbolo']} {p['lado']} {p['lotes']}")
    if not abiertas:
        L.append("  <i>ninguna</i>")
    L.append("")

    L.append(f"<b>Esperando: {len(pendientes)}</b>")
    if pendientes:
        L.append("  " + ", ".join(sorted({o.symbol for o in pendientes})))
    else:
        L.append("  <i>ninguna</i>")
    L.append("")

    L.append("<b>Acumulado de la cuenta</b>")
    for magico, etiqueta in ROBOTS.items():
        mias = [p for p in cerradas.values()
                if p["magico"] == magico and p.get("r") is not None]
        if not mias:
            L.append(f"  {etiqueta}: <i>sin operaciones</i>")
            continue
        n = len(mias)
        g = sum(1 for p in mias if p["r"] > 0)
        L.append(f"  {etiqueta}: {n} ops · {g} ganadas "
                 f"(<b>{100.0 * g / n:.0f}%</b>) · "
                 f"{sum(p['r'] for p in mias):+.2f} R")
    L.append("")
    L.append(f"<i>últimos {DIAS_HISTORIAL} días</i>")
    return "\n".join(L), None


# ------------------------------------------------------------------ vuelta


def una_vuelta(callar=False):
    """Mira, avisa de lo nuevo y devuelve un resumen de lo hecho."""
    if not mt5.initialize():
        return f"no se pudo conectar con MetaTrader 5: {mt5.last_error()}"
    try:
        abiertas = _posiciones()
        cerradas = _cerradas()
    finally:
        mt5.shutdown()

    # La PRIMERA vez no se avisa de nada: si no, al arrancar soltaría de golpe
    # un mes de historial. Se anota lo que hay y se empieza a avisar desde ahí.
    primera = not os.path.exists(ESTADO)
    est = _leer_estado()
    vistas_ab = set(est["abiertas"])
    vistas_ce = set(est["cerradas"])

    nuevas_ab = [t for t in abiertas if t not in vistas_ab]
    nuevas_ce = [p for p in cerradas if p not in vistas_ce]

    enviados, fallos = 0, []
    if not primera and not callar:
        for t in sorted(nuevas_ab, key=lambda k: abiertas[k]["abierta"]):
            e = enviar(msg_entrada(abiertas[t]))
            if e:
                fallos.append(e)
            else:
                enviados += 1
        for pid in sorted(nuevas_ce, key=lambda k: cerradas[k]["cerrada"]):
            p = cerradas[pid]
            e = enviar(msg_cierre(p, _acumulado(cerradas, p["magico"])))
            if e:
                fallos.append(e)
            else:
                enviados += 1

    _guardar_estado({"abiertas": list(abiertas), "cerradas": list(cerradas)})

    if primera:
        return (f"primera vuelta: anotadas {len(abiertas)} abiertas y "
                f"{len(cerradas)} cerradas SIN avisar. "
                f"A partir de ahora, solo lo nuevo.")
    if fallos:
        return f"{enviados} enviados, {len(fallos)} fallaron: {fallos[0]}"
    if enviados:
        return f"{enviados} aviso(s) enviados"
    return f"sin novedad ({len(abiertas)} abiertas, {len(cerradas)} cerradas)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probar", action="store_true",
                    help="comprueba las credenciales y manda un mensaje de prueba")
    ap.add_argument("--chat", action="store_true",
                    help="averigua el chat id: escribele algo al bot primero")
    ap.add_argument("--resumen", action="store_true",
                    help="manda el parte del dia: colocadas, cerradas, abiertas y acierto")
    ap.add_argument("--ver", action="store_true",
                    help="con --resumen, lo enseña por pantalla en vez de mandarlo")
    ap.add_argument("--una-vez", action="store_true")
    ap.add_argument("--cada", type=int, default=0, metavar="SEGUNDOS")
    ap.add_argument("--callar", action="store_true",
                    help="mira y anota, pero no manda nada")
    args = ap.parse_args()

    if args.chat:
        # El chat id no lo da BotFather: sale de un mensaje que le hayas
        # escrito al bot. Aqui se pregunta por él y se enseña SOLO el numero,
        # nunca el token.
        tok, _ = _credenciales()
        if not tok:
            print("\n  Falta TELEGRAM_BOT_TOKEN en .env\n")
            return 1
        try:
            with urllib.request.urlopen(
                    "https://api.telegram.org/bot" + tok + "/getUpdates",
                    timeout=20) as r:
                j = json.loads(r.read().decode())
        except Exception as ex:                              # noqa: BLE001
            print(f"\n  no se pudo preguntar: {ex}\n")
            return 1
        chats = {}
        for u in j.get("result", []):
            m = u.get("message") or u.get("channel_post") or {}
            c = m.get("chat") or {}
            if c.get("id"):
                chats[c["id"]] = c.get("title") or c.get("first_name") or c.get("type")
        print()
        if not chats:
            print("  Ningun mensaje todavia. Escribele algo al bot en Telegram")
            print("  y vuelve a lanzar esto.")
            return 1
        for cid, nombre in chats.items():
            print(f"  TELEGRAM_CHAT_ID={cid}    ({nombre})")
        print()
        return 0

    if args.resumen:
        texto, err = resumen_diario()
        if err:
            print(f"\n  {err}\n")
            return 1
        if args.ver:
            limpio = texto
            for etiqueta in ("<b>", "</b>", "<i>", "</i>", "<code>", "</code>"):
                limpio = limpio.replace(etiqueta, "")
            print()
            print("\n".join("  " + l for l in limpio.split("\n")))
            print()
            return 0
        e = enviar(texto)
        print("  " + ("resumen enviado" if e is None else f"NO se pudo enviar: {e}"))
        return 0 if e is None else 1

    if args.probar:
        tok, chat = _credenciales()
        print()
        print(f"  token: {'puesto (' + tok[:6] + '...)' if tok else 'FALTA'}")
        print(f"  chat:  {chat if chat else 'FALTA'}")
        if not tok or not chat:
            print()
            print("  Pon estas dos lineas en vantage/.env:")
            print("    TELEGRAM_BOT_TOKEN=...")
            print("    TELEGRAM_CHAT_ID=...")
            return 1
        e = enviar("\U0001F527 <b>Vantage EA</b>\nAvisos conectados. "
                   "A partir de ahora recibirás cada entrada y cada resultado.")
        print()
        print("  " + ("enviado, mira el chat"
                      if e is None else f"NO se pudo enviar: {e}"))
        return 0 if e is None else 1

    if args.cada <= 0:
        print("  " + una_vuelta(callar=args.callar))
        return 0

    print(f"\n  Mirando cada {args.cada} segundos. Ctrl+C para parar.\n")
    try:
        while True:
            marca = dt.datetime.now().strftime("%H:%M:%S")
            try:
                r = una_vuelta(callar=args.callar)
            except Exception as ex:                          # noqa: BLE001
                r = f"error inesperado: {ex}"
            print(f"  {marca}  {r}")
            time.sleep(args.cada)
    except KeyboardInterrupt:
        print("\n  Parado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
