#!/usr/bin/env python3
"""simular_embedder.py - Estima en el PC el efecto de cambiar el modelo de vectores (E3) sin tocar el servidor.

Reproduce la búsqueda de AnythingLLM 1.17 con los mismos modelos ONNX cuantizados que usa el servidor:
  1. Vector de la pregunta (pooling «mean» y normalización, con el prefijo «query: » si el modelo lo pide).
  2. Candidatos: los max(10, min(50, ceil(10 % de los fragmentos))) más parecidos por coseno.
  3. Reordenamiento con el cross-encoder ms-marco-MiniLM-L-6-v2 (sigmoide del logit); se quedan los topN primeros.
  4. Se descartan los de similitud < umbral (similitud = coseno).

Entrada: resultados/E3-sim/fragmentos.json (texto y vector de cada fragmento, exportados de LanceDB solo leyendo).
Modelos: .modelos/<org>__<modelo>/ (descargados de Hugging Face).

Uso (desde la carpeta del proyecto, con el entorno del proyecto):
    .venv/bin/python herramientas/simular_embedder.py validar     # el modelo actual debe reproducir los vectores y resultados reales
    .venv/bin/python herramientas/simular_embedder.py comparar    # modelo actual frente a multilingual-e5-small
    .venv/bin/python herramientas/simular_embedder.py candidatos e5-small qwen3-0.6b qwen3vl-2b ...
        # modelos GGUF servidos por un llama-server local en modo embedding (ver EMBEDDERS: puerto y formato);
        # agrega posición del dato (MRR, primer lugar) y las preguntas ingenuas de E8 y E8b

Para los GGUF (en .modelos/gguf/), en otra terminal y solo en CPU para no tocar la GPU:
    llama-server -m .modelos/gguf/Qwen3-Embedding-0.6B-Q8_0.gguf --embedding --pooling last -ngl 0 -c 8192 -b 2048 -ub 2048 --port 8091
    llama-server -m .modelos/gguf/Qwen3-VL-Embedding-2B-Q8_0.gguf --embedding --pooling last -ngl 0 -c 8192 -b 2048 -ub 2048 --port 8092
"""
import csv
import json
import math
import sys
import urllib.request
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_eval import contiene, formato_de, norm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MODELOS = ROOT / ".modelos"
FRAGMENTOS = ROOT / "resultados" / "E3-sim" / "fragmentos.json"
PREGUNTAS = ROOT / "preguntas" / "preguntas.json"
EMBEDDERS = {
    "minilm": {"dir": "Xenova__all-MiniLM-L6-v2", "query": "", "passage": ""},
    "e5-small": {"dir": "MintplexLabs__multilingual-e5-small", "query": "query: ", "passage": "passage: "},
}
# GGUF por HTTP (llama-server --embedding). «sin instrucción» es lo que enviaría AnythingLLM a través de Ollama;
# las variantes con instrucción o plantilla son el techo según las fichas oficiales de Qwen.
QWEN3_INSTR = "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"
QVL = "<|im_start|>system\n{inst}<|im_end|>\n<|im_start|>user\n{t}<|im_end|>\n<|im_start|>assistant\n"
EMBEDDERS.update({
    "qwen3-0.6b": {"url": "http://127.0.0.1:8091", "query": "", "passage": "", "fin": "<|endoftext|>"},
    "qwen3-0.6b-instr": {"url": "http://127.0.0.1:8091", "query": QWEN3_INSTR, "passage": "", "fin": "<|endoftext|>"},
    "qwen3vl-2b": {"url": "http://127.0.0.1:8092", "query": "", "passage": "", "fin": ""},
    "qwen3vl-2b-plantilla": {"url": "http://127.0.0.1:8092", "plantilla": QVL, "inst_q": "Retrieve relevant documents for the query.",
                             "inst_p": "Represent the user's input."},
})
RERANKER = "Xenova__ms-marco-MiniLM-L-6-v2"
REAL = {"prueba": "20261009-0915_base-E1c", "rag-eval": "20261009-1044_base-E1c-rageval"}  # corridas reales con topN 10, umbral 0,2


class Modelo:
    def __init__(self, carpeta, max_len=512):
        self.tok = Tokenizer.from_file(str(MODELOS / carpeta / "tokenizer.json"))
        self.tok.enable_truncation(max_len)
        self.sess = ort.InferenceSession(str(MODELOS / carpeta / "onnx" / "model_quantized.onnx"),
                                         providers=["CPUExecutionProvider"])
        self.entradas = {i.name for i in self.sess.get_inputs()}

    def _feeds(self, enc):
        largo = max(len(e.ids) for e in enc)
        ids = np.array([e.ids + [0] * (largo - len(e.ids)) for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask + [0] * (largo - len(e.ids)) for e in enc], dtype=np.int64)
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.entradas:
            feeds["token_type_ids"] = np.array([e.type_ids + [0] * (largo - len(e.ids)) for e in enc], dtype=np.int64)
        return feeds, mask


class Embedder(Modelo):
    def vectores(self, textos, lote=16):
        out = []
        for i in range(0, len(textos), lote):
            feeds, mask = self._feeds(self.tok.encode_batch(textos[i:i + lote]))
            h = self.sess.run(None, feeds)[0]  # last_hidden_state
            m = mask[..., None].astype(np.float32)
            v = (h * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
            out.append(v / np.linalg.norm(v, axis=1, keepdims=True))
        return np.vstack(out)


class HttpEmbedder:
    """Vectores de un llama-server en modo embedding (API compatible con OpenAI), normalizados."""

    def __init__(self, url):
        self.url = url.rstrip("/") + "/v1/embeddings"

    def vectores(self, textos, lote=16):
        out = []
        for i in range(0, len(textos), lote):
            req = urllib.request.Request(self.url, data=json.dumps({"input": textos[i:i + lote], "model": "x"}).encode(),
                                         headers={"Content-Type": "application/json"})
            js = json.loads(urllib.request.urlopen(req, timeout=900).read())
            v = np.array([d["embedding"] for d in sorted(js["data"], key=lambda d: d["index"])], dtype=np.float32)
            out.append(v / np.linalg.norm(v, axis=1, keepdims=True))
        return np.vstack(out)


def formatear(cfg, textos, rol):
    """Aplica el prefijo o la plantilla del modelo; rol = «query» o «passage»."""
    if "plantilla" in cfg:
        inst = cfg["inst_q"] if rol == "query" else cfg["inst_p"]
        return [cfg["plantilla"].format(inst=inst, t=t) for t in textos]
    return [cfg[rol] + t + cfg.get("fin", "") for t in textos]


class Reranker(Modelo):
    def notas(self, consulta, textos, lote=16):
        out = []
        for i in range(0, len(textos), lote):
            feeds, _ = self._feeds(self.tok.encode_batch([(consulta, t) for t in textos[i:i + lote]]))
            logits = self.sess.run(None, feeds)[0][:, 0]
            out.extend(1 / (1 + np.exp(-logits)))
        return np.array(out)


def preguntas_mirag(fases=("F2-F3", "F4")):
    P = json.loads(PREGUNTAS.read_text(encoding="utf-8"))
    return [q for q in P if q["workspace"] == "mirag" and q["fase"] in fases
            and not q["espera_rechazo"] and q["evidencia"]]


def buscar(qv, consulta, M, textos, reranker, topn=10, umbral=0.2):
    sims = M @ qv
    pool = max(10, min(50, math.ceil(len(textos) * 0.1)))
    cand = np.argsort(-sims)[:pool]
    notas = reranker.notas(consulta, [textos[i] for i in cand])
    orden = [cand[i] for i in np.argsort(-notas, kind="stable")][:topn]
    sel = [i for i in orden if sims[i] >= umbral]
    return sel, set(cand.tolist())


def evaluar(nombre_emb, frag, Q, reranker, cache):
    cfg = EMBEDDERS[nombre_emb]
    emb = cache.setdefault(nombre_emb, HttpEmbedder(cfg["url"]) if "url" in cfg else Embedder(cfg["dir"]))
    res = {}
    for ns, fr in frag.items():
        textos = [f["text"] for f in fr]
        M = emb.vectores(formatear(cfg, textos, "passage"))
        qv = emb.vectores(formatear(cfg, [q["pregunta"] for q in Q], "query"))
        filas = {}
        for k, q in enumerate(Q):
            sel, pool = buscar(qv[k], q["pregunta"], M, textos, reranker)
            es = lambda i: any(contiene(norm(textos[i]), e) for e in q["evidencia"])
            rango = next((r for r, i in enumerate(sel, 1) if es(i)), None)
            filas[q["id"]] = {"dato": rango is not None, "techo": any(es(i) for i in pool), "formato": formato_de(q),
                              "rr": 1 / rango if rango else 0.0, "primero": rango == 1, "fase": q["fase"],
                              "ing": q.get("variante") == "ingenua"}
        res[ns] = filas
    return res


def pct(rs, campo):
    return f"{100 * sum(r[campo] for r in rs) / len(rs):.0f} %"


def main():
    accion = sys.argv[1] if len(sys.argv) > 1 else "comparar"
    frag = json.loads(FRAGMENTOS.read_text(encoding="utf-8"))
    Q = preguntas_mirag()
    reranker = Reranker(RERANKER)
    cache = {}

    if accion == "validar":
        emb = Embedder(EMBEDDERS["minilm"]["dir"])
        for ns, fr in frag.items():
            V = np.array([f["vector"] for f in fr], dtype=np.float32)
            M = emb.vectores([f["text"] for f in fr])
            cos = (V * M).sum(1) / np.linalg.norm(V, axis=1)
            print(f"[{ns}] vectores locales frente a los del servidor: coseno mínimo {cos.min():.4f}, medio {cos.mean():.4f}")
        sim = evaluar("minilm", frag, Q, reranker, cache)
        for ns, filas in sim.items():
            real = {r["id"]: r["evidencia_encontrada"] == "True"
                    for r in csv.DictReader(open(ROOT / "resultados" / REAL[ns] / "recuperacion.csv", encoding="utf-8-sig"), delimiter=";")}
            comunes = [i for i in filas if i in real]
            dif = [i for i in comunes if filas[i]["dato"] != real[i]]
            print(f"[{ns}] búsqueda simulada frente a la real ({REAL[ns]}): {len(comunes) - len(dif)}/{len(comunes)} coinciden"
                  + (f"; distintas: {', '.join(dif)}" if dif else ""))
        return

    if accion == "candidatos":
        nombres = sys.argv[2:] or ["e5-small"]
        Q2 = preguntas_mirag(("F2-F3", "F4", "E8", "E8b"))
        res = {e: evaluar(e, frag, Q2, reranker, cache) for e in nombres}
        print(f"# Simulación: modelos de vectores candidatos\n\n{len(Q2)} preguntas con dato (F3, F4 y las ingenuas de E8 y E8b). "
              "topN 10, umbral 0,2, rerank igual al servidor.\n")
        for ns in frag:
            print(f"## `{ns}` ({len(frag[ns])} fragmentos)\n")
            print("| | " + " | ".join(nombres) + " |\n|---|" + "---|" * len(nombres))
            filas = [("Dato que llega (todas)", lambda r: True, "dato"), ("Dato entre los candidatos", lambda r: True, "techo"),
                     ("Dato en primer lugar", lambda r: True, "primero"),
                     ("Dato que llega, bien hechas (F3)", lambda r: r["fase"] == "F2-F3", "dato"),
                     ("Dato que llega, ingenuas (F4a, E8, E8b)", lambda r: r["ing"], "dato")]
            for nombre, filtro, campo in filas:
                print(f"| {nombre} | " + " | ".join(pct([r for r in res[e][ns].values() if filtro(r)], campo) for e in nombres) + " |")
            print("| MRR del dato | " + " | ".join(f"{np.mean([r['rr'] for r in res[e][ns].values()]):.2f}" for e in nombres) + " |")
            base = nombres[0]
            for e in nombres[1:]:
                gana = sorted(i for i in res[base][ns] if res[e][ns][i]["dato"] and not res[base][ns][i]["dato"])
                pierde = sorted(i for i in res[base][ns] if res[base][ns][i]["dato"] and not res[e][ns][i]["dato"])
                print(f"\n- {e} frente a {base}: llega y antes no ({len(gana)}): {', '.join(gana) or '—'}; "
                      f"se pierde ({len(pierde)}): {', '.join(pierde) or '—'}")
            print()
        return

    res = {e: evaluar(e, frag, Q, reranker, cache) for e in ("minilm", "e5-small")}
    print(f"# Simulación E3: modelo de vectores actual frente a multilingual-e5-small\n")
    print(f"{len(Q)} preguntas (F3 y F4 del workspace de documentos). topN 10, umbral 0,2, rerank igual al servidor.\n")
    for ns in frag:
        print(f"## `{ns}` ({len(frag[ns])} fragmentos)\n")
        print("| | all-MiniLM-L6-v2 (actual) | multilingual-e5-small |\n|---|---|---|")
        for campo, nombre in (("dato", "Dato exacto que llega al modelo"), ("techo", "Dato entre los candidatos (techo)")):
            print(f"| {nombre} | " + " | ".join(pct(list(res[e][ns].values()), campo) for e in ("minilm", "e5-small")) + " |")
        fmts = sorted({r["formato"] for r in res["minilm"][ns].values()})
        for fm in fmts:
            print(f"| {fm} | " + " | ".join(pct([r for r in res[e][ns].values() if r["formato"] == fm], "dato") for e in ("minilm", "e5-small")) + " |")
        gana = sorted(i for i in res["minilm"][ns] if res["e5-small"][ns][i]["dato"] and not res["minilm"][ns][i]["dato"])
        pierde = sorted(i for i in res["minilm"][ns] if res["minilm"][ns][i]["dato"] and not res["e5-small"][ns][i]["dato"])
        print(f"\n- Con e5 llega el dato y antes no ({len(gana)}): {', '.join(gana) or '—'}")
        print(f"- Con e5 se pierde el dato que antes llegaba ({len(pierde)}): {', '.join(pierde) or '—'}\n")


if __name__ == "__main__":
    main()
