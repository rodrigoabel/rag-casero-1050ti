# Resultados

Una carpeta por corrida de `herramientas/rag_eval.py`: `resultados/<AAAAMMDD-HHMM>_<etiqueta>/`. Las corridas nuevas se crean aquí mismo. Solo están las corridas sobre el espacio `rag-eval` (corpus ficticio) y, dentro de ellas, solo las filas de ese espacio: las preguntas sobre notas de Obsidian iban a otro espacio y se quitaron. En unas pocas preguntas reformuladas, el reformulador nombró un documento personal que estaba en el mapa de temas del espacio principal; ese nombre se reemplazó por «[un documento personal]».

## Archivos de cada corrida

| Archivo | Qué tiene |
|---|---|
| `config.json` | La configuración de `rag-eval` en ese momento (modelo, prompt, topN, umbral…), el modelo de vectores y los argumentos de la corrida |
| `chat.csv` | Una fila por respuesta: `id`, `rep`, `veredicto` automático, `segundos`, tokens, `pregunta`, `esperada`, `respuesta` (recortada a 600 caracteres) y `citas` (documentos citados) |
| `respuestas.jsonl` | La respuesta completa, la pregunta enviada (la reformulada, si la hubo) y las fuentes con su puntaje. Sin el texto de los fragmentos |
| `recuperacion.csv` | La búsqueda sin el modelo: si el documento y el dato exacto estaban entre los fragmentos, y en qué posición |
| `revision_manual.csv` | Los veredictos corregidos a mano, con una nota que explica cada uno ([criterios](../docs/CRITERIOS_REVISION.md)) |

Para el puntaje con la revisión manual: `python3 herramientas/puntaje_manual.py resultados/<carpeta>`.

## Qué corrida es cada cosa

| Configuración | Bien hechas (`completo`) | Ingenuas E8 y F4 | Ingenuas E8b |
|---|---|---|---|
| Qwen 3.5 2B, E1c, vectores MiniLM | `20261009-1044_base-E1c-rageval` | — | — |
| Qwen 3.5 2B, E1e (descartado) | `20261009-1108_E1e-rageval` | — | — |
| **Qwen 3.5 2B, E1c, e5-small (referencia)** | `20261009-1156_base-E3-rageval` | `20261009-1309_E8chat-ingenua` (y `-rep2` a `-rep5`, para medir el ruido) | `20261009-1551_E8bchat-ingenua` |
| Qwen 3.5 2B + reformulador Qwen 3.6 35B (v1) | `20261009-1437_E8chat-F3-q35b_mapa` | `20261009-1356_E8chat-q35b_mapa` | `20261009-1554_E8bchat-q35b_v1_mapa` |
| Otros reformuladores | `*_E8chat-F3-*` | `*_E8chat-q35b_*`, `*_E8chat-qwen2b_*`, `*_E8chat-q38_*` | `*_E8bchat-*` |
| Qwen 3.5 4B | `20261010-0037_E6-qwen4b-rageval` | `20261010-0115_E6-qwen4b-E8chat-ingenua` | `20261010-0133_E6-qwen4b-E8bchat-ingenua` |
| Gemma 4 E2B | `20261010-0145_E6-gemma-e2b-rageval` | `20261010-0211_…` | `20261010-0222_…` |
| **Gemma 4 E4B (elegido)** | `20261010-0228_E6-gemma-e4b-rageval` | `20261010-0306_E6-gemma-e4b-E8chat-ingenua` | `20261010-0325_E6-gemma-e4b-E8bchat-ingenua` |
| Gemma 4 E4B, topN 6 | `20261010-0705_E6-gemma-e4b-topn6-rageval` | `20261010-0733_…` | `20261010-0747_…` |
| Gemma 4 E4B, topN 8 | `20261010-0803_E6-gemma-e4b-topn8-rageval` | `20261010-0837_…` | `20261010-0853_…` |
| Gemma 4 E4B + reformulador | `20261010-1242_E6f-gemma-e4b-F3chat-q35b_mapa` | `20261010-1217_E6f-…` | `20261010-1235_E6f-…` |

**Solo búsqueda** (sin el modelo): `*_E2b-pool` (50 candidatos por pregunta, para simular topN y umbral), `*_E3-rageval` (con e5-small) y `*_E8rec-*` / `*_E8brec-*` (preguntas reformuladas).

## Tablas

- `tablas/metricas.csv`: las cifras de cada configuración (las genera `herramientas/graficos.py`).
- `tablas/rendimiento_modelos.csv`: velocidad y VRAM de cada modelo en la GTX 1050 Ti, de los registros de Ollama y `herramientas/medir_velocidad.py`.
