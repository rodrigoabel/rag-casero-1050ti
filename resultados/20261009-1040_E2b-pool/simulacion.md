# Simulación de topN y umbral: 20261009-1040_E2b-pool

100 preguntas con dato exacto definido. Largo máximo de la lista: 15 fragmentos.

## Workspace `rag-eval` (89 preguntas)

**Dato exacto entre los fragmentos que llegarían al modelo**

| topN \ umbral | 0 | 0.1 | 0.2 | 0.3 | texto enviado (car., umbral 0) |
|---|---|---|---|---|---|
| 4 | 85 % | 85 % | 84 % | 82 % | 3.855 |
| 6 | 87 % | 87 % | 85 % | 83 % | 5.774 |
| 8 | 87 % | 87 % | 85 % | 83 % | 7.756 |
| 10 | 87 % | 87 % | 85 % | 83 % | 9.514 |
| 15 | 87 % | 87 % | 85 % | 83 % | 9.514 |
| 20 | 87 % | 87 % | 85 % | 83 % | 9.514 |

**Techo** (el dato está en algún lugar de los candidatos): 87 %. Lo que no está ahí no lo arregla ningún topN: es problema del embedder o del troceo (E3, E4).

**Por formato** (umbral 0,2)

| Formato | n | topN 4 | topN 6 | topN 8 | topN 10 | topN 15 | topN 20 | techo |
|---|---|---|---|---|---|---|---|---|
| Cruce de documentos | 4 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % |
| Formulación | 16 | 81 % | 81 % | 81 % | 81 % | 81 % | 81 % | 88 % |
| PDF digital | 24 | 83 % | 88 % | 88 % | 88 % | 88 % | 88 % | 88 % |
| PDF escaneado (OCR) | 4 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % |
| PowerPoint | 17 | 65 % | 65 % | 65 % | 65 % | 65 % | 65 % | 65 % |
| Word (MarkItDown) | 20 | 95 % | 95 % | 95 % | 95 % | 95 % | 95 % | 95 % |
| Word (raíz, parser AnythingLLM) | 4 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % |

**Dónde quedó el dato** (posición en la lista completa; «—» = no está entre los candidatos)

- **1–4:** 76
- **5–10:** 1 (CRS-11)
- **11–20:** 0
- **21+:** 0
- **—:** 12 (CRS-03, CRS-12, PRO-07, FUN-01, FUN-03, FUN-04, FUN-05, FUN-07, FUN-08, CLI-07, FORM-03a, FORM-07a)

## Workspace `notas-obsidian` (11 preguntas)

**Dato exacto entre los fragmentos que llegarían al modelo**

| topN \ umbral | 0 | 0.1 | 0.2 | 0.3 | texto enviado (car., umbral 0) |
|---|---|---|---|---|---|
| 4 | 100 % | 100 % | 100 % | 100 % | 2.601 |
| 6 | 100 % | 100 % | 100 % | 100 % | 3.840 |
| 8 | 100 % | 100 % | 100 % | 100 % | 4.963 |
| 10 | 100 % | 100 % | 100 % | 100 % | 5.456 |
| 15 | 100 % | 100 % | 100 % | 100 % | 6.462 |
| 20 | 100 % | 100 % | 100 % | 100 % | 6.462 |

**Techo** (el dato está en algún lugar de los candidatos): 100 %. Lo que no está ahí no lo arregla ningún topN: es problema del embedder o del troceo (E3, E4).

**Por formato** (umbral 0,2)

| Formato | n | topN 4 | topN 6 | topN 8 | topN 10 | topN 15 | topN 20 | techo |
|---|---|---|---|---|---|---|---|---|
| Obsidian | 11 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % |

**Dónde quedó el dato** (posición en la lista completa; «—» = no está entre los candidatos)

- **1–4:** 11
- **5–10:** 0
- **11–20:** 0
- **21+:** 0
- **—:** 0

