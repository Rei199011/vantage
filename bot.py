"""
Vantage — Bot de Telegram
----------------------------
Corre el analyzer sobre el watchlist, te manda las recomendaciones por
Telegram y actualiza los datos del panel.

Vantage no opera. No hay botones de ejecución, no hay conexión a ningún
bróker y no hay nada que pueda mandar una orden por su cuenta. Vos leés
la recomendación y decidís qué hacer en tu bróker.

Uso:
    python bot.py              # una pasada: avisos + actualiza el panel, y sale
    python bot.py --daemon     # queda corriendo, revisa cada N minutos
    python bot.py --radar      # escanea el universo amplio y manda el resumen diario
    python bot.py --informe    # cierra las señales vencidas y manda las métricas

Comandos en el chat: /revisar, /estado y /registro (solo responde a tu chat).
"""

import os
import sys
import asyncio
from datetime import datetime, timezone

from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

import market
import universe
import scanner
import journal
from analyzer import analyze, reason_text
from publish import publish, load_previous_signals

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_INTERVAL_MINUTES = 30

# Si está en true, cada ronda hace commit y push de data.json para que
# GitHub Pages muestre datos frescos. Genera un commit por ronda.
AUTO_PUSH = os.getenv("PANEL_AUTO_PUSH", "false").strip().lower() in ("1", "true", "yes")

# Solo llegan a Telegram las órdenes reales. PRECAUCION y OBSERVAR siguen
# calculándose y se ven en el panel, pero no interrumpen: no son operaciones.
ALERT_ON = {"ENTRADA"}

# Si la revisión con IA descartó un símbolo en el radar de la mañana, no se
# avisa de él aunque la vela horaria confirme. Ponelo en False para recibir
# todas las entradas técnicas, revisadas o no.
RESPETAR_VEREDICTO = True

# Evita repetir la misma alerta en cada ronda: {símbolo: última señal avisada}.
# Se siembra desde data.json, así el estado sobrevive a reinicios y funciona
# igual en GitHub Actions, donde cada ejecución empieza en una máquina limpia.
_last_signal: dict[str, str] = {}
_seeded = False


def _esc(texto) -> str:
    """
    Telegram en modo HTML solo exige escapar estos tres caracteres.

    Se usa HTML y no Markdown porque el Markdown clásico se rompe con
    cualquier guion bajo o asterisco que venga en un nombre de empresa,
    y el mensaje entero falla al enviarse.
    """
    return (str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _veredictos() -> dict:
    """{símbolo: veredicto} de la revisión del radar de esta mañana."""
    import json
    import os
    if not os.path.exists("radar.json"):
        return {}
    try:
        with open("radar.json", encoding="utf-8") as f:
            datos = json.load(f)
        return {r["symbol"]: (r.get("ai") or {}).get("veredicto")
                for r in datos.get("top", []) if "symbol" in r}
    except Exception:
        return {}


def _is_owner(update: Update) -> bool:
    """
    ¿El mensaje viene de TU chat?

    Los bots de Telegram son públicos: cualquiera que sepa el @usuario puede
    escribirle. Sin esto, un desconocido podría usar tus comandos.
    """
    chat = update.effective_chat
    return bool(chat and str(chat.id) == str(TELEGRAM_CHAT_ID))


def format_message(r: dict, veredicto: dict | None = None) -> str:
    """Una orden, tal como la vas a leer en el móvil."""
    compra = r["direction"] == "buy"
    icono = "🟢" if compra else "🔴"
    lado = "COMPRA" if compra else "VENTA"
    radar = " 📡" if market.is_promoted(r["symbol"]) else ""

    lineas = [
        f"{icono} <b>{lado} · {_esc(r['display_symbol'])}</b>{radar}",
        f"<i>{_esc(r['name'])}</i>",
        "",
        "<code>"
        f"Entrada   {r['entry']}\n"
        f"Objetivo  {r['take_profit']}\n"
        f"Stop      {r['stop_loss']}\n"
        f"R/B       1 : {r['rr_ratio']}"
        "</code>",
        "",
    ]

    actividad = "volumen" if r["volume_based"] else "rango"
    lineas.append(f"<i>Precio {r['price']} · {r['change_pct']:+}% sesión · "
                  f"RSI {r['rsi']} · {actividad} {r['activity_ratio']}×</i>")

    if veredicto and veredicto.get("resumen"):
        marca = "✅" if veredicto.get("veredicto") == "respaldar" else "⚠️"
        lineas.append(f"\n{marca} <i>{_esc(veredicto['resumen'])}</i>")
        if veredicto.get("momento"):
            lineas.append(f"⏱ {_esc(veredicto['momento'])}")

    return "\n".join(lineas)


async def send_alert(bot: Bot, r: dict, veredictos: dict):
    if "error" in r or r["signal"] not in ALERT_ON:
        return

    if RESPETAR_VEREDICTO and veredictos.get(r["symbol"]) == "descartar":
        print(f"  {r['display_symbol']}: entrada omitida, la revisión la descartó")
        return

    if _last_signal.get(r["symbol"]) == r["signal"]:
        return  # ya avisamos esto, no repetir cada 30 min
    _last_signal[r["symbol"]] = r["signal"]

    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=format_message(r, _detalle_ia(r["symbol"])),
        parse_mode=ParseMode.HTML,
    )


def _detalle_ia(symbol: str) -> dict | None:
    """El veredicto completo de ese símbolo, si el radar lo revisó."""
    import json
    import os
    if not os.path.exists("radar.json"):
        return None
    try:
        with open("radar.json", encoding="utf-8") as f:
            for r in json.load(f).get("top", []):
                if r.get("symbol") == symbol:
                    return r.get("ai")
    except Exception:
        pass
    return None


# --------------------------------------------------------------- comandos


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/estado — qué está vigilando y desde cuándo."""
    if not _is_owner(update):
        return

    activos = market.active_symbols()
    fijos = len(market.WATCHLIST)
    lines = [
        "<b>Vantage</b> · solo recomendaciones, sin ejecución",
        f"Cada hora: {len(activos)} símbolos ({fijos} fijos + "
        f"{len(activos) - fijos} del radar), velas de {market.YF_INTERVAL}",
        f"Radar diario: {len(universe.SYMBOLS)} símbolos, velas de 1d",
        f"Revisión cada {CHECK_INTERVAL_MINUTES} min",
        f"Panel: {'con push automático' if AUTO_PUSH else 'actualización local'}",
    ]
    if _last_signal:
        lines.append("")
        lines.append("Últimas señales avisadas:")
        for sym, sig in _last_signal.items():
            lines.append(f"· {_esc(market.pretty_symbol(sym))}: {sig}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/registro — cómo van las señales pasadas."""
    if not _is_owner(update):
        return
    await update.message.reply_text(
        journal.format_report(journal.stats()), parse_mode=ParseMode.HTML)


async def cmd_revisar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/revisar — fuerza una ronda ahora y devuelve un resumen."""
    if not _is_owner(update):
        return

    await update.message.reply_text("Revisando el watchlist…")
    results = await run_round(context.bot)

    ok = [r for r in results if "error" not in r]
    entradas = [r for r in ok if r["signal"] == "ENTRADA"]

    if entradas:
        resumen = "\n".join(
            f"· <b>{_esc(r['display_symbol'])}</b> {'compra' if r['direction'] == 'buy' else 'venta'} "
            f"en {r['entry']} (R/B 1:{r['rr_ratio']})" for r in entradas
        )
        texto = f"<b>{len(entradas)} operación(es) disponible(s)</b>\n{resumen}"
    else:
        texto = (f"Ninguno de los {len(ok)} símbolos cumple las condiciones de entrada "
                 "ahora mismo. Sin señales es un resultado válido.")

    await update.message.reply_text(texto, parse_mode=ParseMode.HTML)


# --------------------------------------------------------------- rondas


async def run_round(bot: Bot):
    """Analiza todo el watchlist, manda alertas y actualiza el panel."""
    global _seeded
    if not _seeded:
        _last_signal.update(load_previous_signals())
        _seeded = True
        if _last_signal:
            print(f"Estado recuperado: {len(_last_signal)} señales de la ronda anterior")

    veredictos = _veredictos()
    results = []
    for symbol in market.active_symbols():
        r = analyze(symbol)
        results.append(r)
        await send_alert(bot, r, veredictos)
        await asyncio.sleep(0.4)   # no atropellar a Yahoo

    # El registro se escribe SIEMPRE, se avise o no. Lo que se mide es la
    # señal, no si te llegó el mensaje.
    try:
        nuevas = journal.record(results)
        if nuevas:
            print(f"  {nuevas} señal(es) anotadas en el registro")
    except Exception as e:
        print(f"⚠ No se pudo anotar en el registro: {e}")

    try:
        publish(results, push=AUTO_PUSH)
    except Exception as e:
        print(f"⚠ No se pudo actualizar data.json: {e}")

    return results


async def run_informe():
    """Cierra las señales vencidas y manda las métricas acumuladas."""
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    print("Actualizando el registro de señales…")
    cerradas = journal.update()
    print(f"{cerradas} señal(es) cerradas en esta pasada")

    s = journal.stats()
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=journal.format_report(s),
        parse_mode=ParseMode.HTML,
    )


async def run_radar():
    """Escanea el universo amplio, asciende los mejores y manda el resumen."""
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    # Antes de buscar señales nuevas, cerrar las viejas que ya se resolvieron.
    print("Actualizando el registro de señales…")
    try:
        journal.update()
    except Exception as e:
        print(f"⚠ No se pudo actualizar el registro: {e}")

    print(f"Escaneando {len(universe.SYMBOLS)} simbolos...")
    resultados = scanner.scan()
    conjunto = scanner.review(scanner.candidates(resultados))
    radar = scanner.save(resultados, conjunto)

    print(f"{radar['scanned']} analizados, {radar['candidates']} candidatos")
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=scanner.format_digest(radar),
        parse_mode=ParseMode.HTML,
    )


async def run_once():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    results = await run_round(bot)
    errores = [r for r in results if "error" in r]
    if errores:
        print(f"⚠ {len(errores)} símbolo(s) con error: "
              + ", ".join(f"{r['symbol']} ({r['error']})" for r in errores))


def run_daemon():
    """
    Corre en bucle revisando cada CHECK_INTERVAL_MINUTES.

    run_polling() es síncrono y gestiona su propio event loop: envolverlo en
    asyncio.run() da el error "This event loop is already running".
    """
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(CommandHandler("revisar", cmd_revisar))
    app.add_handler(CommandHandler("registro", cmd_registro))

    async def periodic_check(context: ContextTypes.DEFAULT_TYPE):
        await run_round(context.bot)

    if app.job_queue is None:
        print("❌ Falta el job queue. Instalá: pip install \"python-telegram-bot[job-queue]\"")
        sys.exit(1)

    app.job_queue.run_repeating(periodic_check, interval=CHECK_INTERVAL_MINUTES * 60, first=10)

    print(f"Bot corriendo — revisa cada {CHECK_INTERVAL_MINUTES} min. Ctrl+C para detener.")
    app.run_polling()


if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Faltan TELEGRAM_BOT_TOKEN y/o TELEGRAM_CHAT_ID en el archivo .env")
        sys.exit(1)

    if "--daemon" in sys.argv:
        run_daemon()
    elif "--radar" in sys.argv:
        asyncio.run(run_radar())
    elif "--informe" in sys.argv:
        asyncio.run(run_informe())
    else:
        asyncio.run(run_once())
