#!/usr/bin/env python3
"""revisar.py - Lista lo que hay que revisar a mano en una corrida de rag_eval.py (solo filas de rag-eval).

Muestra las respuestas que no son OK y las OK con cifras que no están en la esperada ni en la pregunta
(posible H15: cifra inventada con la cita correcta). Omite las que ya están en revision_manual.csv y
agrupa las repeticiones idénticas. Si la pregunta se reformuló (--reformuladas), muestra la enviada.
Si la misma respuesta (mismo ID y mismo texto) ya tiene veredicto manual en otra corrida, lo indica
con «PREVIO»: así el criterio queda igual entre modelos.

Lee la respuesta completa de chat.jsonl (o de respuestas.jsonl); chat.csv la trae recortada.

Uso (desde la carpeta del proyecto):
    python3 herramientas/revisar.py resultados/<carpeta> > hoja.md
Después, los veredictos van a resultados/<carpeta>/revision_manual.csv (id;rep;veredicto_auto;veredicto_manual;nota).
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = {q["id"]: q for q in json.load(open(ROOT / "preguntas" / "preguntas.json", encoding="utf-8"))}
NUM = re.compile(r"\d+(?:[.,]\d+)*")


def cifras(t):
    return {re.sub(r"[.,]", "", n) for n in NUM.findall(t or "")}


def leer(c: Path):
    """Filas de chat.csv con la respuesta completa y la pregunta enviada, y las revisiones de la carpeta."""
    filas = list(csv.DictReader(open(c / "chat.csv", encoding="utf-8-sig"), delimiter=";"))
    if (c / "chat.jsonl").exists():
        js = [json.loads(l) for l in open(c / "chat.jsonl", encoding="utf-8")]
        completas = [((j["respuesta_api"].get("textResponse") or "").strip(), j["pregunta"]["pregunta"]) for j in js]
    elif (c / "respuestas.jsonl").exists():
        js = {(j["id"], j["rep"]): j for j in map(json.loads, open(c / "respuestas.jsonl", encoding="utf-8"))}
        completas = [(js[(x["id"], x["rep"])]["respuesta"], js[(x["id"], x["rep"])]["pregunta"]) if (x["id"], x["rep"]) in js
                     else (x["respuesta"], x["pregunta"]) for x in filas]
    else:
        completas = [(x["respuesta"], x["pregunta"]) for x in filas]
    rev = {}
    if (c / "revision_manual.csv").exists():
        rev = {(x["id"], x["rep"]): x for x in csv.DictReader(open(c / "revision_manual.csv", encoding="utf-8-sig"), delimiter=";")}
    return filas, completas, rev


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    d = Path(sys.argv[1]).resolve()
    previos = {}
    for c in sorted((ROOT / "resultados").iterdir()):
        if c == d or not (c / "revision_manual.csv").exists() or not (c / "chat.csv").exists():
            continue
        filas, completas, rev = leer(c)
        for x, (txt, _) in zip(filas, completas):
            m = rev.get((x["id"], x["rep"]))
            if m:
                previos.setdefault((x["id"], txt), (m["veredicto_manual"], m["nota"], c.name))

    filas, completas, rev = leer(d)
    vistos = {}
    for x, (txt, enviada) in zip(filas, completas):
        if x["workspace"] != "rag-eval" or (x["id"], x["rep"]) in rev:
            continue
        q = P[x["id"]]
        extra = cifras(txt) - cifras(q["respuesta_esperada"]) - cifras(q["pregunta"]) - cifras(enviada)
        if x["veredicto"] in ("OK", "RECHAZO_OK") and not extra:
            continue
        clave = (x["id"], txt)
        if clave in vistos:
            print(f"- {x['id']} r{x['rep']} {x['veredicto']}: idéntica a r{vistos[clave]}")
            continue
        vistos[clave] = x["rep"]
        prev = previos.get(clave)
        print(f"\n## {x['id']} r{x['rep']} {x['veredicto']} · {q['tipo']}\nP: {q['pregunta']}"
              + (f"\nENVIADA: {enviada}" if enviada != q["pregunta"] else "")
              + f"\nE: {q['respuesta_esperada']}"
              + (f"\nCIFRAS QUE NO ESTÁN EN LA ESPERADA: {', '.join(sorted(extra))}" if extra else "")
              + f"\nR: {txt[:900]}".replace("\n\n", "\n")
              + (f"\n>> PREVIO: {prev[0]} ({prev[2]}): {prev[1][:200]}" if prev else ""))


if __name__ == "__main__":
    main()
