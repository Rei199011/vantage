"""
Vantage — Datos de mercado
-----------------------------
Única fuente de datos del proyecto: Yahoo Finance, vía yfinance.

No hace falta cuenta de bróker, ni API key, ni terminal abierto, ni Windows.
Vantage solo mira el mercado y te avisa; las órdenes las pasás vos a mano
en el bróker que uses.

Uso:
    python market.py            # comprueba que todos los símbolos responden
"""

import pandas as pd

# ---------------------------------------------------------------------------
# TU WATCHLIST — editá esta lista y listo.
#
# Formato: (ticker de Yahoo, nombre a mostrar, clase de activo)
# Para añadir algo, buscalo en finance.yahoo.com y copiá el símbolo de la URL.
# ---------------------------------------------------------------------------
WATCHLIST = [
    ("EURUSD=X", "Euro / Dólar",        "Forex"),
    ("GBPUSD=X", "Libra / Dólar",       "Forex"),
    ("USDJPY=X", "Dólar / Yen",         "Forex"),
    ("GC=F",     "Oro",                 "Metal"),
    ("^NDX",     "Nasdaq 100",          "Índice"),
    ("^GSPC",    "S&P 500",             "Índice"),
    ("^DJI",     "Dow Jones 30",        "Índice"),
    ("NVDA",     "NVIDIA Corp.",        "Acción"),
    ("PLTR",     "Palantir Technologies","Acción"),
    ("SNOW",     "Snowflake Inc.",      "Acción"),
    ("RKLB",     "Rocket Lab USA",      "Acción"),
]

SYMBOLS = [row[0] for row in WATCHLIST]
_META = {row[0]: (row[1], row[2]) for row in WATCHLIST}

# Velas de una hora. 90 días es de sobra para las medias de 50 periodos,
# incluso en acciones, que solo cotizan 6,5 horas al día.
YF_PERIOD = "90d"
YF_INTERVAL = "60m"


class MarketDataUnavailable(RuntimeError):
    """Yahoo no devolvió datos para ese símbolo."""


def get_candles(symbol: str, count: int = 400) -> pd.DataFrame:
    """Open/High/Low/Close/Volume indexado por fecha."""
    import yfinance as yf

    df = yf.download(
        symbol,
        period=YF_PERIOD,
        interval=YF_INTERVAL,
        progress=False,
        auto_adjust=True,
    )

    if df is None or df.empty:
        raise MarketDataUnavailable(f"Yahoo no devolvió datos para '{symbol}'")

    # yfinance devuelve columnas MultiIndex (Price, Ticker) incluso para un solo
    # símbolo. Sin aplanarlas, df["Close"] es un DataFrame y los indicadores fallan.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    faltan = [c for c in ("Open", "High", "Low", "Close") if c not in df.columns]
    if faltan:
        raise MarketDataUnavailable(f"'{symbol}' vino sin las columnas {faltan}")

    if "Volume" not in df.columns:
        df["Volume"] = 0.0

    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(
        subset=["Open", "High", "Low", "Close"]
    )
    df["Volume"] = df["Volume"].fillna(0.0)

    if df.empty:
        raise MarketDataUnavailable(f"'{symbol}' no tiene velas utilizables")

    return df.tail(count)


def has_volume(df: pd.DataFrame) -> bool:
    """
    ¿Este instrumento trae volumen real?

    En los pares de divisas Yahoo devuelve volumen 0: el mercado forex es
    descentralizado y no hay un volumen consolidado. El analyzer necesita
    saberlo para no descartar todas las señales de forex por falta de un
    dato que nunca va a existir.
    """
    return bool(df["Volume"].tail(60).sum() > 0)


# ---------------------------------------------------------------- presentación


def display_name(symbol: str) -> str:
    return _META.get(symbol, (symbol, ""))[0]


def asset_class(symbol: str) -> str:
    return _META.get(symbol, ("", "Otro"))[1]


def pretty_symbol(symbol: str) -> str:
    """EURUSD=X -> EUR/USD · ^NDX -> NDX · GC=F -> ORO"""
    special = {"GC=F": "ORO", "SI=F": "PLATA", "CL=F": "PETRÓLEO",
               "^NDX": "NAS100", "^GSPC": "SPX500", "^DJI": "US30",
               "^GDAXI": "DAX40", "^FTSE": "FTSE100"}
    if symbol in special:
        return special[symbol]
    if symbol.endswith("=X"):
        base = symbol[:-2]
        return f"{base[:3]}/{base[3:]}" if len(base) == 6 else base
    return symbol.lstrip("^")


def price_precision(symbol: str) -> int:
    """Decimales con los que se muestra el precio de cada clase de activo."""
    if symbol.endswith("=X"):
        return 3 if "JPY" in symbol else 5
    return 2


def round_price(symbol: str, price: float) -> float:
    return round(float(price), price_precision(symbol))


def format_price(symbol: str, price: float) -> str:
    return f"{float(price):.{price_precision(symbol)}f}"


if __name__ == "__main__":
    print(f"Comprobando {len(SYMBOLS)} símbolos…\n")
    for sym in SYMBOLS:
        try:
            df = get_candles(sym)
            vol = "con volumen" if has_volume(df) else "SIN volumen (normal en forex)"
            print(f"  ✔ {pretty_symbol(sym):<10} {sym:<11} {len(df):>4} velas · "
                  f"último {format_price(sym, df['Close'].iloc[-1])} · {vol}")
        except Exception as e:
            print(f"  ✘ {pretty_symbol(sym):<10} {sym:<11} {e}")
    print("\nSi algún símbolo falla, buscá el correcto en finance.yahoo.com "
          "y cambialo en WATCHLIST.")
