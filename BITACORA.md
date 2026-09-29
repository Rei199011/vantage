# Bitácora de cambios

Todo lo que se toca en la estrategia, con qué medición lo justifica y cómo
deshacerlo. Si un cambio no está aquí, no se hizo.

## Las reglas

**Los fallos se arreglan el mismo día.** Lotajes mal calculados, órdenes
rechazadas en silencio, EAs que no cargan, duplicados. Eso no es estrategia y
no necesita muestra.

**Los cambios de estrategia se miden antes en el motor**, sobre cientos de
operaciones, contra el listón al azar y con la prueba de las dos mitades. Si no
pasa las tres, no entra.

**Nunca se cambia nada porque las últimas operaciones fueran mal.** A ~14
operaciones al mes hacen falta entre 393 y 1.568 para distinguir una mejora
real del ruido — de dos a nueve años. Reaccionar a una racha es perseguir ruido,
no aprender.

**MetaQuotes es el laboratorio. FTMO no se toca.**

---

## 2026-09-29 · Punto de partida

Autorización de Reinaldo para aplicar cambios en MetaQuotes sin preguntar, con
informe todos los domingos. FTMO queda fuera del acuerdo.

### Cómo está montado

```
MetaQuotes-Demo (12.491 EUR)        laboratorio
  EURUSD EURJPY GBPJPY USDCAD  M15  OB 1_1       1:1, riesgo 500
  XAUUSD                       M5   OB_5min      1:2, riesgo 500

FTMO-Demo (50.000 USD)              desafío, fase 1 al 10%
  EURUSD EURJPY USDCAD         M15  OB 1_1       1:1, riesgo 750 (1,5%)
```

Comunes a las dos: `PermitirCompras=true`, `UsarParciales=false`,
`MargenMaxPct=40`, EMA200 de H1 no negociable, sesión Londres+NY.

### Lo que ya se sabe, para no volver a medirlo

**El lado comprador se queda.** Backtest de Reinaldo en FTMO, 2026, cinco
símbolos, 103 operaciones con compras contra 48 sin ellas: **+21,0% contra
+8,4%**. El acierto es casi igual (58,3% contra 56,2%, z=+0,23) pero las
compras doblan el número de operaciones. Con compras gana ocho meses de nueve;
sin ellas, cuatro. Mi recomendación previa de apagarlas era **errónea**: venía
de medir 2023-2026 en el motor sin comprobar que el lado comprador se comporta
distinto en el periodo reciente.

**El motor y MetaTrader ya coinciden.** Solo ventas: 57,3% en el motor contra
56,2% en el probador; 72 contra 64 operaciones al año. Esa discrepancia que
duró semanas está cerrada — la causaba que el motor solo vendía. Ver
[[motor-solo-vende]].

**No fiarse de `SYMBOL_TRADE_TICK_VALUE`.** En el oro de MetaQuotes dice 0,10
cuando vale 0,88. Todo cálculo de dinero por movimiento va con
`OrderCalcProfit` u `OrderCalcMargin`.

### Riesgo, medido sobre el backtest de 2026 (tres pares, FTMO)

```
riesgo          neto      peor dia  % lim diario   caida max  % lim total
1,0%  (500)  +21,0%         -1.001          40%      -2.268          45%
1,5%  (750)  +31,5%         -1.501          60%      -3.402          68%
2,0% (1000)  +42,0%         -2.001          80%      -4.536          91%
```

Al 2% quedarían 464 USD de colchón: menos de media operación. Se eligió
**1,5%**. Y ojo, esas caídas están medidas sobre operaciones CERRADAS; FTMO
mide la equidad con lo que flota incluido, así que la real será peor.

### Pendiente

- Por qué el motor emite muchas menos señales que la réplica del MQL5, incluso
  contando solo ventas. Sin diagnosticar.
- El espejo y los avisos siguen una sola cuenta (hoy MetaQuotes, fijado en
  `.env` con `MT5_TERMINAL`). FTMO no aparece en la app ni en Telegram.
