"""
Vantage — Escáner del universo amplio
----------------------------------------
Una vez al día revisa los ~180 símbolos de `universe.py` sobre velas diarias,
los puntúa, y asciende los mejores al seguimiento horario de `bot.py`.

Por qué dos niveles:

    universe.py  (180 símbolos, velas diarias, 1 vez al día)
        │  el escáner ordena y se queda con los mejores
        ▼
    watchlist_auto.json  ──> bot.py vigila cada hora, junto a tu lista fija

Rastrear 180 símbolos cada hora no es viable —Yahoo corta el acceso— y tampoco
sería útil: te llegarían treinta avisos al día. La vela diaria dice si el setup
existe; la horaria, cuándo entrar. Este archivo hace lo primero.

Uso:
    python scanner.py            # escanea y asciende
    python scanner.py --dry      # escanea y muestra, sin tocar nada
"""

import os
import sys
import json
from datetime import datetime, timezone

import pandas as pd

import universe
import market
import fundamentals
import ai
import journal
from analyzer import analyze_frame, reason_text

RADAR_FILE = "radar.json"           # el ranking completo, para el panel
AUTO_FILE = "watchlist_auto.json"   # lo que se asciende al seguimiento horario

PROMOTE_TOP = 8      # cuántos ascienden a vigilancia horaria
REVIEW_TOP = 8       # a cuántos les pasa la revisión de IA (1 llamada cada uno)
RADAR_TOP = 20       # cuántos se guardan para mostrar en el panel
BATCH_SIZE = 40      # símbolos por petición; más alto arriesga que Yahoo corte

YF_PERIOD = "1y"
YF_INTERVAL = "1d"


# ------------------------------------------------------------------ descarga


def _download_batch(tickers: list) -> dict:
    """Baja varios símbolos en una sola petición. Devuelve {ticker: DataFrame}."""
    import yfinance as yf

    data = yf.download(
        tickers,
        period=YF_PERIOD,
        interval=YF_INTERVAL,
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    frames = {}
    if data is None or data.empty:
        return frames

    for t in tickers:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if t not in data.columns.get_level_values(0):
                    continue
                df = data[t].copy()
            else:
                df = data.copy()   # un solo ticker: columnas planas

            if "Volume" not in df.columns:
                df["Volume"] = 0.0

            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(
                subset=["Open", "High", "Low", "Close"]
            )
            df["Volume"] = df["Volume"].fillna(0.0)

            if not df.empty:
                frames[t] = df
        except (KeyError, ValueError):
            continue

    return frames


# -------------------------------------------------------------- puntuación


def score(r: dict) -> float:
    """
    Ordena los candidatos que ya pasaron el filtro de entrada.

    Es una heurística, no una probabilidad: pondera lo que el propio sistema
    considera favorable. Que ordene bien está tan sin validar como el resto.
    """
    if r.get("signal") != "ENTRADA":
        return 0.0

    puntos = 40.0
    puntos += min(r["rr_ratio"], 5.0) * 8          # cuanto mejor el riesgo/beneficio
    puntos += min(r["activity_ratio"], 4.0) * 6    # cuanta más actividad inusual

    # Tendencia clara: distancia entre las medias medida en ATR.
    fuerza = r.get("trend_strength", 0.0)
    puntos += min(fuerza, 3.0) * 5

    # Penaliza el RSI acercándose a los extremos: menos recorrido por delante.
    rsi = r["rsi"]
    if r["direction"] == "buy":
        puntos -= max(0.0, rsi - 55) * 0.6
    else:
        puntos -= max(0.0, 45 - rsi) * 0.6

    return round(puntos, 1)


# --------------------------------------------------------------------- scan


def scan(verbose: bool = True) -> list:
    """Analiza todo el universo y devuelve los resultados ordenados por puntuación."""
    symbols = universe.SYMBOLS
    resultados, fallos = [], []

    for i in range(0, len(symbols), BATCH_SIZE):
        lote = symbols[i:i + BATCH_SIZE]
        if verbose:
            print(f"  lote {i // BATCH_SIZE + 1}: {len(lote)} símbolos…")

        frames = _download_batch(lote)

        for t in lote:
            df = frames.get(t)
            if df is None:
                fallos.append(t)
                continue

            r = analyze_frame(df, t, timeframe=YF_INTERVAL)
            if "error" in r:
                fallos.append(t)
                continue

            r["score"] = score(r)
            r["reason"] = reason_text(r)
            resultados.append(r)

    if verbose and fallos:
        print(f"  sin datos: {len(fallos)} ({', '.join(fallos[:8])}"
              f"{'…' if len(fallos) > 8 else ''})")

    resultados.sort(key=lambda r: r["score"], reverse=True)
    return resultados


def candidates(resultados: list) -> list:
    """Solo los que dieron señal de entrada, ya ordenados."""
    return [r for r in resultados if r["signal"] == "ENTRADA"]


# ------------------------------------------------------------------ guardar


def contexto_mercado() -> tuple[str, list]:
    """Descarga los índices de contexto y devuelve (texto para la IA, resultados)."""
    frames = _download_batch(universe.CONTEXT_SYMBOLS)
    indices = []
    for t in universe.CONTEXT_SYMBOLS:
        df = frames.get(t)
        if df is None:
            continue
        r = analyze_frame(df, t, timeframe=YF_INTERVAL)
        if "error" not in r:
            r["name"] = universe.CONTEXT_META.get(t, t)
            indices.append(r)
    return ai.market_context(indices), indices


def review(cands: list) -> dict | None:
    """
    Pasa los mejores candidatos por la revisión de IA: análisis técnico
    contrastado con los números de la empresa.

    Solo se revisan los primeros: el universo entero serían 180 llamadas al
    día para nada, porque la mayoría ni siquiera dio señal.
    """
    motivo = ai.why_unavailable()
    if motivo:
        print(f"  Revisión con IA desactivada: {motivo}")
        return None

    revisados = cands[:REVIEW_TOP]
    print(f"  revisando {len(revisados)} candidatos con {ai.GEMINI_MODEL}…")

    contexto, _ = contexto_mercado()
    print("    contexto de mercado listo")

    for r in revisados:
        fund = fundamentals.get_fundamentals(r["symbol"])
        noticias = ai.news_digest(r["symbol"], r["name"])
        veredicto = ai.analyze_candidate(r, fund, noticias, contexto)
        if veredicto:
            r["ai"] = veredicto
            r["ai"]["noticias"] = noticias
            marca = "con noticias" if veredicto.get("tiene_noticias") else "sin noticias"
            print(f"    {r['display_symbol']:<11} {veredicto['veredicto']:<10} "
                  f"convicción {veredicto.get('conviccion', '?')}/5 · {marca}")

    conjunto = ai.analyze_portfolio(revisados)
    if conjunto:
        print("    visión de conjunto lista")
    return conjunto


def _slim(r: dict) -> dict:
    """Versión ligera para el panel: sin la serie del sparkline ni internos."""
    campos = ("symbol", "display_symbol", "name", "asset_class", "price", "change_pct",
              "signal", "direction", "entry", "take_profit", "stop_loss", "rr_ratio",
              "rsi", "activity_ratio", "activity_label", "volume_based", "score",
              "reason", "ai", "bloqueo")
    return {k: r[k] for k in campos if k in r}


def descartado(r: dict) -> bool:
    """¿La revisión con IA rechazó este candidato?"""
    return (r.get("ai") or {}).get("veredicto") == "descartar"


def revisados_ok(cands: list) -> list:
    """Los que la revisión con IA no rechazó. Todavía sin pasar por el candado."""
    return [r for r in cands if not descartado(r)]


def accionables(cands: list, vivas: dict | None = None) -> list:
    """
    Los que llegan a Telegram como orden.

    Dos filtros: la revisión con IA, y el candado. El candado marca en
    `r["bloqueo"]` el motivo de los que aparta, para poder decirlo en el
    resumen en vez de que desaparezcan sin explicación.
    """
    if vivas is None:
        vivas = journal.abiertas()

    libres = []
    for r in revisados_ok(cands):
        permitido, motivo = journal.permiso(
            r["symbol"], r["direction"], journal.RADAR, vivas)
        if permitido:
            libres.append(r)
        else:
            r["bloqueo"] = motivo
    return libres


def save(resultados: list, conjunto: dict | None = None) -> dict:
    cands = candidates(resultados)
    ordenes = accionables(cands)

    # El ascenso a seguimiento horario NO pasa por el candado, a propósito: un
    # símbolo con una señal viva es justo el que hay que seguir mirando cada
    # hora. Lo que el candado corta son los avisos, no la vigilancia.
    ascendidos = [r["symbol"] for r in revisados_ok(cands)[:PROMOTE_TOP]]

    radar = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe_size": len(universe.SYMBOLS),
        "scanned": len(resultados),
        "candidates": len(cands),
        "timeframe": YF_INTERVAL,
        "reviewed": sum(1 for r in cands[:RADAR_TOP] if "ai" in r),
        "portfolio": conjunto,
        "top": [_slim(r) for r in cands[:RADAR_TOP]],
        # Lo que de verdad sale como orden, ya filtrado por IA y por candado.
        "ordenes": [_slim(r) for r in ordenes[:PROMOTE_TOP]],
    }
    with open(RADAR_FILE, "w", encoding="utf-8") as f:
        json.dump(radar, f, ensure_ascii=False, indent=2)

    with open(AUTO_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": radar["generated_at"],
            "symbols": ascendidos,
        }, f, ensure_ascii=False, indent=2)

    return radar


def format_digest(radar: dict) -> str:
    """
    Resumen para Telegram, en HTML.

    Solo se detallan las operaciones accionables. Lo descartado y lo que se
    queda en observación va en una línea al final: sirve para saber que el
    sistema miró, sin convertir el mensaje en un informe.
    """
    top = radar.get("top", [])
    fecha = datetime.now(timezone.utc).strftime("%d/%m")

    cab = (f"📡 <b>RADAR</b> · {fecha}\n"
           f"<i>{radar['scanned']} de {radar['universe_size']} símbolos revisados</i>")

    if not top:
        return (f"{cab}\n\nSin candidatos hoy: ninguno cumple las tres condiciones "
                f"de entrada. Es un resultado válido, no un fallo.")

    # save() ya dejó resuelto qué sale como orden (IA + candado). Se recalcula
    # solo si viene un radar viejo, de antes de que existiera esa clave.
    ordenes = radar.get("ordenes")
    if ordenes is None:
        ordenes = accionables(top)[:PROMOTE_TOP]

    rechazados = [r for r in top if descartado(r)]
    bloqueados = [r for r in top if r.get("bloqueo")]

    if not ordenes:
        motivo = ("Todos los candidatos fueron descartados en la revisión."
                  if rechazados and not bloqueados else
                  "Los candidatos de hoy ya tienen una señal viva o son contrarios a una.")
        bloques = [cab, "", "<b>Ninguna operación nueva hoy.</b>", motivo]
    else:
        plural = "operación" if len(ordenes) == 1 else "operaciones"
        bloques = [cab, "", f"<b>{len(ordenes)} {plural}</b>", ""]
        for r in ordenes:
            bloques.append(_bloque_orden(r))

    if bloqueados:
        detalle = " · ".join(f"{_esc(r['display_symbol'])} ({_esc(r['bloqueo'])})"
                             for r in bloqueados)
        bloques.append(f"🔒 <i>Candado: {detalle}</i>")

    if rechazados:
        nombres = ", ".join(r["display_symbol"] for r in rechazados)
        bloques.append(f"🚫 <i>Descartados en la revisión: {nombres}</i>")

    conjunto = radar.get("portfolio") or {}
    if conjunto.get("advertencia"):
        bloques.append(f"\n⚠️ <b>Conjunto</b> — {_esc(conjunto['advertencia'])}")

    return "\n".join(bloques)


def _esc(t) -> str:
    """Telegram en modo HTML solo exige escapar estos tres caracteres."""
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _bloque_orden(r: dict) -> str:
    compra = r["direction"] == "buy"
    icono = "🟢" if compra else "🔴"
    lado = "COMPRA" if compra else "VENTA"

    lineas = [
        f"{icono} <b>{lado} · {_esc(r['display_symbol'])}</b>",
        f"<i>{_esc(r['name'])}</i>",
        "",
        "<code>"
        f"Entrada   {r['entry']}\n"
        f"Objetivo  {r['take_profit']}\n"
        f"Stop      {r['stop_loss']}\n"
        f"R/B       1 : {r['rr_ratio']}"
        "</code>",
    ]

    v = r.get("ai") or {}
    if v.get("veredicto"):
        marca = "✅" if v["veredicto"] == "respaldar" else "⚠️"
        lineas.append(f"{marca} {v['veredicto'].capitalize()} · convicción "
                      f"{v.get('conviccion', '?')}/5")
    if v.get("resumen"):
        lineas.append(f"<i>{_esc(v['resumen'])}</i>")
    if v.get("noticia_clave"):
        lineas.append(f"📰 {_esc(v['noticia_clave'])}")
    if v.get("momento"):
        lineas.append(f"⏱ {_esc(v['momento'])}")
    if v.get("conflicto"):
        lineas.append(f"⚡ {_esc(v['conflicto'])}")

    lineas.append("─────────────")
    return "\n".join(lineas)


if __name__ == "__main__":
    dry = "--dry" in sys.argv

    print(f"Escaneando {len(universe.SYMBOLS)} símbolos en velas de {YF_INTERVAL}…")
    resultados = scan()
    cands = candidates(resultados)

    print(f"\n{len(resultados)} analizados · {len(cands)} candidatos\n")
    print(f"{'#':<3} {'símbolo':<11} {'punt.':>6}  {'lado':<7} {'R/B':>5}  nombre")
    for i, r in enumerate(cands[:RADAR_TOP], 1):
        lado = "compra" if r["direction"] == "buy" else "venta"
        print(f"{i:<3} {r['display_symbol']:<11} {r['score']:>6}  {lado:<7} "
              f"1:{r['rr_ratio']:<4} {r['name']}")

    conjunto = None
    if not dry:
        conjunto = review(cands)

    if dry:
        print("\n(--dry: no se guardó nada ni se llamó a la IA)")
    else:
        radar = save(resultados, conjunto)
        print(f"\n✔ {RADAR_FILE} y {AUTO_FILE} actualizados")
        print(f"  ascendidos: {', '.join(r['display_symbol'] for r in cands[:PROMOTE_TOP])}")
