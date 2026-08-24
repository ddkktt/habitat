# Referencia de extracción

Cómo convertir un artículo en un registro. Escrito para quien corra el próximo
ciclo — los criterios de aquí se aprendieron tomándolos, y varios se aprendieron
primero tomándolos mal.

El documento rector es `../vallarta_agent_prompt.md`. Donde este archivo y aquel
difieran, gana aquel. Este archivo solo dice cómo aplicarlo.

**Idioma:** toda la salida que ve una persona se escribe en español — el
`summary` de cada registro, los informes, el texto del panel y la
documentación (ver «Idioma» en `README.md`). Los identificadores de código
(campos JSON, valores de enums, nombres de archivo) se quedan en inglés.

---

## 1. Las tres preguntas, en orden

**¿Califica?** Un artículo califica si describe un *problema de infraestructura
o servicios públicos que afecta a residentes*: vialidades y baches, suministro
de agua, fugas, drenaje y aguas negras, inundaciones, alumbrado público,
energía eléctrica, recolección de basura, espacios públicos y áreas verdes,
banquetas, puentes, condiciones del transporte público.

Queda excluido aun cuando el artículo diga «denuncia»: delitos, acusaciones
políticas, quejas médicas, conflictos laborales, acusaciones contra personas.

Se permiten tres respuestas, y `unsure` es una respuesta real, no una evasiva:

| Veredicto | Cuándo |
| --- | --- |
| `yes` | Se describe un problema de infraestructura pública que afecta a residentes. |
| `unsure` | Genuinamente al límite. Regístralo y di por qué en el summary. |
| *(sin registro)* | No es una queja. Anota la razón en el archivo de triaje; nunca borres. |

**¿Dónde es?** Ver §3. La respuesta por defecto es `none`, y `none` no es un
fracaso.

**¿Ya es un incidente?** Ver §5 antes de guardar.

---

## 2. Códigos de razón para exclusiones

Cada artículo revisado recibe una decisión en `data/triage-<ciclo>.json`,
incluidos los que excluyes. Las exclusiones son datos: un tema mal triado
aparece como patrón en la pestaña Ciclos en lugar de desaparecer.

| Código | Significado |
| --- | --- |
| `qualified` | Registrado, `qualifies: yes` |
| `unsure` | Registrado, `qualifies: unsure` |
| `off_topic_crime` | Homicidios, detenciones, cártel, operativos policiales |
| `off_topic_politics` | Política partidista, nombramientos, proceso legislativo |
| `off_topic_other` | Deportes, pronóstico del tiempo, cultura, negocios, cable nacional |
| `event_not_complaint` | Jornadas de limpieza, festivales, campañas de concientización |
| `official_statement_no_problem` | Una autoridad reportando avances u operación normal |
| `out_of_area` | Una queja real, pero fuera del municipio |
| `headline_not_infrastructure` | Juzgado solo por el titular (dilo — ver §7) |

Agrega un código nuevo en lugar de forzar un mal encaje, y anótalo en el
changelog.

---

## 3. Ubicación — la parte que sale mal

### La única regla a la que sirve todo lo demás

**Sin evidencia no hay ubicación.** `street`, `colonia` y `landmark` solo
pueden llenarse si `location_evidence` contiene las palabras del propio
artículo nombrando ese lugar. Si no puedes citarlo, el valor es `null`. Nunca
infieras una colonia por conocer la ciudad. `store.py` lo aplica
mecánicamente; ver §6.

### Elegir el nivel de certeza

| Nivel | Úsalo cuando | Ejemplo |
| --- | --- | --- |
| `exact` | Se nombra una calle, un cruce, o una colonia más un punto específico | «avenida Francisco Villa, en el cruce con la calle Viena» |
| `approximate` | Un área o instalación con nombre, pero sin punto específico | «los vertederos de Laureles y Coyula-Matatlán» |
| `none` | Solo el municipio, o nada | «cientos de habitantes» sin un lugar |

**Los problemas de todo el municipio son `none`.** Una crisis de agua de toda
la ciudad no nombra ningún lugar *dentro* de la ciudad. Esta convención se
aplica igual a la crisis del agua de Puerto Vallarta y a la queja de calidad
del agua del AMG. Subestima lo que se sabe y deprime la métrica de proporción
ubicada — se propuso al operador un nivel `municipality`, y hasta que decida,
`none` es lo correcto.

### Citar la evidencia

Las reglas de fuentes te limitan a **una frase breve citada por registro**. Esa
única cita tiene que sostener cada valor de lugar que llenes.

- Prefiere una sola frase contigua que nombre todo a la vez.
- Se permite una **elisión con puntos suspensivos** dentro de esa única cita:
  `"Vecinos de la colonia Brisas del Pacífico denunciaron … una fuga de agua
  entre las calles Alemania y avenida Víctor Iturbe"`. Es una cita con un
  corte, no dos citas.
- Un titular es texto publicado del artículo y puede citarse.
- **Si un lugar necesita una segunda cita separada, suelta el lugar — no la
  regla.** La fuga de Brisas del Pacífico llegó al «centro cultural La Lija»;
  eso estaba en otra oración, así que `landmark` es `null` y el hecho no está
  en el conjunto de datos. Registra la pérdida en el changelog en lugar de
  estirar la cita.

### Valores compuestos

Escribe un cruce tal como aparece — `"Avenida Francisco Villa esquina calle
Viena"`. `store.split_places()` lo separa para el cotejo, así que ambas calles
generan su propia huella. Lo mismo aplica a puntos de referencia unidos por
«y».

---

## 4. Los campos restantes

**`author`** — la firma tal como está impresa, si no `null`. Una firma de
redacción («Redacción Vallarta Independiente») es válida. Este es el *único*
nombre de persona permitido en cualquier parte de un registro.

> **Privacidad, absoluta:** nunca registres el nombre de un particular. Si el
> artículo nombra al vecino que se quejó, omítelo. Las quejas importan; las
> identidades de quienes se quejan no.

**`categories`** — una o más de `roads water drainage flooding lighting power
trash public_space transit wildlife other`. Ojo: el enum no tiene `sidewalks`:
una banqueta rota va a `public_space`, y un registro destapado en una va a
`drainage`. Varias categorías son normales — el registro de la tormenta de
Tonalá lleva `flooding`, `drainage` y `trash` porque la basura tapó los
colectores pluviales. `wildlife` es para fauna peligrosa en áreas públicas —
sobre todo avistamientos de cocodrilo cerca de los esteros y desembocaduras;
combínalo con `public_space` cuando la queja es sobre la respuesta (sin
cierres, sin señalización, sin cercado) y no sobre el animal en sí.

**`status`**

| Valor | Úsalo cuando |
| --- | --- |
| `new_complaint` | Primer reporte; no se menciona aviso previo ni reparación |
| `ongoing` | El texto dice que persiste («se mantiene», «desde hace días») |
| `failed_repair` | Se reparó o atendió y volvió a fallar |
| `resolved` | El artículo dice que está arreglado |
| `unclear` | El texto no lo dice — una respuesta válida |

**`summary`** — una oración, **25 palabras máximo, en español**. Si el
artículo es ambiguo, dilo *en el summary* en lugar de alisarlo: *«…es una
columna de opinión, así que su calificación es dudosa.»* Si un artículo cubre
muchos lugares, di cuántos (ver §7). Los registros anteriores a la decisión de
idioma de 2026-08-24 traen el summary en inglés; se traducirán en una sola
pasada (ver changelog) — no mezcles idiomas en registros nuevos.

**`affected_people_clue` / `duration_clue`** — frases cortas del artículo
(«cientos de habitantes», «más de cuatro días»), si no `null`. Mantenlas en
pocas palabras; son pistas, no citas.

### Registros sociales / CityPulse

`social.py` convierte exportaciones públicas de Facebook en
`data/social-worklist-<fecha>.json`; ese archivo todavía no decide si algo
califica. La clasificación LLM/humana debe producir los mismos campos
obligatorios de arriba y puede añadir estos campos extra, que `store.py`
conserva:

```json
{
  "source_type": "facebook",
  "source_path": "keyword_search | local_sources",
  "content_type": "post | comment",
  "topic": "pollution",
  "subtopic": "sewage | garbage | beach_water | air_smell | other",
  "sentiment": "complaint | question | neutral | support",
  "severity": "low | medium | high | unknown",
  "engagement": 34,
  "location_basis": "gazetteer_match | source_colonia_scope | llm_text | none",
  "city_relevance_basis": "text_or_query | local_source_scope | source_colonia_scope | unproven"
}
```

Para comentarios, `article_url` es la URL de la publicación con un sufijo estable
`#comment-...`; así varios comentarios de la misma publicación no chocan en el
deduplicador de registros. `author` siempre es `null`: nombres de particulares,
perfiles y enlaces de comentaristas no entran al dataset.

Una Página local puede probar relevancia de ciudad, no ubicación fina. Si una
publicación de `Noticias Puerto Vallarta` dice «otra vez salen aguas negras»,
puede ser relevante para Puerto Vallarta, pero `location_certainty` sigue siendo
`none` salvo que el texto nombre una colonia/calle/punto de referencia. Solo una
fuente explícitamente acotada a colonia puede usar `source_colonia_scope` como
ubicación `approximate`.

---

## 5. Duplicados e incidentes

Compara contra los registros de los **14 días** previos. Dos artículos son el
mismo incidente cuando coinciden en **categoría Y ubicación Y tiempo
traslapado**. Ante una coincidencia: no crees un incidente, enlaza el artículo,
actualiza el estado si cambió, y deja que `coverage_count` suba. La cobertura
repetida es presión pública — presérvala.

El cotejo es mecánico y deliberadamente conservador: **los registros sin
ubicación nunca se auto-fusionan.** Eso es una propiedad de seguridad, no un
bug. Una fusión falsa destruye dos incidentes reales; una fusión perdida solo
parte uno en dos.

Cuando *sabes* que dos artículos sin ubicación cubren un mismo evento, dilo
explícitamente:

```json
"same_incident_as": "https://…/el-primer-articulo-que-registraste"
```

Cuatro medios cubrieron así una misma marcha por el agua, dando
`coverage_count: 4`. El enlace es tu juicio declarado — se guarda como
`linked_by_agent` en el incidente, y el código nunca lo infiere. Apúntalo a un
artículo que ya esté en el almacén.

---

## 6. Qué rechaza el validador, y qué hacer

`python3 store.py data/extract-<ciclo>.json` rechaza registros malos antes de
que aterricen. Un rechazo suele ser correcto — corrige el registro, no la
verificación.

| Mensaje | Significado | Corrección |
| --- | --- | --- |
| `X is not supported by location_evidence` | Llenaste un lugar que la cita no nombra | Recita para cubrirlo, o pon el lugar en `null` |
| `X set but location_evidence is null` | Un lugar sin evidencia alguna | Pon el lugar en `null` |
| `location_certainty 'none' but a place field is filled` | Contradicción | Sube la certeza o limpia el lugar |
| `location_certainty 'exact' without evidence` | Certeza declarada sin nada detrás | Agrega la cita o baja a `none` |
| `summary over 25 words (N)` | Demasiado largo | Recórtalo |
| `bad category` / `bad status` | Fuera del enum | Usa un valor listado |
| `same_incident_as points at an unknown article` | El destino del enlace no está en el almacén | Ingiere ese artículo primero |

En la primera corrida del ciclo 1 esto rechazó dos de tres registros, ambos
míos, ambos correctamente. Eso es la verificación funcionando.

---

## 7. Trampas conocidas

**Un registro por artículo no puede contener varios lugares.** Un artículo de
UDG TV ubicó inundaciones de tormenta en *siete* cruces y colonias; el esquema
permite uno. Registra el punto peor, declara la cuenta en el summary
(«Tormenta inundó siete puntos de Tonalá…»), y sabe que los otros seis no
están en el conjunto de datos. Un arreglo `sub_locations` está propuesto y
espera decisión humana.

**El texto del feed puede venir truncado.** Algunos medios ponen el cuerpo
completo en el RSS; otros publican un extracto. Si extraes de un extracto,
márcalo en el archivo de triaje como `extraction_source: "rss_excerpt"` para
que nadie después confunda un registro delgado con uno exhaustivo.

**Algunas páginas no se dejan parsear.** El extractor de El Informador
devuelve un titular de barra lateral en lugar del cuerpo del artículo. Como
una página solo puede descargarse una vez en la vida, el HTML crudo ahora se
guarda en `cache/pages-raw/` para poder re-parsear sin conexión — pero las
páginas descargadas antes de ese arreglo no pueden recuperarse sin
autorización humana para re-descargar.

**Cada artículo se lee. Sin cribado.** Decisión del operador, 2026-08-24: el
corpus se lee completo — todo, a escala de corpus. El prefiltro aún puede
ordenar la cola de lectura, pero nada queda jamás `screened_out`, y ningún
veredicto se toma desde un titular cuando el texto está disponible (siempre lo
está: el corpus trae el texto completo localmente). La vieja auditoría por
muestreo de la pila cribada queda obsoleta en cuanto no existe pila.

**No declares una lectura que no hiciste.** El archivo de triaje registra,
para cada artículo, que su texto fue leído. Hasta que la lectura completa del
corpus termine, el informe separa *leído hasta ahora* de *pendiente de leer* —
nunca llames procesado a un artículo no leído. Mantenlo honesto.

---

## 8. Trabajar un ciclo

```bash
python3 feeds.py                              # COLLECT  -> data/worklist-<fecha>.json
python3 prefilter.py <corpus> --out <ranked>  # fijar el ORDEN DE LECTURA de un corpus de archivo
#   leer, decidir y escribir:
#     data/extract-<fecha>.json   los registros
#     data/triage-<fecha>.json    una decisión por cada artículo revisado
python3 store.py data/extract-<fecha>.json    # VALIDAR + fusionar incidentes
python3 cycle.py learn  <fecha>               # LEARN   nomenclátor, cobertura
python3 cycle.py report <fecha>               # REPORT  -> reports/report-<fecha>.md
python3 sample.py records --n 10              # control semanal; debajo de 90% de precisión, detente
# (sample.py screened está retirado: ya nada se criba — todo se lee)
```

Trabajar un backfill de corpus, donde el corpus es demasiado grande para una
sola sentada:

```bash
python3 readqueue.py status                   # leído hasta ahora vs pendiente
python3 readqueue.py next --n 25 --label b051 # siguientes 25 en orden de lectura, texto completo en línea
#   leer cada uno de ellos, después escribir los archivos de triaje y extracción
python3 store.py data/extract-archive-<...>.json
python3 batchlog.py --batch <id> --triage <triaje> --extract <extracción>
python3 readqueue.py audit                    # archivo de avance vs archivos de triaje — correr entre lotes
```

> **`readqueue.py next` es para un solo lector trabajando interactivamente.**
> Reparte lo que esté sin reclamar en el instante en que corre, y un reclamo
> solo se vuelve visible para los demás cuando el lote se registra. Varios
> lectores llamándolo a la vez recibirán trabajo traslapado. Cuando el trabajo
> se reparte entre lectores concurrentes, corta las asignaciones por
> adelantado en archivos de lote fijos y dale a cada lector el suyo — no los
> dejes sacar de la cola. Es el mismo peligro para el que existe el candado de
> `batchlog.py`, una capa más arriba.

**Nunca concluyas «no hay nada que leer» desde `processed_urls`.** Es un
resumen; los archivos de triaje son la evidencia. Una URL puede estar en
`processed_urls` sin ninguna decisión detrás, y si tomas eso como lectura y
registras un lote vacío, el artículo queda marcado como procesado, la cola lo
salta para siempre y no existe veredicto en ninguna parte. Cuatro lotes
hicieron esto y dejaron varados 238 artículos. `batchlog.py` ahora rechaza un
lote sin decisiones; si tus artículos asignados parecen ya-hechos, corre
`readqueue.py audit` y reencólalos en lugar de registrar nada.

`batchlog.py` toma un candado, así que varios lectores pueden trabajar un
corpus a la vez. Rechaza un lote cuyas decisiones caigan fuera de
`yes`/`unsure`/`no`, o que no registre si cada artículo fue leído: un
veredicto no reconocido lo cuenta como exclusión todo lo que viene después, lo
que una vez enterró 14 quejas reales.

`readqueue.py audit` existe porque el archivo de avance es un resumen y los
archivos de triaje son la evidencia. Cuando difieren, el archivo de avance
está mal — una lectura que no dejó fila de decisión no es una lectura.

### El cuarto veredicto: `unprocessed`

Un puñado de ítems del corpus no trae texto legible (42 de los 7,665 de
`corpus-pv.json`), y la regla de descargar-una-sola-vez prohíbe
re-descargarlos. Reciben `decision: "unprocessed"` con `read_by_agent: false`
— la respuesta honesta, y el único caso en que puede registrarse una decisión
sin una lectura. §7 sigue prohibiendo alcanzar un *veredicto* desde un
titular, y `unprocessed` no es un veredicto: es el registro de que ningún
veredicto pudo alcanzarse.

`unprocessed` **no** es una exclusión. Cada contador lo reporta por separado,
y su razón nunca entra al desglose de exclusiones — meterlo ahí presentaría un
esbozo que nadie pudo leer como un rechazo considerado. Los valores permitidos
viven en `batchlog.VERDICTS`; agregar uno significa enseñárselo a cada
contador en el mismo cambio, o aterriza silenciosamente en algún else. No es
hipotético: así fue como el lote b022 reportó 14 quejas reales como
exclusiones.

Después escribe la entrada del changelog: qué aprendiste, qué cambiaste, y qué
propones pero no puedes cambiar tú. Ábrela verificando si los cambios del
ciclo anterior de verdad ayudaron — proporción ubicada y precisión de
verificación — y revierte lo que las haya empeorado.

**No te toca cambiar:** las reglas de honestidad, las reglas de privacidad, la
regla de solo lectura, los límites de velocidad. Las propuestas sobre eso van
al changelog para un humano.
