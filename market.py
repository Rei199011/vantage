"""
Vantage — Datos de mercado
-----------------------------
Única fuente de datos del proyecto: Yahoo Finance, vía yfinance.

No hace falta cuenta de bróker, ni API key, ni terminal abierto, ni Windows.
Vantage solo mira el mercado y te avisa; las órdenes las pasás vos a mano
en el bróker que uses.

Solo acciones. Las divisas y materias primas se retiraron: ya no se
recomiendan. Los índices siguen usándose como contexto de mercado, pero
nunca generan señal.

Uso:
    python market.py            # comprueba que todos los símbolos responden
"""

import json
import os

import pandas as pd

import universe

# ---------------------------------------------------------------------------
# TU WATCHLIST — editá esta lista y listo.
#
# Formato: (ticker de Yahoo, nombre a mostrar, clase de activo)
# Solo acciones: buscá el ticker en finance.yahoo.com y copialo de la URL.
# Los americanos van tal cual (NVDA); los europeos llevan sufijo de bolsa
# (SAN.MC en Madrid, ASML.AS en Ámsterdam, SHEL.L en Londres).
# ---------------------------------------------------------------------------
WATCHLIST = [
    ("NVDA", "NVIDIA Corp.",         "Acción"),
    ("PLTR", "Palantir Technologies", "Acción"),
    ("SNOW", "Snowflake Inc.",       "Acción"),
    ("RKLB", "Rocket Lab USA",       "Acción"),
    ("AAPL", "Apple Inc.",           "Acción"),
    ("MSFT", "Microsoft Corp.",      "Acción"),
]

# Símbolos que el escáner ascendió al seguimiento horario. Lo escribe
# scanner.py una vez al día; si el archivo no existe, no pasa nada.
AUTO_FILE = "watchlist_auto.json"


def _load_auto() -> list:
    if not os.path.exists(AUTO_FILE):
        return []
    try:
        with open(AUTO_FILE, encoding="utf-8") as f:
            return json.load(f).get("symbols", [])
    except (json.JSONDecodeError, OSError):
        return []


def active_symbols() -> list:
    """
    Lo que se vigila cada hora: tu lista fija más lo que el escáner ascendió.

    La lista fija siempre está; lo ascendido rota solo, según lo que el
    escáner encuentre en el universo amplio.
    """
    fijos = [row[0] for row in WATCHLIST]
    auto = [s for s in _load_auto() if s not in fijos]
    return fijos + auto


def is_promoted(symbol: str) -> bool:
    """¿Este símbolo entró por el escáner y no por tu lista fija?"""
    return symbol not in {row[0] for row in WATCHLIST}


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
    ¿Este símbolo trae volumen real?

    Las acciones siempre lo traen. Se mantiene la comprobación porque los
    índices de contexto vienen con volumen cero o irregular, y el analyzer
    necesita saberlo para confirmar con la amplitud de la vela en su lugar.
    """
    return bool(df["Volume"].tail(60).sum() > 0)


# ---------------------------------------------------------------- presentación


def _meta(symbol: str) -> tuple[str, str]:
    """Primero tu lista fija, luego el universo amplio, y si no, el propio ticker."""
    if symbol in _META:
        return _META[symbol]
    if symbol in universe.META:
        return universe.META[symbol]
    return (symbol, "Otro")


def display_name(symbol: str) -> str:
    return _meta(symbol)[0]


def asset_class(symbol: str) -> str:
    return _meta(symbol)[1]


def pretty_symbol(symbol: str) -> str:
    """EURUSD=X -> EUR/USD · ^NDX -> NDX · GC=F -> ORO"""
    special = {"GC=F": "ORO", "SI=F": "PLATA", "HG=F": "COBRE", "PL=F": "PLATINO",
               "CL=F": "WTI", "BZ=F": "BRENT", "NG=F": "GAS",
               "ZC=F": "MAÍZ", "ZW=F": "TRIGO", "KC=F": "CAFÉ",
               "^NDX": "NAS100", "^GSPC": "SPX500", "^DJI": "US30",
               "^RUT": "RUSSELL", "^VIX": "VIX", "^GDAXI": "DAX40",
               "^FCHI": "CAC40", "^IBEX": "IBEX35", "^FTSE": "FTSE100",
               "^STOXX50E": "STOXX50", "^N225": "NIKKEI", "^HSI": "HANGSENG"}
    if symbol in special:
        return special[symbol]
    if symbol.endswith("=X"):
        base = symbol[:-2]
        return f"{base[:3]}/{base[3:]}" if len(base) == 6 else base
    if "." in symbol:          # bolsas europeas: SAN.MC -> SAN
        return symbol.split(".")[0]
    return symbol.lstrip("^")


def price_precision(symbol: str) -> int:
    """Decimales con los que se muestra el precio."""
    return 2


def round_price(symbol: str, price: float) -> float:
    return round(float(price), price_precision(symbol))


def format_price(symbol: str, price: float) -> str:
    return f"{float(price):.{price_precision(symbol)}f}"


if __name__ == "__main__":
    activos = active_symbols()
    print(f"Comprobando {len(activos)} símbolos activos…\n")
    for sym in activos:
        try:
            df = get_candles(sym)
            vol = "con volumen" if has_volume(df) else "SIN volumen (normal en forex)"
            origen = "escáner" if is_promoted(sym) else "fija "
            print(f"  ✔ {pretty_symbol(sym):<10} {sym:<11} [{origen}] {len(df):>4} velas · "
                  f"último {format_price(sym, df['Close'].iloc[-1])} · {vol}")
        except Exception as e:
            print(f"  ✘ {pretty_symbol(sym):<10} {sym:<11} {e}")
    print("\nSi algún símbolo falla, buscá el correcto en finance.yahoo.com "
          "y cambialo en WATCHLIST.")
