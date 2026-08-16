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

    for r in revisados:
        fund = fundamentals.get_fundamentals(r["symbol"]) if r["asset_class"] == "Acción" else None
        veredicto = ai.analyze_candidate(r, fund)
        if veredicto:
            r["ai"] = veredicto
            print(f"    {r['display_symbol']:<11} {veredicto['veredicto']:<10} "
                  f"convicción {veredicto.get('conviccion', '?')}/5")

    conjunto = ai.analyze_portfolio(revisados)
    if conjunto:
        print("    visión de conjunto lista")
    return conjunto


def _slim(r: dict) -> dict:
    """Versión ligera para el panel: sin la serie del sparkline ni internos."""
    campos = ("symbol", "display_symbol", "name", "asset_class", "price", "change_pct",
              "signal", "direction", "entry", "take_profit", "stop_loss", "rr_ratio",
              "rsi", "activity_ratio", "activity_label", "volume_based", "score",
              "reason", "ai")
    return {k: r[k] for k in campos if k in r}


def save(resultados: list, conjunto: dict | None = None) -> dict:
    cands = candidates(resultados)
    ascendidos = [r["symbol"] for r in cands[:PROMOTE_TOP]]

    radar = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe_size": len(universe.SYMBOLS),
        "scanned": len(resultados),
        "candidates": len(cands),
        "timeframe": YF_INTERVAL,
        "reviewed": sum(1 for r in cands[:RADAR_TOP] if "ai" in r),
        "portfolio": conjunto,
        "top": [_slim(r) for r in cands[:RADAR_TOP]],
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
    """Resumen para Telegram."""
    top = radar["top"]
    cab = (f"📡 *Radar diario* — {radar['scanned']} de {radar['universe_size']} "
           f"símbolos revisados")

    if not top:
        return (f"{cab}\n\nNingún candidato cumple hoy las tres condiciones de entrada. "
                "Sin señales es un resultado válido.")

    marca = {"respaldar": "\u2705", "matizar": "\u26a0\ufe0f", "descartar": "\u274c"}

    lineas = [cab, f"{radar['candidates']} candidatos \u00b7 los mejores:\n"]
    for i, r in enumerate(top[:PROMOTE_TOP], 1):
        lado = "compra" if r["direction"] == "buy" else "venta"
        v = r.get("ai") or {}

        cabecera = f"{i}. *{r['display_symbol']}* — {lado} · {r['name']}"
        if v.get("veredicto"):
            cabecera += (f"\n   {marca.get(v['veredicto'], '')} {v['veredicto'].upper()}"
                         f" · convicción {v.get('conviccion', '?')}/5")

        lineas.append(
            f"{cabecera}\n"
            f"   {r['entry']} → {r['take_profit']} · stop {r['stop_loss']} · "
            f"R/B 1:{r['rr_ratio']}"
        )
        if v.get("resumen"):
            lineas.append(f"   _{v['resumen']}_")
        if v.get("conflicto"):
            lineas.append(f"   \u26a1 {v['conflicto']}")

    conjunto = radar.get("portfolio") or {}
    if conjunto.get("advertencia"):
        lineas.append(f"\n\U0001F9ED *Visión de conjunto*\n{conjunto['advertencia']}")

    lineas.append("\n_Ascendidos a seguimiento horario. Los avisos de entrada "
                  "llegan cuando la vela de una hora lo confirme._")
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
