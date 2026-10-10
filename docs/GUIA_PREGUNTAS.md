# Cómo preguntarle a tu RAG (modelo pequeño)

> **Escrita para Qwen 3.5 2B** (9/10/2026), el modelo con que empezaron las pruebas. Con **Gemma 4 E4B** las preguntas ingenuas ya funcionan bien (95 %, [E6](RESULTADOS.md#e6-modelos-de-respuesta)), pero las reglas siguen ayudando, y los límites de la tabla final (cálculos, cifras parecidas, listas completas) valen para cualquier modelo.

Esta guía es el punto de partida: la fase **F4** del plan mide qué reglas ayudan de verdad con tu configuración, y conviene actualizarla con lo que salga.

## La idea clave

El modelo **no lee tus documentos completos**. Cuando preguntas, pasa esto:

1. Tu pregunta se convierte en un vector y se buscan los **4 a 10 trozos de ~1.000 caracteres** más parecidos (≈ 1 a 3 párrafos cada uno).
2. Solo esos trozos, más tu pregunta, llegan al modelo de respuesta.
3. El modelo responde con eso. Si el trozo con la respuesta no llegó, no puede responder bien (o inventa).

Por eso, **la pregunta tiene que parecerse al texto del documento**. Y como el modelo es pequeño, la tarea tiene que ser **simple y explícita**.

## 10 reglas

| # | Regla | Por qué |
|---|---|---|
| 1 | **Usa las palabras del documento**: nombres propios, códigos, siglas y términos técnicos tal como aparecen | La búsqueda compara palabras y significado; los nombres exactos son la mejor pista |
| 2 | **Nombra el documento o el tema**: "según el informe jurídico de la Ruta Costera Sur…" | Evita que traiga trozos de otro documento parecido |
| 3 | **Una pregunta por mensaje** | Con dos preguntas, la búsqueda trae trozos para una sola y el modelo mezcla |
| 4 | **Pide el formato solo si hace falta, y corto**: "en 3 viñetas", "con número y unidad" | Las instrucciones también entran en la búsqueda y pueden alejarla del dato. `FORM-02b`, con "Responde solo con el monto y la unidad", trajo el documento correcto, pero no el párrafo de la multa |
| 5 | **No agregues "si no aparece, dilo" ni "copia la frase"** | Medido en el E0 (9/10): el puntaje bajó de 75 % a 63 %. El modelo dijo "no aparece" cuando sí estaba, se contradijo ("no aparece… 14 supervisores") y la búsqueda empeoró. Decir "no está" es tarea del prompt del sistema |
| 6 | **Evita "resúmeme todo"** sobre documentos largos; pide **una sección** concreta | El modelo solo ve unos pocos trozos, no el documento entero |
| 7 | **Para comparar o calcular, primero pide los datos por separado**; haz tú el cálculo o pídele que muestre la operación | Los modelos de 2B se equivocan a menudo en aritmética y en cruzar varios datos |
| 8 | **Escribe las siglas completas la primera vez**: "Ingreso Total de la Concesión (ITC)" | La sigla sola puede no parecerse al texto |
| 9 | **Usa fechas absolutas**: "agosto de 2026", no "el mes pasado" | El modelo no sabe a qué te refieres |
| 10 | **Revisa las citas**: si no aparece el documento correcto, reformula con sus palabras | Te dice si el problema fue la búsqueda o el modelo |

## Ejemplos: ingenua frente a bien hecha

Son los pares de la fase F4 (`FORM-01` a `FORM-08`).

| Ingenua | Bien hecha | Qué cambió |
|---|---|---|
| ¿y el caché? | En la especificación técnica de la Plataforma Cóndor, ¿cuál es el TTL de la caché Redis? Responde con el número y la unidad. | Documento, término exacto (TTL, Redis), formato |
| multa? | Según el informe jurídico de la concesión Ruta Costera Sur, ¿cuál es la multa diaria por incumplir el índice de serviciabilidad? Responde solo con el monto y la unidad. | Hay varias multas: se precisa cuál |
| cuéntame del horno | Según el procedimiento PO-FLS-014 de sangrado del horno flash, ¿en qué rango debe estar la temperatura de la mata? | Código del documento y dato concreto |
| ¿cómo está el clima? | En el informe de clima laboral 2026 de la Fundición Los Arrayanes, ¿qué puntaje obtuvo la dimensión Comunicación interna? | Ambigüedad (¿meteorológico?) y dato concreto |
| dame todo lo de la concesión | Según el informe jurídico de la Ruta Costera Sur, indica en viñetas: plazo máximo de la concesión, plazo de construcción y fecha de puesta en servicio provisoria. | De "todo" a 3 datos con formato |
| ¿qué pasó con la planta de ácido? | En la presentación de indicadores Q3 2026 de la Fundición Los Arrayanes, ¿cuántas horas estuvo detenida la planta de ácido en agosto y por qué? | Contexto, período y dato |
| ¿quién es Tomás? | En la retrospectiva del Sprint 42 del equipo Cóndor, ¿de qué historias es responsable Tomás Rivas y en qué estado está cada una? | Nombre completo, documento y qué quieres saber de él |
| ¿qué es el ITC? | En el informe jurídico de la Ruta Costera Sur, ¿cuál fue el Ingreso Total de la Concesión (ITC) de la oferta adjudicada? | Sigla desarrollada y dato concreto |

## Lo que mostraron las primeras pruebas (9/10/2026)

- **Pregunta bien hecha = 7 de 8 veces llega el dato; pregunta ingenua = 1 de 8** (con el modelo de vectores antiguo).
  - **Desde E3 (9/10), las preguntas ingenuas también traen el dato:** 95–98 %.
  - **Pero el modelo las responde peor:** 67 % frente a 86 % con la pregunta bien hecha. Ante una pregunta vaga («multa?», «¿quién es Tomás?») suele decir «No encontré» aunque tenga el párrafo delante.
  - **Las reglas siguen valiendo,** ahora para que el modelo entienda qué responder.
- **Una cita correcta NO garantiza una respuesta correcta.** En dos casos el modelo citó el documento correcto y aun así inventó (invirtió una recomendación y dio una meta en lugar del valor real). Para cifras, montos, plazos y recomendaciones, **abre la cita y comprueba que el dato esté en el fragmento**.
- **Cuidado con términos de dominio con doble sentido:** "ley de mata" lo entendió como "norma". Escribe "ley de cobre de la mata (% Cu)". Lo mismo con siglas o palabras comunes con sentido técnico (garantía, plazo, factor, índice).
- **Distingue lo que preguntas:** "¿qué *dimensión* fue peor evaluada?" se confundió con "¿qué *área*?". Si el documento tiene varias cosas parecidas, nómbrala exactamente.
- **Las notas de Obsidian se responden muy bien** (10/10): son cortas y usan las mismas palabras que tus preguntas.
- **Las instrucciones dentro de la pregunta empeoran el resultado** (E0, 9/10). Agregar "si no aparece, dilo. Copia la frase que lo respalda" bajó el puntaje de 75 % a 63 %. La pregunta debe llevar solo lo que buscas, con las palabras del documento.

## Plantilla general

```
Según <documento o tema>, ¿<pregunta concreta con las palabras del documento>?
(Opcional, corto) Responde <en una frase / con número y unidad / en N viñetas>.
```

## Plantillas por profesión

**Ingeniería de software**
- "En la especificación de <sistema>, ¿qué <puerto, timeout, límite o rol> tiene <componente o endpoint>? Responde con el valor exacto."
- "Según el ADR-<número>, ¿qué alternativas se descartaron y por qué? Responde en viñetas."
- "En la retrospectiva del Sprint <N>, ¿qué historias quedaron bloqueadas y por qué?" (las notas del orador también se buscan)

**Derecho: concesiones públicas**
- "Según el contrato o informe de <concesión>, ¿cuál es el plazo de <construcción / concesión / garantía> y desde cuándo se cuenta?"
- "¿Qué multa establece <documento> por <incumplimiento concreto>? Indica monto, unidad y periodicidad."
- "¿Qué recomienda el informe sobre <tema> y con qué plazo?"
- Cuidado con los **plazos y montos parecidos**: pide siempre "cuál" (construcción frente a explotación, borrador frente a adjudicado).

**Psicología organizacional**
- "En el estudio de clima <año> de <empresa>, ¿qué puntaje obtuvo la dimensión <nombre exacto>?"
- "¿Qué área tuvo el puntaje más bajo en <dimensión> y qué explicación da el informe?"
- "¿Qué acuerdos se tomaron en el taller del <fecha>?" (funciona también con actas escaneadas)
- Para comparar años o áreas: primero pide cada dato por separado.

**Metalurgia del cobre**
- "Según el procedimiento <código>, ¿en qué rango debe estar <parámetro> y qué hacer si se sale del rango?"
- "En los indicadores de <período> de <planta>, ¿cuál fue <recuperación / captura de azufre / disponibilidad> y cuál era la meta?"
- "¿Qué EPP o distancia de seguridad exige el procedimiento <código> durante <operación>?"
- Las **cifras con unidades** (°C, %, Nm³/t, bar): pide "valor y unidad exactos".

## Cuando no responde bien

1. **Mira las citas.** ¿Aparece el documento correcto?
   - **No:** problema de **búsqueda**. Reformula con palabras exactas del documento (regla 1) o nombra el documento (regla 2).
   - **Sí, pero respondió mal:** problema del **modelo**. Simplifica: una sola pregunta, con las palabras exactas del documento y nombrando la cosa precisa ("la *dimensión*", no "lo peor evaluado").
2. **Dice "no hay información" y sabes que está.** Usa el término exacto del documento. Si aun así falla, anota la pregunta: es material para los experimentos E2 a E4.
3. **Da cifras distintas cada vez.** Es la temperatura: la configuración original usa 1,0 (hallazgo H5). El E1 la baja a 0,2. Mientras tanto, desconfía de las dos cifras y abre la fuente.
4. **Mezcla dos documentos.** Nombra el documento en la pregunta.
5. **Inventa.** Pregunta: "¿en qué documento y sección aparece eso?". Si no puede indicarlo, desconfía.

## Límites conocidos: dónde verificar siempre

> **Revisado el 9/10/2026 después de E3** (modelo de vectores multilingüe). La búsqueda ahora trae el párrafo correcto el 99 % de las veces, también en tablas y presentaciones. Lo que queda son errores del modelo al **leer** o **calcular**, no al buscar. Detalle en [RESULTADOS.md](RESULTADOS.md#e3-modelo-de-vectores-multilingüe).

| Caso | Qué pasa | Qué hacer |
|---|---|---|
| **Tablas** (indicadores mensuales en presentaciones, plazos y montos en PDF) | Ahora sí se encuentran, pero el modelo puede tomar la fila o la columna equivocada, o mezclar dos cifras. En las pruebas respondió «41.300 t», una cifra que no existe, en vez de 14.300 t (agosto) | Nombra el indicador, el mes y la planta tal como aparecen en la tabla. **Comprueba la cifra en la fuente** antes de usarla |
| **Cifras parecidas en el mismo documento** (dos plazos, dos montos, acumulado frente a umbral, valor frente a meta) | Puede dar la cifra de al lado: 380 UTM (lo acumulado) en vez de 1.200 UTM (el umbral), o la fecha de vencimiento en vez del plazo en años | Di exactamente cuál quieres. **Toda cifra que vayas a usar en un escrito, informe o decisión, compruébala en la fuente** (el bot la muestra en «Fuentes consultadas») |
| **Artículos, cláusulas o secciones numeradas vecinas** (reglamentos, contratos, bases) | Si dos artículos quedan en el mismo trozo, a veces responde con el de al lado: en las pruebas con un reglamento real dio el texto del séptimo artículo transitorio cuando se preguntó por el sexto (la misma pregunta, repetida, respondió bien dos veces) | Pregunta con el encabezado tal como está en el documento («SEXTO ARTÍCULO TRANSITORIO»). **Antes de citar un artículo, compruébalo en la fuente**: la respuesta puede variar de una vez a otra |
| **«¿En qué artículos, cláusulas o documentos aparece X?»** (listas completas) | El RAG solo lee unos 10 trozos: no puede asegurar que estén todos. Además, el modelo puede agregar a la lista un artículo que tenía a la vista pero que no menciona X: en las pruebas con un reglamento real respondió dos artículos y solo uno mencionaba el tema (el otro trataba del cómputo de plazos) | Para búsquedas exhaustivas, busca la palabra en el documento (Ctrl+F en el PDF). Usa el RAG para preguntar **qué dice** un artículo concreto, no para listar todos |
| **Cálculos** (porcentajes, promedios, sumas) | Se equivoca con seguridad: dio «38 %» en vez de 84 % (38 de 45) y la cifra de un mes como si fuera el promedio | **No le pidas cuentas.** Pide los datos por separado y haz tú el cálculo |
| **Juntar datos de dos documentos** en una pregunta | A veces trae solo uno o responde «No encontré» | Una pregunta por documento |
| **Preguntas con un dato falso** («¿por qué la concesión es de 50 años?») | Responde «No encontré» en vez de corregir (no inventa) | Pregunta sin suponer el dato: «¿cuál es el plazo de la concesión?» |
| **«No encontré esa información»** | Ya casi nunca es porque falte el párrafo: a menudo el modelo lo tenía y no lo reconoció (sobre todo con paráfrasis, notas del orador o listas de tareas) | Reformula con las palabras exactas del documento o nombra el documento. Si sigue igual, búscalo tú |
| **Documentos muy largos de otro tema en el mismo espacio** | Con el modelo de vectores nuevo pesan mucho menos (un reglamento de 200 fragmentos pasó de ocupar el 59 % al 27 % de lo que lee el modelo), pero siguen metiendo ruido | Mejor un espacio por tema o por persona. No mezcles documentos grandes de temas distintos |

**En resumen:** el RAG sirve para **encontrar** el dato y el documento. Para **usar** una cifra, un plazo o un monto, ábrelo en la fuente.

## Lo que un modelo de 2B hace bien y mal

| Bien | Regular o mal |
|---|---|
| Encontrar un dato puntual si la pregunta usa las palabras del documento | Resumir documentos largos completos |
| Leer una fila de una tabla | Comparar varias tablas o documentos a la vez |
| Responder "no está" cuando el prompt se lo pide | Calcular promedios o porcentajes |
| Seguir un formato simple (viñetas, una frase) | Entender preguntas vagas o con dobles sentidos |
