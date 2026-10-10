#!/usr/bin/env python3
"""Verifica las frases que el modelo dice copiar de los documentos (E0, E1b) y marca respuestas contradictorias.

Para cada respuesta de <carpeta>/chat.csv:
  * Extrae las frases entre comillas ("…", “…”, «…») de al menos 6 palabras.
  * Las busca en el texto convertido de los documentos (vista_previa_conversion/, el mismo que se subió).
      LITERAL   : ≥ 90 % de sus tríos de palabras aparecen en algún documento
      RETOCADA  : 50–90 % (copiada con cambios)
      INVENTADA : < 50 %
    También dice si la frase está en el documento correcto para esa pregunta.
  * Marca CONTRADICCIÓN cuando la respuesta empieza diciendo que no aparece, pero el puntaje encontró
    el dato (OK, OK_CON_RUIDO o PARCIAL).

Uso (desde la carpeta del proyecto):
    python3 herramientas/verificar_citas.py resultados/<carpeta>
"""
import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "vista_previa_conversion"
PREGUNTAS = ROOT / "preguntas" / "preguntas.json"
INICIO_RECHAZO = re.compile(r"^\W*(no (aparece|se encuentra|encontr|existe|hay|se menciona|se especifica|se indica|se proporciona))")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[*_`>|#\\]", " ", s)
    return re.sub(r"[^\w%°.,:;/()+-]+", " ", s).strip()


def trios(s: str) -> set:
    w = norm(s).replace(".", " ").replace(",", " ").split()
    return {tuple(w[i:i + 3]) for i in range(len(w) - 2)}


def frases(texto: str) -> list[str]:
    # primero se emparejan todas las comillas (también las cortas) y después se filtra por largo;
    # si se exigiera el largo en la regex, el texto entre dos citas cortas se tomaría por una cita
    out = []
    for p in (r'"([^"]*)"', r"“([^”]*)”", r"«([^»]*)»"):
        out += [m.strip(" *") for m in re.findall(p, texto or "")]
    return [f for f in out if len(f.split()) >= 6]


def main():
    carpeta = Path(sys.argv[1])
    docs = {p.name.split(".")[0]: trios(p.read_text(encoding="utf-8"))
            for p in DOCS.rglob("*.md") if "cambios" not in p.parts and "usuario2" not in p.parts}
    P = {q["id"]: q for q in json.loads(PREGUNTAS.read_text(encoding="utf-8"))}
    filas = list(csv.DictReader(open(carpeta / "chat.csv", encoding="utf-8-sig"), delimiter=";"))

    tipos, con_frase, contradic, detalle = Counter(), 0, [], []
    for f in filas:
        fs = frases(f["respuesta"])
        if fs:
            con_frase += 1
        esperada = P[f["id"]]["fuente_esperada"]
        esperada = [esperada] if isinstance(esperada, str) else esperada
        for fr in fs:
            t = trios(fr)
            mejor, doc = max(((len(t & d) / max(1, len(t)), n) for n, d in docs.items()), default=(0, ""))
            clase = "LITERAL" if mejor >= 0.9 else "RETOCADA" if mejor >= 0.5 else "INVENTADA"
            tipos[clase] += 1
            en_correcto = any(re.sub(r"[^a-z0-9]", "", norm(e)) in re.sub(r"[^a-z0-9]", "", norm(doc)) for e in esperada if e)
            if clase != "LITERAL" or not en_correcto:
                detalle.append(f"| {f['id']} r{f['rep']} | {f['veredicto']} | {clase} ({mejor:.0%}) | "
                               f"{doc if mejor >= 0.5 else '—'}{'' if en_correcto or mejor < 0.5 else ' (otro documento)'} | "
                               f"{fr[:110].replace('|', '/')} |")
        # en una premisa falsa, «no encontré eso» seguido del dato correcto es corregir la premisa, no contradecirse
        if (f["veredicto"] in ("OK", "OK_CON_RUIDO", "PARCIAL") and P[f["id"]]["tipo"] != "premisa_falsa"
                and INICIO_RECHAZO.search(norm(f["respuesta"]))):
            contradic.append(f"| {f['id']} r{f['rep']} | {f['veredicto']} | {f['respuesta'][:140].replace(chr(10), ' ').replace('|', '/')} |")

    total = sum(tipos.values())
    print(f"# Verificación de citas: {carpeta.name}\n")
    print(f"- Respuestas con al menos una frase citada: {con_frase}/{len(filas)}")
    print(f"- Frases citadas: {total} · " + " · ".join(f"{k}: {v} ({100 * v / max(1, total):.0f} %)"
                                                      for k, v in sorted(tipos.items())))
    print(f"- Respuestas contradictorias (dicen «no aparece» pero dan el dato): {len(contradic)}\n")
    if detalle:
        print("## Frases no literales o de otro documento\n\n| ID | Veredicto | Clase | Documento | Frase |\n|---|---|---|---|---|")
        print("\n".join(detalle))
    if contradic:
        print("\n## Respuestas contradictorias\n\n| ID | Veredicto | Inicio de la respuesta |\n|---|---|---|")
        print("\n".join(contradic))


if __name__ == "__main__":
    main()
