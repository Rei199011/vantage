"""
Vantage — Datos fundamentales
--------------------------------
Trae de Yahoo Finance las cifras económicas de una empresa: valoración,
márgenes, crecimiento, deuda y próxima presentación de resultados.

Existe por una razón concreta. Si le pides a un modelo de lenguaje que haga
"análisis fundamental" sin darle datos, se los inventa a partir de lo que
recuerda de su entrenamiento — cifras de hace año y medio, presentadas con
total seguridad. Este módulo es lo que convierte esa fantasía en análisis:
el modelo solo ve números que vienen de una fuente, y se le prohíbe añadir
otros.

Los pares de divisas, materias primas e índices no tienen fundamentales.
Para esos se devuelve None y el análisis se queda en técnico, que es lo
honesto.
"""

import math

# Campos de yfinance que interesan, con su nombre legible.
CAMPOS = [
    ("sector", "Sector"),
    ("industry", "Industria"),
    ("marketCap", "Capitalización"),
    ("trailingPE", "PER (12m)"),
    ("forwardPE", "PER estimado"),
    ("priceToBook", "Precio / valor contable"),
    ("enterpriseToEbitda", "EV / EBITDA"),
    ("profitMargins", "Margen neto"),
    ("operatingMargins", "Margen operativo"),
    ("revenueGrowth", "Crecimiento de ingresos"),
    ("earningsGrowth", "Crecimiento de beneficio"),
    ("returnOnEquity", "ROE"),
    ("debtToEquity", "Deuda / fondos propios"),
    ("currentRatio", "Ratio de liquidez"),
    ("freeCashflow", "Flujo de caja libre"),
    ("totalRevenue", "Ingresos"),
    ("dividendYield", "Rentabilidad por dividendo"),
    ("beta", "Beta"),
    ("fiftyTwoWeekHigh", "Máximo 52 semanas"),
    ("fiftyTwoWeekLow", "Mínimo 52 semanas"),
    ("targetMeanPrice", "Precio objetivo medio (analistas)"),
    ("numberOfAnalystOpinions", "Nº de analistas"),
    ("recommendationKey", "Consenso de analistas"),
    ("heldPercentInstitutions", "% en manos institucionales"),
    ("shortPercentOfFloat", "% de free float en corto"),
]

PORCENTAJES = {
    "profitMargins", "operatingMargins", "revenueGrowth", "earningsGrowth",
    "returnOnEquity", "dividendYield", "heldPercentInstitutions", "shortPercentOfFloat",
}


def _limpio(valor):
    """Descarta los None, los NaN y las cadenas vacías que devuelve yfinance."""
    if valor is None:
        return None
    if isinstance(valor, float) and (math.isnan(valor) or math.isinf(valor)):
        return None
    if isinstance(valor, str) and not valor.strip():
        return None
    return valor


def get_fundamentals(symbol: str) -> dict | None:
    """
    Devuelve las cifras económicas de una acción, o None si no aplica
    (divisas, materias primas, índices) o si Yahoo no las tiene.
    """
    import yfinance as yf

    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        return None

    # Sin sector no es una empresa: es un par, un futuro o un índice.
    if not _limpio(info.get("sector")):
        return None

    datos = {}
    for clave, etiqueta in CAMPOS:
        valor = _limpio(info.get(clave))
        if valor is None:
            continue
        if clave in PORCENTAJES and isinstance(valor, (int, float)):
            valor = round(valor * 100, 2)
            etiqueta += " (%)"
        elif isinstance(valor, float):
            valor = round(valor, 3)
        datos[etiqueta] = valor

    if len(datos) < 4:
        return None

    fecha = _proxima_presentacion(symbol)
    if fecha:
        datos["Próximos resultados"] = fecha

    return datos or None


def _proxima_presentacion(symbol: str) -> str | None:
    """
    Fecha de la próxima presentación de resultados.

    Es el riesgo más concreto que puede tener una operación técnica: un buen
    setup puede evaporarse en un segundo cuando la empresa publica.
    """
    import yfinance as yf

    try:
        cal = yf.Ticker(symbol).calendar
    except Exception:
        return None

    if not cal:
        return None

    try:
        fechas = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if not fechas:
            return None
        primera = fechas[0] if isinstance(fechas, (list, tuple)) else fechas
        return str(primera)[:10]
    except (AttributeError, IndexError, TypeError):
        return None


def resumen_texto(datos: dict | None) -> str:
    """Versión en texto plano, para meterla en el prompt sin ambigüedad."""
    if not datos:
        return "Sin datos fundamentales: no es una empresa cotizada."
    return "\n".join(f"- {k}: {v}" for k, v in datos.items())


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:] or ["NVDA", "SAN.MC", "EURUSD=X", "GC=F"]:
        d = get_fundamentals(s)
        print(f"\n=== {s} ===")
        print(resumen_texto(d))
