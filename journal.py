"""
Vantage — Registro de señales
--------------------------------
Guarda cada señal en el momento en que se emite, y días después comprueba
qué pasó con ella. Es la pieza que convierte Vantage en algo medible.

Por qué esto y no un backtest:

Un backtest sobre el universo actual está contaminado. Las 134 empresas de
`universe.py` son las que hoy existen y cotizan bien; las que quebraron o
salieron del índice no están. Probar la estrategia sobre las supervivientes
infla los resultados, y es el error más caro y más común del oficio.

Este registro no tiene ese problema. Anota la señal ANTES de conocer el
resultado, sobre el universo real de ese día, y con los precios que hubo.
Es más lento —hacen falta semanas— pero lo que mide es cierto.

Uso:
    python journal.py            # actualiza las abiertas y muestra las métricas
    python journal.py --stats    # solo las métricas, sin tocar nada
"""

import io
import os
import json
from datetime import datetime, timezone, date

import pandas as pd

JOURNAL_FILE = "journal.json"

# Días naturales que se le dan a una señal antes de darla por caducada.
MAX_DIAS_ABIERTA = 30

# Coste estimado de ida y vuelta (comisión + horquilla + deslizamiento),
# expresado como fracción del riesgo de la operación. Se resta a TODOS los
# resultados. Sin esto, las métricas mienten a favor.
COSTE_EN_R = 0.05

# A partir de cuántas operaciones cerradas tiene sentido mirar los números.
MINIMO_FIABLE = 30


# ------------------------------------------------------------------ almacén


def _cargar() -> dict:
    if not os.path.exists(JOURNAL_FILE):
        return {"version": 1, "signals": []}
    try:
        with io.open(JOURNAL_FILE, encoding="utf-8") as f:
            datos = json.load(f)
        datos.setdefault("signals", [])
        return datos
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "signals": []}


def _guardar(datos: dict):
    datos["updated_at"] = datetime.now(timezone.utc).isoformat()
    with io.open(JOURNAL_FILE, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


# -------------------------------------------------------------------- candado

# Los dos canales que emiten señales. El radar mira vela diaria y ve la
# tendencia de fondo; el seguimiento mira vela horaria y ve el momento.
RADAR = "radar"
SEGUIMIENTO = "seguimiento"


def _canal(s: dict) -> str:
    """De qué canal vino una señal ya guardada."""
    return RADAR if RADAR in (s.get("origen") or "") else SEGUIMIENTO


def abiertas() -> dict:
    """{símbolo: señal viva}. Es el estado que consulta el candado."""
    return {s["symbol"]: s for s in _cargar()["signals"] if s["status"] == "abierta"}


def permiso(symbol: str, direction: str, canal: str,
            vivas: dict | None = None) -> tuple[bool, str]:
    """
    ¿Se puede emitir esta señal? Devuelve (permitido, motivo).

    UNA SOLA SEÑAL VIVA POR SÍMBOLO. Sin esta regla el sistema vuelve a avisar
    en cuanto reaparece el pico de actividad, y como las medias 20/50 siguen
    apuntando al mismo lado después de un stop de 1,8 ATR, reentra siempre en
    la misma dirección y siempre a peor precio. Medido sobre el historial de
    agosto de 2026: 8 reentradas tras un stop, 8 a peor precio.

    PRIORIDAD AL RADAR cuando los dos canales discrepan. En BP el radar dio
    compra y el seguimiento vendió dos veces contra ella: las dos ventas al
    stop, la compra del radar en beneficio. En SAN, compra del radar a las
    06:04 y venta del seguimiento a las 09:53, al stop en 3,1 horas. El marco
    corto pierde cuando pelea contra la tendencia que el largo ya identificó.
    """
    viva = (abiertas() if vivas is None else vivas).get(symbol)
    if viva is None:
        return True, ""

    desde = viva.get("signal_date", "?")
    lado = "compra" if viva["direction"] == "buy" else "venta"

    if viva["direction"] == direction:
        return False, f"reentrada: ya hay una {lado} viva desde {desde}"

    if _canal(viva) == RADAR:
        # Contraria a una señal del radar: no se abre, venga de donde venga.
        return False, f"contraria a la {lado} del radar del {desde}, que tiene prioridad"

    if canal == RADAR:
        # El radar sí releva al seguimiento: es el único caso en que se cede.
        # Aviso honesto: en el historial de agosto de 2026 no se dio ni una vez
        # (el radar siempre llegó primero), así que esta rama va sin medir.
        return True, f"el radar releva la {lado} del seguimiento del {desde}"

    return False, f"contraria a la {lado} viva desde {desde}"


def _relevar(viva: dict, precio: float | None = None):
    """
    Aparta una señal del seguimiento porque el radar emite la contraria.

    Se marca 'relevada' y se deja `r_multiple` en None a propósito: no sabemos
    cómo habría acabado, y apuntarla como ganada o perdida sería inventarse un
    resultado. stats() solo cuenta las que tienen r_multiple, así que queda
    fuera de las métricas en vez de ensuciarlas. `r_al_relevar` guarda cómo iba.
    """
    viva["status"] = "relevada"
    viva["closed_at"] = date.today().isoformat()
    if precio is not None:
        riesgo = abs(float(viva["entry"]) - float(viva["stop_loss"]))
        if riesgo > 0:
            mov = (precio - viva["entry"]) if viva["direction"] == "buy" \
                else (viva["entry"] - precio)
            viva["close_price"] = round(float(precio), 4)
            viva["r_al_relevar"] = round(mov / riesgo, 3)


# ------------------------------------------------------------------ registrar


def record(resultados: list, origen: str = SEGUIMIENTO) -> int:
    """
    Anota las señales de entrada nuevas. Devuelve cuántas se añadieron.

    Aplica el mismo candado que decide los avisos, para que el registro y lo
    que llega a Telegram no puedan desincronizarse: lo que no se avisa,
    tampoco se anota.
    """
    datos = _cargar()
    vivas = {s["symbol"]: s for s in datos["signals"] if s["status"] == "abierta"}
    hoy = date.today().isoformat()
    nuevas = 0

    for r in resultados:
        if "error" in r or r.get("signal") != "ENTRADA" or not r.get("direction"):
            continue

        permitido, motivo = permiso(r["symbol"], r["direction"], origen, vivas)
        if not permitido:
            continue
        if motivo:                      # el radar releva una del seguimiento
            _relevar(vivas[r["symbol"]], r.get("price"))

        v = r.get("ai") or {}
        nueva = {
            "id": f"{r['symbol']}-{hoy}",
            "symbol": r["symbol"],
            "display_symbol": r.get("display_symbol", r["symbol"]),
            "name": r.get("name", ""),
            "asset_class": r.get("asset_class", ""),
            "origen": origen,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "signal_date": hoy,

            # Todo lo que se sabía en el momento de emitirla. Se guarda entero
            # para poder preguntar después qué tipo de señal funciona mejor.
            "direction": r["direction"],
            "entry": r["entry"],
            "take_profit": r["take_profit"],
            "stop_loss": r["stop_loss"],
            "rr_ratio": r["rr_ratio"],
            "rsi": r.get("rsi"),
            "activity_ratio": r.get("activity_ratio"),
            "trend_strength": r.get("trend_strength"),
            "score": r.get("score"),
            "ai_veredicto": v.get("veredicto"),
            "ai_conviccion": v.get("conviccion"),
            "tenia_noticias": v.get("tiene_noticias"),

            # Se rellena al cerrarla.
            "status": "abierta",
            "closed_at": None,
            "close_price": None,
            "r_multiple": None,
            "dias_abierta": None,
        }
        datos["signals"].append(nueva)
        vivas[r["symbol"]] = nueva       # el candado ya la ve en esta misma ronda
        nuevas += 1

    if nuevas:
        _guardar(datos)
    return nuevas


# ------------------------------------------------------------------ evaluar


def _velas_diarias(simbolos: list) -> dict:
    """Velas diarias del último año para varios símbolos, en una sola petición."""
    import yfinance as yf

    if not simbolos:
        return {}

    data = yf.download(simbolos, period="1y", interval="1d", group_by="ticker",
                       auto_adjust=True, progress=False, threads=True)
    if data is None or data.empty:
        return {}

    frames = {}
    for t in simbolos:
        try:
            df = data[t].copy() if isinstance(data.columns, pd.MultiIndex) else data.copy()
            df = df[["Open", "High", "Low", "Close"]].dropna()
            if not df.empty:
                frames[t] = df
        except (KeyError, ValueError):
            continue
    return frames


def _evaluar(señal: dict, df: pd.DataFrame) -> dict | None:
    """
    Recorre las velas posteriores a la señal y decide qué pasó.

    El caso peliagudo es cuando una misma vela toca el objetivo Y el stop.
    Con velas diarias es imposible saber cuál llegó primero, así que se marca
    como "ambigua" y se contabiliza como pérdida. Suponer lo contrario es la
    forma más habitual de que un backtest mienta.
    """
    inicio = pd.Timestamp(señal["signal_date"])
    posteriores = df[df.index.normalize() > inicio]
    if posteriores.empty:
        return None

    entrada = float(señal["entry"])
    tp = float(señal["take_profit"])
    sl = float(señal["stop_loss"])
    compra = señal["direction"] == "buy"
    riesgo = abs(entrada - sl)
    if riesgo <= 0:
        return None

    for fecha, vela in posteriores.iterrows():
        alto, bajo = float(vela["High"]), float(vela["Low"])
        toca_tp = alto >= tp if compra else bajo <= tp
        toca_sl = bajo <= sl if compra else alto >= sl

        if toca_tp and toca_sl:
            return _cierre(señal, fecha, sl, "ambigua", -1.0)
        if toca_tp:
            return _cierre(señal, fecha, tp, "objetivo", abs(tp - entrada) / riesgo)
        if toca_sl:
            return _cierre(señal, fecha, sl, "stop", -1.0)

    dias = (date.today() - date.fromisoformat(señal["signal_date"])).days
    if dias >= MAX_DIAS_ABIERTA:
        ultimo = float(posteriores["Close"].iloc[-1])
        movimiento = (ultimo - entrada) if compra else (entrada - ultimo)
        return _cierre(señal, posteriores.index[-1], ultimo, "caducada", movimiento / riesgo)

    return None   # sigue abierta


def _cierre(señal: dict, fecha, precio: float, estado: str, r: float) -> dict:
    dias = (fecha.date() - date.fromisoformat(señal["signal_date"])).days
    return {
        "status": estado,
        "closed_at": fecha.date().isoformat(),
        "close_price": round(float(precio), 4),
        # El coste se resta siempre, gane o pierda: también se paga al perder.
        "r_multiple": round(r - COSTE_EN_R, 3),
        "dias_abierta": dias,
    }


def update(verbose: bool = True) -> int:
    """Comprueba las señales abiertas contra el precio posterior. Devuelve cuántas cerró."""
    datos = _cargar()
    abiertas = [s for s in datos["signals"] if s["status"] == "abierta"]
    if not abiertas:
        if verbose:
            print("  Sin señales abiertas que comprobar.")
        return 0

    if verbose:
        print(f"  comprobando {len(abiertas)} señales abiertas…")

    frames = _velas_diarias(sorted({s["symbol"] for s in abiertas}))
    cerradas = 0

    for s in abiertas:
        df = frames.get(s["symbol"])
        if df is None:
            continue
        resultado = _evaluar(s, df)
        if resultado:
            s.update(resultado)
            cerradas += 1
            if verbose:
                print(f"    {s['display_symbol']:<10} {s['status']:<10} "
                      f"{s['r_multiple']:+.2f}R en {s['dias_abierta']} días")

    if cerradas:
        _guardar(datos)
    return cerradas


# ------------------------------------------------------------------ métricas


def stats() -> dict:
    """
    Las métricas que de verdad importan.

    La central no es el porcentaje de acierto, sino la ESPERANZA en R: cuánto
    se gana o pierde de media por operación, medido en múltiplos del riesgo.
    Un sistema que acierta el 35% con objetivos de 3R gana dinero; uno que
    acierta el 65% con objetivos de 0.5R lo pierde. Casi todo el mundo mira
    el número equivocado.
    """
    datos = _cargar()
    señales = datos["signals"]
    cerradas = [s for s in señales if s["status"] != "abierta" and s["r_multiple"] is not None]
    abiertas = [s for s in señales if s["status"] == "abierta"]

    base = {
        "total": len(señales),
        "abiertas": len(abiertas),
        "cerradas": len(cerradas),
        "minimo_fiable": MINIMO_FIABLE,
        "suficientes": len(cerradas) >= MINIMO_FIABLE,
        "coste_en_r": COSTE_EN_R,
    }

    if not cerradas:
        base["mensaje"] = "Todavía no hay ninguna señal cerrada."
        return base

    erres = [s["r_multiple"] for s in cerradas]
    ganadoras = [r for r in erres if r > 0]
    perdedoras = [r for r in erres if r <= 0]

    base.update({
        "objetivo": sum(1 for s in cerradas if s["status"] == "objetivo"),
        "stop": sum(1 for s in cerradas if s["status"] == "stop"),
        "ambigua": sum(1 for s in cerradas if s["status"] == "ambigua"),
        "caducada": sum(1 for s in cerradas if s["status"] == "caducada"),
        "tasa_acierto": round(len(ganadoras) / len(cerradas) * 100, 1),
        "esperanza_r": round(sum(erres) / len(erres), 3),
        "total_r": round(sum(erres), 2),
        "r_medio_ganadora": round(sum(ganadoras) / len(ganadoras), 2) if ganadoras else 0.0,
        "r_medio_perdedora": round(sum(perdedoras) / len(perdedoras), 2) if perdedoras else 0.0,
        "peor_racha": _peor_racha(cerradas),
        "dias_medios": round(sum(s["dias_abierta"] for s in cerradas) / len(cerradas), 1),
        "por_veredicto": _agrupar(cerradas, lambda s: s.get("ai_veredicto") or "sin revisar"),
        "por_direccion": _agrupar(cerradas, lambda s: "compra" if s["direction"] == "buy" else "venta"),
        "por_noticias": _agrupar(cerradas, lambda s: "con noticias" if s.get("tenia_noticias") else "sin noticias"),
    })

    if not base["suficientes"]:
        base["mensaje"] = (f"Solo {len(cerradas)} operaciones cerradas. Por debajo de "
                           f"{MINIMO_FIABLE} estos números no distinguen una ventaja "
                           f"real del azar.")
    return base


def _peor_racha(cerradas: list) -> int:
    """La racha de pérdidas consecutivas más larga. Es lo que hay que aguantar."""
    ordenadas = sorted(cerradas, key=lambda s: s["closed_at"] or "")
    peor = actual = 0
    for s in ordenadas:
        if s["r_multiple"] <= 0:
            actual += 1
            peor = max(peor, actual)
        else:
            actual = 0
    return peor


def _agrupar(cerradas: list, clave) -> dict:
    """Métricas por grupo. Sirve para preguntarle cosas al registro."""
    grupos = {}
    for s in cerradas:
        grupos.setdefault(clave(s), []).append(s["r_multiple"])
    return {
        k: {
            "n": len(v),
            "esperanza_r": round(sum(v) / len(v), 3),
            "tasa_acierto": round(sum(1 for r in v if r > 0) / len(v) * 100, 1),
        }
        for k, v in sorted(grupos.items(), key=lambda kv: -len(kv[1]))
    }


def format_report(s: dict) -> str:
    """Informe para Telegram, en HTML."""
    if not s["cerradas"]:
        return (f"📒 <b>REGISTRO</b>\n\n{s['total']} señales anotadas, "
                f"{s['abiertas']} abiertas.\n<i>Ninguna cerrada todavía: hacen falta "
                f"días para que toquen objetivo o stop.</i>")

    signo = "🟢" if s["esperanza_r"] > 0 else "🔴"
    lineas = [
        "📒 <b>REGISTRO DE SEÑALES</b>",
        f"<i>{s['cerradas']} cerradas · {s['abiertas']} abiertas</i>",
        "",
        "<code>"
        f"Esperanza   {s['esperanza_r']:+.2f} R\n"
        f"Acierto     {s['tasa_acierto']}%\n"
        f"Ganadora    {s['r_medio_ganadora']:+.2f} R\n"
        f"Perdedora   {s['r_medio_perdedora']:+.2f} R\n"
        f"Acumulado   {s['total_r']:+.2f} R\n"
        f"Peor racha  {s['peor_racha']} seguidas\n"
        f"Duración    {s['dias_medios']} días"
        "</code>",
        "",
        f"{signo} <b>{'Esperanza positiva' if s['esperanza_r'] > 0 else 'Esperanza negativa'}</b>"
        f" — cada operación {'suma' if s['esperanza_r'] > 0 else 'resta'} "
        f"{abs(s['esperanza_r']):.2f}R de media, ya descontados costes.",
    ]

    ver = s.get("por_veredicto") or {}
    if len(ver) > 1:
        detalle = " · ".join(f"{k} {v['esperanza_r']:+.2f}R (n={v['n']})"
                             for k, v in ver.items())
        lineas.append(f"\n🤖 <b>Por veredicto de la IA</b>\n{detalle}")

    if s.get("mensaje"):
        lineas.append(f"\n⚠️ <i>{s['mensaje']}</i>")

    return "\n".join(lineas)


if __name__ == "__main__":
    import sys

    if "--stats" not in sys.argv:
        print("Actualizando señales abiertas…")
        cerradas = update()
        print(f"{cerradas} cerradas en esta pasada.\n")

    s = stats()
    print(json.dumps(s, ensure_ascii=False, indent=2))
