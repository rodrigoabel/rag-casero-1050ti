# Experimentos

Cada experimento es un archivo que describe **un solo cambio** y que `herramientas/rag_config.py` aplica, verifica y revierte:

```json
{"descripcion": "E6c: gemma4:e4b-texto-gpu solo en rag-eval",
 "workspaces": ["rag-eval"],
 "cambios": {"chatModel": "gemma4:e4b-texto-gpu"}}
```

Un valor que empieza con `@` se lee de un archivo de esta carpeta (`"openAiPrompt": "@E1c_prompt_sistema_es.txt"`). Los resultados y el análisis de cada uno están en [docs/RESULTADOS.md](../docs/RESULTADOS.md).

| Archivos | Experimento |
|---|---|
| `E0_correr.sh` | E0: instrucción al final de la pregunta (sin cambiar el servidor) |
| `E1*.json`, `E1*_prompt_sistema_es.txt`, `E1_respuesta_rechazo_es.txt`, `E1_correr.sh` | E1: prompt del sistema en español. **`E1c` es el que quedó** |
| `E5_Modelfile.qwen3.5-2b-rag` | E5 (no se corrió): muestreo más conservador para Qwen 3.5 2B |
| `E6_qwen35_4b.json`, `E6b_gemma4_e2b.json`, `E6c_gemma4_e4b.json` | E6: cada modelo de respuesta, solo en `rag-eval` |
| `E6d_gemma4_e4b_topn6.json`, `E6e_gemma4_e4b_topn8.json` | E6d y E6e: Gemma 4 E4B con topN 6 y 8 |
| `E6_medir.sh` | Las tres corridas de medición de un modelo ([método](../docs/METODO.md), paso 4) |
| `crear_variante_texto.sh` | Crea la variante «solo texto» de un modelo de Ollama ([método](../docs/METODO.md), paso 2) |
| `E8_mapa_mirag.md`, `E8_mapa_obsidian.md` | E8: mapas de temas para el reformulador (título y secciones de cada documento, sin cifras) |
| `E8_*.json`, `E8b_*.json` | E8: preguntas reformuladas, listas para `rag_eval.py --reformuladas` |
| `PROD_*.json` | Plantillas para dejar un espacio nuevo con la configuración de producción |

**Nombres de las preguntas reformuladas** (`E8[b]_<reformulador>_<variante>[_F3].json`):
- `E8_` reformula las ingenuas de E8 y F4; `E8b_`, las de E8b; `_F3`, las bien hechas (para comprobar que no empeoran).
- Reformulador: `q35b` = Qwen 3.6 35B-A3B (Q5), `q38` = Qwen 3.8 27B, `qwen2b` = Qwen 3.5 2B.
- Variante: `mapa` o `v1_mapa` (reglas v1 con mapa de temas, la aplicada), `v2_mapa`, `v3_mapa`, `sinmapa`, `auto` (mapa automático).
- Cada archivo guarda en `meta` el modelo, las reglas y el prompt usados, y por pregunta la original y la reformulada.
