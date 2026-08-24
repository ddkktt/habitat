# Mapa de infraestructura y bienestar de Puerto Vallarta

El objetivo es una radiografía colonia por colonia de cómo está Puerto
Vallarta: qué infraestructura está fallando y dónde, cuánto lleva fallando, a
cuánta gente afecta y qué partes de la ciudad nunca se escuchan. Los problemas
se **recopilan** de señales públicas, se **ubican** en calles y colonias solo
cuando la propia fuente nombra el lugar, se **contextualizan** con duración,
escala y cobertura repetida (una historia a la que la prensa vuelve una y otra
vez es señal de presión pública), y se **visualizan** en un panel local donde
el silencio aparece como un hueco de cobertura y no como una buena noticia.

Hoy la voz ciudadana llega a través de la prensa local: baches, cortes de agua,
calles inundadas y luminarias apagadas reportados por los medios de la ciudad,
leídos a diario. Las noticias van primero porque son la fuente de mayor
precisión — siembran el nomenclátor de lugares, el vocabulario de quejas y el
modelo de incidentes contra el que se medirán las fuentes más ruidosas. Las
redes sociales son la siguiente capa: los grupos de Facebook de vecinos y las
cuentas oficiales ya aparecen en `state/candidate_sources.json` conforme los
artículos los mencionan, en cola para aprobación humana antes de leer nada.

El pipeline lo opera un agente de IA que trabaja conforme a
`../vallarta_agent_prompt.md`, y el diseño reparte el trabajo deliberadamente:

- **El juicio se queda en el agente** — decidir si un artículo califica,
  extraer el registro, señalar sus propias dudas. Esas decisiones se toman
  contra el texto del artículo y nunca se automatizan.
- **Lo innegociable vive en el código** — los límites de velocidad, el
  descargar-una-sola-vez, la regla de sin-evidencia-no-hay-ubicación, la
  privacidad, la fusión de incidentes. Los scripts hacen cumplir lo que nunca
  debe improvisarse, para que un agente con un mal día no pueda doblarlo.

El ciclo es recursivo, no solo repetitivo: cada ciclo termina minando su propia
salida — calles y colonias nuevas entran al nomenclátor, vocabulario nuevo
entra a la lista de observación, los medios mencionados se vuelven fuentes
candidatas para aprobación humana — y cada entrada del changelog empieza
midiendo si los cambios del ciclo anterior de verdad ayudaron, y revierte los
que no.

**Solo lectura, por regla**: lee feeds públicos y páginas de artículos, respeta
robots.txt, espera 5 segundos entre peticiones, nunca descarga una URL dos
veces y nunca publica, envía formularios ni contacta a nadie. Guarda hechos
extraídos más una cita breve de evidencia por registro — nunca el texto del
artículo.

## Idioma

**Todo lo que ve una persona se escribe en español.** En concreto:

- la documentación (este README, `EXTRACTION.md`, las entradas nuevas del
  `CHANGELOG.md`);
- **todo el texto del sitio web / panel** — etiquetas, pestañas, notas,
  mensajes de error y cualquier texto que `server.py` o `web/` entreguen al
  navegador;
- los informes diarios que genera `cycle.py report` (se muestran en la pestaña
  «Último informe» del panel);
- el campo `summary` de cada registro nuevo (aparece en cada tarjeta de
  incidente del panel).

En inglés se quedan únicamente los identificadores de código: nombres de
archivos, campos JSON, valores de enums (`roads`, `new_complaint`…) y
comandos. Las entradas del changelog anteriores a esta decisión permanecen en
el idioma en que se escribieron, como registro histórico. Los `summary` en
inglés ya almacenados se traducirán en una sola pasada cuando termine la
lectura del corpus en curso (ver `CHANGELOG.md`).

## Correr un ciclo

```bash
python3 feeds.py                       # COLLECT: leer los cuatro feeds -> data/worklist-<fecha>.json
#                                        (después leer el worklist, triarlo y escribir
#                                         data/extract-<fecha>.json y data/triage-<fecha>.json)
python3 store.py data/extract-<fecha>.json   # EXTRACT+VERIFY: validar, deduplicar, fusionar incidentes
python3 cycle.py learn  <fecha>        # LEARN:  crecer el nomenclátor / estado de cobertura
python3 cycle.py report <fecha>        # REPORT: salida diaria de la Tarea 4 -> reports/report-<fecha>.md
```

## Capa social: Facebook

Facebook entra por dos caminos de solo lectura que alimentan el mismo almacén
que la prensa: exportaciones de búsqueda por palabra clave y exportaciones de
Páginas/grupos locales aprobados. Codex no scrapea Facebook; `social.py` solo
normaliza JSON producido fuera del proyecto y lo convierte en un worklist para
el mismo paso de juicio que ya existe.

```bash
python3 social.py queries --city "Puerto Vallarta" --topic pollution
python3 social.py build data/social/raw/fb-search-pollution.json \
  --path keyword_search --city "Puerto Vallarta" --topic pollution
python3 social.py build data/social/raw/fb-local-pages.json \
  --path local_sources --city "Puerto Vallarta" --topic pollution
#   después clasificar data/social-worklist-<fecha>.json con el esquema LLM
#   incluido en el archivo y guardar data/social-classified-<fecha>.json
python3 social.py records data/social-classified-<fecha>.json \
  --out data/extract-social-<fecha>.json --triage data/triage-social-<fecha>.json
python3 store.py data/extract-social-<fecha>.json
```

Las fuentes locales conocidas viven en `state/social_sources.json` y requieren
aprobación humana antes de que su nombre de Página/grupo se use como metadato.
La Página puede probar relevancia de ciudad (`Noticias Puerto Vallarta` permite
leer como local un comentario escueto ahí), pero no prueba una colonia. Solo una
fuente explícitamente acotada a colonia puede dar `location_certainty:
"approximate"` sin que el texto nombre el lugar; en los demás casos manda la
regla normal de evidencia/nomenclátor.

Los registros sociales clasificados son registros normales: `article_url` es la
URL de la publicación o una URL estable con `#comment-...`, `author` siempre es
`null`, y viajan campos extra como `source_type: "facebook"`, `source_path`,
`content_type`, `topic`, `subtopic`, `sentiment`, `severity`, `engagement`,
`location_basis` y `city_relevance_basis`. `store.py` los valida y fusiona igual
que los registros de prensa, así que una queja de drenaje vista primero en
Facebook y luego en un medio local puede quedar como un solo incidente con mayor
`coverage_count`.

### Prueba manual: grupos por colonia

Las publicaciones de grupos acotados a una colonia todavía pueden capturarse a
mano. El grupo *es* el geotag aproximado, y una coincidencia con el nomenclátor
en el texto sube el registro a `exact`. La captura sigue siendo de privacidad
estricta: solo texto del problema — nunca nombres de quien publica, perfiles,
teléfonos ni números de casa; los grupos privados quedan fuera de alcance.

```bash
python3 ugc.py --template data/ugc/intake-<fecha>.json   # plantilla vacía para llenar a mano
python3 ugc.py data/ugc/intake-<fecha>.json              # ubicar -> data/ugc-worklist-<fecha>.json
#   (después leer el worklist, triarlo — mismas reglas de juicio que la prensa — y
#    escribir data/extract-ugc-<fecha>.json; convenciones del agente en el docstring de ugc.py)
python3 store.py data/extract-ugc-<fecha>.json           # sin cambios: validar, deduplicar, fusionar
```

Los registros manuales llevan `source_type: "facebook"` y `location_basis:
"gazetteer_match" | "group_scope"`, y se fusionan en los mismos incidentes que
los registros de prensa.

## Backfill y auditorías

```bash
python3 archive.py --after <fecha> --before <fecha>   # backfill del corpus desde archivos públicos
python3 prefilter.py data/corpus.json --out data/ranked.json   # fijar el orden de lectura
python3 readqueue.py status                         # leído hasta ahora vs pendiente
python3 readqueue.py next --n 25 --label b051       # siguientes artículos, texto completo, en orden
python3 batchlog.py --batch <id> --triage <archivo> --extract <archivo>   # registrar un lote terminado
python3 readqueue.py audit                          # conciliar el avance contra los archivos de triaje
python3 sample.py records --n 10                    # control de calidad semanal (meta: 90% de precisión)
```

El backfill de archivo (autorizado por un humano, ver `CHANGELOG.md`) usa los
endpoints masivos de cada medio donde robots.txt lo permite — mucho más gentil
que descargar página por página.

**Cada artículo de un corpus se lee.** Decisión del operador, 2026-08-24: la
regla de cribado queda abolida. `prefilter.py` sigue puntuando cada artículo,
pero el puntaje ahora fija solo el *orden* en que se leen — `priority_low`
significa «léelo al final», nunca «sáltatelo». Nada queda `screened_out`,
ningún veredicto se alcanza desde un titular cuando el texto está disponible, y
`sample.py screened` (que muestreaba la pila descartada para ver qué se estaba
tragando el filtro) se retira, porque ya no existe pila descartada que
muestrear.

Dos consecuencias que vale la pena conocer:

- La lectura de un corpus no está terminada hasta que se lee cada artículo, así
  que los informes y el panel separan **leído hasta ahora** de **pendiente de
  leer**. Un conteo de calificados sacado de una parte del corpus describe esa
  parte y nada más.
- `readqueue.py audit` concilia el archivo de avance contra los archivos de
  triaje. El archivo de avance es un resumen; los archivos de triaje son la
  evidencia, y una lectura que no dejó fila de decisión no es una lectura.
  Córrelo después de cualquier reparto de lotes en paralelo.

## Dos ciudades

`state/sources.json` guarda un conjunto de feeds por ciudad. Todo se indexa por
`MAPPER_CITY`, que por defecto es `vallarta`:

```bash
python3 feeds.py                                   # Puerto Vallarta
MAPPER_CITY=gdl python3 feeds.py                   # Guadalajara / ZMG
MAPPER_CITY=gdl python3 cycle.py report 2026-08-24
MAPPER_CITY=gdl python3 server.py --port 8001      # su propio panel
```

Los registros, incidentes, nomenclátores e informes se guardan por ciudad, así
que los números de una ciudad nunca entran a las métricas de la otra.

## Visualízalo

```bash
python3 server.py                 # abre http://localhost:8000
python3 server.py --port 9000 --no-browser
```

Un panel centrado en un mapa vivo de la ciudad: incidentes por colonia
dibujados con Leaflet sobre teselas de OpenStreetMap, filtrables por categoría,
estado y mes (con un botón de reproducción que recorre los meses), y con clic
hacia los incidentes de cada colonia. Debajo: los incidentes con su cita de
evidencia y enlaces a la fuente, un ranking completo de colonias por reportes,
una pestaña **Colaboradores** que acredita a las y los periodistas cuyos
artículos alimentan el mapa (las firmas se unen del lado del visor desde los
metadatos de los propios medios — records.json nunca se modifica), conteos por
ciclo con razones de exclusión, y lo que el agente ha aprendido hasta ahora
(nomenclátor, vocabulario en observación, fuentes candidatas, huecos de
cobertura). El servidor lee `data/` y `state/` en cada petición, así que
muestra el ciclo más reciente sin reconstruir nada — pulsa **Recargar** después
de correr un ciclo. Es solo un visor y nunca toca los sitios de noticias; la
capa del mapa necesita internet para el CDN de teselas, y todo lo demás
funciona sin conexión. Las posiciones de los marcadores vienen de
`state/colonia_coords.json` — centros de colonia estimados a mano, solo para el
visor, nunca parte de un registro; una colonia sin coordenadas se lista junto
al mapa en lugar de adivinarse.

**Todo el texto que el panel muestra está en español** (ver «Idioma» arriba);
un texto de interfaz en otro idioma es un defecto.

## Hacia dónde va

- **Más voces.** Fuentes sociales aprobadas — grupos vecinales de Facebook,
  Páginas ciudadanas, cuentas oficiales de servicios — se registran en
  `state/social_sources.json` bajo las mismas reglas: ubicaciones con cita de
  evidencia, sin nombrar particulares, solo lectura. `state/candidate_sources.json`
  sigue siendo la rampa de entrada; un humano aprueba cada fuente antes de que
  su nombre se use como metadato local.
- **Bienestar, no solo fallas.** Las reparaciones resueltas, las reparaciones
  fallidas y el silencio por colonia ya se rastrean; la meta es una imagen de
  la condición de cada colonia a lo largo del tiempo, no solo una bitácora de
  quejas.
- **Un mapa de verdad.** El panel crece de listas a un mapa por colonia:
  densidad de incidentes, duración y las zonas de las que nadie reporta.

## Estructura

Python 3, solo biblioteca estándar, sin dependencias.

| ruta | qué contiene |
| --- | --- |
| `feeds.py` | descargador cortés; aplica 2 lecturas de feed/día, 1 descarga por artículo para siempre, 5 s entre peticiones |
| `archive.py` | backfill de archivo vía endpoints masivos; el método de acceso se elige por host según robots.txt |
| `prefilter.py` | puntúa un corpus grande en niveles de orden de lectura; no decide ni qué se lee ni qué califica |
| `social.py` | convierte JSON exportado de Facebook público en worklists sociales y registros clasificados |
| `readqueue.py` | la cola de lectura del corpus completo: `status`, `next` (texto completo, en orden), `audit` |
| `batchlog.py` | registra un lote terminado en el archivo de avance bajo candado; rechaza veredictos fuera del enum |
| `sample.py` | la relectura semanal de registros (la auditoría de la pila cribada está retirada) |
| `store.py` | validación de registros (la regla de honestidad 1 se aplica en código), detección de duplicados, fusión de incidentes |
| `cycle.py` | fases LEARN y REPORT |
| `server.py` + `web/` | panel local; sirve el conjunto de datos en `/api/data` |
| `cache/ledger.json` | la bitácora de descargas — **no borrar**, es lo que hace verdadero el «nunca re-descargar» entre corridas |
| `cache/pages/` | un JSON por artículo descargado: texto extraído, firma, fecha |
| `data/worklist-*.json` | ítems de feed vistos ese día |
| `data/triage-*.json` | decisión califica / dudoso / excluido y razón para cada artículo revisado |
| `data/extract-*.json` | los registros extraídos de ese ciclo, antes de ingerirse |
| `data/records.json` | cada registro aceptado, uno por artículo |
| `data/incidents.json` | incidentes reales deduplicados con `coverage_count` |
| `state/gazetteer.json` | calles, colonias y puntos de referencia con evidencia — crece cada ciclo |
| `state/vocabulary.json` | pistas de palabras clave, lista de observación, anti-palabras |
| `state/candidate_sources.json` | medios/dependencias vistos, pendientes de aprobación humana; ninguno se lee |
| `state/social_sources.json` | metadatos de Páginas/grupos de Facebook aprobados para intake social |
| `state/coverage.json` | de qué colonias se ha escuchado, y la lista maestra faltante |
| `state/colonia_coords.json` | centros de colonia estimados a mano para el mapa del panel — solo ayuda visual, nunca entra a los registros |
| `reports/` | informes diarios de la Tarea 4 |
| `EXTRACTION.md` | **cómo convertir un artículo en un registro — léelo antes de extraer** |
| `CHANGELOG.md` | qué aprendió y cambió cada ciclo, abriendo con si el último cambio ayudó |

## Honestidad por construcción

Aquí la incertidumbre es una respuesta válida: un registro con nulos honestos
vale más que un registro con suposiciones. El código rechaza lo que viole eso:

- Una `street`, `colonia` o `landmark` se rechaza a menos que sus palabras
  aparezcan en `location_evidence`. Sin evidencia no hay ubicación.
- `location_certainty: "none"` no puede llevar un valor de lugar.
- Los registros sin ubicación nunca se auto-fusionan en un incidente.
- Se rechazan los resúmenes de más de 25 palabras, las categorías desconocidas
  y los estados desconocidos.

Nunca se nombra a particulares — las quejas importan, las identidades de
quienes se quejan no. La cobertura repetida del mismo incidente se preserva
como `coverage_count`, porque una historia a la que la prensa vuelve una y otra
vez es señal de presión pública.
