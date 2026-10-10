#!/usr/bin/env python3
"""Puntaje automático frente a manual de una corrida de rag_eval.py.

Lee <carpeta>/chat.csv y, si existe, <carpeta>/revision_manual.csv (id;rep;veredicto_auto;veredicto_manual;nota),
que corrige los veredictos revisados a mano. Muestra el puntaje por conjunto, formato y tipo, y lista las
alucinaciones confirmadas.

Uso (desde la carpeta del proyecto): python3 herramientas/puntaje_manual.py resultados/<carpeta>
"""
import csv, json, sys
from pathlib import Path
from collections import defaultdict
carpeta = sys.argv[1]
PUNTOS = {"OK": 2, "RECHAZO_OK": 2, "OK_CON_RUIDO": 1, "PARCIAL": 1, "FALLA": 0, "RECHAZO_FALSO": 0, "ALUCINA": 0, "ERROR": 0}
P = {q['id']: q for q in json.load(open(Path(__file__).resolve().parents[1] / 'preguntas' / 'preguntas.json', encoding='utf-8'))}
r = list(csv.DictReader(open(f'{carpeta}/chat.csv', encoding='utf-8-sig'), delimiter=';'))
try:
    rev = {(x['id'], x['rep']): x['veredicto_manual'] for x in csv.DictReader(open(f'{carpeta}/revision_manual.csv', encoding='utf-8-sig'), delimiter=';')}
except FileNotFoundError:
    rev = {}
for x in r:
    x['man'] = rev.get((x['id'], x['rep']), x['veredicto'])
    x['fase'] = P[x['id']]['fase']; x['rapida'] = P[x['id']]['rapida']
def pct(rows, campo):
    s = [PUNTOS[x[campo]] for x in rows if x[campo] in PUNTOS]
    return f"{sum(s)}/{2*len(s)} ({100*sum(s)/max(1,2*len(s)):.0f} %)"
grupos = {"Todo": r, "F3 (89 preguntas)": [x for x in r if x['fase']=='F2-F3'], "F4 formulación": [x for x in r if x['fase']=='F4'],
          "Subconjunto rápido (26)": [x for x in r if x['rapida']]}
print("| Conjunto | Automático | Manual |\n|---|---|---|")
for n, g in grupos.items():
    if g: print(f"| {n} | {pct(g,'veredicto')} | {pct(g,'man')} |")
F3 = grupos["F3 (89 preguntas)"]
for clave in ('formato', 'tipo'):
    d = defaultdict(list)
    for x in F3: d[x[clave]].append(x)
    print(f"\n| {clave} (F3) | Automático | Manual |\n|---|---|---|")
    for k in sorted(d): print(f"| {k} | {pct(d[k],'veredicto')} | {pct(d[k],'man')} |")
from collections import Counter
print("\nVeredictos manuales (F3):", dict(Counter(x['man'] for x in F3)))
print("Alucinaciones (manual):", sorted({f"{x['id']} r{x['rep']}" for x in r if x['man']=='ALUCINA'}))
