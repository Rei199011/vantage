"""
Vantage — Motor de análisis
------------------------------
Calcula indicadores técnicos sobre las velas de market.py y genera
recomendaciones con niveles de entrada, take profit y stop loss.

Vantage NO opera. Solo te dice qué está mirando y en qué niveles.
Las órdenes las pasás vos a mano, en el bróker que uses.

Uso:
    python analyzer.py                 # todo el watchlist
    python analyzer.py EURUSD=X NVDA   # símbolos sueltos

La lógica no está validada contra histórico: son cálculos técnicos,
no una previsión.
"""

import sys

import pandas as pd

import market

# ---------- Parámetros configurables ----------
ATR_PERIOD = 14          # ventana para medir la volatilidad (ATR)
SL_ATR_MULT = 1.8        # distancia del stop loss, en múltiplos de ATR
MIN_RR = 1.8             # riesgo/beneficio mínimo para considerarlo "entrada"
RSI_PERIOD = 14
VOLUME_SPIKE_MULT = 1.8  # volumen actual vs promedio para considerarlo inusual
RANGE_SPIKE_MULT = 1.6   # alternativa al volumen cuando no hay dato (forex)
SR_LOOKBACK = 60         # velas hacia atrás para buscar soporte y resistencia


def atr(df, period=ATR_PERIOD):
    """Average True Range: cuánto se mueve el precio, de media, por vela."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def true_range(df):
    prev_close = df["Close"].shift(1)
    return pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)


def rsi(df, period=RSI_PERIOD):
    """Relative Strength Index: si está sobrecomprado o sobrevendido."""
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    return (100 - (100 / (1 + rs))).fillna(50)


def find_support_resistance(df, lookback=SR_LOOKBACK):
    recent = df.tail(lookback)
    return float(recent["Low"].min()), float(recent["High"].max())


def _daily_change_pct(df):
    """
    Variación respecto al cierre de la sesión anterior.

    Se agrupa por día en vez de restar 24 horas: en acciones e índices,
    24 horas atrás pueden ser tres sesiones distintas.
    """
    closes = df["Close"].groupby(df.index.date).last()
    if len(closes) < 2:
        return 0.0
    ref, last = float(closes.iloc[-2]), float(closes.iloc[-1])
    return round((last - ref) / ref * 100, 2) if ref else 0.0


def _sparkline(df, points=24):
    closes = df["Close"].tail(points).tolist()
    if len(closes) < 2:
        return []
    lo, hi = min(closes), max(closes)
    span = hi - lo
    if span == 0:
        return [0.5] * len(closes)
    return [round((c - lo) / span, 4) for c in closes]


def analyze(symbol: str) -> dict:
    """Trae las velas de un símbolo y lo analiza."""
    try:
        df = market.get_candles(symbol)
    except market.MarketDataUnavailable as e:
        return {"symbol": symbol, "error": str(e)}
    except ImportError:
        return {"symbol": symbol, "error": "Falta yfinance: pip install -r requirements.txt"}
    except Exception as e:
        return {"symbol": symbol, "error": f"No se pudieron traer velas: {e}"}

    return analyze_frame(df, symbol)


def analyze_frame(df, symbol: str, timeframe: str = "60m") -> dict:
    """
    Analiza velas ya descargadas.

    Separado de analyze() para que el escáner, que baja cientos de símbolos
    por lotes en una sola petición, use exactamente el mismo cálculo.
    """
    df = df.copy()

    min_bars = max(ATR_PERIOD, RSI_PERIOD, 50) + 5
    if len(df) < min_bars:
        return {"symbol": symbol, "error": f"Solo {len(df)} velas, hacen falta {min_bars}"}

    df["ATR"] = atr(df)
    df["RSI"] = rsi(df)
    df["TR"] = true_range(df)
    df["VolAvg20"] = df["Volume"].rolling(20).mean()
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()

    last = df.iloc[-1]
    price = float(last["Close"])
    current_atr = float(last["ATR"])
    current_rsi = float(last["RSI"])

    # ---- Confirmación de que "está pasando algo" ----
    # Con volumen real se mira el volumen. En forex, donde Yahoo devuelve cero
    # porque el mercado no tiene volumen consolidado, se mira la expansión del
    # rango: una vela mucho más ancha que la media indica la misma actividad.
    volume_based = market.has_volume(df)
    if volume_based:
        vol_avg = float(last["VolAvg20"])
        activity_ratio = round(float(last["Volume"]) / vol_avg, 2) if vol_avg > 0 else 1.0
        activity_spike = activity_ratio >= VOLUME_SPIKE_MULT
        activity_label = "volumen"
    else:
        activity_ratio = round(float(last["TR"]) / current_atr, 2) if current_atr > 0 else 1.0
        activity_spike = activity_ratio >= RANGE_SPIKE_MULT
        activity_label = "rango"

    support, resistance = find_support_resistance(df)

    trend_up = bool(last["SMA20"] > last["SMA50"])
    trend_down = bool(last["SMA20"] < last["SMA50"])

    # Cuán separadas están las medias, medido en ATR. Sirve para comparar la
    # fuerza de la tendencia entre instrumentos que se mueven a escalas distintas:
    # 20 puntos en el Nasdaq y 20 pips en el euro no son comparables en bruto.
    trend_strength = (round(abs(float(last["SMA20"]) - float(last["SMA50"])) / current_atr, 2)
                      if current_atr > 0 else 0.0)
    overbought = current_rsi >= 70
    oversold = current_rsi <= 30

    direction = "buy" if trend_up else "sell" if trend_down else None

    if direction == "buy":
        stop_loss = price - current_atr * SL_ATR_MULT
        natural_tp = price + current_atr * SL_ATR_MULT * MIN_RR
        take_profit = resistance if resistance > natural_tp else natural_tp
        risk, reward = price - stop_loss, take_profit - price
    elif direction == "sell":
        stop_loss = price + current_atr * SL_ATR_MULT
        natural_tp = price - current_atr * SL_ATR_MULT * MIN_RR
        take_profit = support if support < natural_tp else natural_tp
        risk, reward = stop_loss - price, price - take_profit
    else:
        stop_loss = take_profit = risk = reward = 0.0

    rr_ratio = round(reward / risk, 2) if risk > 0 else 0.0
    good_rr = rr_ratio >= MIN_RR

    # PRECAUCION = la tendencia dice una cosa y el RSI está en el extremo
    # contrario, señal de que el movimiento puede estar agotado.
    if direction == "buy" and overbought:
        signal = "PRECAUCION"
    elif direction == "sell" and oversold:
        signal = "PRECAUCION"
    elif direction and good_rr and activity_spike:
        signal = "ENTRADA"
    else:
        signal = "OBSERVAR"

    r = lambda p: market.round_price(symbol, p)

    return {
        "symbol": symbol,
        "display_symbol": market.pretty_symbol(symbol),
        "name": market.display_name(symbol),
        "asset_class": market.asset_class(symbol),
        "price": r(price),
        "change_pct": _daily_change_pct(df),
        "entry": r(price),
        "take_profit": r(take_profit),
        "stop_loss": r(stop_loss),
        "rr_ratio": rr_ratio,
        "rsi": round(current_rsi, 1),
        "atr": r(current_atr),
        "activity_ratio": activity_ratio,
        "activity_label": activity_label,
        "activity_spike": activity_spike,
        "volume_based": volume_based,
        "trend_up": trend_up,
        "trend_down": trend_down,
        "trend_strength": trend_strength,
        "support": r(support),
        "resistance": r(resistance),
        "direction": direction,
        "signal": signal,
        "spark": _sparkline(df),
        "timeframe": timeframe,
        "last_candle": df.index[-1].isoformat(),
    }


def reason_text(r: dict) -> str:
    """Frase corta que explica por qué salió esa señal."""
    if "error" in r:
        return r["error"]

    bits = []
    if r["direction"] == "buy":
        bits.append("media de 20 sobre la de 50 (tendencia alcista)")
    elif r["direction"] == "sell":
        bits.append("media de 20 bajo la de 50 (tendencia bajista)")
    else:
        bits.append("medias cruzadas, sin tendencia definida")

    if r["activity_spike"]:
        if r["volume_based"]:
            bits.append(f"volumen {r['activity_ratio']}x el promedio de 20 velas")
        else:
            bits.append(f"rango de la vela {r['activity_ratio']}x el habitual")

    if r["rsi"] >= 70:
        bits.append(f"RSI {r['rsi']} en zona de sobrecompra")
    elif r["rsi"] <= 30:
        bits.append(f"RSI {r['rsi']} en zona de sobreventa")

    if r["signal"] == "OBSERVAR" and r["direction"] and r["rr_ratio"] < MIN_RR:
        bits.append(f"riesgo/beneficio 1:{r['rr_ratio']}, por debajo del mínimo de 1:{MIN_RR}")

    return "; ".join(bits).capitalize() + "."


def format_report(results):
    lines = []
    for r in results:
        if "error" in r:
            lines.append(f"\n{r['symbol']}: {r['error']}")
            continue

        side = {"buy": "COMPRA", "sell": "VENTA"}.get(r["direction"], "—")
        lines.append(f"\n{'='*56}")
        lines.append(f"{r['display_symbol']}  —  {r['signal']}  ({side})")
        lines.append(f"{'='*56}")
        lines.append(f"Precio:             {r['price']}   ({r['change_pct']:+}% sesión)")
        if r["direction"]:
            lines.append(f"Entrada sugerida:   {r['entry']}")
            lines.append(f"Take profit:        {r['take_profit']}")
            lines.append(f"Stop loss:          {r['stop_loss']}")
            lines.append(f"Riesgo/Beneficio:   1 : {r['rr_ratio']}")
        lines.append(f"RSI:                {r['rsi']}")
        lines.append(f"Actividad ({r['activity_label']}): {r['activity_ratio']}x"
                     + ("  ⚠ inusual" if r["activity_spike"] else ""))
        lines.append(f"Soporte / Resist.:  {r['support']} / {r['resistance']}")
        lines.append(f"Lectura:            {reason_text(r)}")
    return "\n".join(lines)


if __name__ == "__main__":
    symbols = sys.argv[1:] if len(sys.argv) > 1 else market.SYMBOLS
    print(format_report([analyze(s) for s in symbols]))
    print("\n" + "-"*56)
    print("Recomendaciones para operar a mano. No es asesoría financiera.")
