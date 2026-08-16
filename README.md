# Vantage

Panel privado + bot de Telegram que vigila un watchlist y te avisa cuando
aparece un setup, con niveles de entrada, take profit y stop loss.

**Vantage no opera.** No tiene acceso a ningún bróker, no guarda credenciales
de trading y no hay nada en el código que pueda mandar una orden. Solo mira el
mercado y te lo cuenta; las órdenes las pasás vos a mano, donde quieras.

No es asesoría financiera regulada.

---

## Qué hace cada archivo

| Archivo | Qué es |
|---|---|
| `universe.py` | El **universo amplio** que el radar rastrea a diario (~180 símbolos) |
| `scanner.py` | Barrido diario: puntúa el universo y asciende los mejores |
| `market.py` | Datos de Yahoo Finance y tu **watchlist fija** |
| `analyzer.py` | Indicadores y señales (ENTRADA / OBSERVAR / PRECAUCION), en compra y en venta |
| `bot.py` | Bot de Telegram: avisos y comandos `/revisar` y `/estado` |
| `publish.py` | Genera `data.json`, que es lo que lee el panel |
| `dashboard.html` | El boletín. Se publica en GitHub Pages y se instala como app en el iPhone |
| `.env.example` | Plantilla — copiar a `.env` y completar (solo si corrés en local) |
| `.github/workflows/vantage.yml` | Seguimiento horario en los servidores de GitHub |
| `.github/workflows/radar.yml` | Barrido diario del universo amplio |

Funciona en dos niveles:

```
universe.py (180 símbolos)  ──velas diarias──> scanner.py ──ordena──> radar diario a Telegram
                                                    │
                                    asciende los 8 mejores
                                                    ▼
market.py (tu lista fija) + ascendidos ──velas horarias──> analyzer.py ──> avisos a Telegram
                                                    │
                                                    └──> publish.py ──> dashboard.html
```

**Por qué dos niveles y no uno.** Rastrear 180 símbolos cada hora no es viable
—Yahoo corta el acceso— y tampoco sería útil: te llegarían treinta avisos al día
y dejarías de leerlos. La vela diaria dice **si el setup existe**; la horaria,
**cuándo entrar**. El radar busca dónde mirar, el seguimiento vigila.

La única credencial de todo el proyecto es el token de Telegram. Vive en `.env`
si corrés en local, o como *secret* del repo si usás GitHub Actions. En ninguno
de los dos casos acaba en el código.

`data.json` se sube al repo a propósito: además de alimentar el panel, guarda
qué señales ya te avisó, para no repetirlas en la ronda siguiente.

---

## 1. Probar (opcional, solo si tenés Python)

Si vas a usar GitHub Actions, podés saltarte esta sección entera: la primera
ejecución del workflow hace de prueba.

```bash
pip install -r requirements.txt
cp .env.example .env        # completá el token y el chat ID de Telegram

python market.py            # ¿responden todos los símbolos?
python analyzer.py          # ¿salen señales?
python publish.py           # genera data.json
python bot.py               # manda una ronda de avisos
```

`market.py` comprueba símbolo por símbolo que Yahoo devuelve datos y te dice
cuántas velas trae cada uno.

## Las dos listas

**`market.py` → `WATCHLIST`** es tu lista fija: lo que se vigila cada hora,
pase lo que pase. Once símbolos de partida.

**`universe.py`** es lo que el radar rastrea a diario. Unos 180: los pares de
divisas líquidos, materias primas, índices globales y grandes cotizadas de
EE.UU. y Europa. De ahí ascienden 8 cada día al seguimiento horario, y rotan
solos según lo que encuentre.

En Telegram y en el panel, lo que viene del radar sale marcado, para que sepas
si un aviso es de tu lista o un hallazgo.

Se pueden ampliar los dos. Añadir al universo cuesta tiempo de ejecución: 180
símbolos tardan alrededor de un minuto porque se descargan por lotes de 40.
Con 400 iría bien; con 3.000, Yahoo te cortaría.

### Formato de los símbolos

El watchlist fijo va como lista de tuplas:
`(ticker de Yahoo, nombre a mostrar, clase de activo)`.

Para añadir algo, buscalo en finance.yahoo.com y copiá el símbolo de la URL.
La nomenclatura tiene truco:

| Tipo | Formato | Ejemplos |
|---|---|---|
| Divisas | `PAR=X` | `EURUSD=X`, `USDJPY=X`, `EURGBP=X` |
| Materias primas | `TICKER=F` | `GC=F` (oro), `SI=F` (plata), `CL=F` (petróleo) |
| Índices | `^TICKER` | `^NDX`, `^GSPC`, `^DJI`, `^GDAXI`, `^FTSE` |
| Acciones | el ticker | `NVDA`, `PLTR`, `SNOW` |

### Volumen: por qué el forex es distinto

En divisas, Yahoo devuelve **volumen cero**. No es un fallo: el mercado forex
es descentralizado y no existe un volumen consolidado.

Eso importa porque el analyzer usa un pico de actividad como una de las tres
condiciones de entrada. Si exigiera volumen, ningún par de divisas daría jamás
una señal. Cuando no hay volumen, el sistema usa en su lugar la **expansión del
rango**: una vela mucho más ancha de lo habitual indica la misma actividad.

En el panel y en Telegram se indica cuál de los dos se usó en cada caso.

---

## 2. Publicar el panel

Repo en GitHub → Settings → Pages → branch `main`, carpeta `/ (root)`.

En un par de minutos:

```
https://TU_USUARIO.github.io/vantage/dashboard.html
```

**En el iPhone:** abrí esa URL en **Safari** → compartir → *Agregar a pantalla
de inicio*. Queda como una app.

Antes del primer `git push`, comprobá que `.env` no aparece en `git status`.

Si abrís el panel antes de generar datos, verás un boletín vacío que te indica
qué falta. Es lo esperado.

---

## 3. Dejarlo corriendo

Hay dos formas. **La recomendada no necesita instalar nada en tu ordenador.**

### Opción A — GitHub Actions (sin Python en tu PC)

El repo trae `.github/workflows/vantage.yml`. GitHub ejecuta el análisis en sus
servidores, te manda el aviso por Telegram y sube los datos del panel él solo.
Tu ordenador puede estar apagado.

Solo hay que guardar el token donde GitHub pueda leerlo:

> Settings → Secrets and variables → Actions → **New repository secret**
> - `TELEGRAM_BOT_TOKEN` = tu token
> - `TELEGRAM_CHAT_ID` = tu chat id

Los secrets no se ven ni en un repo público, y no aparecen en los logs.

Por defecto revisa **cada hora, de 06:00 a 21:00 UTC, de lunes a viernes**.
Para cambiarlo, editá la línea `cron` del workflow. En la pestaña **Actions**
tenés un botón *Run workflow* que lanza una revisión al momento — es el
sustituto de `/revisar`, y funciona desde la app de GitHub en el móvil.

Lo que hay que saber de este camino:

- **El horario no es puntual.** GitHub retrasa las tareas programadas cuando
  hay carga, a veces varios minutos. Por eso el cron está en el minuto 17 y no
  en punto: las tareas en punto se acumulan y sufren más retraso.
- **El cron va en UTC**, no en hora española. En verano, España es UTC+2.
- **Se pierden los comandos del chat.** `/revisar` y `/estado` necesitan un
  proceso vivo escuchando; en Actions no lo hay. Queda el botón *Run workflow*.
- **Repo público**: minutos de Actions ilimitados. En repo privado, el plan
  gratuito da 2.000 minutos al mes, que da justo para esta frecuencia.
- **Los workflows programados se desactivan solos** tras 60 días sin actividad
  en el repo. Como cada ejecución hace commit de `data.json`, no debería pasar,
  pero si un día dejan de llegar avisos, mirá la pestaña Actions: aparece un
  botón para reactivarlo.

### Opción B — en tu propio ordenador

Necesita Python instalado (python.org, marcando *Add Python to PATH*).

```bash
python bot.py --daemon
```

Revisa cada 30 minutos, manda los avisos y regenera `data.json`. Con
`PANEL_AUTO_PUSH=true` en el `.env`, además sube los datos y el panel se
actualiza solo. A cambio de la instalación, conservás `/revisar` y `/estado`.

Si lo montás como servicio, acordate de que el proceso corre sin vos delante:
`git` no puede pedirte contraseña. Configurá una clave SSH sin passphrase o un
credential helper, o el push fallará en silencio cada media hora.

### Windows (Programador de tareas)

Nueva tarea → desencadenador *Al iniciar sesión* → acción: `pythonw.exe` con
argumentos `bot.py --daemon`, e **Iniciar en** la carpeta del proyecto (ahí se
escriben el log y `data.json`).

### Linux (systemd)

```ini
[Unit]
Description=Vantage
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/RUTA/A/vantage
ExecStart=/usr/bin/python3 /RUTA/A/vantage/bot.py --daemon
Restart=always
RestartSec=10
User=TU_USUARIO

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now vantage
```

En Mac, lo mismo con un `.plist` en `~/Library/LaunchAgents/`.

---

## 4. Ajustar la sensibilidad

En `scanner.py`:

| Parámetro | Por defecto | Qué controla |
|---|---|---|
| `PROMOTE_TOP` | 8 | Cuántos ascienden a seguimiento horario cada día |
| `RADAR_TOP` | 20 | Cuántos se muestran en la tabla del panel |
| `BATCH_SIZE` | 40 | Símbolos por petición a Yahoo |

En la cabecera de `analyzer.py`:

| Parámetro | Por defecto | Qué controla |
|---|---|---|
| `MIN_RR` | 1.8 | Riesgo/beneficio mínimo para llamarlo entrada |
| `SL_ATR_MULT` | 1.8 | Distancia del stop, en múltiplos de ATR |
| `VOLUME_SPIKE_MULT` | 1.8 | Cuánto volumen se considera inusual |
| `RANGE_SPIKE_MULT` | 1.6 | Lo mismo, por rango, cuando no hay volumen |
| `RSI_PERIOD` / `ATR_PERIOD` | 14 | Ventanas de los indicadores |
| `SR_LOOKBACK` | 60 | Velas hacia atrás para soporte y resistencia |

En `bot.py`: `CHECK_INTERVAL_MINUTES` y `ALERT_ON`, que decide de qué señales
te avisa (por defecto, entradas y precauciones; las de observación solo salen
en el panel para no llenarte el chat).

---

### Cómo se ordena el radar

La puntuación pondera el riesgo/beneficio, cuánta actividad inusual hay y cuán
separadas están las medias (medido en ATR, para poder comparar el Nasdaq con el
euro). Resta puntos si el RSI ya va camino del extremo, porque queda menos
recorrido.

Es una heurística, no una probabilidad. Que ordene bien está tan sin validar
como el resto del sistema.

---

## Lo que falta

La lógica —medias 20/50, RSI, ATR y pico de actividad— **no está validada
contra histórico**. Que el sistema funcione no dice nada sobre si acierta.

Antes de darle peso a sus recomendaciones, lo razonable es un backtest sobre
varios años que muestre cuántas señales hubo, qué proporción llegó al take
profit y cuál fue la peor racha. Es la pieza que falta.

Otras ideas:

- Filtro de sesión: no avisar en horas de poca liquidez
- Filtro de calendario económico
- Registro de las señales para poder medirlas después
- Ampliar el universo a más bolsas europeas y asiáticas
