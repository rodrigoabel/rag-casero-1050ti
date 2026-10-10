# El corpus ficticio y el banco de preguntas

**Todo es inventado:** empresas, personas, cifras y contratos. Así el modelo no puede «saber» las respuestas de antemano: si responde bien, es porque las recuperó del RAG. Y se puede publicar.

Lo genera `herramientas/generar_corpus.py` (con `python-docx`, `python-pptx`, `fpdf2` y `Pillow`); no conviene editar a mano los documentos ni `preguntas.json`, porque salen de ese mismo script.

## Los documentos

Cada uno corresponde a una persona de la familia y a un formato que el RAG tiene que leer:

| Documento | Formato y camino de conversión | Para | Preguntas |
|---|---|---|---|
| Informe jurídico de la concesión «Ruta Costera Sur» | PDF digital, con tablas (plazos, tarifas, garantías, multas) | Abogado de concesiones públicas | `CRS-*` (16) |
| Minuta de reunión de la concesión | Word en la raíz de `Mi_RAG` (lo convierte AnythingLLM) | Abogado | `MIN-*` (4) |
| Informe de clima laboral 2026, Fundición Los Arrayanes | Word (MarkItDown), con tablas por dimensión y área | Psicólogo organizacional | `CLI-*` (10) |
| Acta del taller de liderazgo | **PDF escaneado** (imagen con ruido, requiere OCR) | Psicólogo organizacional | `ACT-*` (4) |
| Procedimiento PO-FLS-014, sangrado del horno flash | PDF digital, con tabla de parámetros | Ingeniero metalurgista del cobre | `PRO-*` (10) |
| Indicadores de proceso Q3 2026 de la fundición | **PowerPoint**, con tablas, gráfico y notas del orador | Ingeniero metalurgista | `FUN-*` (9) |
| Especificación técnica de la Plataforma Cóndor | Word (MarkItDown), con historial de versiones | Ingeniero de software | `CON-*` (12) |
| Retrospectiva del Sprint 42 del equipo Cóndor | **PowerPoint**, con gráfico de bugs y notas del orador | Ingeniero de software | `SPR-*` (8) |
| Notas de Obsidian (proyecto, decisión de arquitectura, diario, persona, lugar, receta…) | Markdown con frontmatter, callouts, tareas y enlaces | Ingeniero de software | `OBS-*` (12) |

**Carpetas** (`corpus/`):
- `usuario1/Mi_RAG/`: los 8 documentos que se suben al espacio `rag-eval`. `office/` y `pdf/` reproducen las carpetas del servidor, donde cada subcarpeta usa un conversor distinto (hallazgo H9).
- `usuario1/Obsidian_Vault/…`: las notas, para un espacio de notas.
- `usuario2/Mi_RAG/`: un documento con una palabra clave, para comprobar que un usuario no ve los documentos de otro (F7).
- `cambios/`: versiones modificadas de dos archivos, para medir la actualización (F6).

## Las preguntas

`preguntas/preguntas.json` (y la misma tabla en `preguntas.csv`): **163 preguntas**, cada una con su respuesta esperada.

| Fase | Preguntas | Qué mide |
|---|---|---|
| **F2-F3** | 89 (77 sobre documentos y 12 sobre notas) | Preguntas bien hechas: con el nombre del documento y las palabras exactas |
| **F4** | 16 (8 pares) | La misma pregunta, ingenua y bien hecha («multa?» frente a «según el informe jurídico…, ¿cuál es la multa diaria por…?») |
| **E8** | 35 | Ingenuas, escritas como en Telegram por cada persona de la familia |
| **E8b** | 16 | Ingenuas nuevas, escritas **después** de ajustar el reformulador, para detectar sobreajuste |
| **F6** | 4 | Actualización: la respuesta cambia al reemplazar un documento |
| **F7** | 3 | Aislamiento: la palabra clave de `usuario2` no debe aparecer en los espacios de `usuario1` |

**Tipos de pregunta en F2-F3** (las trampas están a propósito):

| Tipo | Cuántas | Qué pone a prueba |
|---|---|---|
| `factual` | 34 | Un dato puntual |
| `tabla` | 10 | Leer la fila y la columna correctas |
| `parafrasis` | 6 | Preguntar con otras palabras que las del documento |
| `rechazo` | 5 | El dato no existe: debe decir que no está |
| `sintesis`, `profundo`, `cruce` | 4, 2, 4 | Juntar varias partes o varios documentos |
| `ocr` | 4 | Leer el PDF escaneado |
| `notas_orador`, `grafico` | 3, 1 | Lo que en una presentación no está en las diapositivas |
| `metadatos` | 3 | Quién firma o aprueba un documento y cuándo |
| `frontmatter`, `callout`, `tareas`, `enlaces` | 2, 1, 1, 1 | Partes especiales de las notas de Obsidian |
| `version` | 2 | Dar el valor vigente, no el de una versión antigua (o distinguir el borrador del contrato final) |
| `calculo` | 2 | Un porcentaje y un promedio a partir de datos del documento |
| `premisa_falsa`, `distractor` | 1, 1 | «¿Por qué la concesión es de 50 años?» (son 32); dos garantías parecidas en el mismo documento |
| `idioma`, `personal` | 1, 1 | Una pregunta en inglés sobre un documento en español; una nota personal (una receta) |

27 preguntas forman el **subconjunto rápido** (`--rapida`), para pruebas de humo. 12 esperan un rechazo.

**Campos de cada pregunta:**

| Campo | Para qué |
|---|---|
| `id`, `fase`, `tipo`, `dificultad` | Identificación y clasificación |
| `workspace` | `mirag` (documentos, va a `--ws-mirag`), `obsidian` (notas) o `usuario2` |
| `pregunta`, `respuesta_esperada` | Lo que se pregunta y lo que debería responder |
| `requeridas` | Grupos de términos que la respuesta debe contener; cada grupo acepta variantes (`[["1.200", "1200"], ["12 meses"]]`) |
| `prohibidas` | Términos que delatan un error (la cifra de al lado, la versión antigua) |
| `fuente_esperada`, `evidencia` | Documento y frase que deben aparecer entre los fragmentos recuperados: separan errores de búsqueda de errores del modelo |
| `espera_rechazo` | El dato no existe: lo correcto es decir que no está |
| `par`, `variante` | En F4 y en las ingenuas, la pregunta bien hecha con que se compara |
| `rapida`, `revision_manual`, `notas` | Subconjunto rápido, aviso para revisar a mano y comentarios |

## Generar y verificar

```bash
python3 -m venv .venv && .venv/bin/pip install -r herramientas/requirements.txt
.venv/bin/python herramientas/generar_corpus.py     # corpus/ y preguntas/
.venv/bin/python herramientas/verificar_corpus.py   # convierte como el servidor y comprueba cada respuesta esperada
```

- `generar_corpus.py` usa la fuente DejaVu; si no está en `/usr/share/fonts/TTF`, indica la carpeta con la variable `CORPUS_FUENTES`.
- `verificar_corpus.py` deja en `vista_previa_conversion/` el texto exacto que verá el RAG de cada documento. Ahí se buscan las cifras al revisar a mano.
