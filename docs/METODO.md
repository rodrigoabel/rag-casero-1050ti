# Método: cómo evaluar un modelo nuevo

Este es el procedimiento con que se compararon Qwen 3.5 2B, Qwen 3.5 4B, Gemma 4 E2B y Gemma 4 E4B (experimento E6). Sirve para cualquier modelo de Ollama que salga después: se mide con el mismo corpus, las mismas preguntas y el mismo criterio de revisión, así que el resultado se puede poner al lado de los de [RESULTADOS.md](RESULTADOS.md).

**Tiempo:** ~1 h de corridas por modelo (con ~13 s por respuesta) y ~30–60 min de revisión manual.

**Regla de oro: un experimento a la vez,** con un respaldo antes y volviendo a la configuración de referencia al terminar.

## 0. Requisitos

- AnythingLLM (probado con 1.17) con Ollama como proveedor de modelos, y una clave de API (Configuración → Herramientas → API Keys).
- Python 3. Las herramientas de medición usan solo la biblioteca estándar. Para el corpus y los gráficos: `python3 -m venv .venv && .venv/bin/pip install -r herramientas/requirements.txt`.
- Variables de entorno:

```bash
export ANYTHINGLLM_URL=http://<servidor>:3001/api/v1
export ANYTHINGLLM_API_KEY=<tu clave>     # o en ~/.config/prueba_rag/api_key (chmod 600)
export OLLAMA_URL=http://<servidor>:11434
export RAG_SERVIDOR_SSH=usuario@<servidor> # solo para la comprobación de respaldo de rag_config.py
```

## 1. Preparar el banco de pruebas (una sola vez)

1. **Los documentos.** Sube a AnythingLLM los 8 archivos de `corpus/usuario1/Mi_RAG/` (Word, PowerPoint, PDF digital y escaneado). Si quieres regenerarlos: `.venv/bin/python herramientas/generar_corpus.py`, y luego `.venv/bin/python herramientas/verificar_corpus.py` para comprobar que cada respuesta esperada sobrevive a la conversión a texto.
2. **El espacio `rag-eval`,** solo con esos 8 documentos. Que no tenga nada más: un documento grande ajeno ocupa los puestos de la búsqueda y falsea la medición (hallazgo H14 en [RESULTADOS.md](RESULTADOS.md#e2-topn-umbral-y-reordenador)).
3. **La configuración de referencia** (la de todas las mediciones de E6 en adelante):

| Ajuste | Valor |
|---|---|
| Modelo de vectores (global) | `multilingual-e5-small` (nativo de AnythingLLM) |
| Modo de chat | `query` |
| Prompt del sistema | `experimentos/E1c_prompt_sistema_es.txt` |
| Temperatura | 0,2 |
| Mensaje de rechazo | `experimentos/E1_respuesta_rechazo_es.txt` |
| topN / umbral de similitud | 10 / 0,2 |
| Búsqueda | `rerank` (reordenador) |
| Contexto de Ollama | 16.384 tokens (el que envía AnythingLLM) |
| Troceo | 1.000 caracteres con 20 de solapamiento (el de fábrica) |

   Se aplica desde la web o con `rag_config.py` (ver el paso 3).
4. **Comprueba la conexión:** `python3 herramientas/rag_eval.py estado --ws-mirag rag-eval`.

## 2. Preparar el modelo candidato

1. **Descárgalo:** `ollama pull <modelo>` (Q4_K_M es un buen punto de partida para 4 GB).
2. **Crea la variante «solo texto».** Muchos modelos nuevos traen un proyector de visión (y de audio) de hasta ~1 GB que Ollama carga aunque no se use. AnythingLLM no envía imágenes al modelo de respuesta, así que sobra:

```bash
bash experimentos/crear_variante_texto.sh <modelo> <modelo>-texto --simular   # muestra qué cambia
bash experimentos/crear_variante_texto.sh <modelo> <modelo>-texto             # repartido si no cabe
bash experimentos/crear_variante_texto.sh <modelo> <modelo>-texto-gpu --gpu   # todas las capas en la GPU
```

3. **Mide si cabe y cuánto tarda,** con prompts reales del RAG y sin tocar AnythingLLM:

```bash
python3 herramientas/medir_velocidad.py <modelo>-texto-gpu --n 5
```

   - Debe decir **100 % en la GPU**. Si no, usa la variante sin `--gpu` (más lenta) o un modelo más chico.
   - **Latencia esperada ≈ 3.400 tokens ÷ lectura (tok/s) + respuesta ÷ generación (tok/s)**. Con Gemma 4 E4B: 3.400 ÷ 290 ≈ 12 s, más ~1 s de búsqueda.
   - `--num-batch 1024` prueba lotes más grandes al leer el contexto. En la GTX 1050 Ti no aceleró y usó 176 MiB más.

## 3. Asignar el modelo solo a `rag-eval`

Crea un archivo de experimento (hay ejemplos en `experimentos/E6*.json`):

```json
{"descripcion": "E6x: <modelo> solo en rag-eval",
 "workspaces": ["rag-eval"],
 "cambios": {"chatModel": "<modelo>-texto-gpu"}}
```

```bash
python3 herramientas/rag_config.py aplicar experimentos/E6x_<modelo>.json --simular   # qué cambiaría
python3 herramientas/rag_config.py aplicar experimentos/E6x_<modelo>.json              # aplica y verifica
```

- `aplicar` guarda antes la configuración actual en `resultados/<fecha>_config_antes_<experimento>.json` y anota el cambio en `resultados/cambios_config.log`.
- Exige un respaldo reciente del servidor (servicio `respaldo-config.service`, por `ssh`). Si respaldas de otra forma, hazlo y usa `--sin-respaldo`.
- **Un modelo por vez en la GPU:** si otros espacios usan otro modelo, Ollama descarga uno y carga el otro en cada cambio. No uses el RAG para otra cosa mientras corre la medición.

## 4. Correr las tres mediciones

```bash
bash experimentos/E6_medir.sh <etiqueta>      # p. ej. gemma4-e4b
```

Hace, una tras otra (las mismas corridas de todas las referencias):

| Corrida | Preguntas | Repeticiones | Mide |
|---|---|---|---|
| `completo` | F3 (89 bien hechas) y F4 (8 pares ingenua/bien hecha), más la búsqueda sin modelo | 2 | Calidad con preguntas bien hechas, latencia |
| `chat --fase E8,F4` | 35 ingenuas de E8 + 8 ingenuas de F4 | 2 | Preguntas como las escribe la familia |
| `chat --fase E8b` | 16 ingenuas nuevas (escritas después, para no sobreajustar) | 3 | Lo mismo, con preguntas que nadie vio al ajustar |

Cada corrida queda en `resultados/<fecha>_<etiqueta>/` con `chat.csv`, `chat.jsonl` (la respuesta completa de la API) y `resumen.md`. Las preguntas de notas de Obsidian van a otro espacio: **solo se cuentan las filas de `rag-eval`**.

## 5. Revisar a mano

El puntaje automático (`veredicto` en `chat.csv`) busca las palabras requeridas de la respuesta esperada. No detecta una cifra falsa con la cita correcta, ni una respuesta correcta escrita de otra forma. Por eso se revisa a mano, con [los criterios](CRITERIOS_REVISION.md):

1. En las corridas de ingenuas, aplica las reglas fijas de E8 (artefactos conocidos del banco):

```bash
python3 herramientas/revision_e8.py resultados/<fecha>_<etiqueta>-E8chat-ingenua resultados/<fecha>_<etiqueta>-E8bchat-ingenua
```

2. Para cada corrida, arma la hoja de revisión:

```bash
python3 herramientas/revisar.py resultados/<carpeta> > hoja.md
```

   Lista las respuestas que no son OK y las OK con cifras que no están en la esperada. Si una respuesta idéntica ya se revisó en otra corrida, muestra su veredicto («PREVIO») para mantener el criterio.
3. **Busca cada cifra extra en el corpus** (en `vista_previa_conversion/`, que genera `verificar_corpus.py`, o en `herramientas/generar_corpus.py`). Una cifra que no está, o que es de otra cosa, es una respuesta falsa.
4. Anota los cambios en `resultados/<carpeta>/revision_manual.csv`:

```
id;rep;veredicto_auto;veredicto_manual;nota
SPR-08;1;FALLA;PARCIAL;No calcula el porcentaje: da 38 puntos de 45 comprometidos (≈ 84 %)
```

## 6. Comparar

```bash
python3 herramientas/comparar_modelos.py \
  "Gemma 4 E4B=resultados/20261010-0228_E6-gemma-e4b-rageval,resultados/20261010-0306_E6-gemma-e4b-E8chat-ingenua,resultados/20261010-0325_E6-gemma-e4b-E8bchat-ingenua" \
  "nuevo=resultados/<completo>,resultados/<E8chat>,resultados/<E8bchat>"
```

Para sumarlo a los gráficos, agrega sus tres carpetas a `CONFIGS` (y su nombre a `MODELOS`) en `herramientas/graficos.py` y corre `.venv/bin/python herramientas/graficos.py`.

**Cómo leer la comparación:**
- **Ruido:** la misma corrida repetida varía ±1 punto en las ingenuas (5 repeticiones del 2B: 67 ± 1 %). Diferencias de 3 puntos o más son reales.
- **Lo que más pesa es «con algo falso»** (alucinaciones y respuestas correctas con un detalle inventado): para un abogado o un ingeniero, una cifra falsa cuesta más que unos segundos de espera.
- Después, las **ingenuas** (como pregunta la gente) y los **rechazos correctos** (que no invente cuando el dato no está; 8 preguntas).
- La **latencia** es la de la repetición 1: en la 2, `llama-server` reutiliza el prompt de su caché y sale más rápida que en el uso real.

## 7. Volver a la referencia

```bash
python3 herramientas/rag_config.py revertir --a resultados/<fecha>_config_antes_E6x_<modelo>.json
```

## 8. Pasar a producción (si gana)

1. Respaldo.
2. Cambia el modelo global: en la web (Configuración → LLM) o con la API, `POST /v1/system/update-env` con `{"OllamaLLMModelPref": "<modelo>"}`. No hace falta reiniciar el contenedor.
3. Quita los `chatModel` fijos de los espacios, para que todos usen el mismo modelo (dos modelos de respuesta no caben juntos en 4 GB).
4. Prueba de humo: `python3 herramientas/rag_eval.py chat --rapida --etiqueta humo` (26 preguntas).
5. Si las consultas llegan por la API (un bot, por ejemplo), envía un `sessionId` nuevo por pregunta: sin él, AnythingLLM agrega las consultas anteriores al prompt (ver [ARQUITECTURA.md](ARQUITECTURA.md#el-bot-y-el-historial-de-la-api)).

## Variantes del método

- **Cambiar otro ajuste** (topN, prompt, umbral): el mismo camino, con el ajuste en `cambios` del experimento. Ejemplos: `experimentos/E6d_gemma4_e4b_topn6.json`, `E1c.json`.
- **Probar un reformulador de preguntas** (E8): `herramientas/reformular.py` genera las preguntas reformuladas y `rag_eval.py --reformuladas <archivo>` las usa en lugar de las originales. Las reformulaciones de Qwen 3.6 35B están guardadas en `experimentos/E8*_q35b_*.json`, así que se pueden medir con otro modelo de respuesta sin volver a generarlas.
- **Probar topN y umbral sin el modelo** (E2): `rag_eval.py recuperacion --topn 50 --umbral 0` y `herramientas/simular_busqueda.py`, que reproduce la búsqueda de AnythingLLM para cualquier combinación.
- **Probar otro modelo de vectores sin tocar el servidor** (E3, E9): `herramientas/simular_embedder.py` reproduce la búsqueda en el PC con los mismos modelos ONNX.

## Errores que conviene evitar

- **Pasar los argumentos dentro de una variable en zsh** (`$EVAL $ARGS`): zsh no la separa en palabras y la corrida puede ignorar el argumento sin avisar. Pasó con `--reformuladas`; por eso `rag_eval.py` ahora rechaza argumentos sobrantes.
- **Medir en un espacio con otros documentos:** cambia qué fragmentos llegan al modelo.
- **Confiar en el puntaje automático** para decidir entre dos configuraciones parecidas.
- **Cambiar el modelo de vectores sin volver a asignar los documentos:** en AnythingLLM 1.17 borra todas las asignaciones de todos los espacios (ver `herramientas/cambiar_embedder.py`).
