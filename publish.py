"""
Vantage — Publicador del panel
---------------------------------
Convierte los resultados del analyzer en `data.json`, que es lo que lee
`dashboard.html`. Opcionalmente hace commit y push para que GitHub Pages
se actualice solo.

El panel es una página estática: no calcula nada ni llama a ninguna API.
Tu máquina genera el JSON y GitHub Pages lo sirve.

Uso:
    python publish.py                    # analiza el watchlist y escribe data.json
    python publish.py --push             # además hace commit y push a GitHub
"""

import io
import os
import json
import subprocess
from datetime import datetime, timezone

from dotenv import load_dotenv

import market
from analyzer import analyze, reason_text

load_dotenv()

DATA_FILE = "data.json"
RADAR_FILE = "radar.json"
EVENTS_FILE = "events.json"      # historial local del feed de alertas
MAX_EVENTS = 12

TIMEZONE_LABEL = os.getenv("PANEL_TIMEZONE_LABEL", "UTC")


# ------------------------------------------------------------------ eventos


def load_radar() -> dict:
    """El ranking del ultimo escaneo diario, si existe."""
    if not os.path.exists(RADAR_FILE):
        return {}
    try:
        with io.open(RADAR_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def load_previous_signals() -> dict:
    """
    {símbolo: señal} de la última publicación.

    Sirve para no repetir avisos. Importa sobre todo en GitHub Actions, donde
    cada ejecución arranca en una máquina limpia: sin esto, el bot volvería a
    avisarte de la misma señal en cada ronda.
    """
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {r["symbol"]: r["signal"] for r in data.get("watchlist", []) if "symbol" in r}
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


def _load_events() -> list:
    if not os.path.exists(EVENTS_FILE):
        return []
    try:
        with open(EVENTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _detect_events(results: list) -> list:
    """Saca eventos publicables de la ronda actual. Solo hechos medibles."""
    now = datetime.now(timezone.utc)
    events = []

    for r in results:
        if "error" in r:
            continue
        sym = r["display_symbol"]

        if r["signal"] == "ENTRADA":
            side = "compra" if r["direction"] == "buy" else "venta"
            events.append({
                "kind": "Señal",
                "kind_class": "",
                "symbol": sym,
                "time": now.isoformat(),
                "body": (f"Setup de <strong>{side}</strong> con riesgo/beneficio "
                         f"1:{r['rr_ratio']}. Entrada {r['entry']}, stop {r['stop_loss']}."),
            })
        elif r["signal"] == "PRECAUCION":
            events.append({
                "kind": "Precaución",
                "kind_class": "sentiment",
                "symbol": sym,
                "time": now.isoformat(),
                "body": (f"RSI en <strong>{r['rsi']}</strong> contra la tendencia de las medias. "
                         f"El movimiento puede estar agotado."),
            })

        if r["activity_spike"] and r["signal"] != "ENTRADA":
            etiqueta = "Volumen" if r["volume_based"] else "Rango"
            events.append({
                "kind": etiqueta,
                "kind_class": "",
                "symbol": sym,
                "time": now.isoformat(),
                "body": (f"{etiqueta} <strong>{r['activity_ratio']}x</strong> lo habitual, "
                         f"sin setup válido todavía."),
            })

        if r["price"] >= r["resistance"]:
            events.append({
                "kind": "Nivel",
                "kind_class": "filing",
                "symbol": sym,
                "time": now.isoformat(),
                "body": f"Precio en máximos de las últimas 60 velas (<strong>{r['resistance']}</strong>).",
            })
        elif r["price"] <= r["support"]:
            events.append({
                "kind": "Nivel",
                "kind_class": "filing",
                "symbol": sym,
                "time": now.isoformat(),
                "body": f"Precio en mínimos de las últimas 60 velas (<strong>{r['support']}</strong>).",
            })

    return events


def _merge_events(new_events: list) -> list:
    """Añade los nuevos al historial evitando duplicados consecutivos."""
    history = _load_events()
    seen = {(e["symbol"], e["kind"], e["body"]) for e in history[:4]}
    fresh = [e for e in new_events if (e["symbol"], e["kind"], e["body"]) not in seen]
    merged = fresh + history
    merged = merged[:MAX_EVENTS]

    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return merged


# ------------------------------------------------------------------ resumen


def _rule_based_brief(results: list) -> str:
    ok = [r for r in results if "error" not in r]
    entradas = [r for r in ok if r["signal"] == "ENTRADA"]
    precaucion = [r for r in ok if r["signal"] == "PRECAUCION"]

    if not ok:
        return ("No se pudieron traer datos de mercado en esta ronda. "
                "Revisá la conexión a internet o los símbolos del watchlist.")

    parts = []

    if entradas:
        for r in entradas:
            side = "compra" if r["direction"] == "buy" else "venta"
            parts.append(
                f"<strong class='hi'>{r['display_symbol']}</strong> presenta un setup de {side}: "
                f"entrada en {r['entry']}, take profit en {r['take_profit']} y stop loss en "
                f"{r['stop_loss']} (riesgo/beneficio 1:{r['rr_ratio']}), con "
                f"{'volumen' if r['volume_based'] else 'rango'} "
                f"{r['activity_ratio']}x lo habitual."
            )
    else:
        parts.append(
            "Ningún instrumento del watchlist cumple hoy las tres condiciones de entrada "
            "(tendencia definida, volumen inusual y riesgo/beneficio mínimo). "
            "Sin señales es un resultado válido, no un fallo del sistema."
        )

    for r in precaucion:
        parts.append(
            f"Cautela en <strong class='lo'>{r['display_symbol']}</strong>: el RSI está en "
            f"{r['rsi']}, en extremo contrario a la tendencia de las medias."
        )

    movers = sorted(ok, key=lambda r: abs(r["change_pct"]), reverse=True)[:2]
    if movers:
        txt = ", ".join(f"{m['display_symbol']} {m['change_pct']:+}%" for m in movers)
        parts.append(f"Mayor movimiento en las últimas 24 horas: {txt}.")

    parts.append(
        f"Lectura sobre velas de {market.YF_INTERVAL}. Los niveles son cálculo técnico, "
        "no una previsión, y el sistema no está validado contra histórico. "
        "Vantage no opera: las órdenes las pasás vos."
    )
    return " ".join(parts)


def _ai_brief(results: list) -> str | None:
    """Editorial con Gemini, si hay GEMINI_API_KEY. Si falla, se usa el de reglas."""
    import ai
    return ai.write_brief(results, timeframe=market.YF_INTERVAL)


# ------------------------------------------------------------------ publicar


def _system_status(results: list) -> list:
    """Estado del sistema para el panel. No hay credenciales ni cuentas que reportar."""
    ok = [r for r in results if "error" not in r]
    sin_volumen = sum(1 for r in ok if not r["volume_based"])
    clases = sorted({r["asset_class"] for r in ok})

    return [
        {
            "name": "Datos de mercado",
            "pulse": "ok" if ok else "warn",
            "rows": [
                ["Fuente", f"Yahoo Finance · velas {market.YF_INTERVAL}"],
                ["Cobertura", ", ".join(clases) if clases else "sin datos"],
                ["Símbolos", f"{len(ok)} de {len(market.SYMBOLS)} respondiendo"],
            ],
            "pill": "Solo lectura",
            "pill_class": "read",
        },
        {
            "name": "Confirmación de actividad",
            "pulse": "info",
            "rows": [
                ["Con volumen", f"{len(ok) - sin_volumen} símbolos"],
                ["Por rango", f"{sin_volumen} símbolos (forex y similares)"],
            ],
            "pill": "Cálculo local",
            "pill_class": "local",
        },
        {
            "name": "Radar",
            "pulse": "ok" if _radar_ok() else "warn",
            "rows": _radar_rows(),
            "pill": "Escaneo diario",
            "pill_class": "read",
        },
        {
            "name": "Avisos por Telegram",
            "pulse": "ok" if _telegram_ok() else "warn",
            "rows": [
                ["Estado", "configurado" if _telegram_ok() else "no configurado"],
                ["Avisa de", "entradas y precauciones"],
            ],
            "pill": "Token solo en tu máquina",
            "pill_class": "local",
        },
        {
            "name": "Revisión con IA",
            "pulse": "ok" if _ai_ok() else "warn",
            "rows": _ai_rows(),
            "pill": "Opcional",
            "pill_class": "local",
        },
        {
            "name": "Registro de señales",
            "pulse": "ok" if _journal_stats().get("cerradas") else "info",
            "rows": _journal_rows(),
            "pill": "Medición en curso",
            "pill_class": "read",
        },
        {
            "name": "Ejecución",
            "pulse": "ok",
            "rows": [
                ["Modo", "ninguno · solo recomendaciones"],
                ["Órdenes", "las pasás vos, en tu bróker"],
            ],
            "pill": "Sin acceso a ningún bróker",
            "pill_class": "local",
        },
    ]


def _radar_ok() -> bool:
    return bool(load_radar().get("top"))


def _radar_rows() -> list:
    r = load_radar()
    if not r:
        return [["Estado", "sin escanear todavia"],
                ["Universo", "se revisa una vez al dia"]]
    return [
        ["Universo", f"{r.get('universe_size', 0)} simbolos"],
        ["Candidatos", f"{r.get('candidates', 0)} con senal"],
        ["Velas", r.get("timeframe", "1d")],
    ]


def _journal_stats() -> dict:
    """Métricas del registro de señales, si ya hay alguna."""
    try:
        import journal
        return journal.stats()
    except Exception:
        return {}


def _ai_ok() -> bool:
    import ai
    return ai.available()


def _ai_rows() -> list:
    import ai
    if not ai.available():
        return [["Estado", "no configurada"],
                ["Efecto", "el editorial se arma con reglas"]]
    r = load_radar()
    return [
        ["Modelo", ai.GEMINI_MODEL],
        ["Revisados", f"{r.get('reviewed', 0)} candidatos del radar"],
        ["Alcance", "contraste técnico y económico"],
    ]


def _journal_rows() -> list:
    s = _journal_stats()
    if not s.get("total"):
        return [["Estado", "sin señales anotadas"],
                ["Objetivo", "medir si las señales aciertan"]]
    if not s.get("cerradas"):
        return [["Anotadas", f"{s['total']}"],
                ["Abiertas", f"{s['abiertas']}"],
                ["Cerradas", "ninguna todavía"]]
    return [
        ["Cerradas", f"{s['cerradas']} de {s['total']}"],
        ["Esperanza", f"{s['esperanza_r']:+.2f} R por operación"],
        ["Acierto", f"{s['tasa_acierto']}%"],
    ]


def _telegram_ok() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def build_payload(results: list) -> dict:
    ok = [r for r in results if "error" not in r]
    events = _merge_events(_detect_events(results))
    brief = _ai_brief(results) or _rule_based_brief(results)

    radar = load_radar()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone_label": TIMEZONE_LABEL,
        "granularity": market.YF_INTERVAL,
        "execution": False,
        "source": "Yahoo Finance",
        "watchlist": [
            {**r, "reason": reason_text(r), "promoted": market.is_promoted(r["symbol"])}
            for r in ok
        ],
        "errors": [
            {"symbol": r["symbol"], "error": r["error"]} for r in results if "error" in r
        ],
        "events": events,
        "brief": brief,
        "radar": radar,
        "journal": _journal_stats(),
        "status": _system_status(results),
    }


def publish(results: list, push: bool = False) -> dict:
    payload = build_payload(results)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"✔ {DATA_FILE} actualizado ({len(payload['watchlist'])} instrumentos, "
          f"{len(payload['errors'])} con error)")

    if push:
        git_push()
    return payload


def git_push():
    """Commit + push de data.json para que GitHub Pages se actualice."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        subprocess.run(["git", "add", DATA_FILE], check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"Datos del panel — {stamp}"],
            capture_output=True, text=True,
        )
        if "nothing to commit" in (result.stdout + result.stderr):
            print("· Sin cambios que subir.")
            return
        subprocess.run(["git", "push"], check=True, capture_output=True)
        print("✔ Cambios subidos a GitHub. El panel se actualiza en 1-2 minutos.")
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        print(f"⚠ No se pudo hacer push: {err.strip() or e}")


if __name__ == "__main__":
    import sys

    results = [analyze(s) for s in market.active_symbols()]
    publish(results, push="--push" in sys.argv)
