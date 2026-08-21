"""
Vantage — pruebas del candado
--------------------------------
Casos construidos a mano, de resultado conocido. Se ejecutan antes de fiarse
del candado en producción.

    python test_candado.py

No tocan el journal.json real: cada prueba trabaja sobre un archivo temporal.
"""

import io
import json
import os
import sys
import tempfile

import journal

_fallos = []
_pasadas = 0


def comprobar(condicion, titulo, detalle=""):
    global _pasadas
    if condicion:
        _pasadas += 1
        print(f"  ok   {titulo}")
    else:
        _fallos.append(titulo)
        print(f"  FALLO {titulo}" + (f"\n        {detalle}" if detalle else ""))


def sembrar(*señales):
    """Deja journal.json con las señales dadas y devuelve la ruta temporal."""
    fd, ruta = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with io.open(ruta, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "signals": list(señales)}, f)
    journal.JOURNAL_FILE = ruta
    return ruta


def viva(symbol, direction, origen, fecha="2026-08-20",
         entry=100.0, sl=95.0, tp=115.0, status="abierta"):
    return {
        "id": f"{symbol}-{fecha}", "symbol": symbol, "display_symbol": symbol,
        "name": symbol, "asset_class": "Acción", "origen": origen,
        "recorded_at": f"{fecha}T06:00:00+00:00", "signal_date": fecha,
        "direction": direction, "entry": entry, "take_profit": tp,
        "stop_loss": sl, "rr_ratio": 3.0, "rsi": 55.0, "activity_ratio": 2.0,
        "trend_strength": 1.0, "score": 60.0, "ai_veredicto": None,
        "ai_conviccion": None, "tenia_noticias": None,
        "status": status, "closed_at": None, "close_price": None,
        "r_multiple": None, "dias_abierta": None,
    }


def señal(symbol, direction, precio=100.0):
    """Un resultado del analyzer, tal como llega a record()."""
    return {
        "symbol": symbol, "display_symbol": symbol, "name": symbol,
        "asset_class": "Acción", "signal": "ENTRADA", "direction": direction,
        "price": precio, "entry": precio, "take_profit": precio * 1.15,
        "stop_loss": precio * 0.95, "rr_ratio": 3.0, "rsi": 55.0,
        "activity_ratio": 2.0, "trend_strength": 1.0,
    }


# --------------------------------------------------------------------------
print("\n=== permiso(): las seis situaciones posibles ===\n")

sembrar()
ok, _ = journal.permiso("NVDA", "buy", journal.SEGUIMIENTO)
comprobar(ok, "símbolo sin señal viva: se permite")

sembrar(viva("NVDA", "buy", journal.SEGUIMIENTO))
ok, motivo = journal.permiso("NVDA", "buy", journal.SEGUIMIENTO)
comprobar(not ok and "reentrada" in motivo,
          "misma dirección con una viva: se bloquea la reentrada", motivo)

sembrar(viva("NVDA", "buy", journal.RADAR))
ok, motivo = journal.permiso("NVDA", "sell", journal.SEGUIMIENTO)
comprobar(not ok and "prioridad" in motivo,
          "seguimiento contra una viva del radar: manda el radar", motivo)

sembrar(viva("NVDA", "buy", journal.RADAR))
ok, motivo = journal.permiso("NVDA", "sell", journal.RADAR)
comprobar(not ok, "radar contra su propia señal viva: se bloquea", motivo)

sembrar(viva("NVDA", "buy", journal.SEGUIMIENTO))
ok, motivo = journal.permiso("NVDA", "sell", journal.RADAR)
comprobar(ok and "releva" in motivo,
          "radar contra una viva del seguimiento: releva", motivo)

sembrar(viva("NVDA", "buy", journal.SEGUIMIENTO))
ok, motivo = journal.permiso("NVDA", "sell", journal.SEGUIMIENTO)
comprobar(not ok, "seguimiento contra su propia señal viva: se bloquea", motivo)

sembrar(viva("NVDA", "buy", journal.SEGUIMIENTO, status="stop"))
ok, _ = journal.permiso("NVDA", "buy", journal.SEGUIMIENTO)
comprobar(ok, "una señal ya cerrada no bloquea nada")

sembrar(viva("NVDA", "buy", journal.SEGUIMIENTO))
ok, _ = journal.permiso("AAPL", "buy", journal.SEGUIMIENTO)
comprobar(ok, "el candado es por símbolo, no global")


# --------------------------------------------------------------------------
print("\n=== record(): el registro aplica el mismo candado ===\n")

sembrar(viva("NVDA", "buy", journal.SEGUIMIENTO))
n = journal.record([señal("NVDA", "buy")], origen=journal.SEGUIMIENTO)
comprobar(n == 0, "no anota la reentrada bloqueada", f"anotó {n}")

sembrar(viva("BP.L", "buy", journal.RADAR))
n = journal.record([señal("BP.L", "sell")], origen=journal.SEGUIMIENTO)
comprobar(n == 0, "no anota la contraria a una viva del radar", f"anotó {n}")

sembrar()
n = journal.record([señal("NVDA", "buy"), señal("AAPL", "sell")])
comprobar(n == 2, "anota dos símbolos distintos", f"anotó {n}")

# Dos señales del mismo símbolo en la misma tanda: solo entra la primera.
sembrar()
n = journal.record([señal("NVDA", "buy"), señal("NVDA", "sell")])
comprobar(n == 1, "dentro de una misma ronda el candado ya cierra", f"anotó {n}")


# --------------------------------------------------------------------------
print("\n=== el relevo del radar ===\n")

sembrar(viva("NVDA", "buy", journal.SEGUIMIENTO, entry=100.0, sl=95.0))
n = journal.record([señal("NVDA", "sell", precio=104.0)], origen=journal.RADAR)
datos = json.load(io.open(journal.JOURNAL_FILE, encoding="utf-8"))
relevada = [s for s in datos["signals"] if s["status"] == "relevada"]
nueva = [s for s in datos["signals"] if s["status"] == "abierta"]

comprobar(n == 1, "el radar sí abre la contraria", f"anotó {n}")
comprobar(len(relevada) == 1, "la del seguimiento queda marcada 'relevada'")
comprobar(len(nueva) == 1 and nueva[0]["direction"] == "sell",
          "queda una sola señal viva, la del radar")
comprobar(relevada and relevada[0]["r_multiple"] is None,
          "la relevada NO lleva r_multiple: no se inventa el resultado")
comprobar(relevada and relevada[0].get("r_al_relevar") == 0.8,
          "pero sí guarda cómo iba: (104-100)/5 = +0,8 R",
          str(relevada[0].get("r_al_relevar") if relevada else None))

s = journal.stats()
comprobar(s["cerradas"] == 0,
          "la relevada no cuenta como cerrada en las métricas", str(s["cerradas"]))
comprobar(s["abiertas"] == 1, "y tampoco como abierta", str(s["abiertas"]))


# --------------------------------------------------------------------------
print("\n=== los dos casos reales que motivaron el candado ===\n")

# BP: el radar compró el 16, el seguimiento vendió el 17 y el 18. Las dos
# ventas murieron en el stop mientras la compra del radar ganaba.
sembrar(viva("BP.L", "buy", journal.RADAR, fecha="2026-08-16", entry=522.90,
             sl=495.58, tp=572.07))
bloqueadas = 0
for precio in (522.26, 532.50):
    ok, _ = journal.permiso("BP.L", "sell", journal.SEGUIMIENTO)
    bloqueadas += 0 if ok else 1
comprobar(bloqueadas == 2, "BP: el candado corta las dos ventas contra el radar")

# SAN: compra del radar a las 06:04, venta del seguimiento a las 09:53.
sembrar(viva("SAN.MC", "buy", journal.RADAR, fecha="2026-08-21", entry=12.30,
             sl=11.91, tp=13.12))
ok, _ = journal.permiso("SAN.MC", "sell", journal.SEGUIMIENTO)
comprobar(not ok, "SAN: el candado corta la venta de 3h49m después")

# RKLB: tres compras encadenadas, cada una a peor precio que la anterior.
sembrar(viva("RKLB", "buy", journal.SEGUIMIENTO, fecha="2026-08-17", entry=84.93))
cortadas = sum(0 if journal.permiso("RKLB", "buy", journal.SEGUIMIENTO)[0] else 1
               for _ in (78.37, 75.24))
comprobar(cortadas == 2, "RKLB: el candado corta las dos reentradas a peor precio")


# --------------------------------------------------------------------------
print(f"\n{'='*58}")
if _fallos:
    print(f"{_pasadas} pruebas pasadas, {len(_fallos)} FALLIDAS:")
    for f in _fallos:
        print(f"  · {f}")
    sys.exit(1)
print(f"{_pasadas}/{_pasadas} pruebas pasadas.")
