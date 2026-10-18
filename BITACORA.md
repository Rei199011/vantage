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

---

## 2026-10-07 · Dos fallos del motor, el suelo del stop y US30

Día largo. Se arreglan dos fallos del motor —uno de ellos llevaba contaminando
todo lo medido— y con el motor bueno se rehacen las dos conclusiones que
dependían solo de él.

### El fallo de la migaja, que explicaba el 8 % que llevaba una semana buscando

Para simular el 1:1 se venía usando `peso_tp1=0.999` con `objetivo=3R`: cierra el
99,9 % en 1R y **deja un 0,1 % corriendo hasta 3R**. Esa migaja mantiene la
posición abierta, y mientras hay posición abierta el motor **no toma ninguna
entrada nueva**.

Lo destapó US30:

```
duración mediana de una operación:    1,2 horas
duración máxima:                    447,0 horas    <-- 18 días y medio
```

Dieciocho días con una operación de stop a 50 puntos en un índice que se mueve
300 al día. Imposible, salvo que lo que siguiera abierto fuese una migaja
buscando un objetivo que casi nunca llegaba.

De las 15 entradas que el probador tomaba y el motor no en US30 2026, **nueve
eran exactamente eso**: el motor estaba «ocupado» con un resto de semanas atrás.

Antes había probado tres hipótesis y las había descartado midiéndolas: la altura
del order block (coincide, el máximo del año cuadra al centésimo de pip), el tipo
de orden, y el suelo del stop. Ninguna era. **Nunca miré las duraciones**, que es
donde estaba a la vista.

Arreglo: `sin_parciales=True` en `ObDosLados`, que emite el objetivo en 1R y
ningún parcial. El motor rechaza `objetivo_veces_riesgo=1.0` cuando hay
parciales —y con razón, un parcial que cae en el objetivo no es un parcial—, así
que la salida no era forzar ese número sino no emitir parcial ninguno.

**Resultado, contra los seis backtests de Reinaldo:**

```
  par       con migaja   sin migaja   probador
  XAUUSD        34           35          35
  USDCAD        34           39          38
  GBPJPY        31           38          37
  EURUSD        48           50          48
  EURJPY        14           17          15
  US30M         51           61          65
  TOTAL        212          240         238      -15,2%  ->  +0,8%
```

Y desaparecen las duraciones imposibles: el oro de 618 horas a 100, GBPJPY de
412 a 108.

### El segundo fallo: el listón salía vacío sin avisar

Al estrenar el modo sin parciales, el listón al azar dejó de producir señales: su
comprobación de geometría exigía `tp2 < tp1`, y sin parciales **el objetivo ES el
1:1**, así que los dos caen en el mismo precio. Descartaba todo.

Y lo hacía **en silencio**: la sección del informe aparecía sin una sola línea,
sin error. Si no llego a mirarla, el suelo del stop se habría dado por validado
con dos pruebas de tres.

### El suelo del stop: confirmado en 0,06 %, y con mejor argumento

Rehecho el barrido con el motor bueno:

```
  suelo   ops  acierto  R total   neto (desliz. 1,1 pips)
  0,04%   179   63,1%    +49,1        +27.113
  0,06%   148   66,2%    +50,0        +31.277
  0,08%   119   68,9%    +47,0        +31.751
  0,10%    98   68,4%    +38,0        +26.013
  0,12%    79   67,1%    +29,0        +20.135
  0,15%    59   66,1%    +20,2        +14.213
```

Dos cosas cambian respecto a la medición rota, las dos a favor del 0,06:

**El R total ahora tiene un máximo claro en 0,06 %.** Con la migaja salía plano
entre 0,04 y 0,08 y no distinguía. Ahora +49,1 → **+50,0** → +47,0: pasado el
0,06 ya se tira filo, no solo operaciones caras.

**Y en dinero 0,06 y 0,08 quedan empatados** (+31.277 contra +31.751, un 1,5 %
que es ruido). Antes el 0,08 ganaba por un 5 %.

Las tres pruebas, con el motor bueno:

```
  1. dos mitades   0,06%:  64,9% y 67,6%     estable
  2. listón        0,06%:  66,2% contra 50,7%  ventaja +15,6 pt  z=3,95
  3. por par       mejora o empata en cuatro de cinco; solo USDCAD prefiere 0,04
```

**Lo aplicado el 06/10 en MetaQuotes era correcto y no se toca.**

### US30M: el arreglo no lo rescata

Reinaldo lo puso a operar con su backtest de 2026 (65 ops, 55,4 %, +26,5 %) y
objetó, con razón, que el motor ya había fallado antes con años anteriores —fue
lo que pasó con las compras—. Arreglado el motor, los años anteriores dicen lo
mismo:

```
  año    ops  acierto  total R
  2022    59   52,5%     +4,2
  2023    74   41,9%    -11,0
  2024    71   35,2%    -20,2
  2025    78   38,5%    -22,0
  2026    61   50,8%     +5,4
  TODO   344   43,3%    -42,6

  listón 47,2%  ->  la estrategia va 3,8 puntos POR DEBAJO del azar
```

Y ahora el motor sí cuadra con el probador en 2026: **61 operaciones contra 65**,
donde antes eran 51. Así que ya no vale escudarse en que el motor no sabe medir
índices.

**Decisión de Reinaldo: se queda, con revisión escrita por adelantado.**

```
US30M entra el 07/10/2026 con el backtest de 2026.
Se revisa a las 30 operaciones en vivo:
    acierto < 45%   se quita
    acierto > 55%   se queda y deja de discutirse
    entre medias    se espera a 50 operaciones
```

Fijar el criterio antes es lo que impide que luego cada uno lea los números a su
favor. Lo que sí queda cerrado: **US30 no va a FTMO**. Su caída de equidad en el
backtest de 2026 es del 15,86 % sobre un límite del 10 %.

### Lo que esto obliga a recordar

Todo lo medido **solo con el motor** antes del 07/10 llevaba la migaja dentro. Lo
validado contra el probador de Reinaldo se sostiene, porque el recuento estaba
bajo en todas las configuraciones por igual y la comparación entre ellas no se
altera: **la decisión de la EMA sigue en pie**.

Y la lección que conviene no olvidar: tres hipótesis medidas y descartadas
correctamente, y la causa estaba en una columna que nunca miré. Cuando los
números no cuadran, mirar también lo que no se está midiendo.

---

## 2026-10-13 · Informe semanal (semana del 05 al 12/10)

### Arreglado en MetaQuotes

**1. El suelo del stop había vuelto a 0,04 % sin avisar.** Reinaldo lo puso a
0,06 % a mano el 08/10 a las 00:02, pero el terminal se reinició a las 09:38 sin
cerrar limpio y MT5 solo guarda los parámetros de los gráficos al cerrar bien.
Volvió a arrancar con 0,04 % en los seis gráficos y así ha operado cinco días.
Lo prueba la línea `PARAMETROS:` de cada EA en `MQL5/Logs/20261008.log`
(00:02 dice 0.06 %, 09:39 dice 0.04 %).

- Hecho: cierre limpio del terminal, `RiesgoMinPctPrecio=0.04 -> 0.06` en los
  seis `Profiles/Charts/Default/chart0*.chr`, relanzado. A las 09:38:53 del
  13/10 las seis EAs escriben `suelo=0.06%`. Sin órdenes duplicadas.
- Justificación: la medición del 07/10 (148 ops, 66,2 %, +15,6 pt sobre el
  listón, z=3,95). No es un cambio nuevo; es restaurar lo decidido.
- Deshacer: copia de los perfiles en
  `Profiles/Charts/Default.antes-suelo006-20261013/`; cerrar el terminal limpio,
  copiarla encima de `Default/` y relanzar.

**2. Las EAs se descolgaban al arrancar si la ficha del símbolo llegaba vacía.**
El 05/10 a las 09:20, tras un reinicio, cuatro gráficos (EURUSD, GBPJPY, EURJPY,
USDCAD) dieron `Ficha del instrumento incompleta: valor=0.0` → `INIT_FAILED` →
EA quitada del gráfico. Estuvieron **cuatro horas** sin EA hasta que alguien las
recargó a las 13:25.

- Hecho: en `OnInit` de `OB_sin_EMA.mq5` y `OB 1_1.mq5`, si `tick` o
  `valor_tick` salen a 0, reintenta cada 0,5 s hasta 15 s antes de rendirse.
  No toca nada de la lógica de trading. Compilados con 0 errores y 0 avisos.
- Deshacer: copias `*.mq5.antes-espera-ficha` y `*.ex5.antes-espera-ficha` en
  `MQL5/Experts/`.

### Visto y no arreglado

- **US30M no puede operar en esta cuenta.** `symbol_info("US30M").trade_mode`
  es 0 (deshabilitado), igual que `US30`. 237 órdenes rechazadas con
  `[Trade disabled]` entre el 05 y el 12/10, ninguna aceptada. La regla de
  revisión del 07/10 (a las 30 operaciones) no puede cumplirse aquí nunca.
  La EA se deja en el gráfico: no hace daño.
- Los lunes a las 09:00 algunas órdenes salen con `[no connection]` y entran al
  cuarto de hora siguiente. Normal del arranque de semana; no se toca.

### FTMO: perdida el 08/10 (solo informe)

La cuenta es **"$50k FTMO Free Trial 1-Step"**. El 08/10 cerró dos stops
seguidos al 1,5 % (USDCAD −817,14 y EURUSD −736,84 con comisión) y FTMO cerró la
segunda él mismo (`CLOSED_BY_FTMO`). Desde las 17:26 el servidor tiene el
trading deshabilitado y la EA acumula `[Trade disabled]` cada 15 minutos.

Los números cuadran con un **límite diario del 3 %**, no del 5 %: saldo a
medianoche 50.127,64, suelo al 3 % = 48.627,64, saldo tras el cierre 48.511,41.
**La tabla de riesgo del 29/09 se hizo contra el 5 %**; contra el 3 %, dos
pérdidas al 1,5 % más comisión ya lo rompen. El 3 % está deducido de las cifras:
confirmarlo en las reglas del 1-Step.

Otro dato: con stops de 4-5 pips la comisión (~5 USD/lote) y el deslizamiento
del stop pesan. El EURUSD del 06/10 perdió −1,32 R: 0,11 R de comisión y 1,1
pips de deslizamiento sobre un stop de 4,5. Las EAs de FTMO siguen con suelo
0,04 % y sin el arreglo del arranque.

### Resultados de la semana (R con el riesgo real de cada posición)

```
MetaQuotes (riesgo 150)          FTMO (riesgo 750)
05/10 GBPJPY compra  +1,00 R     06/10 EURUSD venta   -1,32 R
05/10 GBPJPY compra  -1,00 R     06/10 EURJPY venta   +0,93 R
08/10 XAUUSD compra  +1,00 R     08/10 USDCAD compra  -1,10 R
08/10 USDCAD compra  -1,00 R     08/10 EURUSD venta   -1,02 R  CLOSED_BY_FTMO
08/10 GBPJPY compra  -1,00 R
12/10 GBPJPY compra  +1,00 R
-----                            -----
6 ops, 3 ganadas, -0,01 R        4 ops, 1 ganada, -2,51 R
-10,15 EUR                       -1.997,27 USD
```

Sin parciales en ninguna: cada posición tiene una sola salida. Abierta a cierre:
USDCAD compra 2,29 lotes en MetaQuotes. Diez operaciones no dicen nada de la
estrategia, y no se cambia nada por ellas.

### La idea medida: order block con FVG. NO entra.

La condición que más repite la literatura ICT/SMC: un OB «de verdad» deja un
hueco de valor (fair value gap) en el desplazamiento que sale de él. Estudio en
`motor/estudios/fvg_ob.py` + `fvg_ob_juntar.py`, volcados en
`motor/salidas/fvg/`. Configuración de producción (sin EMA salvo EURJPY, suelo
0,06 %, 1R entero, Londres+NY, sin costes), **2023-03 a 2026-09**, cinco pares,
listón con 4 semillas.

Primer hallazgo: con el hueco buscado en las 5 velas siguientes, **39 de 41 OBs
lo tienen** — el quiebre de estructura que ya exige la regla casi siempre lo
abre. Así que se mide la definición estricta: el hueco lo abre la vela
inmediatamente siguiente al OB.

```
                     ops   acierto   esperanza    total    vs liston
  todos (ahora)      894    56,0%     +0,150    +134,3 R   +6,4 pt  z=3,81
  CON fvg            572    55,8%     +0,158     +90,4 R   +6,6 pt  z=3,17
  SIN fvg            338    55,3%     +0,112     +37,9 R   +5,8 pt  z=2,14
```

- **Mitades:** CON 50,5 % / 61,1 %; SIN 50,6 % / 59,9 %. Igual de mal y de bien.
- **Listón:** +6,6 pt contra +5,8 pt. Ocho décimas: ruido.
- **Por par:** el CON gana en GBPJPY, EURJPY y XAUUSD por menos de 3 puntos, y
  pierde en EURUSD y USDCAD.

**El hueco no distingue nada.** Filtrar por él tiraría el 36 % de las
operaciones y bajaría el total de +134 a +90 R por la misma ventaja. Descartado;
no volver a medirlo.

### Dato que conviene no perder

Sobre 3,6 años y 894 operaciones, la configuración actual tiene ventaja real
sobre el azar (**+6,4 pt, z=3,81**), pero está **muy concentrada en el periodo
reciente**: +0,049 R hasta octubre de 2024 (IC cruzando el cero) contra +0,252 R
desde entonces. No cambia nada hoy, pero es la razón para no extrapolar el
backtest de 2026 a los años que vengan.

---

## 2026-10-13 (noche) · La compra de USDCAD: quiebre pequeño y OB = pivote. Ninguna entra.

Reinaldo cuestionó la compra de USDCAD del 13/10 (límite 1,42608, stop
1,42504, −1 R). Reconstruida con las velas M15:

- **El quiebre no fue solo de mechas.** El máximo previo de 60 velas era 1,42675
  (12/10 14:15). La vela de las 17:45 cerró en 1,42729: +5,4 pips con cuerpo; la
  mecha llegó a +9,0. Exigir cierre no habría quitado esta entrada.
- **Sí era un quiebre pequeño** tras un rango de 9 pips (1,42586-1,42675), y el
  OB era la propia vela del mínimo (16:30, una mecha de barrido).

Se midieron las dos dudas. Estudio en `motor/estudios/quiebre_y_pivote.py`,
volcados en `motor/salidas/qp/`, juntados con `fvg_ob_juntar.py`.
Configuración de producción, 2023-03 a 2026-09, cinco pares, listón con 4
semillas. Ojo: el filtro descarta el OB en vez de buscar uno más antiguo, como
haría la EA si se programara.

**Diagnóstico previo, caro de encontrar:** el **95 %** de los order blocks que
detecta la regla son la propia vela del pivote (EURUSD 95,0 %, USDCAD 95,9 %).
No es una rareza de esta entrada: es lo normal. Y el quiebre mediano, medido al
emitir la señal, son ~7 ATR(14); el decil más bajo, ~1,4 ATR.

### Idea 1: quiebre mínimo en ATR. NO entra.

```
                         ops  acierto  esperanza   total   1a mitad  2a mitad  vs liston
  todos (ahora)          894   56,0%    +0,150   +134,3 R   51,0%     61,1%   +6,4 pt z=3,81
  quiebre >= 1,5 ATR     586   55,8%    +0,143    +83,9 R   49,2%     63,3%   +7,5 pt z=3,64
  quiebre >= 3 ATR       378   56,1%    +0,164    +62,1 R   49,2%     63,5%   +7,4 pt z=2,88
  quiebre >= 6 ATR       161   58,4%    +0,210    +33,8 R   49,4%     67,5%   +8,7 pt z=2,20
  SOLO quiebre < 1,5     325   56,3%    +0,158    +51,4 R   54,5%     57,8%   +7,4 pt z=2,67
```

Los quiebres pequeños rinden **igual** que el resto (56,3 % y +7,4 pt sobre el
azar), y en la primera mitad son incluso los mejores. El 58,4 % de ≥6 ATR viene
entero de la segunda mitad (49,4 % en la primera) y se hunde en el oro (46,3 %).
Filtrar solo quita operaciones: el total cae de +134 a +84 R con el umbral más
suave.

### Idea 2: descartar OB = pivote. NO entra, y el dato apunta al revés.

```
                         ops  acierto  esperanza   total   vs liston
  OB distinto del pivote  25   32,0%    -0,360     -9,0 R  -12,0 pt z=-1,20
  SOLO OB = pivote       874   56,8%    +0,165   +144,3 R   +7,2 pt z=4,23
```

Quitar los OB = pivote dejaría 25 operaciones en 3,6 años, y esas van **peor**
(32 %). Lo contrario —quedarse solo con OB = pivote— mejora las tres pruebas
sobre el papel (+144 contra +134 R, las dos mitades, los cinco pares), pero
toda la diferencia sale de **25 operaciones con z = −1,2**. Muy por debajo de las
393 que hacen falta. No se aplica; se anota por si con más historia se sostiene.

**No cambia nada en MetaQuotes.** La entrada del 13/10 era una operación normal
de la regla, no un caso raro.

---

## 2026-10-18 · Walk-forward, Monte Carlo y la EMA, medida limpia

Reinaldo propuso comprar StrategyQuant X para mejorar. Se descartó por ahora y
se construyó en el motor lo único de esa herramienta que de verdad nos faltaba.
El porqué está más abajo. Las tres mediciones quedan en `estudios/`:
`walk_forward.py`, `monte_carlo.py` y `ema_limpio.py`.

### Por qué no StrategyQuant, de momento

La edición mínima con walk-forward y Monte Carlo es la **Professional, 1.490 $**
(la Starter no trae el Optimizer). Pero el problema no es el precio:

**No puede leer nuestra estrategia.** Su propia documentación dice que *no se
puede coger el código MQL y copiarlo y pegarlo*; los bloques propios se escriben
como snippets en Java. Para que tocara el order block habría que reescribir la
regla entera **por tercera vez**, después del MQL5 y el motor. Acabamos de pasar
dos semanas cazando diferencias entre **dos** implementaciones.

**Y para lo que está diseñado es justo lo que nos ha mordido.** Genera miles de
estrategias y se queda con las mejores: la versión industrial del error de las
compras, del stop estrecho y del 0,08 %. Tiene sentido comprarlo el día que se
quiera abrir el frente de **buscar estrategias nuevas**, que es otro proyecto.

### Walk-forward: el 0,06 % confirmado sobre cuatro años

Doce tramos de cuatro meses, de 2023-01 a 2026-09:

```
  fijo 0,04%                          +125,2 R
  fijo 0,06%                          +132,3 R   <- el mejor
  fijo 0,08%                          +113,4 R
  fijo 0,10%                           +94,0 R
  elegir segun el tramo anterior      +121,9 R
  el mejor de cada tramo (IMPOSIBLE)  +153,3 R
```

**El 0,06 % no era cosa de 2026**: es el mejor valor fijo sobre casi cuatro años
y fue el mejor en 6 de los 12 tramos. La decisión del 06/10 se tomó con nueve
meses y aguanta con cuarenta y cinco.

**Y reoptimizar no sirve.** Elegir cada tramo el ganador del anterior da +121,9 R,
diez por debajo de dejarlo quieto. Nada de retocar el suelo cada trimestre.

Un aviso que se ve en la tabla: los tramos de 2023 dan +1,5, +1,6 y +4,1 R
mientras los de 2025-2026 dan +23, +11, +21, +18, +19. **El filo es mucho mayor
en los dos últimos años.** Los números recientes son más optimistas que la media
histórica.

### Monte Carlo: robusto por las cuatro vías

Sobre las 148 operaciones de 2026, 5.000 repeticiones:

```
  otro orden      caida mediana -5,0 R   p5 -8,0   la real (-4,0) fue percentil 62
  bootstrap       total mediano +50,3 R  p5 +30,8  anos en perdidas: 0,0%
  perder entradas al 25% todavia da +37,5 R; al 50%, +25,0 R
  peaje           el filo se agota en 0,32 R por operacion (49 EUR a 150 de riesgo)
```

Los dos números útiles en la práctica: **la caída que hay que estar dispuesto a
aguantar es -8 R (1.200 EUR)**, no los -4 que tocaron; y hay **seis veces de
margen** sobre la comisión de FTMO (0,054 R) antes de que el coste se lo coma.

El Monte Carlo prueba robustez, **no existencia**: remuestrea un año bueno. Lo
que descarta el sobreajuste es el listón, y el walk-forward avisa de que 2023 era
bastante más flojo.

### La EMA sí separa, medida limpiamente

Para cada operación del sin-EMA se mira si el precio estaba del lado correcto de
la EMA200 de H1 **en su propia vela de entrada** — la condición exacta de la EA
con EMA. (Comprobación: de las 92 operaciones con-EMA, 0 sin acuerdo.)

```
  la EMA de acuerdo   105 ops   69,5%   +41,7 R   z=+4,00   vs azar +18,4 pt
  la EMA en contra     54 ops   55,6%    +7,3 R   z=+0,82   vs azar  +4,4 pt
  todas               159 ops   64,8%   +49,0 R   z=+3,73   vs azar +13,6 pt
```

Son **13,9 puntos**, no los 21,5 que daba el criterio de solape del 16/10: aquel
apaño inflaba el efecto. Pero pasa las tres pruebas: las dos mitades (65,4 y 73,6
contra 55,6 y 55,6), **los cinco instrumentos en la misma dirección**, y el
listón.

Las 54 operaciones «en contra» aportan +7,3 R con z = 0,82: indistinguibles de
una moneda, pero pagan comisión, ocupan margen y bloquean entradas.

### Las tres configuraciones, con la caída medida por Monte Carlo

```
  opcion                          ops  acierto   total   caida p5   total EUR/ano
  A. solo con EMA                  92   67,4%   +33,3 R      --
  B. sin EMA, todo (opera hoy)    159   64,8%   +49,0 R    -8,0 R      +7.356
  C. sin EMA + la EMA de filtro   105   69,5%   +41,7 R    -6,0 R      +6.258
```

C da **un 25 % menos de caída por un 15 % menos de beneficio**. Mejor ratio, peor
total.

**Decisión: no se cambia nada por ahora.** B lleva diez días corriendo, el margen
de mejora es modesto, y pasar a C exige un modo nuevo en la EA —elegir el order
block más cercano y *después* exigir el acuerdo de la EMA, que hoy no existe— más
otra ronda de verificación contra el probador.

**C es la configuración a usar el día que se vuelva a un desafío**, donde el
límite de caída pesa más que el total. Queda escrito para no volver a medirlo.

### CORRECCIÓN del 18/10, por la tarde: el filtro de la EMA no compensa

Lo escrito más arriba sobre la opción C —105 operaciones al 69,5 % y +41,7 R—
**está mal**, y el error es el mismo que ya se cometió esa misma mañana con el
criterio de solapes: medir una aproximación en vez de simular lo que la EA hace.

Aquel número salió de filtrar **después** las operaciones del sin-EMA. Pero una
EA no filtra después: cuando la EMA veta una entrada, **la posición no se abre**,
y al no abrirse queda libre para tomar otra cosa. Filtrar a posteriori conserva
el bloqueo de unas operaciones que luego se descartan.

Implementado el modo de verdad en el motor (`ema_como_filtro`) y comparado con
el filtrado posterior: **90 operaciones contra 105, +35,3 R contra +41,7**. Solo
86 coinciden.

Las tres opciones, ya bien medidas, con la caída por Monte Carlo de 20.000
barajadas:

```
                            ops  acierto   total  caida p5   EUR/ano
  el mas cercano a secas    159   64,8%   +49,0 R   -8,0 R    7.356
  el mas cercano + veto      90   68,9%   +35,3 R   -6,0 R    5.292
  la EMA decide el lado      92   67,4%   +33,3 R   -6,3 R    4.992
```

**El filtro no compensa.** Acierta más pero gana un 28 % menos, y el ratio
tampoco mejora: 6,1 R de beneficio por R de caída sin filtro contra 5,9 con él.

Y el argumento de «mejor para un desafío» tampoco se sostiene. Si lo que limita
es la caída, se baja el riesgo hasta que quepa: con el sin-EMA se podría
arriesgar el 1,25 % por operación y con el filtro el 1,67 %, y sobre la cuenta
sale **61 % contra 59 %**. Gana igualmente el sin-EMA.

**Lo que opera hoy es la mejor de las tres.** No se cambia nada.

La EA `OB_filtro_EMA.mq5` queda construida, compilada y guardada, con su
cabecera diciendo que no compensa y por qué. Mágico 20261018, sin estrenar.

Lo que **sí** queda demostrado es que la EMA **separa**: 69,5 % cuando acompaña
contra 55,6 % cuando no, con los cinco instrumentos en la misma dirección. Lo
que no se sostiene es que convenga actuar sobre esa diferencia vetando entradas:
la operación que se veta no se sustituye por nada mejor.
