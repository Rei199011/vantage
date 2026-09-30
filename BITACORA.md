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

---

## 2026-09-29 · Fibonacci, la noche y la EMA

Reinaldo pide tres cosas: medir los retrocesos con Fibonacci para ver qué order
blocks se respetan, probar qué pasa **sin** la EMA, y buscar alternativas a
tener el bot apagado de noche. Todo medido sobre **2026**, cinco instrumentos,
sesión Londres+NY, sin costes. Sólo 2026 y a propósito: medir 2023-2026 es lo
que produjo la recomendación errónea de apagar las compras.

Los tres estudios están en `Desktop/motor/estudios/`:
`tres_frentes_2026.py`, `horas_2026.py`, `sin_ema_validar_2026.py`.

### Fibonacci: no hay señal. Cerrado.

Cada order block colocado dentro del retroceso del impulso que lo originó
(0 = donde acabó el impulso, 1 = el pivote de origen), sobre las 111
operaciones del año:

```
  0,000 - 0,500     15    60,0%
  0,500 - 0,618      4   100,0%     cuatro operaciones: ruido
  0,618 - 0,786     40    62,5%     la "zona dorada"
  0,786 - 0,950     45    57,8%
  0,950 o mas        7    71,4%
```

La zona dorada da 62,5% contra el 62,2% del conjunto: **tres décimas**. Partida
en dos mitades del año da 65% y 60%, que es lo que hace el ruido. **La
profundidad del retroceso no distingue nada.** No volver a medirlo.

### La noche: apagar es correcto. Cerrado.

Lo práctico primero, porque había que descartarlo: el ordenador **no se apaga**
(7 días de encendido seguidos, cero suspensiones, `STANDBYIDLE` a 0). Y si se
apagara tampoco habría huérfanos: la EA borra las pendientes al salir de sesión
(`OB 1_1.mq5:313`) y las posiciones llevan stop y objetivo en el bróker.

Lo que apagamos de noche es el **filtro de sesión**, y abrirlo sale peor:

```
                            ops   acierto   esperanza
  07-21 UTC (lo de ahora)   111    62,2%     +0,258
  24 horas                  153    59,5%     +0,221
  solo Londres (07-16)       83    63,9%     +0,281
  solo NY (13-21)            62    64,5%     +0,311
```

Con el horario abierto, por tramos de hora UTC de entrada:

```
  21-00  cierre NY / Sidney     12    50,0%
  00-03  Tokio abriendo         17    47,1%    esperanza -0,06
  03-07  Tokio tarde            21    52,4%
  07-13  Londres                47    63,8%
  13-17  solape Londres-NY      38    65,8%    el mejor tramo del dia
  17-21  NY tarde               18    61,1%
  ---
  TODA LA NOCHE (21-07)         50    50,0%
```

Cincuenta operaciones nocturnas con **50,0% clavado**, que a 1:1 es cero. Aguanta
partido en dos mitades (52% y 48%) y no lo salva ningún instrumento; los yenes
son los peores (EURJPY 30% en 10, GBPJPY 46,7% en 15). El USDCAD al 75% son ocho
operaciones.

Y cuesta por los dos lados: dentro de la tanda de 24 horas el tramo diurno da
**103** operaciones, mientras que el motor limitado a 07-21 da **111**. De
madrugada el precio **consume order blocks** que se habrían operado por la
mañana.

Recortarse al solape 13-17 subiría el filo por operación pero dejaría 38
operaciones al año. No se recomienda.

### La EMA: pasa las tres pruebas. Es la mejora más grande que ha aparecido.

Sin EMA la dirección deja de decidirla la media: se buscan los dos lados y gana
el order block cuyo borde de entrada esté más cerca del precio.

```
                ops   acierto   esperanza    total
  con EMA       111    62,2%      +0,258     +28,6 R
  SIN EMA       180    61,7%      +0,248     +44,7 R
```

Medio punto menos de acierto y **un 62% más de operaciones**.

**1. Las dos mitades del año.** Con EMA 65,5% y 58,9%. Sin EMA 64,4% y 58,9%.
Las cuatro positivas, y la degradación es **idéntica** en las dos
configuraciones: es cosa del año, no de quitar la media.

**2. El listón al azar**, 8 pasadas con la dirección sorteada. Esto es lo que
zanja el asunto:

```
                ops   acierto   liston          ventaja
  con EMA       111    62,2%    50,3% +-1,6    +11,9 puntos    z = 2,51
  SIN EMA       180    61,7%    49,7% +-1,4    +12,0 puntos    z = 3,22
```

Las 69 operaciones de más **no vienen diluidas**: traen el mismo filo. Con más
muestra el resultado es *más* sólido, no menos. Esto es exactamente lo que
falló con las compras, y aquí no falla.

**3. Instrumento por instrumento.** Mejora el total en cuatro de cinco:

```
            con EMA              SIN EMA
  EURUSD    54,3%   +3,0 R       55,1%   +5,0 R
  GBPJPY    54,5%   +2,0 R       60,6%   +7,0 R
  EURJPY    64,3%   +4,0 R       52,0%   +1,0 R      el unico que baja
  USDCAD    80,0%  +12,0 R       74,4%  +19,3 R
  XAUUSD    65,0%   +7,6 R       64,7%  +12,4 R
```

EURJPY es el que menos muestra tenía con EMA: 14 operaciones. Su 64,3% nunca fue
un dato del que fiarse.

**Lectura.** La EMA no estaba equivocada, estaba **de más**. Los order blocks
tienen filo por sí mismos; la media partía la muestra en dos sin separar buenas
de malas. Coincide con lo que dice Reinaldo: la usaba para leer la tendencia y
no es una regla.

### Lo que se ha hecho con esto, y lo que NO

Se ha creado `OB_sin_EMA.mq5` (Vantage_OB_V1.6, magic **20260930**) en
MetaQuotes. Es la V1.5 letra por letra más un `input bool UsarEMA`. Compila con
0 errores y 0 avisos. Diff verificado: sólo cambian las cuatro cosas queridas
(version, dos `#property description`, el input nuevo, el magic y el bloque de
decisión de dirección).

**`OB 1_1.mq5` NO se ha tocado.** Sigue corriendo con lo suyo, y en FTMO no se
ha movido nada.

Con `UsarEMA=true` la V1.6 debe dar **exactamente** lo mismo que la V1.5 en el
probador. Ese es el control: si los dos backtests no coinciden, algo se rompió
al copiar y no vale nada de lo de arriba.

**Pendiente antes de mover producción:** pasar los cinco pares por el probador
de MT5 y comparar contra el backtest de la V1.5 del mismo periodo. Esto sale
del motor, y con las compras el motor decía una cosa y el probador la
contraria. Por eso es un fichero nuevo y no un cambio.

### El probador contesta: EURUSD sin EMA, 2026

Reinaldo lanzó `OB_sin_EMA` con `UsarEMA=false` en EURUSD, M15, del 01/01/2026
al 29/09/2026, depósito 15.000 €, riesgo 500. El informe está en
`Downloads/No EMA.html`. Los scripts que lo desmenuzan quedaron en el
scratchpad de la sesión; si se necesitan otra vez, rehacerlos es media hora.

**Las señales del motor eran correctas.** El probador da 48 posiciones y 56,25%
de acierto; el motor predijo 49 operaciones y 55,1%. Y el 1:1 ejecuta limpio:
las ganadoras pagan +1,025 R, las perdedoras cuestan −1,009 R, razón de pago
1,016. La horquilla no se come nada apreciable. Esperanza real +0,135 R por
operación, **mejor** que los +0,103 R que predijo el motor.

**Pero el dinero no apareció.** 48 operaciones a +0,135 R con 500 € de riesgo
son +3.243 € (+21,6%). El informe da **+1.155,68 € (+7,7%)**, con 11,23% de
caída de balance y 13,73% de equidad. Faltan 2.088 €.

**Se fueron en el lotaje, y el culpable es `MargenMaxPct=40`:**

```
  stop      lotes   riesgo real   pedido
   5,2 pips  2,60      116 EUR    500
   6,9 pips  2,71      160 EUR    500
   7,7 pips  3,20      216 EUR    500
  24,7 pips  2,31      499 EUR    500   correcto
  70,2 pips  0,83      501 EUR    500   correcto
```

500 € de riesgo en un stop de 5 pips son 11 lotes, y una cuenta de 15.000 € al
1:100 no los aguanta. El techo los clava en 2,6-3,2 y el riesgo cae hasta 116 €.
Con stops anchos el lotaje sale bien.

**Y el reparto queda exactamente al revés del filo:**

```
                    ops   acierto   riesgo medio    dinero
  stop < 12 pips     27    66,7%       234 EUR     +2.632
  stop >= 12 pips    21    42,9%       488 EUR     -1.463
```

Pone 234 € donde acierta dos de cada tres y 488 € donde falla más de la mitad.
El filo existe y el dimensionamiento lo devuelve.

**Esto es un fallo, no estrategia**, así que entra por la vía rápida. Pero no se
arregla subiendo `MargenMaxPct`: eso reintroduce los rechazos por "no money"
(ver [[ea-lotaje-supera-el-margen]]). El problema de fondo es que una cuenta de
15.000 € no puede arriesgar 500 € (3,3%) en un stop de 5 pips.

### Lo que falla en el motor, dicho con precisión

El motor dimensiona **toda** operación a 1R exacto y no sabe que la cuenta tiene
un techo de margen. Por eso sus totales en R son correctos como medida del filo
pero **inalcanzables como dinero** en una cuenta pequeña. No es un error de
lectura de la estrategia: es que mide el filo y no la cuenta.

### Pendiente, en orden, para mañana

1. **Meter el techo de margen en el motor**, con el tamaño de cuenta como
   parámetro, para que los totales en R sean los que la cuenta puede coger.
2. **Medir el corte del stop estrecho** sobre los cinco instrumentos, con las
   dos mitades y el listón. El 66,7% contra 42,9% da z = 1,65 sobre un solo par
   y un solo año, y encima se encontró mirando: no llega para creerlo.
3. **Calcular el riesgo que de verdad cabe** en MetaQuotes (12.491 €) sin que el
   techo recorte, y en FTMO (50.000 $, donde el techo casi no debería morder).
4. **Falta el control:** EURUSD con `UsarEMA=true`, mismo periodo. Sin él no se
   puede decir si el sin-EMA ayudó o estorbó en este par.

Y un dato que conviene no olvidar: en la medición del motor EURUSD era **el par
más flojo de los cinco** (54,3% y +3,0 R con EMA, contra el 80% y +12,0 R de
USDCAD). Que rinda poco es coherente con lo medido, no una sorpresa.

---

## 2026-09-30 · La EMA, contrastada en el probador

Reinaldo lanzó cinco backtests en el probador de MT5 (M15, 01/01–29/09/2026,
15.000 €, riesgo 500, margen 40 %). Todos con objetivo 1R efectivo. Los informes
están en `Downloads/`.

### El motor predice, no ajusta

Las predicciones se hicieron **antes** de cada pasada y quedaron escritas en el
chat:

```
  caso                ops pred   ops real   acierto pred   acierto real
  EURUSD con EMA         35         35          54,3%          60,00%
  EURUSD sin EMA         49         48          55,1%          56,25%
  USDCAD con EMA         20         18          80,0%          77,78%
  USDCAD sin EMA         39         38          74,4%          73,68%
  XAUUSD sin EMA         34         35          64,7%          60,00%
```

Error medio: **0,8 operaciones** en el recuento, **2,9 puntos** en el acierto, y
sin sesgo (la media de los errores es −0,1). El motor queda contrastado en cinco
casos independientes. Ver [[motor-backtest-verificado]].

### El sin-EMA gana, en los dos pares medidos de las dos formas

EURUSD + USDCAD sobre la misma cuenta, mes a mes:

```
  mes          sin EMA    con EMA
  enero            +16      +971
  febrero       +1.216      +475
  marzo         +1.419    +1.195
  abril         +1.169      +367
  mayo            +787      +542
  junio           +360      +343
  julio         +1.508      +427
  agosto          +228       +86
  septiembre    +1.125      +410
  TOTAL         +7.830    +4.815
  media/mes       +870      +535
  meses verdes    9 de 9    9 de 9
  operaciones   86 (64%)  53 (66%)
```

**+335 € al mes más, y sin perder ningún mes.** El sin-EMA gana en siete de los
nueve meses. Y el reparto importa: en **EURUSD gana el con-EMA** (+1.988 contra
+1.169), en **USDCAD gana el sin-EMA por goleada** (+6.661 contra +2.828). No es
que la EMA estorbe siempre; es que doblar el número de operaciones compensa
donde el par tiene filo, y no compensa donde el par es flojo.

### El oro es lo que da la irregularidad, no la EMA

Añadiendo XAUUSD sin EMA la media sube a 1.388 €/mes, pero aparecen los dos
únicos meses rojos del año: junio −133 y agosto −270. El oro perdió −493, −960 y
−498 en junio, julio y agosto, y llevó la caída de equidad al 15,67 %.

Sin oro no hay ningún mes en pérdidas.

### Las caídas: el sin-EMA cae más hondo

```
  par              caida balance   caida equidad
  EURUSD con EMA        7,27%          9,77%
  EURUSD sin EMA       11,23%         13,73%
  USDCAD con EMA        1,41%          3,18%
  USDCAD sin EMA        2,99%          5,23%
  XAUUSD sin EMA       14,20%         15,67%
```

Más operaciones es más exposición. Y estas caídas salieron **con el riesgo
recortado al 42-56 %** por el techo de margen: con el riesgo completo serían
aproximadamente el doble.

### El margen del probador no es el de la consulta en vivo

Dato caro de encontrar, sacado de los logs del probador
(`Tester/.../Agent-127.0.0.1-3000/logs/`), donde la EA escribe una línea por
recorte:

```
  simbolo   recortes    min   mediana    max      en vivo   factor
  EURUSD      10.191   1.382    2.115   2.437      1.000     2,115
  USDCAD       5.033   1.331    1.850   2.105        882     2,098
```

**El probador aplica 2,1 veces el margen que devuelve `order_calc_margin`.** El
factor es el mismo en los dos pares, así que es calibrable. Sin esta corrección
cualquier simulación de euros da lotes el doble de grandes que los que el
probador dejó pasar.

XAUUSD **no aparece**: nunca tocó el techo, porque sus stops son anchos en
porcentaje y el lotaje sale pequeño. Coherente con que sus ganadoras salieran a
508 € del riesgo completo de 500.

### Preset del probador: arreglado

`MQL5/Profiles/Tester/OB 1_1.set` traía `ObjetivoVecesR=3.0` y
`UsarParciales=true`, de cuando la EA usaba parcial más corredor. Puesto en 1.0
y false; copia en `OB 1_1.set.antes-de-1a1`.

Aviso para la próxima: **editar el .set con el terminal abierto no sirve.** MT5
guarda los parámetros en memoria y los reescribe al lanzar. Hay que cambiarlos
en el diálogo.

### Un error propio, y cómo se cazó

Rechacé el primer EURUSD con EMA por llevar `ObjetivoVecesR=3.0` y
`UsarParciales=true`, y le hice repetir la pasada. **Era válida.** El informe
traía `PesoTP1=1`, y en `OB 1_1.mq5:830` está escrito que con `PesoTP1 >= 1.0` se
cierra la posición ENTERA en TP1: el corredor a 3R no lleva volumen. Lo
confirmaba el propio informe, cuya mayor ganadora era 514 € ≈ 1R y no 1.500.

Lección: antes de invalidar un informe, comprobar los parámetros **contra el
código**, no contra lo que parecen decir.

### Cerrado hoy, para no volver a medirlo

**El stop estrecho no vale.** El corte que salió en EURUSD (66,7 % con stop bajo
12 pips contra 42,9 % por encima) **no se replica** en los otros cuatro pares.
Medido en porcentaje del precio, que es lo comparable entre instrumentos, el
tramo más estrecho es el **peor** de los cinco en las dos configuraciones (53,8 %
con EMA, 51,3 % sin EMA). Ningún tramo llega a Bonferroni (z = 1,71 y 1,70 sobre
2,81 exigido), y el mejor tramo cambia según la configuración, que es la firma
del ruido. El motor **sí** reproduce el corte en EURUSD (63,0 % contra 45,5 %):
era una particularidad de ese par y ese año.
