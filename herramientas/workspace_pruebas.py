#!/usr/bin/env python3
"""workspace_pruebas.py - Crea o borra el workspace de pruebas `rag-eval` (experimento E2b, hallazgo H14).

`rag-eval` contiene solo los 8 documentos del corpus ficticio de Mi_RAG. Los toma de los que ya están en el
workspace `prueba`, sin volver a subirlos, y copia su configuración (prompt, temperatura, topN, umbral, rerank...).
No toca `prueba`, `notas-obsidian` ni los espacios de Usuario2.

Protecciones (las mismas de rag_config.py):
  * No hace nada si hay una corrida de rag_eval.py en curso.
  * 'crear' exige un respaldo-config.service exitoso de las últimas 3 horas.
  * Solo crea o borra el slug `rag-eval`; nunca otro.
  * Verifica el resultado y lo anota en resultados/cambios_config.log.

Uso (desde la carpeta del proyecto):
    python3 herramientas/workspace_pruebas.py crear
    python3 herramientas/workspace_pruebas.py ver
    python3 herramientas/workspace_pruebas.py borrar
Para medir: rag_eval.py ... --ws-mirag rag-eval
"""
import os
import sys
from pathlib import Path

from rag_config import CAMPOS, SERVIDOR, anotar, corrida_en_curso, iguales, leer, respaldo_reciente
from rag_eval import ROOT, URL_DEF, api_key, http

SLUG = "rag-eval"
ORIGEN = os.environ.get("RAG_ESPACIO_ORIGEN", "prueba")  # espacio que ya tiene los 8 documentos
# los 8 documentos del corpus ficticio de Mi_RAG (nombres de archivo sin extensión)
CORPUS = sorted(p.stem for p in (ROOT / "corpus" / "usuario1" / "Mi_RAG").rglob("*") if p.is_file())


def workspace(key, slug):
    st, js, _ = http("GET", f"{URL_DEF}/workspace/{slug}", key, timeout=30)
    w = js.get("workspace") if st == 200 else None
    w = w[0] if isinstance(w, list) and w else w
    return w or None


def docs_corpus(w):
    return sorted(d["docpath"] for d in w.get("documents") or [] if any(d["docpath"].split("/")[-1].startswith(c + ".") for c in CORPUS))


def cmd_ver(key):
    w = workspace(key, SLUG)
    if not w:
        print(f"No existe el workspace `{SLUG}`.")
        return
    print(f"`{SLUG}`: {len(w.get('documents') or [])} documentos")
    for d in w.get("documents") or []:
        print(f"  {d['docpath']}")
    for c in CAMPOS:
        print(f"  {c:<21} {str(w.get(c))[:70]!r}")


def cmd_crear(key):
    if workspace(key, SLUG):
        sys.exit(f"Ya existe `{SLUG}`. Revísalo con 'ver' o bórralo con 'borrar'.")
    ok, detalle = respaldo_reciente()
    print(f"Respaldo: {detalle}")
    if not ok:
        sys.exit(f"Falta un respaldo reciente: ssh {SERVIDOR} 'sudo systemctl start respaldo-config.service'")
    origen = workspace(key, ORIGEN)
    adds = docs_corpus(origen)
    if len(adds) != len(CORPUS):
        sys.exit(f"En `{ORIGEN}` encontré {len(adds)} de los {len(CORPUS)} documentos del corpus: {adds}")
    config = {c: origen.get(c) for c in CAMPOS}
    st, js, _ = http("POST", f"{URL_DEF}/workspace/new", key, {"name": SLUG, **config}, timeout=60)
    nuevo = (js.get("workspace") or {}) if st == 200 else {}
    if nuevo.get("slug") != SLUG:
        sys.exit(f"ERROR al crear (HTTP {st}): {js}. Si se creó con otro slug, bórralo a mano en la web.")
    print(f"Creado `{SLUG}`. Agregando {len(adds)} documentos (reutiliza los vectores en caché)...")
    st, js, _ = http("POST", f"{URL_DEF}/workspace/{SLUG}/update-embeddings", key, {"adds": adds}, timeout=600)
    if st != 200:
        sys.exit(f"ERROR al agregar documentos (HTTP {st}): {js}")
    w = workspace(key, SLUG)
    malos = [c for c in CAMPOS if not iguales(w.get(c), config[c])]
    docs = docs_corpus(w)
    if malos or len(docs) != len(CORPUS) or len(w.get("documents") or []) != len(CORPUS):
        sys.exit(f"ERROR en la verificación: campos distintos {malos}; documentos {len(w.get('documents') or [])}")
    anotar(f"crear {SLUG}  {len(docs)} documentos del corpus; configuración copiada de {ORIGEN}")
    print(f"✓ `{SLUG}` creado y verificado: {len(docs)} documentos, configuración igual a `{ORIGEN}`.")


def cmd_borrar(key):
    if not workspace(key, SLUG):
        print(f"No existe `{SLUG}`; nada que borrar.")
        return
    st, js, _ = http("DELETE", f"{URL_DEF}/workspace/{SLUG}", key, timeout=120)
    if st != 200 or workspace(key, SLUG):
        sys.exit(f"ERROR al borrar (HTTP {st}): {js}")
    anotar(f"borrar {SLUG}")
    print(f"✓ `{SLUG}` borrado. Los documentos siguen en `{ORIGEN}`.")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("crear", "ver", "borrar"):
        sys.exit(__doc__)
    if sys.argv[1] != "ver" and corrida_en_curso():
        sys.exit("Hay una corrida de rag_eval.py en curso.")
    key = api_key()
    {"crear": cmd_crear, "ver": cmd_ver, "borrar": cmd_borrar}[sys.argv[1]](key)


if __name__ == "__main__":
    main()
