#!/usr/bin/env python3
"""Arma una hoja de revisión manual a partir de un chat.csv de rag_eval.py.

Secciones:
  1. Filas no OK (ALUCINA, FALLA, RECHAZO_FALSO, PARCIAL, OK_CON_RUIDO, REVISAR, ERROR).
  2. Filas OK o RECHAZO_OK cuya respuesta trae cifras que no están en la respuesta esperada
     (posible H15: cifra inventada con la cita correcta).
  3. Preguntas cuyo veredicto cambia entre repeticiones.

Uso (desde la carpeta del proyecto):
  python3 herramientas/hoja_revision.py resultados/<carpeta> preguntas/preguntas.json > hoja.md
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

carpeta, preguntas_json = Path(sys.argv[1]), Path(sys.argv[2])
filas = list(csv.DictReader(open(carpeta / "chat.csv", encoding="utf-8-sig"), delimiter=";"))
preguntas = {q["id"]: q for q in json.load(open(preguntas_json, encoding="utf-8"))}

NUM = re.compile(r"\d+(?:[.,]\d+)*")


def cifras(texto):
    # normaliza 1.234,5 / 1,234.5 / 96,5 a solo dígitos para comparar sin importar el separador
    return {re.sub(r"[.,]", "", n) for n in NUM.findall(texto or "")}


def bloque(f, motivo=""):
    q = preguntas.get(f["id"], {})
    lineas = [f"### {f['id']} (rep {f['rep']}) · {f['veredicto']} · {f['tipo']} · {f['formato']}",
              ""]
    if motivo:
        lineas += [f"**Por qué se revisa:** {motivo}", ""]
    lineas += [f"- **Pregunta:** {f['pregunta']}",
               f"- **Esperada:** {f['esperada']}",
               f"- **Evidencia que debía llegar:** {', '.join(q.get('evidencia', [])) or '—'}",
               f"- **Diagnóstico automático:** {f['diagnostico'] or '—'}",
               f"- **Citas:** {f['citas'] or '—'}",
               "", "> " + (f["respuesta"] or "").replace("\n", "\n> "), "",
               "**Veredicto manual:** ___ · **Nota:** ___", ""]
    return "\n".join(lineas)


no_ok = [f for f in filas if f["veredicto"] not in ("OK", "RECHAZO_OK")]
orden = ["ERROR", "ALUCINA", "FALLA", "RECHAZO_FALSO", "PARCIAL", "OK_CON_RUIDO", "REVISAR"]
no_ok.sort(key=lambda f: (orden.index(f["veredicto"]) if f["veredicto"] in orden else 99, f["id"], f["rep"]))

sospechosas = []
for f in filas:
    if f["veredicto"] not in ("OK", "RECHAZO_OK"):
        continue
    extra = cifras(f["respuesta"]) - cifras(f["esperada"]) - cifras(f["pregunta"])
    extra = {n for n in extra if len(n) >= 2 or n != "0"}  # ignora un "0" suelto
    if extra:
        sospechosas.append((f, "cifras en la respuesta que no están en la esperada: " + ", ".join(sorted(extra))))

por_id = defaultdict(dict)
for f in filas:
    por_id[f["id"]][f["rep"]] = f["veredicto"]
inestables = {i: v for i, v in por_id.items() if len(set(v.values())) > 1}

out = [f"# Hoja de revisión manual: {carpeta.name}", "",
       f"- Filas: {len(filas)} · No OK: {len(no_ok)} · OK con cifras extra: {len(sospechosas)} · "
       f"Preguntas inestables entre repeticiones: {len(inestables)}", ""]
out += ["## 3. Inestables entre repeticiones", "", "| ID | Veredictos |", "|---|---|"]
out += [f"| {i} | {' / '.join(f'rep {r}: {v}' for r, v in sorted(vs.items()))} |" for i, vs in sorted(inestables.items())]
out += ["", "## 1. No OK", ""] + [bloque(f) for f in no_ok]
out += ["## 2. OK con cifras que no están en la esperada (posible H15)", ""] + [bloque(f, m) for f, m in sospechosas]
print("\n".join(out))
