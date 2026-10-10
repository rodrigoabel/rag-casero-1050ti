#!/usr/bin/env python3
"""medir_velocidad.py - Mide un modelo de Ollama con prompts reales del RAG, sin pasar por AnythingLLM.

Arma el mismo prompt que envía AnythingLLM (prompt del sistema E1c + los fragmentos que devuelve la búsqueda
del workspace + la pregunta) para varias preguntas distintas de la F3, y los manda directo a Ollama con el
contexto de AnythingLLM (16.384 tokens). Muestra, por pregunta, la carga, la lectura del contexto (tok/s),
la generación (tok/s) y el total; al final, cuánto del modelo quedó en la GPU (/api/ps).

Sirve para el paso 2 del método (docs/METODO.md): saber si un modelo cabe en la GPU y cuánto tardará antes de
medir su calidad. No cambia la configuración de AnythingLLM ni de Ollama.

Uso (desde la carpeta del proyecto):
    python3 herramientas/medir_velocidad.py gemma4:e4b-texto-gpu
    python3 herramientas/medir_velocidad.py qwen3.5:4b --n 8 --num-batch 1024
Variables: OLLAMA_URL (por defecto http://localhost:11434), ANYTHINGLLM_URL y ANYTHINGLLM_API_KEY (como rag_eval.py).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from rag_eval import PREGUNTAS, ROOT, URL_DEF, api_key, http

OLLAMA_DEF = os.environ.get("OLLAMA_URL", "http://localhost:11434")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modelo")
    ap.add_argument("--n", type=int, default=5, help="cantidad de preguntas (prompts distintos)")
    ap.add_argument("--num-batch", type=int, help="options.num_batch de Ollama (-b y -ub de llama-server)")
    ap.add_argument("--workspace", default="rag-eval")
    ap.add_argument("--topn", type=int, default=10)
    ap.add_argument("--prompt", default="experimentos/E1c_prompt_sistema_es.txt")
    ap.add_argument("--ollama", default=OLLAMA_DEF)
    ap.add_argument("--url", default=URL_DEF, help="API de AnythingLLM")
    args = ap.parse_args()

    sistema = (ROOT / args.prompt).read_text(encoding="utf-8").strip()
    preguntas = [q for q in json.load(open(PREGUNTAS, encoding="utf-8"))
                 if q["fase"] == "F2-F3" and q["workspace"] == "mirag" and not q["espera_rechazo"]][::7][:args.n]
    key = api_key()
    for q in preguntas:
        st, js, _ = http("POST", f"{args.url}/workspace/{args.workspace}/vector-search", key,
                         {"query": q["pregunta"], "topN": args.topn}, timeout=120)
        if st != 200:
            sys.exit(f"vector-search respondió {st}")
        ctx = "".join(f"[CONTEXT {i}]:\n{r.get('text', '')}\n[END CONTEXT {i}]\n\n" for i, r in enumerate(js.get("results", [])))
        body = {"model": args.modelo, "stream": False, "think": False, "keep_alive": 300,
                "messages": [{"role": "system", "content": sistema + "\nContext:\n" + ctx},
                             {"role": "user", "content": q["pregunta"]}],
                "options": {"num_ctx": 16384, "temperature": 0.2, **({"num_batch": args.num_batch} if args.num_batch else {})}}
        req = urllib.request.Request(f"{args.ollama.rstrip('/')}/api/chat", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=600))
        except urllib.error.HTTPError as e:
            sys.exit(f"HTTP {e.code}: {e.read()[:300]}")
        pe, ev = max(r.get("prompt_eval_duration", 1), 1) / 1e9, max(r.get("eval_duration", 1), 1) / 1e9
        print(f"{q['id']:7s} carga {r.get('load_duration', 0) / 1e9:5.1f} s | contexto {r.get('prompt_eval_count')} tok a "
              f"{r.get('prompt_eval_count', 0) / pe:5.0f} tok/s | genera {r.get('eval_count')} tok a "
              f"{r.get('eval_count', 0) / ev:5.1f} tok/s | total {r.get('total_duration', 0) / 1e9:5.1f} s")
    ps = json.load(urllib.request.urlopen(f"{args.ollama.rstrip('/')}/api/ps", timeout=10))
    for m in ps.get("models", []):
        if m.get("name") == args.modelo or m.get("model") == args.modelo:
            tot, gpu = m.get("size", 0), m.get("size_vram", 0)
            print(f"\nEn la GPU: {100 * gpu / max(tot, 1):.0f} % del modelo (lo mismo que muestra «ollama ps»). "
                  "Si no es el 100 %, prueba una variante «solo texto» o num_gpu 99; la VRAM total, con nvidia-smi.")


if __name__ == "__main__":
    main()
