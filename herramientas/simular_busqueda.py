#!/usr/bin/env python3
"""Simula topN y umbral de AnythingLLM a partir de UNA corrida de búsqueda con el grupo completo de candidatos.

Corre primero (sin modelo, no cambia el servidor):
    python3 herramientas/rag_eval.py recuperacion --topn 50 --umbral 0 --etiqueta E2-pool

Por qué funciona (AnythingLLM 1.17, utils/vectorDbProviders/lance):
  * Con rerank, toma los 10–50 mejores por vector (10 % de los fragmentos del workspace), los reordena,
    ordena por nota del reranker y corta los topN primeros. Después descarta los de similitud < umbral
    (similitud = 1 − distancia del vector, no la nota del reranker). Sin rerank: los topN más parecidos y el
    mismo filtro. En ambos casos el resultado con (topN, umbral) es el prefijo de largo topN de la lista
    completa, filtrado por umbral.
  * Por eso basta con la lista completa (topN 50, umbral 0) para calcular cualquier combinación.

Uso: python3 herramientas/simular_busqueda.py resultados/<carpeta> [--topn 4,6,8,10,15,20,30] [--umbral 0,0.1,0.2,0.3]
     [--validar resultados/<carpeta con recuperacion.csv real>]
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_eval import clave, contiene, formato_de, lista, norm  # noqa: E402

WS = {"mirag": "rag-eval", "obsidian": "notas-obsidian", "usuario2": "espacio-usuario2"}


def similitud(d):
    # misma fórmula que distanceToSimilarity de AnythingLLM
    if not isinstance(d, (int, float)):
        return 0.0
    if d >= 1.0:
        return 0.0
    return 1 - abs(d) if d < 0 else 1 - d


def evaluar(q, resultados, topn, umbral):
    sel = [r for r in resultados[:topn] if similitud(r["distance"]) >= umbral]
    titulos = [clave(r["title"]) for r in sel]
    fuente = all(any(clave(f) in t for t in titulos) for f in lista(q["fuente_esperada"]))
    evid = None
    rango = None
    if q["evidencia"]:
        for i, r in enumerate(sel, 1):
            if any(contiene(norm(r["text"]), e) for e in q["evidencia"]):
                evid, rango = True, i
                break
        else:
            evid = False
    return {"fuente": fuente, "evid": evid, "rango": rango, "n": len(sel), "chars": sum(len(r["text"]) for r in sel)}


def pct(a, b):
    return f"{100 * a / b:.0f} %" if b else "—"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpeta")
    ap.add_argument("--topn", default="4,6,8,10,15,20,30,50")
    ap.add_argument("--umbral", default="0,0.1,0.2,0.25,0.3")
    ap.add_argument("--validar", help="carpeta con recuperacion.csv real para comprobar la simulación")
    args = ap.parse_args()
    topns = [int(x) for x in args.topn.split(",")]
    umbrales = [float(x) for x in args.umbral.split(",")]

    filas = [json.loads(l) for l in (Path(args.carpeta) / "recuperacion.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    filas = [f for f in filas if f["http"] == 200 and f["pregunta"]["evidencia"]]
    print(f"# Simulación de topN y umbral: {Path(args.carpeta).name}\n")
    print(f"{len(filas)} preguntas con dato exacto definido. Largo máximo de la lista: "
          f"{max(len(f['resultados']) for f in filas)} fragmentos.\n")

    # el slug real sale de la corrida (p. ej. --ws-mirag rag-eval), no de los valores por defecto
    cfg = Path(args.carpeta) / "config.json"
    slugs = dict(WS)
    if cfg.exists():
        a_ = json.loads(cfg.read_text(encoding="utf-8")).get("argumentos", {})
        slugs.update({k: a_.get(f"ws_{k}", v) for k, v in WS.items()})
    for ws in ("mirag", "obsidian"):
        g = [f for f in filas if f["pregunta"]["workspace"] == ws]
        if not g:
            continue
        print(f"## Workspace `{slugs[ws]}` ({len(g)} preguntas)\n")
        print("**Dato exacto entre los fragmentos que llegarían al modelo**\n")
        print("| topN \\ umbral | " + " | ".join(f"{u:g}" for u in umbrales) + " | texto enviado (car., umbral 0) |")
        print("|---|" + "---|" * (len(umbrales) + 1))
        for k in topns:
            celdas = []
            for u in umbrales:
                ev = [evaluar(f["pregunta"], f["resultados"], k, u) for f in g]
                celdas.append(pct(sum(e["evid"] for e in ev), len(ev)))
            chars = sum(evaluar(f["pregunta"], f["resultados"], k, 0)["chars"] for f in g) / len(g)
            print(f"| {k} | " + " | ".join(celdas) + f" | {chars:,.0f} |".replace(",", "."))
        techo = [evaluar(f["pregunta"], f["resultados"], 10 ** 6, 0) for f in g]
        print(f"\n**Techo** (el dato está en algún lugar de los candidatos): {pct(sum(e['evid'] for e in techo), len(techo))}. "
              f"Lo que no está ahí no lo arregla ningún topN: es problema del embedder o del troceo (E3, E4).\n")

        # por formato, con topN actuales y alternativas
        print("**Por formato** (umbral 0,2)\n")
        fmts = sorted({formato_de(f["pregunta"]) for f in g})
        print("| Formato | n | " + " | ".join(f"topN {k}" for k in topns) + " | techo |")
        print("|---|---|" + "---|" * (len(topns) + 1))
        for fm in fmts:
            gf = [f for f in g if formato_de(f["pregunta"]) == fm]
            celdas = [pct(sum(evaluar(f["pregunta"], f["resultados"], k, 0.2)["evid"] for f in gf), len(gf)) for k in topns]
            t = pct(sum(evaluar(f["pregunta"], f["resultados"], 10 ** 6, 0)["evid"] for f in gf), len(gf))
            print(f"| {fm} | {len(gf)} | " + " | ".join(celdas) + f" | {t} |")
        print()

        # preguntas cuyo dato está fuera de los candidatos o muy abajo
        print("**Dónde quedó el dato** (posición en la lista completa; «—» = no está entre los candidatos)\n")
        pos = defaultdict(list)
        for f in g:
            e = evaluar(f["pregunta"], f["resultados"], 10 ** 6, 0)
            r = e["rango"]
            clase = "1–4" if r and r <= 4 else "5–10" if r and r <= 10 else "11–20" if r and r <= 20 else "21+" if r else "—"
            pos[clase].append(f["pregunta"]["id"])
        for clase in ("1–4", "5–10", "11–20", "21+", "—"):
            ids = pos.get(clase, [])
            print(f"- **{clase}:** {len(ids)}" + (f" ({', '.join(ids)})" if clase != "1–4" and ids else ""))
        print()

    if args.validar:
        real = {r["id"]: r for r in csv.DictReader(open(Path(args.validar) / "recuperacion.csv", encoding="utf-8-sig"), delimiter=";")}
        cfg = json.load(open(Path(args.validar) / "config.json", encoding="utf-8"))["workspaces"]
        dif = []
        for f in filas:
            q = f["pregunta"]
            w = cfg[q["workspace"]]
            e = evaluar(q, f["resultados"], w["topN"], w["similarityThreshold"])
            r = real.get(q["id"])
            if r and str(e["evid"]) != r["evidencia_encontrada"]:
                dif.append(f"{q['id']}: simulado {e['evid']}, real {r['evidencia_encontrada']}")
        print(f"## Validación contra `{Path(args.validar).name}` (topN y umbral de cada workspace)\n")
        print(f"Coincidencias: {len(filas) - len(dif)}/{len(filas)}" + ("" if not dif else "\n\n- " + "\n- ".join(dif)))


if __name__ == "__main__":
    main()
