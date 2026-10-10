#!/usr/bin/env python3
"""graficos.py - Gráficos y tabla de métricas de las pruebas, a partir de las corridas de resultados/.

Usa el mismo cálculo que comparar_modelos.py (revision_manual.csv y solo las filas de rag-eval).
Cada configuración se define abajo (CONFIGS) con sus corridas: completo (F3), chat E8 + F4 y chat E8b.

Necesita matplotlib:  .venv/bin/pip install matplotlib

Uso (desde la carpeta del proyecto):
    .venv/bin/python herramientas/graficos.py                 # docs/graficos/*.png y resultados/tablas/metricas.csv
    .venv/bin/python herramientas/graficos.py --salida otra/carpeta
"""
import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from comparar_modelos import PUNTOS, P, ROOT, grupos, p95, pct  # noqa: E402

R = "resultados/"
# Corridas de cada configuración (las tres de E6_medir.sh: completo, E8 + F4 y E8b)
CONFIGS = {
    "Qwen 3.5 2B": [R + "20261009-1156_base-E3-rageval", R + "20261009-1309_E8chat-ingenua", R + "20261009-1551_E8bchat-ingenua"],
    "Qwen 3.5 4B": [R + "20261010-0037_E6-qwen4b-rageval", R + "20261010-0115_E6-qwen4b-E8chat-ingenua",
                    R + "20261010-0133_E6-qwen4b-E8bchat-ingenua"],
    "Gemma 4 E2B": [R + "20261010-0145_E6-gemma-e2b-rageval", R + "20261010-0211_E6-gemma-e2b-E8chat-ingenua",
                    R + "20261010-0222_E6-gemma-e2b-E8bchat-ingenua"],
    "Gemma 4 E4B": [R + "20261010-0228_E6-gemma-e4b-rageval", R + "20261010-0306_E6-gemma-e4b-E8chat-ingenua",
                    R + "20261010-0325_E6-gemma-e4b-E8bchat-ingenua"],
    "Gemma 4 E4B, topN 6": [R + "20261010-0705_E6-gemma-e4b-topn6-rageval", R + "20261010-0733_E6-gemma-e4b-topn6-E8chat-ingenua",
                            R + "20261010-0747_E6-gemma-e4b-topn6-E8bchat-ingenua"],
    "Gemma 4 E4B, topN 8": [R + "20261010-0803_E6-gemma-e4b-topn8-rageval", R + "20261010-0837_E6-gemma-e4b-topn8-E8chat-ingenua",
                            R + "20261010-0853_E6-gemma-e4b-topn8-E8bchat-ingenua"],
    "Qwen 3.5 2B + reformulador": [R + "20261009-1437_E8chat-F3-q35b_mapa", R + "20261009-1356_E8chat-q35b_mapa",
                                   R + "20261009-1554_E8bchat-q35b_v1_mapa"],
    "Gemma 4 E4B + reformulador": [R + "20261010-1242_E6f-gemma-e4b-F3chat-q35b_mapa", R + "20261010-1217_E6f-gemma-e4b-E8chat-q35b_mapa",
                                   R + "20261010-1235_E6f-gemma-e4b-E8bchat-q35b_v1_mapa"],
    "Qwen 3.5 2B, prompt E1c (antes de E3)": [R + "20261009-1044_base-E1c-rageval"],
}
MODELOS = ["Qwen 3.5 2B", "Qwen 3.5 4B", "Gemma 4 E2B", "Gemma 4 E4B"]
CORTO = {"Qwen 3.5 2B": "Qwen 3.5\n2B", "Qwen 3.5 4B": "Qwen 3.5\n4B", "Gemma 4 E2B": "Gemma 4\nE2B", "Gemma 4 E4B": "Gemma 4\nE4B"}
COLOR = {"Qwen 3.5 2B": "#9aa5b1", "Qwen 3.5 4B": "#5f7488", "Gemma 4 E2B": "#e0a03a", "Gemma 4 E4B": "#2e7d5b"}
AZUL, VERDE, ROJO, GRIS = "#3b6ea8", "#2e7d5b", "#c0392b", "#7f8c8d"
META_S = 10  # latencia objetivo (s)

VEREDICTOS = [("OK", "Correcta", "#2e7d5b"), ("OK_CON_RUIDO", "Correcta con un detalle falso", "#8fc9a8"),
              ("RECHAZO_OK", "Rechazo correcto", "#5aa9a0"), ("PARCIAL", "Parcial", "#f2c14e"),
              ("RECHAZO_FALSO", "«No encontré» teniendo el dato", "#e98a3c"), ("FALLA", "Falla", "#d35f4d"),
              ("ALUCINA", "Alucinación", "#7b1f1f")]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "axes.titlesize": 12, "figure.facecolor": "white", "savefig.dpi": 160,
                     "axes.grid": True, "grid.color": "#e6e6e6", "axes.axisbelow": True, "axes.grid.axis": "y"})


def medir(nombre: str) -> dict:
    g = grupos(CONFIGS[nombre])
    ing = g["e8"] + g["e8b"]
    return {"nombre": nombre, "f3": pct(g["f3"])[0] if g["f3"] else None, "n_f3": len(g["f3"]),
            "ing": pct(ing)[0] if ing else None, "n_ing": len(ing),
            "e8": pct(g["e8"])[0] if g["e8"] else None, "e8b": pct(g["e8b"])[0] if g["e8b"] else None,
            "falsas_f3": sum(x["falso"] for x in g["f3"]), "falsas_ing": sum(x["falso"] for x in ing),
            "rechazo_falso": sum(x["man"] == "RECHAZO_FALSO" for x in g["f3"] + ing),
            "lat_med": statistics.median(g["lat"]) if g["lat"] else None, "lat_p95": p95(g["lat"]) if g["lat"] else None,
            "lats": g["lat"], "veredictos": Counter(x["man"] for x in g["f3"] + ing)}


def etiquetas(ax, barras, fmt="{:.0f} %", dy=1.0, tam=9):
    for b in barras:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width() / 2, h + dy, fmt.format(h).replace(".", ","), ha="center", va="bottom", fontsize=tam)


def guardar(fig, salida: Path, nombre: str):
    fig.tight_layout()
    fig.savefig(salida / nombre, bbox_inches="tight")
    plt.close(fig)
    print("  ", salida / nombre)


def g_evolucion(M, salida):
    etapas = ["E1c\nprompt en español", "E3\nvectores e5-small", "E8\n+ reformulador", "E6\nGemma 4 E4B\n(sin reformulador)"]
    f3 = [M["Qwen 3.5 2B, prompt E1c (antes de E3)"]["f3"], M["Qwen 3.5 2B"]["f3"], M["Qwen 3.5 2B + reformulador"]["f3"], M["Gemma 4 E4B"]["f3"]]
    ing = [None, M["Qwen 3.5 2B"]["ing"], M["Qwen 3.5 2B + reformulador"]["ing"], M["Gemma 4 E4B"]["ing"]]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    x = range(len(etapas))
    ax.plot(x, f3, marker="o", lw=2.4, color=AZUL, label="Preguntas bien hechas (F3, 154 respuestas)")
    ax.plot(list(x)[1:], ing[1:], marker="s", lw=2.4, color=VERDE, label="Preguntas ingenuas (E8 y E8b, 127)")
    for i, v in enumerate(f3):
        ax.annotate(f"{v:.0f} %", (i, v), textcoords="offset points", xytext=(0, 8), ha="center", color=AZUL, fontsize=9)
    for i, v in enumerate(ing):
        if v is not None:
            ax.annotate(f"{v:.0f} %", (i, v), textcoords="offset points", xytext=(0, -16), ha="center", color=VERDE, fontsize=9)
    ax.set_xticks(list(x), etapas)
    ax.set_ylim(60, 102)
    ax.set_ylabel("Puntaje con revisión manual")
    ax.set_title("Cómo mejoró el RAG, experimento a experimento")
    ax.legend(loc="lower right", frameon=False)
    ax.text(0, 66.5, "(sin preguntas ingenuas:\nllegaron en E8)", ha="center", fontsize=8, color=GRIS)
    guardar(fig, salida, "evolucion.png")


def g_modelos(M, salida):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [2.2, 1]})
    x = range(len(MODELOS))
    w = 0.38
    b1 = a1.bar([i - w / 2 for i in x], [M[m]["ing"] for m in MODELOS], w, color=VERDE, label="Ingenuas (127)")
    b2 = a1.bar([i + w / 2 for i in x], [M[m]["f3"] for m in MODELOS], w, color=AZUL, label="Bien hechas (F3, 154)")
    etiquetas(a1, b1)
    etiquetas(a1, b2)
    a1.set_xticks(list(x), [CORTO[m] for m in MODELOS])
    a1.set_ylim(0, 122)
    a1.set_ylabel("Puntaje con revisión manual")
    a1.set_title("Calidad de la respuesta")
    a1.legend(loc="upper center", ncol=2, frameon=False)
    falsas = [M[m]["falsas_f3"] + M[m]["falsas_ing"] for m in MODELOS]
    b3 = a2.bar(list(x), falsas, color=[COLOR[m] for m in MODELOS])
    etiquetas(a2, b3, fmt="{:.0f}", dy=0.15)
    a2.set_xticks(list(x), [m.replace("Qwen 3.5 ", "Qwen\n").replace("Gemma 4 ", "Gemma\n") for m in MODELOS])
    a2.set_ylim(0, max(falsas) + 2)
    a2.set_title("Respuestas con algo falso")
    a2.set_ylabel("de 281")
    fig.suptitle("Modelos de respuesta en una GTX 1050 Ti (4 GB), mismo RAG y mismas preguntas", fontsize=11, y=1.02)
    guardar(fig, salida, "modelos_calidad.png")


def g_calidad_latencia(M, salida):
    puntos = MODELOS + ["Gemma 4 E4B, topN 8", "Gemma 4 E4B, topN 6"]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.axvspan(0, META_S, color="#eaf4ee", zorder=0)
    ax.text(META_S - 0.2, 70.5, "meta: ≤ 10 s", ha="right", fontsize=9, color=VERDE)
    for n in puntos:
        m = M[n]
        base = n.split(",")[0]
        falsas = m["falsas_f3"] + m["falsas_ing"]
        ax.scatter(m["lat_med"], m["ing"], s=90 + 60 * falsas, color=COLOR[base], edgecolor="white", lw=1.5, zorder=3,
                   marker="o" if "," not in n else "D")
        txt = (n.replace("Gemma 4 ", "").replace("Qwen 3.5 ", "Qwen ") + f"\n{falsas} con algo falso")
        if n == "Gemma 4 E4B":
            txt = "E4B, topN 10 (elegido)\n0 con algo falso"
        dx, dy = {"Gemma 4 E4B, topN 6": (-10, -32), "Gemma 4 E4B, topN 8": (-10, 12), "Qwen 3.5 4B": (10, -24),
                  "Gemma 4 E2B": (-14, 12)}.get(n, (10, 6))
        ax.annotate(txt, (m["lat_med"], m["ing"]), textcoords="offset points", xytext=(dx, dy), fontsize=8.5,
                    ha="right" if dx < 0 else "left")
    ax.set_xlim(0, 16)
    ax.set_ylim(68, 100)
    ax.set_xlabel("Latencia mediana por respuesta (s)")
    ax.set_ylabel("Puntaje en preguntas ingenuas")
    ax.set_title("Calidad frente a latencia")
    ax.text(15.8, 68.8, "El tamaño del punto crece con las respuestas que tienen algo falso", ha="right", fontsize=8, color=GRIS)
    ax.grid(axis="x", color="#e6e6e6")
    guardar(fig, salida, "calidad_vs_latencia.png")


def g_veredictos(M, salida):
    fig, ax = plt.subplots(figsize=(9, 3.6))
    nombres = list(reversed(MODELOS))
    for j, n in enumerate(nombres):
        v = M[n]["veredictos"]
        total = sum(v.values())
        izq = 0
        for clave, _, color in VEREDICTOS:
            ancho = 100 * v.get(clave, 0) / total
            ax.barh(j, ancho, left=izq, color=color, edgecolor="white", lw=0.6)
            if ancho >= 4:
                ax.text(izq + ancho / 2, j, f"{ancho:.0f}", ha="center", va="center", fontsize=8,
                        color="white" if clave in ("OK", "ALUCINA", "FALLA") else "black")
            izq += ancho
    ax.set_yticks(range(len(nombres)), [n.replace("\n", " ") for n in nombres])
    ax.set_xlim(0, 100)
    ax.set_xlabel("% de las respuestas (bien hechas e ingenuas, 281 por modelo)")
    ax.set_title("Qué tipo de respuesta da cada modelo")
    ax.grid(False)
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in VEREDICTOS], labels=[t for _, t, _ in VEREDICTOS],
              loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=4, frameon=False, fontsize=8.5)
    guardar(fig, salida, "veredictos.png")


def g_topn(M, salida):
    nombres = ["Gemma 4 E4B, topN 6", "Gemma 4 E4B, topN 8", "Gemma 4 E4B"]
    xl = ["topN 6", "topN 8", "topN 10"]
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(10.5, 3.8))
    x = range(3)
    w = 0.38
    etiquetas(a1, a1.bar([i - w / 2 for i in x], [M[n]["ing"] for n in nombres], w, color=VERDE, label="Ingenuas"))
    etiquetas(a1, a1.bar([i + w / 2 for i in x], [M[n]["f3"] for n in nombres], w, color=AZUL, label="Bien hechas"))
    a1.set_ylim(0, 125)
    a1.set_title("Puntaje")
    a1.legend(loc="upper center", ncol=2, fontsize=8, frameon=False)
    falsas = [M[n]["falsas_f3"] + M[n]["falsas_ing"] for n in nombres]
    etiquetas(a2, a2.bar(list(x), falsas, color=[ROJO, ROJO, VERDE]), fmt="{:.0f}", dy=0.1)
    a2.set_ylim(0, max(falsas) + 1.5)
    a2.set_title("Respuestas con algo falso")
    lat = [M[n]["lat_med"] for n in nombres]
    etiquetas(a3, a3.bar(list(x), lat, color=GRIS), fmt="{:.1f} s", dy=0.2)
    a3.axhline(META_S, ls="--", color=VERDE, lw=1)
    a3.text(-0.45, META_S + 0.3, "meta 10 s", color=VERDE, fontsize=8, ha="left")
    a3.set_ylim(0, 16)
    a3.set_title("Latencia mediana")
    for a in (a1, a2, a3):
        a.set_xticks(list(x), xl)
    fig.suptitle("Gemma 4 E4B con menos fragmentos: más rápido, pero vuelven las respuestas falsas", fontsize=11, y=1.03)
    guardar(fig, salida, "topn.png")


def g_reformulador(M, salida):
    nombres = ["Qwen 3.5 2B", "Qwen 3.5 2B + reformulador", "Gemma 4 E4B", "Gemma 4 E4B + reformulador"]
    xl = ["Qwen 2B", "Qwen 2B\n+ reformulador", "Gemma E4B", "Gemma E4B\n+ reformulador"]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = range(4)
    w = 0.38
    etiquetas(ax, ax.bar([i - w / 2 for i in x], [M[n]["ing"] for n in nombres], w, color=VERDE, label="Ingenuas (127)"))
    etiquetas(ax, ax.bar([i + w / 2 for i in x], [M[n]["f3"] for n in nombres], w, color=AZUL, label="Bien hechas (F3, 154)"))
    ax.set_xticks(list(x), xl)
    ax.set_ylim(0, 122)
    ax.set_ylabel("Puntaje con revisión manual")
    ax.set_title("Reformular la pregunta con Qwen 3.6 35B: ayuda al 2B, empeora a Gemma")
    ax.legend(loc="upper center", ncol=2, frameon=False)
    guardar(fig, salida, "reformulador.png")


def g_latencia(M, salida):
    fig, ax = plt.subplots(figsize=(8, 4))
    datos = [M[m]["lats"] for m in MODELOS]
    bp = ax.boxplot(datos, patch_artist=True, widths=0.55, showfliers=True, medianprops={"color": "black"},
                    flierprops={"marker": ".", "markersize": 4, "markerfacecolor": GRIS, "markeredgecolor": GRIS})
    for caja, m in zip(bp["boxes"], MODELOS):
        caja.set_facecolor(COLOR[m])
        caja.set_alpha(0.85)
    ax.axhline(META_S, ls="--", color=VERDE, lw=1)
    ax.text(4.45, META_S + 0.4, "meta ≤ 10 s", color=VERDE, fontsize=8, ha="right")
    ax.set_xticks(range(1, 5), [CORTO[m] for m in MODELOS])
    ax.set_ylabel("Segundos por respuesta")
    ax.set_title("Latencia por respuesta (F3 y F4, primera repetición)")
    guardar(fig, salida, "latencia.png")


def g_rendimiento(salida):
    f = ROOT / "resultados" / "tablas" / "rendimiento_modelos.csv"
    filas = list(csv.DictReader(open(f, encoding="utf-8"), delimiter=";"))
    nombres = [r["modelo"] for r in filas]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    y = range(len(filas))
    colores = [COLOR.get(r["familia"], GRIS) for r in filas]
    b1 = a1.barh(list(y), [float(r["lectura_tok_s"]) for r in filas], color=colores)
    b2 = a2.barh(list(y), [float(r["generacion_tok_s"]) for r in filas], color=colores)
    for b, r in zip(b1, filas):
        a1.text(b.get_width() + 10, b.get_y() + b.get_height() / 2, f"{float(r['lectura_tok_s']):.0f}", va="center", fontsize=8.5)
    for b, r in zip(b2, filas):
        a2.text(b.get_width() + 0.8, b.get_y() + b.get_height() / 2,
                f"{float(r['generacion_tok_s']):.0f}   ({r['vram_gb'].replace('.', ',')} GB, capas en GPU: {r['capas_gpu']})", va="center", fontsize=8.5)
    a1.set_yticks(list(y), nombres)
    a1.invert_yaxis()
    a1.set_title("Lectura del contexto (tok/s)")
    a2.set_title("Generación (tok/s), VRAM y capas en la GPU")
    a1.set_xlim(0, 1000)
    a2.set_xlim(0, 110)
    for a in (a1, a2):
        a.grid(axis="x", color="#e6e6e6")
        a.grid(axis="y", visible=False)
    fig.suptitle("Velocidad en la GTX 1050 Ti con un prompt real del RAG (~3.400 tokens)", fontsize=11, y=1.03)
    guardar(fig, salida, "rendimiento_gpu.png")


def g_recuperacion(salida):
    corridas = {"all-MiniLM-L6-v2 (antes)": R + "20261009-1044_base-E1c-rageval",
                "multilingual-e5-small (E3)": R + "20261009-1156_base-E3-rageval"}
    por_formato = {}
    for nombre, c in corridas.items():
        filas = [r for r in csv.DictReader(open(ROOT / c / "recuperacion.csv", encoding="utf-8-sig"), delimiter=";")
                 if r["workspace"] == "rag-eval" and P[r["id"]]["fase"] == "F2-F3" and not P[r["id"]]["espera_rechazo"]]
        d = defaultdict(list)
        for r in filas:
            d[r["formato"]].append(r["evidencia_encontrada"] == "True")
            d["Total"].append(r["evidencia_encontrada"] == "True")
        por_formato[nombre] = {k: (100 * sum(v) / len(v), len(v)) for k, v in d.items()}
    formatos = ["Total", "PowerPoint", "PDF digital", "Word (MarkItDown)", "Word (raíz, parser AnythingLLM)",
                "PDF escaneado (OCR)", "Cruce de documentos"]
    xl = ["Total", "PowerPoint", "PDF digital", "Word\n(MarkItDown)", "Word (parser\nAnythingLLM)", "PDF escaneado\n(OCR)",
          "Cruce de\ndocumentos"]
    fig, ax = plt.subplots(figsize=(10, 4))
    x = range(len(formatos))
    w = 0.38
    for k, (nombre, color) in enumerate(zip(corridas, [GRIS, VERDE])):
        etiquetas(ax, ax.bar([i + (k - 0.5) * w for i in x], [por_formato[nombre][f][0] for f in formatos], w, color=color,
                             label=nombre), tam=8)
    ax.set_xticks(list(x), [f"{t}\n({por_formato['multilingual-e5-small (E3)'][f][1]})" for t, f in zip(xl, formatos)], fontsize=8.5)
    ax.set_ylim(0, 125)
    ax.set_ylabel("% de preguntas con el dato en los fragmentos")
    ax.set_title("¿Llega el dato al modelo? Modelo de vectores original frente a uno multilingüe")
    ax.legend(loc="upper center", ncol=2, frameon=False)
    guardar(fig, salida, "recuperacion_embedder.png")


def tabla(M, f: Path):
    f.parent.mkdir(parents=True, exist_ok=True)
    campos = ["nombre", "ing", "n_ing", "e8", "e8b", "f3", "n_f3", "falsas_f3", "falsas_ing", "rechazo_falso", "lat_med", "lat_p95"]
    with open(f, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(campos)
        for m in M.values():
            w.writerow([m[c] if not isinstance(m[c], float) else f"{m[c]:.1f}" for c in campos])
    print("  ", f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default="docs/graficos", help="carpeta de los PNG (relativa al proyecto)")
    args = ap.parse_args()
    salida = ROOT / args.salida
    salida.mkdir(parents=True, exist_ok=True)
    M = {n: medir(n) for n in CONFIGS}
    tabla(M, ROOT / "resultados" / "tablas" / "metricas.csv")
    g_evolucion(M, salida)
    g_modelos(M, salida)
    g_calidad_latencia(M, salida)
    g_veredictos(M, salida)
    g_topn(M, salida)
    g_reformulador(M, salida)
    g_latencia(M, salida)
    g_rendimiento(salida)
    g_recuperacion(salida)
    print(json.dumps({n: {k: (round(v, 1) if isinstance(v, float) else v) for k, v in m.items() if k not in ("lats", "veredictos")}
                      for n, m in M.items()}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
