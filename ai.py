"""
Vantage — Capa de IA (Gemini)
--------------------------------
Le pide a Gemini que revise cada candidato del radar cruzando el análisis
técnico que ya calculó el sistema con los datos económicos de la empresa.

Todo es opcional: si no hay GEMINI_API_KEY, Vantage funciona igual y el
panel usa el resumen por reglas.

Configuración (.env o secret del repo):
    GEMINI_API_KEY=tu_clave           # se saca gratis en aistudio.google.com
    GEMINI_MODEL=gemini-flash-latest  # opcional; el alias apunta al Flash actual

Coste: con los 8 candidatos del radar más el resumen, son unas 10 llamadas
al día. El plan gratuito de AI Studio permite del orden de mil.

--------------------------------------------------------------------------
Sobre qué se le pide y qué NO
--------------------------------------------------------------------------
Un modelo de lenguaje no predice precios. Pedirle "¿subirá?" produce un
párrafo convincente y sin valor predictivo, y encima te da confianza para
actuar. Aquí se le pide otra cosa: que CONTRASTE la señal técnica contra
los números de la empresa y señale cuándo no encajan.

Por eso el prompt le autoriza explícitamente a decir "descartar". Un
revisor que siempre respalda no revisa nada: solo añade prosa que hace
parecer más sólida una señal que no ha cambiado.
"""

import os
import json

from dotenv import load_dotenv

load_dotenv()

# Ojo con el `or` en vez del segundo argumento de os.getenv: en GitHub Actions,
# ${{ vars.GEMINI_MODEL }} se resuelve como CADENA VACÍA cuando esa variable no
# existe. os.getenv("X", "defecto") solo aplica el defecto si la variable falta
# por completo, no si está vacía — y un nombre de modelo vacío hace que todas
# las llamadas fallen en silencio.
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or "").strip() or "gemini-flash-latest"


def why_unavailable() -> str | None:
    """Devuelve el motivo concreto por el que la IA no puede usarse, o None."""
    if not GEMINI_API_KEY:
        return ("falta GEMINI_API_KEY (o llegó vacía). En GitHub Actions, "
                "comprobá que el secret existe y que el workflow lo pasa en env:")
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return "falta el paquete google-genai. Revisá requirements.txt"
    return None


def available() -> bool:
    return why_unavailable() is None


# El cliente se guarda a nivel de módulo a propósito.
#
# Escribir `genai.Client(...).models.generate_content(...)` no funciona: solo
# se conserva una referencia a `.models`, así que Python destruye el objeto
# Client y al destruirlo cierra la conexión HTTP por debajo. La petición sale
# sobre un socket ya cerrado y falla con "Cannot send a request, as the client
# has been closed".
#
# Además, reutilizarlo evita reabrir la conexión en cada una de las nueve
# llamadas de la ronda.
_CLIENT = None


def _client():
    global _CLIENT
    if _CLIENT is None:
        from google import genai
        _CLIENT = genai.Client(api_key=GEMINI_API_KEY)
    return _CLIENT


def _generate(prompt: str, as_json: bool = True) -> str:
    from google.genai import types

    config = types.GenerateContentConfig(
        temperature=0.2,          # bajo: queremos consistencia, no creatividad
        max_output_tokens=1600,
        response_mime_type="application/json" if as_json else "text/plain",
    )

    cliente = _client()          # referencia viva mientras dura la petición
    resp = cliente.models.generate_content(
        model=GEMINI_MODEL, contents=prompt, config=config
    )
    return (resp.text or "").strip()


def _parse_json(texto: str) -> dict | None:
    if not texto:
        return None
    limpio = texto.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        datos = json.loads(limpio.strip())
        return datos if isinstance(datos, dict) else None
    except json.JSONDecodeError:
        return None


# ============================================================== el prompt

REGLAS = """\
REGLAS DE OBLIGADO CUMPLIMIENTO

1. Usá EXCLUSIVAMENTE los datos que aparecen abajo. No recurras a nada que
   recuerdes sobre esta empresa: tu conocimiento tiene meses de antigüedad y
   sería una cifra inventada presentada con seguridad. Si un dato no está,
   escribí "sin datos" y seguí.
2. No predigas el precio. Nada de "subirá", "alcanzará", "es probable que".
   Tu trabajo es contrastar, no adivinar.
3. No des probabilidades ni porcentajes de acierto. No los tenés.
4. Si lo técnico y lo económico apuntan en sentidos opuestos, decilo
   explícitamente. No promedies ni busques un término medio cómodo: la
   contradicción es la información más útil que podés aportar.
5. Estás autorizado y animado a responder "descartar". La señal técnica ya
   pasó un filtro automático; tu valor está en detectar cuándo ese filtro se
   equivoca, no en confirmarlo. Un revisor que siempre respalda no sirve.
6. Escribí en español, en frases cortas y concretas. Sin jerga de folleto
   financiero, sin adjetivos de relleno, sin listas de tópicos genéricos que
   valdrían para cualquier valor.
7. Recordá que estas señales no están validadas contra histórico. No trates
   el sistema que las generó como si fuera fiable."""

ESQUEMA = """\
Devolvé SOLO un objeto JSON, sin texto alrededor ni ```:

{
  "veredicto": "respaldar" | "matizar" | "descartar",
  "conviccion": 1-5,
  "tecnico": "2-3 frases sobre qué dice el precio y la estructura técnica",
  "economico": "2-3 frases sobre los números de la empresa; si no hay datos fundamentales, explicá qué contexto falta para juzgar este activo",
  "conflicto": "una frase si lo técnico y lo económico se contradicen, o null",
  "riesgos": ["riesgo concreto y verificable en los datos", "otro"],
  "invalidaria": "qué hecho concreto tumbaría esta idea",
  "resumen": "una sola frase, la que leerías en el móvil"
}"""


def _prompt_candidato(tecnico: dict, fundamental_txt: str) -> str:
    datos = {k: v for k, v in tecnico.items() if k not in ("spark", "reason")}
    return f"""\
Sos un analista revisando una señal generada por un sistema técnico automático.
El sistema detectó un setup y quiere una segunda opinión antes de que un humano
decida nada. Vantage no ejecuta órdenes: la persona opera a mano.

{REGLAS}

=== SEÑAL TÉCNICA DETECTADA (calculada por el sistema, sobre velas diarias) ===
{json.dumps(datos, ensure_ascii=False, indent=2)}

Cómo leer estos campos:
- signal ENTRADA significa que se cumplieron tres condiciones a la vez:
  tendencia definida (media de 20 vs media de 50), actividad inusual
  (volumen o amplitud de la vela) y riesgo/beneficio por encima de 1:1.8.
- direction es el sentido del setup: buy = compra, sell = venta.
- activity_ratio compara la actividad actual con la habitual.
- trend_strength es la separación entre medias medida en ATR.
- score es la puntuación interna de ordenación, una heurística sin validar.

=== DATOS ECONÓMICOS DE LA EMPRESA (Yahoo Finance) ===
{fundamental_txt}

Tu tarea: cruzar ambas lecturas y decir si la señal merece atención, si merece
matices, o si hay que descartarla.

{ESQUEMA}"""


def analyze_candidate(tecnico: dict, fundamental: dict | None) -> dict | None:
    """Revisa un candidato. Devuelve el veredicto o None si falla."""
    if not available():
        return None

    import fundamentals

    try:
        texto = _generate(_prompt_candidato(tecnico, fundamentals.resumen_texto(fundamental)))
    except Exception as e:
        print(f"    Fallo al analizar {tecnico.get('symbol')} con modelo "
              f"'{GEMINI_MODEL}': {type(e).__name__}: {e}")
        return None

    datos = _parse_json(texto)
    if not datos or "veredicto" not in datos:
        print(f"    Respuesta no interpretable para {tecnico.get('symbol')}")
        return None

    datos["modelo"] = GEMINI_MODEL
    datos["tiene_fundamentales"] = bool(fundamental)
    return datos


# ------------------------------------------------- visión de conjunto


def analyze_portfolio(candidatos: list) -> dict | None:
    """
    Mira los candidatos como un conjunto, no uno a uno.

    El sistema analiza cada símbolo aislado y no tiene ninguna noción de
    correlación. Puede darte plata en venta y platino en compra el mismo día,
    o seis ideas que en realidad son la misma apuesta macro repetida. Esto
    es lo que lo detecta.
    """
    if not available() or not candidatos:
        return None

    resumen = [
        {
            "simbolo": c.get("display_symbol"),
            "nombre": c.get("name"),
            "clase": c.get("asset_class"),
            "sector": (c.get("ai") or {}).get("sector") or c.get("sector"),
            "sentido": "compra" if c.get("direction") == "buy" else "venta",
            "veredicto_ia": (c.get("ai") or {}).get("veredicto"),
        }
        for c in candidatos
    ]

    prompt = f"""\
Estos son los candidatos que un sistema técnico ha seleccionado hoy. Cada uno
se analizó por separado: el sistema NO tiene ninguna noción de correlación
entre activos.

{REGLAS}

=== CANDIDATOS DE HOY ===
{json.dumps(resumen, ensure_ascii=False, indent=2)}

Tu tarea es mirarlos como conjunto y responder tres cosas:
1. ¿Hay concentración? ¿Varios candidatos son en realidad la misma apuesta
   (mismo sector, misma materia prima, misma exposición macro)?
2. ¿Hay contradicciones? ¿Se recomienda comprar un activo y vender otro que
   suele moverse en la misma dirección?
3. ¿Qué tendría que saber alguien antes de tomar varias de estas a la vez?

Devolvé SOLO este JSON:

{{
  "concentracion": "una o dos frases, o null si están bien repartidos",
  "contradicciones": "una o dos frases, o null",
  "advertencia": "la frase que más le conviene leer hoy",
  "grupos": [["SIMBOLO", "SIMBOLO"]]
}}"""

    try:
        datos = _parse_json(_generate(prompt))
    except Exception as e:
        print(f"    Visión de conjunto no disponible: {e}")
        return None

    return datos


# ------------------------------------------------- editorial del panel


def write_brief(results: list, timeframe: str = "60m") -> str | None:
    """Redacta el editorial del panel. Devuelve None si no hay IA disponible."""
    if not available():
        return None

    compacto = [
        {k: r[k] for k in ("display_symbol", "name", "asset_class", "signal", "direction",
                           "price", "change_pct", "entry", "take_profit", "stop_loss",
                           "rr_ratio", "rsi", "activity_ratio", "support", "resistance")
         if k in r}
        for r in results if "error" not in r
    ]

    prompt = f"""\
Escribí el editorial del boletín privado de mercado de una persona. Lo lee
por la mañana en el móvil, antes de decidir nada.

{REGLAS}

=== ESTADO DEL SEGUIMIENTO (velas de {timeframe}) ===
{json.dumps(compacto, ensure_ascii=False, indent=2)}

Instrucciones de estilo:
- Entre 4 y 6 frases. Prosa continua, sin listas ni titulares.
- Empezá por lo que de verdad importa hoy. Si no hay señales de entrada,
  decilo con naturalidad: no hay que rellenar.
- Marcá los símbolos con <strong class='hi'>SÍMBOLO</strong> si su señal es
  ENTRADA, y con <strong class='lo'>SÍMBOLO</strong> si es PRECAUCION.
- Cerrá recordando que son niveles técnicos sin validar contra histórico.

Devolvé SOLO este JSON:

{{"texto": "el editorial, con las etiquetas <strong> donde corresponda"}}"""

    try:
        datos = _parse_json(_generate(prompt))
    except Exception as e:
        print(f"⚠ Editorial con IA no disponible ({e}); se usa el de reglas.")
        return None

    return (datos or {}).get("texto") or None


if __name__ == "__main__":
    if not available():
        print("IA no configurada. Falta GEMINI_API_KEY o el paquete google-genai.")
        print("La clave se saca gratis en https://aistudio.google.com")
        raise SystemExit(1)

    print(f"Modelo: {GEMINI_MODEL}")
    prueba = {
        "symbol": "NVDA", "display_symbol": "NVDA", "name": "NVIDIA",
        "asset_class": "Acción", "signal": "ENTRADA", "direction": "buy",
        "price": 187.42, "entry": 187.42, "take_profit": 204.0, "stop_loss": 179.5,
        "rr_ratio": 2.09, "rsi": 61.4, "activity_ratio": 2.3, "trend_strength": 1.4,
        "support": 172.1, "resistance": 198.4, "score": 88.2,
    }
    import fundamentals
    v = analyze_candidate(prueba, fundamentals.get_fundamentals("NVDA"))
    print(json.dumps(v, ensure_ascii=False, indent=2))
