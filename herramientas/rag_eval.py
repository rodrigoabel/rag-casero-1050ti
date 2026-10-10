#!/usr/bin/env python3
"""
rag_eval.py - Ejecuta el banco de preguntas contra AnythingLLM y puntúa automáticamente.

Solo usa la biblioteca estándar de Python (se puede correr con el python3 del sistema).

Separa los dos lugares donde un RAG puede fallar:
  * recuperacion : usa /workspace/{slug}/vector-search (SIN pasar por el modelo) y mide si el documento
                   correcto y el dato exacto aparecen entre los fragmentos recuperados.
  * chat         : hace la pregunta real (/workspace/{slug}/chat, modo query) y puntúa la respuesta.
                   Con las fuentes que devuelve, diagnostica si el fallo fue de BÚSQUEDA o de GENERACIÓN.

Clave de API: crea una en AnythingLLM (Configuración -> Herramientas -> API Keys) y guárdala en
    ~/.config/prueba_rag/api_key   (chmod 600)      o en la variable ANYTHINGLLM_API_KEY

Ejemplos (desde la carpeta del proyecto):
    python3 herramientas/rag_eval.py estado
    python3 herramientas/rag_eval.py recuperacion --etiqueta baseline
    python3 herramientas/rag_eval.py chat --rapida --etiqueta humo
    python3 herramientas/rag_eval.py completo --etiqueta baseline --repeticiones 2
    python3 herramientas/rag_eval.py chat --fase F4 --etiqueta formulacion
    python3 herramientas/rag_eval.py chat --fase F6 --etiqueta actualizacion
    python3 herramientas/rag_eval.py chat --ids CON-07,CRS-13
    python3 herramientas/rag_eval.py chat --rapida --etiqueta sufijo --sufijo " Copia la frase del documento que lo respalda."
    python3 herramientas/rag_eval.py comparar resultados/<carpeta_A> resultados/<carpeta_B>
    python3 herramientas/rag_eval.py recuperacion --fase E8 --reformuladas experimentos/E8_qwen2b_mapa.json   # E8
    python3 herramientas/rag_eval.py repuntuar resultados/<carpeta> [...]   # tras corregir preguntas.json
"""

import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
PREGUNTAS = ROOT / "preguntas" / "preguntas.json"
RESULTADOS = ROOT / "resultados"
URL_DEF = os.environ.get("ANYTHINGLLM_URL", "http://localhost:3001/api/v1")
WS_DEF = {"mirag": "rag-eval", "obsidian": "notas-obsidian", "usuario2": "espacio-usuario2"}
FASES_DEF = {"F2-F3", "F4"}

FORMATO = {"CON": "Word (MarkItDown)", "SPR": "PowerPoint", "CRS": "PDF digital", "MIN": "Word (raíz, parser AnythingLLM)",
           "PRO": "PDF digital", "FUN": "PowerPoint", "CLI": "Word (MarkItDown)", "ACT": "PDF escaneado (OCR)",
           "OBS": "Obsidian", "X": "Cruce de documentos", "AIS": "Aislamiento", "UPD": "Actualización",
           "FORM": "Formulación", "ING": "Ingenua (E8)"}

RECHAZO = ["no encontr", "no encuentro", "no se encontr", "no hay informacion", "no tengo informacion",
           "no dispongo", "no se menciona", "no menciona", "no aparece", "no se especifica", "no especifica",
           "no esta disponible", "no se indica", "no indica", "no contiene", "no proporciona", "no se proporciona",
           "no se detalla", "no figura", "no puedo responder", "no puedo determinar", "no cuento con",
           "no relevant information", "there is no relevant information", "not mentioned", "no information"]

PUNTOS = {"OK": 2, "RECHAZO_OK": 2, "OK_CON_RUIDO": 1, "PARCIAL": 1, "FALLA": 0, "RECHAZO_FALSO": 0,
          "ALUCINA": 0, "ERROR": 0}


# ------------------------------------------------------------------ texto
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").replace(" ", " ").replace(" ", " ").replace("\\_", "_"))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", s)


def clave(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(s))


def contiene(texto_n: str, kw: str) -> bool:
    k = norm(kw).strip()
    if re.fullmatch(r"[\d.,]+", k):  # números: 4 no debe coincidir con 4471, ni 2 con 2,7
        return re.search(rf"(?<![\d.,]){re.escape(k)}(?!\d|[.,]\d)", texto_n) is not None
    if k[:1].isalnum():  # texto: solo al comienzo de una palabra («dos» no coincide con «proporcionados»)
        return re.search(rf"(?<![a-z0-9]){re.escape(k)}", texto_n) is not None
    return k in texto_n


def sin_think(t: str) -> str:
    return re.sub(r"<think>.*?</think>", "", t or "", flags=re.S).strip()


def lista(x):
    return x if isinstance(x, list) else [x]


# ------------------------------------------------------------------ API
def api_key() -> str:
    k = os.environ.get("ANYTHINGLLM_API_KEY", "").strip()
    if k:
        return k
    f = Path.home() / ".config" / "prueba_rag" / "api_key"
    if f.exists():
        if f.stat().st_mode & 0o077:
            print(f"AVISO: {f} es legible por otros usuarios; usa: chmod 600 {f}", file=sys.stderr)
        return f.read_text().strip()
    sys.exit("Falta la clave de API: define ANYTHINGLLM_API_KEY o crea ~/.config/prueba_rag/api_key (chmod 600).")


def http(method, url, key, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(url, data=data, method=method,
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                   "Accept": "application/json"})
    t0 = time.time()
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}"), time.time() - t0
    except error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")[:300]}, time.time() - t0
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}, time.time() - t0


def workspace_info(base, key, slug):
    st, js, _ = http("GET", f"{base}/workspace/{slug}", key, timeout=30)
    if st != 200:
        return None
    w = js.get("workspace")
    w = w[0] if isinstance(w, list) and w else w
    if not w:
        return None
    campos = ["name", "slug", "chatMode", "chatModel", "openAiTemp", "openAiHistory", "similarityThreshold", "topN",
              "vectorSearchMode", "queryRefusalResponse", "openAiPrompt"]
    info = {c: w.get(c) for c in campos}
    info["documentos"] = len(w.get("documents") or [])
    return info


def system_info(base, key):
    st, js, _ = http("GET", f"{base}/system", key, timeout=30)
    if st != 200:
        return {}
    s = js.get("settings", js)
    return {k: v for k, v in s.items()
            if isinstance(v, (str, int, float, bool, type(None)))
            and not any(x in k.lower() for x in ("key", "secret", "token", "password", "pass"))
            and any(x in k for x in ("LLM", "Ollama", "Embedding", "Vector", "Model", "TextSplitter", "Chunk"))}


# ------------------------------------------------------------------ selección
def cargar(args):
    P = json.loads(PREGUNTAS.read_text(encoding="utf-8"))
    if args.ids:
        ids = {i.strip() for i in args.ids.split(",")}
        P = [q for q in P if q["id"] in ids]
    else:
        fases = set(args.fase.split(",")) if args.fase else FASES_DEF
        P = [q for q in P if q["fase"] in fases or args.todas]
        if args.rapida:
            P = [q for q in P if q["rapida"]]
        if args.tipo:
            tipos = set(args.tipo.split(","))
            P = [q for q in P if q["tipo"] in tipos]
    if args.reformuladas:
        # E8: reemplaza el texto por el de reformular.py; el puntaje sigue usando lo esperado de la pregunta original
        R = json.loads(Path(args.reformuladas).read_text(encoding="utf-8"))["preguntas"]
        P = [dict(q, pregunta=R[q["id"]]["reformulada"], pregunta_original=q["pregunta"]) if q["id"] in R else q
             for q in P]
        print(f"Reformuladas desde {args.reformuladas}: {sum(1 for q in P if 'pregunta_original' in q)} de {len(P)}")
    return P


def slug_de(q, args):
    return {"mirag": args.ws_mirag, "obsidian": args.ws_obsidian, "usuario2": args.ws_usuario2}[q["workspace"]]


def formato_de(q):
    return FORMATO.get(q["id"].split("-")[0], "?")


def rango(items, pred):
    for i, it in enumerate(items, 1):
        if pred(it):
            return i
    return None


# ------------------------------------------------------------------ recuperación
def evaluar_recuperacion(args, key, P, out):
    filas = []
    # lista completa de resultados (título, nota del rerank, distancia, texto) para simular topN y umbral sin volver a consultar
    crudo = open(out / "recuperacion.jsonl", "w", encoding="utf-8")
    for n, q in enumerate(P, 1):
        if q["espera_rechazo"] and q["tipo"] != "aislamiento":
            continue
        slug = slug_de(q, args)
        body = {"query": q["pregunta"] + args.sufijo}
        if args.topn:
            body["topN"] = args.topn
        if args.umbral is not None:
            body["scoreThreshold"] = args.umbral
        st, js, dt = http("POST", f"{args.url}/workspace/{slug}/vector-search", key, body, timeout=120)
        res = js.get("results", []) if st == 200 else []
        titulos = [norm((r.get("metadata") or {}).get("title", "")) for r in res]
        textos = [norm(r.get("text", "")) for r in res]
        rf = [rango(titulos, lambda t, f=f: clave(f) in clave(t)) for f in lista(q["fuente_esperada"])]
        re_ = rango(textos, lambda t: any(contiene(t, e) for e in q["evidencia"])) if q["evidencia"] else None
        fuga = None
        if q["tipo"] == "aislamiento" and q["espera_rechazo"]:
            fuga = any("aislamiento_usuario2" in clave(t) or "guayacan" in t for t in titulos + textos)
        fila = {"id": q["id"], "workspace": slug, "tipo": q["tipo"], "formato": formato_de(q),
                "http": st, "n_resultados": len(res),
                "rango_fuente": ",".join("-" if r is None else str(r) for r in rf),
                "fuente_encontrada": all(r is not None for r in rf),
                "rango_evidencia": re_ if re_ is not None else "",
                "evidencia_encontrada": (re_ is not None) if q["evidencia"] else "",
                "score_max": round(max([r.get("score", 0) for r in res] or [0]), 3),
                "fuga_aislamiento": "" if fuga is None else fuga,
                "segundos": round(dt, 2),
                "top": " | ".join(f"{(r.get('metadata') or {}).get('title', '?')} ({r.get('score', 0):.2f})" for r in res[:5]),
                "error": js.get("error", "") if st != 200 else ""}
        filas.append(fila)
        crudo.write(json.dumps({"pregunta": q, "consulta": body, "http": st, "resultados": [
            {"title": (r.get("metadata") or {}).get("title", ""), "score": r.get("score"), "distance": r.get("distance"),
             "text": r.get("text", "")} for r in res]}, ensure_ascii=False) + "\n")
        marca = "✓" if fila["fuente_encontrada"] and fila["evidencia_encontrada"] in ("", True) else "✗"
        if fuga is not None:
            marca = "✗ FUGA" if fuga else "✓ aislado"
        print(f"  [{n}/{len(P)}] {marca} {q['id']:<8} fuente@{fila['rango_fuente']} evid@{fila['rango_evidencia'] or '-'} "
              f"score_max={fila['score_max']}")
        time.sleep(args.pausa)
    crudo.close()
    escribir(out / "recuperacion.csv", filas)
    return filas


# ------------------------------------------------------------------ chat
def puntuar(q, texto, fuentes):
    t = norm(texto)
    es_rechazo = any(p in t for p in RECHAZO)
    prohib = [k for k in q["prohibidas"] if contiene(t, k)]
    grupos = q["requeridas"]
    ok_g = [g for g in grupos if any(contiene(t, k) for k in g)]
    if q["espera_rechazo"]:
        if prohib:
            v = "ALUCINA"
        elif es_rechazo:
            v = "RECHAZO_OK"
        else:
            v = "REVISAR"  # no rechazó explícitamente: revisar si inventó algo
    elif not grupos:
        v = "REVISAR"
    elif len(ok_g) == len(grupos):
        v = "OK_CON_RUIDO" if prohib else "OK"
    elif es_rechazo and not ok_g:
        v = "RECHAZO_FALSO"
    elif ok_g:
        v = "PARCIAL"
    else:
        v = "FALLA"

    tit = [norm(f.get("title", "")) for f in fuentes]
    txt = [norm(f.get("text", "")) for f in fuentes]
    fuente_ok = all(any(clave(fu) in clave(x) for x in tit) for fu in lista(q["fuente_esperada"]))
    evid_ok = any(contiene(x, e) for x in txt for e in q["evidencia"]) if q["evidencia"] else None
    diag = ""
    if v in ("FALLA", "RECHAZO_FALSO", "PARCIAL"):
        if not fuente_ok or evid_ok is False:
            diag = "BÚSQUEDA: el dato no llegó al modelo"
        else:
            diag = "GENERACIÓN: el dato llegó pero el modelo no lo usó bien"
    elif v == "ALUCINA":
        diag = "ALUCINACIÓN: afirmó algo que no está o no debía ver"
    return v, prohib, len(ok_g), len(grupos), fuente_ok, evid_ok, diag


def evaluar_chat(args, key, P, out):
    filas, crudo = [], open(out / "chat.jsonl", "w", encoding="utf-8")
    stamp = out.name
    total = len(P) * args.repeticiones
    k = 0
    for q in P:
        slug = slug_de(q, args)
        for rep in range(1, args.repeticiones + 1):
            k += 1
            body = {"message": q["pregunta"] + args.sufijo, "mode": args.modo, "sessionId": f"rag-eval-{stamp}-{q['id']}-{rep}"}
            st, js, dt = http("POST", f"{args.url}/workspace/{slug}/chat", key, body, timeout=args.timeout)
            if st != 200 or js.get("error"):
                v, resp, fuentes = "ERROR", js.get("error", f"HTTP {st}"), []
                prohib, nok, ng, fok, eok, diag = [], 0, len(q["requeridas"]), False, None, "ERROR de API"
            else:
                resp = sin_think(js.get("textResponse") or "")
                fuentes = js.get("sources") or []
                v, prohib, nok, ng, fok, eok, diag = puntuar(q, resp, fuentes)
            if q["revision_manual"] and v not in ("ERROR",):
                diag = (diag + " | " if diag else "") + "revisar a mano"
            m = js.get("metrics") or {}
            fila = {"id": q["id"], "rep": rep, "workspace": slug, "tipo": q["tipo"], "formato": formato_de(q),
                    "par": q.get("par") or "", "variante": q.get("variante") or "", "veredicto": v,
                    "puntos": PUNTOS.get(v, ""), "requeridas_ok": f"{nok}/{ng}", "prohibidas_halladas": ";".join(prohib),
                    "fuente_en_citas": fok, "evidencia_en_citas": "" if eok is None else eok, "diagnostico": diag,
                    "segundos": round(dt, 1), "tokens_salida": m.get("completion_tokens", ""),
                    "tok_por_seg": round(m["outputTps"], 1) if isinstance(m.get("outputTps"), (int, float)) else "",
                    "pregunta": q["pregunta"], "esperada": q["respuesta_esperada"],
                    "respuesta": resp.replace("\n", " ")[:600],
                    "citas": " | ".join(dict.fromkeys(f.get("title", "?") for f in fuentes))}
            filas.append(fila)
            crudo.write(json.dumps({"pregunta": q, "respuesta_api": js, "segundos": dt}, ensure_ascii=False) + "\n")
            print(f"  [{k}/{total}] {v:<13} {q['id']:<9} {dt:5.1f}s  {resp[:90].replace(chr(10), ' ')!r}")
            time.sleep(args.pausa)
    crudo.close()
    escribir(out / "chat.csv", filas)
    return filas


# ------------------------------------------------------------------ informes
def escribir(path, filas):
    if not filas:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(filas)


def pct(a, b):
    return f"{100 * a / b:.0f} %" if b else "—"


def resumen(out, cfg, rec, chat):
    L = [f"# Resultados: {out.name}", "", f"Fecha: {datetime.now():%Y-%m-%d %H:%M}", ""]
    L += ["## Configuración usada", "", "```json", json.dumps(cfg, ensure_ascii=False, indent=1)[:4000], "```", ""]
    if rec:
        L += ["## Recuperación (sin modelo)", ""]
        normales = [r for r in rec if r["fuga_aislamiento"] == ""]
        fo = sum(1 for r in normales if r["fuente_encontrada"])
        con_ev = [r for r in normales if r["evidencia_encontrada"] != ""]
        eo = sum(1 for r in con_ev if r["evidencia_encontrada"] is True)
        rr = [1 / int(r["rango_evidencia"]) if r["rango_evidencia"] != "" else 0 for r in con_ev]
        L += [f"- Documento correcto entre los recuperados: **{fo}/{len(normales)} ({pct(fo, len(normales))})**",
              f"- Dato exacto entre los fragmentos recuperados: **{eo}/{len(con_ev)} ({pct(eo, len(con_ev))})**",
              f"- MRR del dato exacto (1 = siempre primero): **{statistics.mean(rr):.2f}**" if rr else "",
              ""]
        fugas = [r for r in rec if r["fuga_aislamiento"] is True]
        if any(r["fuga_aislamiento"] != "" for r in rec):
            L += [f"- Aislamiento: **{'FUGA en ' + ', '.join(r['id'] for r in fugas) if fugas else 'sin fugas'}**", ""]
        L += ["| Formato | Dato recuperado |", "|---|---|"]
        for fmt in sorted({r["formato"] for r in con_ev}):
            g = [r for r in con_ev if r["formato"] == fmt]
            ok = sum(1 for r in g if r["evidencia_encontrada"] is True)
            L.append(f"| {fmt} | {ok}/{len(g)} ({pct(ok, len(g))}) |")
        L.append("")
        malas = [r for r in con_ev if r["evidencia_encontrada"] is not True]
        if malas:
            L += ["", "**No recuperadas:** " + ", ".join(r["id"] for r in malas), ""]
    if chat:
        val = [c for c in chat if c["puntos"] != ""]
        pts = sum(c["puntos"] for c in val)
        L += ["## Respuestas del modelo", "",
              f"- Puntaje: **{pts}/{2 * len(val)} ({pct(pts, 2 * len(val))})** sobre {len(val)} respuestas puntuables "
              f"(OK y RECHAZO_OK = 2, PARCIAL y OK_CON_RUIDO = 1, resto = 0).",
              f"- Pendientes de revisión manual (REVISAR): {sum(1 for c in chat if c['veredicto'] == 'REVISAR')}", ""]
        cuenta = {}
        for c in chat:
            cuenta[c["veredicto"]] = cuenta.get(c["veredicto"], 0) + 1
        L += ["| Veredicto | Cantidad |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(cuenta.items())] + [""]
        for campo, titulo in (("tipo", "Tipo de pregunta"), ("formato", "Formato del documento")):
            L += [f"| {titulo} | Puntaje |", "|---|---|"]
            for k in sorted({c[campo] for c in val}):
                g = [c for c in val if c[campo] == k]
                p = sum(c["puntos"] for c in g)
                L.append(f"| {k} | {p}/{2 * len(g)} ({pct(p, 2 * len(g))}) |")
            L.append("")
        seg = [c["segundos"] for c in chat if c["veredicto"] != "ERROR"]
        if seg:
            seg_o = sorted(seg)
            L += [f"- Latencia: media {statistics.mean(seg):.1f} s, mediana {statistics.median(seg):.1f} s, "
                  f"p95 {seg_o[max(0, int(0.95 * len(seg_o)) - 1)]:.1f} s, máxima {max(seg):.1f} s", ""]
        diags = [c for c in chat if c["diagnostico"].startswith(("BÚSQUEDA", "GENERACIÓN", "ALUCINACIÓN"))]
        if diags:
            b = sum(1 for c in diags if c["diagnostico"].startswith("BÚSQUEDA"))
            g = sum(1 for c in diags if c["diagnostico"].startswith("GENERACIÓN"))
            a = sum(1 for c in diags if c["diagnostico"].startswith("ALUCINACIÓN"))
            L += ["## ¿Dónde falla?", "", f"- Fallos de **búsqueda** (el dato no llegó al modelo): {b}",
                  f"- Fallos de **generación** (llegó, pero respondió mal): {g}", f"- **Alucinaciones**: {a}", ""]
        pares = {}
        for c in chat:
            if c["par"]:
                pares.setdefault(c["par"], {}).setdefault(c["variante"], []).append(c["veredicto"])
        if pares:
            L += ["## Formulación: pregunta ingenua vs bien hecha", "", "| Par | Ingenua | Mejorada |", "|---|---|---|"]
            for p, d in sorted(pares.items()):
                L.append(f"| {p} | {', '.join(d.get('ingenua', []))} | {', '.join(d.get('mejorada', []))} |")
            L.append("")
        L += ["## Detalle de lo que no salió OK", "", "| ID | Rep | Veredicto | Diagnóstico | Respuesta (recorte) |",
              "|---|---|---|---|---|"]
        for c in chat:
            if c["veredicto"] not in ("OK", "RECHAZO_OK"):
                L.append(f"| {c['id']} | {c['rep']} | {c['veredicto']} | {c['diagnostico']} | "
                         f"{c['respuesta'][:160].replace('|', '/')} |")
    (out / "resumen.md").write_text("\n".join(x for x in L if x is not None), encoding="utf-8")
    print(f"\nResumen: {out / 'resumen.md'}")


def leer_csv(p):
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def repuntuar(carpeta: Path):
    """Vuelve a puntuar chat.csv desde chat.jsonl (respuesta y fuentes guardadas) con el preguntas.json actual.
    No consulta al servidor. El chat.csv original queda en chat.csv.orig (solo la primera vez)."""
    filas, jsonl = leer_csv(carpeta / "chat.csv"), carpeta / "chat.jsonl"
    if not filas or not jsonl.exists():
        sys.exit(f"{carpeta}: faltan chat.csv o chat.jsonl")
    crudo = [json.loads(linea) for linea in jsonl.read_text(encoding="utf-8").splitlines() if linea.strip()]
    if len(crudo) != len(filas):
        sys.exit(f"{carpeta}: chat.csv ({len(filas)}) y chat.jsonl ({len(crudo)}) no tienen las mismas filas")
    P = {q["id"]: q for q in json.loads(PREGUNTAS.read_text(encoding="utf-8"))}
    orig = carpeta / "chat.csv.orig"
    if not orig.exists():
        orig.write_bytes((carpeta / "chat.csv").read_bytes())
    cambios = []
    for fila, c in zip(filas, crudo):
        if fila["id"] != c["pregunta"]["id"]:
            sys.exit(f"{carpeta}: el orden de chat.csv y chat.jsonl no coincide ({fila['id']} / {c['pregunta']['id']})")
        if fila["veredicto"] == "ERROR":
            continue
        q, js = P[fila["id"]], c["respuesta_api"]
        v, prohib, nok, ng, fok, eok, diag = puntuar(q, sin_think(js.get("textResponse") or ""), js.get("sources") or [])
        if q["revision_manual"]:
            diag = (diag + " | " if diag else "") + "revisar a mano"
        if v != fila["veredicto"]:
            cambios.append(f"{fila['id']} r{fila['rep']}: {fila['veredicto']} -> {v}")
        fila.update({"veredicto": v, "puntos": PUNTOS.get(v, ""), "requeridas_ok": f"{nok}/{ng}",
                     "prohibidas_halladas": ";".join(prohib), "fuente_en_citas": fok,
                     "evidencia_en_citas": "" if eok is None else eok, "diagnostico": diag})
    escribir(carpeta / "chat.csv", filas)
    nota = (f"\n\n> **Repuntuado el {datetime.now():%Y-%m-%d %H:%M}** con el `preguntas.json` vigente: "
            f"{len(cambios)} veredictos cambiaron ({'; '.join(cambios) or '—'}). Las cifras de arriba son las "
            f"originales; el `chat.csv` actual tiene las nuevas (el original está en `chat.csv.orig`).\n")
    if cambios and (carpeta / "resumen.md").exists():
        with open(carpeta / "resumen.md", "a", encoding="utf-8") as f:
            f.write(nota)
    print(f"{carpeta.name}: {len(cambios)} cambios" + "".join(f"\n  {x}" for x in cambios))


def comparar(a: Path, b: Path):
    """Compara dos corridas. Las cifras se calculan solo sobre las preguntas que están en ambas
    (p. ej. un experimento con --rapida frente a la línea base completa). Acepta carpetas con
    chat.csv, con recuperacion.csv o con ambos."""
    def por_id(rows):
        d = {}
        for r in rows:
            d.setdefault(r["id"], []).append(r)
        return d

    def pct(rs, campo):
        n = [r for r in rs if r[campo] in ("True", "False")]
        return 100 * sum(1 for r in n if r[campo] == "True") / max(1, len(n))

    def cambios(da, db, valor):
        mejor, peor = [], []
        for i in sorted(set(da) & set(db)):
            ma, mb = valor(da[i]), valor(db[i])
            if ma is None or mb is None or ma == mb:
                continue
            (mejor if mb > ma else peor).append(i)
        return mejor, peor

    ca, cb = leer_csv(a / "chat.csv"), leer_csv(b / "chat.csv")
    ra, rb = leer_csv(a / "recuperacion.csv"), leer_csv(b / "recuperacion.csv")
    if not (ca and cb) and not (ra and rb):
        sys.exit("Las dos carpetas deben tener chat.csv o las dos recuperacion.csv")
    print(f"A: {a.name}\nB: {b.name}")

    if ra and rb:
        da, db = por_id(ra), por_id(rb)
        comunes = set(da) & set(db)
        ra, rb = [r for r in ra if r["id"] in comunes], [r for r in rb if r["id"] in comunes]
        print(f"\n== Recuperación ({len(comunes)} preguntas en común)")
        print(f"Dato exacto recuperado: A {pct(ra, 'evidencia_encontrada'):.0f} %   ->   B {pct(rb, 'evidencia_encontrada'):.0f} %")
        print(f"Documento correcto:     A {pct(ra, 'fuente_encontrada'):.0f} %   ->   B {pct(rb, 'fuente_encontrada'):.0f} %")
        rango_ = lambda rs: (-int(rs[0]["rango_evidencia"]) if rs[0]["rango_evidencia"] else -99)
        mejor, peor = cambios(da, db, rango_)
        fmt = lambda i: f"  {i:<9} evid@{da[i][0]['rango_evidencia'] or '-'}  ->  evid@{db[i][0]['rango_evidencia'] or '-'}"
        print(f"Dato sube de posición o aparece ({len(mejor)}):")
        print("\n".join(fmt(i) for i in mejor) or "  -")
        print(f"Dato baja de posición o se pierde ({len(peor)}):")
        print("\n".join(fmt(i) for i in peor) or "  -")

    if ca and cb:
        da, db = por_id(ca), por_id(cb)
        comunes = set(da) & set(db)
        ca, cb = [r for r in ca if r["id"] in comunes], [r for r in cb if r["id"] in comunes]
        print(f"\n== Respuestas ({len(comunes)} preguntas en común; filas: A {len(ca)}, B {len(cb)})")
        punt = lambda rs: 100 * sum(int(r["puntos"]) for r in rs if r["puntos"]) / max(1, 2 * sum(1 for r in rs if r["puntos"]))
        print(f"Puntaje: A {punt(ca):.0f} %   ->   B {punt(cb):.0f} %")
        print(f"Dato exacto en las citas (llegó al modelo): A {pct(ca, 'evidencia_en_citas'):.0f} %   ->   B {pct(cb, 'evidencia_en_citas'):.0f} %")

        def media(rs):
            p = [int(r["puntos"]) for r in rs if r["puntos"] not in ("", None)]
            return statistics.mean(p) if p else None

        mejor, peor = cambios(da, db, media)
        fmt = lambda i: f"  {i:<9} {'/'.join(r['veredicto'] for r in da[i])}  ->  {'/'.join(r['veredicto'] for r in db[i])}"
        print(f"\nMejoraron ({len(mejor)}):")
        print("\n".join(fmt(i) for i in mejor) or "  -")
        print(f"\nEmpeoraron ({len(peor)}):")
        print("\n".join(fmt(i) for i in peor) or "  -")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("accion", choices=["estado", "recuperacion", "chat", "completo", "comparar", "repuntuar"])
    ap.add_argument("carpetas", nargs="*", help="para 'comparar': dos carpetas de resultados; para 'repuntuar': una o más")
    ap.add_argument("--url", default=URL_DEF)
    ap.add_argument("--ws-mirag", default=WS_DEF["mirag"])
    ap.add_argument("--ws-obsidian", default=WS_DEF["obsidian"])
    ap.add_argument("--ws-usuario2", default=WS_DEF["usuario2"])
    ap.add_argument("--fase", help="F2-F3 (base), F4 (formulación), F6 (actualización), F7 (aislamiento); separadas por coma")
    ap.add_argument("--todas", action="store_true", help="todas las fases")
    ap.add_argument("--rapida", action="store_true", help="solo el subconjunto rápido (~27 preguntas)")
    ap.add_argument("--tipo", help="filtra por tipo (factual,tabla,rechazo,...)")
    ap.add_argument("--ids", help="lista de IDs separados por coma")
    ap.add_argument("--repeticiones", type=int, default=1, help="repetir cada pregunta (mide variabilidad)")
    ap.add_argument("--modo", default="query", choices=["query", "chat"])
    ap.add_argument("--topn", type=int, help="topN para vector-search (por defecto, el del workspace)")
    ap.add_argument("--umbral", type=float, help="scoreThreshold para vector-search (por defecto, el del workspace)")
    ap.add_argument("--pausa", type=float, default=1.0, help="segundos entre preguntas")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--etiqueta", default="prueba")
    ap.add_argument("--sufijo", default="", help="texto que se agrega al final de cada pregunta (prueba instrucciones del lado de la pregunta)")
    ap.add_argument("--reformuladas", help="JSON de reformular.py: reemplaza el texto de esas preguntas (E8)")
    args = ap.parse_args()

    if args.accion == "repuntuar":
        if not args.carpetas:
            sys.exit("Uso: rag_eval.py repuntuar <carpeta> [<carpeta> ...]")
        for c in args.carpetas:
            repuntuar(Path(c))
        return 0
    if args.accion == "comparar":
        if len(args.carpetas) != 2:
            sys.exit("Uso: rag_eval.py comparar <carpeta_A> <carpeta_B>")
        return comparar(Path(args.carpetas[0]), Path(args.carpetas[1]))

    if args.carpetas:
        # argparse toma como posicional cualquier argumento con espacios (p. ej. "--reformuladas x.json" sin separar)
        sys.exit(f"Argumentos no reconocidos para '{args.accion}': {args.carpetas}")
    key = api_key()
    slugs = {"mirag": args.ws_mirag, "obsidian": args.ws_obsidian, "usuario2": args.ws_usuario2}
    cfg = {"url": args.url, "workspaces": {}, "sistema": system_info(args.url, key),
           "argumentos": {k: v for k, v in vars(args).items() if k not in ("carpetas",)}}
    for rol, slug in slugs.items():
        cfg["workspaces"][rol] = workspace_info(args.url, key, slug) or {"slug": slug, "error": "no accesible"}

    if args.accion == "estado":
        print(json.dumps(cfg, ensure_ascii=False, indent=1))
        return 0

    P = cargar(args)
    if not P:
        sys.exit("No hay preguntas con esos filtros.")
    out = RESULTADOS / f"{datetime.now():%Y%m%d-%H%M}_{re.sub(r'[^A-Za-z0-9_-]', '_', args.etiqueta)}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(P)} preguntas -> {out}")
    rec = chat = []
    if args.accion in ("recuperacion", "completo"):
        print("\n== Recuperación (vector-search, sin modelo)")
        rec = evaluar_recuperacion(args, key, P, out)
    if args.accion in ("chat", "completo"):
        print(f"\n== Chat (modo {args.modo}, {args.repeticiones} repetición/es)")
        chat = evaluar_chat(args, key, P, out)
    resumen(out, cfg, rec, chat)
    return 0


if __name__ == "__main__":
    sys.exit(main())
