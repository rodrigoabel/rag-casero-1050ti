#!/usr/bin/env python3
"""cambiar_embedder.py - Cambia el modelo de vectores de AnythingLLM (E3) y vuelve a asignar los documentos.

Por qué hace falta: en AnythingLLM 1.17, cambiar EmbeddingModelPref llama a resetAllVectorStores, que borra los
vectores, la caché de vectores y TODAS las asignaciones de documentos de TODOS los workspaces (los archivos convertidos
siguen en la biblioteca). Hay que volver a asignar cada documento a cada workspace para vectorizarlo con el modelo nuevo.

Pasos (desde la carpeta del proyecto):
    python3 herramientas/cambiar_embedder.py inventario                   # solo lee; guarda resultados/<fecha>_inventario.json
    ssh usuario@<servidor> 'sudo systemctl stop mirag-sync && sudo systemctl start respaldo-config.service'
    python3 herramientas/cambiar_embedder.py cambiar MintplexLabs/multilingual-e5-small --inventario resultados/<fecha>_inventario.json
    python3 herramientas/cambiar_embedder.py reasignar resultados/<fecha>_inventario.json
    python3 herramientas/cambiar_embedder.py verificar resultados/<fecha>_inventario.json
    ssh usuario@<servidor> 'sudo systemctl start mirag-sync'
Volver atrás: el mismo procedimiento con Xenova/all-MiniLM-L6-v2, o restaurar el respaldo de /var/lib/anythingllm.

Protecciones: no hace nada si hay una corrida de rag_eval.py en curso; 'cambiar' exige un respaldo de los últimos
30 min y un inventario de los últimos 30 min con todas las asignaciones actuales; todo queda en resultados/cambios_config.log.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from rag_config import SERVIDOR, anotar, corrida_en_curso, respaldo_reciente
from rag_eval import RESULTADOS, ROOT, URL_DEF, api_key, http

MODELOS = ["Xenova/all-MiniLM-L6-v2", "MintplexLabs/multilingual-e5-small", "Xenova/nomic-embed-text-v1"]
VENTANA = 30 * 60


def sistema(key):
    st, js, _ = http("GET", f"{URL_DEF}/system", key, timeout=30)
    s = js.get("settings", js) if st == 200 else {}
    return {k: s.get(k) for k in ("EmbeddingEngine", "EmbeddingModelPref", "VectorDB")}


def asignaciones(key):
    st, js, _ = http("GET", f"{URL_DEF}/workspaces", key, timeout=30)
    if st != 200:
        sys.exit(f"No pude listar los workspaces (HTTP {st})")
    out = {}
    for w in js.get("workspaces", []):
        st, j2, _ = http("GET", f"{URL_DEF}/workspace/{w['slug']}", key, timeout=30)
        ww = j2.get("workspace")
        ww = ww[0] if isinstance(ww, list) else ww
        out[w["slug"]] = sorted(d["docpath"] for d in ww.get("documents") or [])
    return out


def cmd_inventario(key, _args):
    inv = {"fecha": datetime.now().isoformat(timespec="seconds"), "sistema": sistema(key), "workspaces": asignaciones(key)}
    destino = RESULTADOS / f"{datetime.now():%Y%m%d-%H%M}_inventario.json"
    destino.write_text(json.dumps(inv, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Modelo de vectores: {inv['sistema']}")
    for s, d in inv["workspaces"].items():
        print(f"  {s:<24} {len(d):>3} documentos")
    print(f"Total: {sum(len(d) for d in inv['workspaces'].values())} asignaciones -> {destino.relative_to(ROOT)}")


def cargar_inventario(ruta):
    inv = json.loads(Path(ruta).read_text(encoding="utf-8"))
    return inv, datetime.fromisoformat(inv["fecha"])


def cmd_cambiar(key, args):
    if len(args) < 3 or args[1] != "--inventario":
        sys.exit("Uso: cambiar <modelo> --inventario <archivo>")
    modelo, (inv, fecha) = args[0], cargar_inventario(args[2])
    if modelo not in MODELOS:
        sys.exit(f"Modelo no previsto: {modelo}. Opciones: {MODELOS}")
    actual = sistema(key)
    if actual["EmbeddingModelPref"] == modelo:
        sys.exit(f"Ya está en {modelo}; nada que cambiar.")
    if (datetime.now() - fecha).total_seconds() > VENTANA:
        sys.exit("El inventario tiene más de 30 minutos: vuelve a correr 'inventario'.")
    if asignaciones(key) != inv["workspaces"]:
        sys.exit("Las asignaciones actuales no coinciden con el inventario: vuelve a correr 'inventario'.")
    ok, detalle = respaldo_reciente()
    print(f"Respaldo: {detalle}")
    if not ok or "hace" in detalle and int(detalle.split("hace ")[1].split(" ")[0]) > VENTANA // 60:
        sys.exit(f"Falta un respaldo de los últimos 30 min: ssh {SERVIDOR} 'sudo systemctl start respaldo-config.service'")
    print(f"Cambiando {actual['EmbeddingModelPref']} -> {modelo}. Esto BORRA todas las asignaciones de documentos.")
    st, js, _ = http("POST", f"{URL_DEF}/system/update-env", key, {"EmbeddingModelPref": modelo}, timeout=900)
    if st != 200 or js.get("error"):
        sys.exit(f"ERROR (HTTP {st}): {js}")
    nuevo = sistema(key)
    quedan = sum(len(d) for d in asignaciones(key).values())
    anotar(f"cambiar_embedder  {actual['EmbeddingModelPref']} -> {nuevo['EmbeddingModelPref']}  (asignaciones restantes: {quedan})")
    print(f"✓ Modelo ahora: {nuevo['EmbeddingModelPref']}. Asignaciones que quedan: {quedan} (se esperan 0).")
    print(f"Siguiente: python3 herramientas/cambiar_embedder.py reasignar {args[2]}")


def cmd_reasignar(key, args):
    inv, _ = cargar_inventario(args[0])
    for slug, docs in inv["workspaces"].items():
        actuales = set(asignaciones(key).get(slug, []))
        faltan = [d for d in docs if d not in actuales]
        if not faltan:
            print(f"  {slug:<24} sin cambios ({len(docs)} documentos)")
            continue
        t0 = time.time()
        st, js, _ = http("POST", f"{URL_DEF}/workspace/{slug}/update-embeddings", key, {"adds": faltan}, timeout=3600)
        if st != 200:
            sys.exit(f"ERROR en {slug} (HTTP {st}): {js}")
        print(f"  {slug:<24} +{len(faltan)} documentos en {time.time() - t0:.0f} s")
    anotar(f"reasignar  desde {Path(args[0]).name}")
    cmd_verificar(key, args)


def cmd_verificar(key, args):
    inv, _ = cargar_inventario(args[0])
    actual = asignaciones(key)
    malos = {s: (len(d), len(actual.get(s, []))) for s, d in inv["workspaces"].items() if sorted(actual.get(s, [])) != d}
    print(f"Modelo de vectores: {sistema(key)['EmbeddingModelPref']}")
    if malos:
        sys.exit(f"Distinto del inventario (esperados, actuales): {malos}")
    print(f"✓ Las {sum(len(d) for d in inv['workspaces'].values())} asignaciones coinciden con el inventario.")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("inventario", "cambiar", "reasignar", "verificar"):
        sys.exit(__doc__)
    if sys.argv[1] in ("cambiar", "reasignar") and corrida_en_curso():
        sys.exit("Hay una corrida de rag_eval.py en curso.")
    key = api_key()
    {"inventario": cmd_inventario, "cambiar": cmd_cambiar, "reasignar": cmd_reasignar,
     "verificar": cmd_verificar}[sys.argv[1]](key, sys.argv[2:])


if __name__ == "__main__":
    main()
