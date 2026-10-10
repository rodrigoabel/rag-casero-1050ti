#!/usr/bin/env python3
"""comparar_modelos.py - Compara modelos de respuesta (E6) con el criterio de la revisión manual.

Cada modelo se describe como  etiqueta=carpeta1,carpeta2,...  con sus corridas de rag_eval.py:
  * completo        -> F3 (bien hechas) y F4
  * chat --fase F2-F3 -> solo F3 (por ejemplo, con --reformuladas)
  * chat --fase E8,F4 -> ingenuas de E8 (35) más las 8 ingenuas de la F4
  * chat --fase E8b -> ingenuas nuevas de E8b (16)
Solo cuenta las filas de rag-eval: las preguntas de Obsidian van a notas-obsidian, que usa siempre el modelo global.
Lee <carpeta>/revision_manual.csv si existe (como puntaje_manual.py). «Con algo falso» = ALUCINA o una nota que
dice «falso» (el criterio de los análisis de E3 y E8). La latencia es la de la repetición 1: en la 2 el prompt
ya está en la caché de llama-server y sale más rápida de lo real.

Uso (desde la carpeta del proyecto):
  python3 herramientas/comparar_modelos.py "2b=resultados/A,resultados/B,resultados/C" "qwen4b=resultados/D,..."
"""
import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUNTOS = {"OK": 2, "RECHAZO_OK": 2, "OK_CON_RUIDO": 1, "PARCIAL": 1, "FALLA": 0, "RECHAZO_FALSO": 0, "ALUCINA": 0, "ERROR": 0}
P = {q["id"]: q for q in json.load(open(ROOT / "preguntas" / "preguntas.json", encoding="utf-8"))}


def filas(carpeta: Path):
    r = list(csv.DictReader(open(carpeta / "chat.csv", encoding="utf-8-sig"), delimiter=";"))
    rev = {}
    if (carpeta / "revision_manual.csv").exists():
        rev = {(x["id"], x["rep"]): x for x in
               csv.DictReader(open(carpeta / "revision_manual.csv", encoding="utf-8-sig"), delimiter=";")}
    out = []
    for x in r:
        if x["workspace"] != "rag-eval":
            continue
        m = rev.get((x["id"], x["rep"]))
        x["man"] = m["veredicto_manual"] if m else x["veredicto"]
        x["falso"] = x["man"] == "ALUCINA" or bool(m and "falso" in m["nota"].lower())
        x["fase"] = P[x["id"]]["fase"]
        x["variante"] = P[x["id"]].get("variante") or ""
        out.append(x)
    return out


def pct(rows):
    s = [PUNTOS[x["man"]] for x in rows if x["man"] in PUNTOS]
    return 100 * sum(s) / max(1, 2 * len(s)), len(s)


def p95(v):
    v = sorted(v)
    return v[min(len(v) - 1, round(0.95 * (len(v) - 1)))] if v else float("nan")


def grupos(carpetas: list[str]) -> dict:
    """Filas de rag-eval de las corridas, separadas en F3, F4, ingenuas E8 y E8b, más la latencia (rep. 1)."""
    g = {"completo": [], "E8": [], "E8b": []}
    for c in carpetas:
        d = ROOT / c if not Path(c).is_absolute() else Path(c)
        a = json.load(open(d / "config.json", encoding="utf-8"))["argumentos"]
        clave = "completo" if a["accion"] == "completo" or a.get("fase") == "F2-F3" else ("E8b" if a.get("fase") == "E8b" else "E8")
        g[clave] += filas(d)
    return {
        "completo": g["completo"],
        "f3": [x for x in g["completo"] if x["fase"] == "F2-F3"],
        "f4": [x for x in g["completo"] if x["fase"] == "F4"],
        "e8": [x for x in g["E8"] if x["fase"] == "E8" or (x["fase"] == "F4" and x["variante"] == "ingenua")],
        "e8b": [x for x in g["E8b"] if x["fase"] == "E8b"],
        "lat": [float(x["segundos"]) for x in g["completo"] if x["rep"] == "1" and x["segundos"]],
    }


def modelo(spec: str):
    nombre, carpetas = spec.split("=", 1)
    gr = grupos(carpetas.split(","))
    f3, f4, e8, e8b, lat = gr["f3"], gr["f4"], gr["e8"], gr["e8b"], gr["lat"]
    g = {"completo": gr["completo"]}
    ft = [x for x in f3 if P[x["id"]]["tipo"] in ("factual", "tabla")]
    ing = e8 + e8b
    return {
        "Modelo": nombre,
        "F3 bien hechas": "%.0f %% (%d)" % pct(f3),
        "OK factual y tabla": "%.0f %%" % (100 * sum(x["man"] == "OK" for x in ft) / max(1, len(ft))),
        "F4": "%.0f %% (%d)" % pct(f4),
        "Ingenuas E8": "%.0f %% (%d)" % pct(e8),
        "Ingenuas E8b": "%.0f %% (%d)" % pct(e8b),
        "Ingenuas combinado": "%.1f %%" % pct(ing)[0],
        "«No encontré» con el dato (F3 / ingenuas)": f"{sum(x['man'] == 'RECHAZO_FALSO' for x in f3)} / "
                                                     f"{sum(x['man'] == 'RECHAZO_FALSO' for x in ing)}",
        "Alucinaciones (F3 / ingenuas)": f"{sum(x['man'] == 'ALUCINA' for x in f3)} / {sum(x['man'] == 'ALUCINA' for x in ing)}",
        "Con algo falso (F3 / ingenuas)": f"{sum(x['falso'] for x in f3)} / {sum(x['falso'] for x in ing)}",
        "Rechazos correctos": "%d/%d" % (sum(x["man"] == "RECHAZO_OK" for x in f3 if P[x["id"]]["espera_rechazo"]),
                                        sum(1 for x in f3 if P[x["id"]]["espera_rechazo"])),
        "Latencia mediana / p95 (rep. 1)": f"{statistics.median(lat):.1f} / {p95(lat):.1f} s" if lat else "—",
        "Errores": str(sum(x["man"] == "ERROR" for x in g["completo"] + ing)),
        "_veredictos_F3": dict(Counter(x["man"] for x in f3)),
    }


def main():
    ms = [modelo(s) for s in sys.argv[1:]]
    if not ms:
        sys.exit(__doc__)
    campos = [k for k in ms[0] if not k.startswith("_") and k != "Modelo"]
    print("| | " + " | ".join(m["Modelo"] for m in ms) + " |")
    print("|---" * (len(ms) + 1) + "|")
    for k in campos:
        print(f"| {k} | " + " | ".join(m[k] for m in ms) + " |")
    print()
    for m in ms:
        print(f"Veredictos F3 de {m['Modelo']}: {m['_veredictos_F3']}")


if __name__ == "__main__":
    main()
