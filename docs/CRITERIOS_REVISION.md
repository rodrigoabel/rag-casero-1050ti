# Criterios de revisión

Cada respuesta tiene dos veredictos: el **automático**, que calcula `rag_eval.py`, y el **manual**, que se anota en `revision_manual.csv` cuando el automático se equivoca. Todas las cifras de este repositorio usan el manual.

## Por qué hace falta revisar a mano

El hallazgo que más pesó en todo el proyecto (**H15**): **un modelo puede inventar una cifra y citar el documento correcto.** El usuario ve la fuente, confía y se lleva un dato falso. Ejemplos reales de la línea base, con Qwen 3.5 2B:

| Pregunta | Qué dijo | Lo correcto |
|---|---|---|
| ¿Cuánto tiempo tiene la concesionaria para construir la obra? | «32 años» | 48 meses (32 años es el plazo de la concesión) |
| Captura de azufre y su meta | «95,8 %, supera ligeramente su meta de 96,5 %» | No cumple la meta |
| ¿Qué módulo tuvo más bugs? | «lotes, 6 bugs» | despachos, 8 |
| ¿Qué es la UTM? (de pasada) | «Unidades de Tránsito Multa» | Unidad Tributaria Mensual |

El puntaje automático contó varias de estas como correctas. Y al revés: un prompt (E1e) que subía 4 puntos en automático **duplicaba** las respuestas con contenido falso en la revisión manual.

## El veredicto automático

`rag_eval.py` normaliza la respuesta (minúsculas, sin tildes) y la compara con los campos de la pregunta en `preguntas/preguntas.json`:

| Veredicto | Cuándo |
|---|---|
| `OK` | Contiene todos los grupos de `requeridas` (cada grupo acepta variantes: `["1.200", "1200"]`) |
| `OK_CON_RUIDO` | Como OK, pero además contiene algo de `prohibidas` (una cifra o un término que delata un error) |
| `PARCIAL` | Contiene algunos grupos de `requeridas`, no todos |
| `RECHAZO_FALSO` | Dice «no encontré» (o parecido) y no trae ningún dato requerido |
| `RECHAZO_OK` | La pregunta espera un rechazo (el dato no existe) y el modelo lo rechaza |
| `ALUCINA` | La pregunta espera un rechazo y la respuesta contiene algo prohibido |
| `FALLA` | No contiene nada de lo requerido ni rechaza |
| `REVISAR` | No se puede decidir solo (por ejemplo, un rechazo esperado sin rechazo explícito) |

Además diagnostica dónde falló, con las fuentes que devuelve la API: **BÚSQUEDA** (el dato no llegó al modelo) o **GENERACIÓN** (llegó y el modelo no lo usó bien).

## El veredicto manual

| Veredicto | Puntos | Significa |
|---|---|---|
| `OK` | 2 | Correcta y sin nada falso |
| `RECHAZO_OK` | 2 | Rechazo correcto: el dato no está y lo dice |
| `OK_CON_RUIDO` | 1 | Responde bien, pero agrega un detalle falso |
| `PARCIAL` | 1 | Correcta pero incompleta, o con los datos sin la conclusión |
| `RECHAZO_FALSO` | 0 | «No encontré» teniendo el dato |
| `FALLA` | 0 | No responde lo que se pregunta (sin afirmar algo falso) |
| `ALUCINA` | 0 | Afirma algo falso como respuesta |

**Puntaje** = puntos ÷ (2 × respuestas). **«Con algo falso»** = `ALUCINA`, más las respuestas cuya nota dice que traen algo falso (`OK_CON_RUIDO` con un detalle inventado). Es la cifra que más pesa al decidir.

## Reglas fijas

Para que el criterio sea el mismo entre modelos y entre experimentos:

| Situación | Veredicto | Ejemplo |
|---|---|---|
| Da los datos para un cálculo, pero no lo hace | `PARCIAL` | «38 puntos de 45» sin el 84 % |
| Hace el cálculo y le da mal | `ALUCINA` | «82,2 %» (es 38/45 ≈ 84,4 %); «13.800 t» de promedio (es septiembre; el promedio es 13.933 t) |
| Da la fecha de vencimiento cuando se pregunta el plazo | `PARCIAL` | «vence en marzo de 2056» en vez de «32 años» |
| A «¿cumplimos la meta?» da el valor y la meta, pero no dice «no» | `PARCIAL` | «95,8 %, la meta es 96,5 %» |
| Concluye lo contrario de sus propios datos | `ALUCINA` | «Sí, se cumplió la meta de 96,5 %, ya que alcanzó el 95,8 %» |
| Toma la fecha de carga del archivo (metadato) como fecha del documento | `ALUCINA` | «firmado el 10/9/2026, 3:42 AM» |
| Da la cifra de algo parecido como si fuera lo preguntado | `ALUCINA` | «La ley de mata objetivo es 45 cm» (es la altura de la mata; la ley es 62 % Cu) |
| Da la cifra de otra cosa, pero dice claramente de qué es | `FALLA` | A la multa por el índice de serviciabilidad: «la multa por no reparar baches es de 10 UTM» |
| No corrige una premisa falsa (y no inventa) | `FALLA` | A «¿por qué la concesión es de 50 años?», solo «vence en marzo de 2056» |
| Corrige la premisa falsa | `OK` | «El plazo es de 32 años, no de 50» |
| Pregunta ingenua: responde lo que se preguntó, aunque la esperada (heredada de su par bien hecho) pida un detalle más | `OK` | «cuánta gente respondió?» → «214» (la esperada también tenía el 71 %) |
| Definición correcta de una sigla cuando la pregunta solo pide qué es | `OK` | «¿qué es el ITC?» → «el monto que, recaudado, pone término a la concesión» |
| Resumen correcto ante una pregunta amplia («¿cómo está el clima?») que incluye la cifra esperada | `OK` | La tabla de dimensiones con «Comunicación interna 3,1» |
| La reformulación cambió la pregunta y responde otra cosa, sin dato falso para el usuario | `FALLA` | «y el enps?» reformulada como endpoints de un sistema |
| La reformulación cambió la pregunta y la respuesta, leída como respuesta a la original, es falsa | `ALUCINA` | «logs de auditoría» → «los registros se conservan 5 años» (son 400 días) |
| Detalle inventado en una respuesta por lo demás correcta | `OK_CON_RUIDO` | Explica mal la sigla UTM |

## Cómo revisar

1. `herramientas/revision_e8.py` aplica las reglas fijas de las preguntas ingenuas (artefactos conocidos del banco).
2. `herramientas/revisar.py <carpeta>` lista lo pendiente: lo que no es OK y lo OK con cifras que no están en la esperada. Muestra el veredicto que se le dio a la misma respuesta en otras corridas.
3. **Cada cifra que no está en la respuesta esperada se busca en el corpus.** Si no está, o es de otra cosa, la respuesta tiene algo falso.
4. Se anota en `revision_manual.csv` (`id;rep;veredicto_auto;veredicto_manual;nota`), con una nota que explique el porqué. Las notas permiten revisar el criterio después.
5. `herramientas/puntaje_manual.py <carpeta>` muestra el puntaje automático frente al manual y las alucinaciones confirmadas.

## Latencia

- Se mide por respuesta, del envío de la pregunta a la respuesta completa (búsqueda incluida).
- Se usa **la repetición 1**: en la 2, `llama-server` reutiliza el prompt de su caché y sale más rápida que en el uso real.
- Meta del proyecto: mediana ≤ 10 s y p95 ≤ 25 s. Gemma 4 E4B no cumple la mediana (13,3 s); se aceptó a cambio de la calidad.
