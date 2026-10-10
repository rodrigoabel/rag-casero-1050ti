#!/usr/bin/env python3
"""rag_config.py - Aplica y revierte cambios de configuración de los workspaces de AnythingLLM (experimentos E1, E2...).

Solo usa la biblioteca estándar (python3 del sistema) y la misma clave de API que rag_eval.py.

Un experimento se describe en un .json de experimentos/:
    {"descripcion": "...",
     "workspaces": ["prueba", "notas-obsidian"],
     "cambios": {"openAiPrompt": "@E1_prompt_sistema_es.txt", "openAiTemp": 0.2}}
Un valor que empieza con "@" se lee de ese archivo de experimentos/.

Protecciones:
  * No cambia nada si hay una corrida de rag_eval.py en curso (falsearía sus resultados).
  * 'aplicar' exige un respaldo-config.service exitoso de las últimas 3 horas (salvo --sin-respaldo).
  * Antes de cambiar, guarda la configuración actual en resultados/<fecha>_config_antes_<exp>.json.
  * Después de cambiar, vuelve a leer el workspace y comprueba cada campo.
  * Cada cambio queda anotado en resultados/cambios_config.log.

Ejemplos (desde la carpeta del proyecto):
    python3 herramientas/rag_config.py ver
    python3 herramientas/rag_config.py aplicar experimentos/E1a.json --simular
    python3 herramientas/rag_config.py aplicar experimentos/E1a.json
    python3 herramientas/rag_config.py revertir                      # a resultados/estado_inicial.json
    python3 herramientas/rag_config.py revertir --a resultados/<fecha>_config_antes_E1a.json
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rag_eval import RESULTADOS, ROOT, URL_DEF, api_key, http, workspace_info

SERVIDOR = os.environ.get("RAG_SERVIDOR_SSH", "usuario@servidor")  # para comprobar el respaldo (respaldo-config.service)
EXPERIMENTOS = ROOT / "experimentos"
ESTADO_INICIAL = RESULTADOS / "estado_inicial.json"
REGISTRO = RESULTADOS / "cambios_config.log"
# campos que los experimentos pueden tocar y que 'revertir' restaura
CAMPOS = ["openAiPrompt", "openAiTemp", "queryRefusalResponse", "topN", "similarityThreshold",
          "vectorSearchMode", "openAiHistory", "chatMode", "chatModel"]
# chatModel: modelo de respuesta propio del workspace (E6). La API no guarda chatProvider: queda None y usa el
# proveedor global (Ollama), así que basta con chatModel. None = el modelo global (OLLAMA_MODEL_PREF)
VENTANA_RESPALDO = 3 * 3600


def corrida_en_curso() -> bool:
    # anclado al intérprete: un shell cuyo comando solo *menciona* rag_eval.py (p. ej. una cadena con &&) no cuenta
    r = subprocess.run(["pgrep", "-f", r"^[^ ]*python[0-9.]* .*rag_eval\.py (completo|chat|recuperacion)"],
                       capture_output=True)
    return r.returncode == 0


def respaldo_reciente() -> tuple[bool, str]:
    cmd = "systemctl show respaldo-config.service -p Result -p ExecMainExitTimestamp --timestamp=unix; date +%s"
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=5", SERVIDOR, cmd], capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        return False, f"no pude consultar el servidor: {r.stderr.strip()[:200]}"
    props = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)
    ahora = int(r.stdout.split()[-1])
    marca = props.get("ExecMainExitTimestamp", "").lstrip("@")
    if not marca.isdigit():
        return False, "respaldo-config.service no se ha ejecutado desde el último arranque"
    edad = ahora - int(marca)
    detalle = f"último respaldo hace {edad // 60} min, resultado {props.get('Result')}"
    return props.get("Result") == "success" and edad <= VENTANA_RESPALDO, detalle


def valor(v):
    if isinstance(v, str) and v.startswith("@"):
        return (EXPERIMENTOS / v[1:]).read_text(encoding="utf-8").strip()
    return v


def iguales(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-9
    return a == b


def corto(v) -> str:
    if isinstance(v, str):
        v1 = v.replace("\n", " ")
        return repr(v1[:70] + ("…" if len(v1) > 70 else "")) + (f" ({len(v)} car.)" if len(v) > 70 else "")
    return repr(v)


def anotar(texto: str):
    with open(REGISTRO, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {texto}\n")


def leer(key, slug) -> dict:
    w = workspace_info(URL_DEF, key, slug)
    if w is None:
        sys.exit(f"No pude leer el workspace {slug}")
    return w


def cambiar(key, nombre, objetivo: dict[str, dict], simular: bool) -> int:
    """objetivo = {slug: {campo: valor}}. Envía solo los campos que difieren y verifica."""
    total = 0
    for slug, campos in objetivo.items():
        actual = leer(key, slug)
        dif = {c: v for c, v in campos.items() if not iguales(actual.get(c), v)}
        print(f"\n[{slug}]")
        if not dif:
            print("  sin cambios (ya tiene esos valores)")
            continue
        for c, v in dif.items():
            print(f"  {c}: {corto(actual.get(c))}\n  {' ' * len(c)}  -> {corto(v)}")
        if simular:
            continue
        st, js, _ = http("POST", f"{URL_DEF}/workspace/{slug}/update", key, dif, timeout=60)
        if st != 200:
            sys.exit(f"  ERROR HTTP {st}: {js.get('error', js)}")
        despues = leer(key, slug)
        malos = [c for c, v in dif.items() if not iguales(despues.get(c), v)]
        if malos:
            sys.exit(f"  ERROR: tras el cambio no coinciden {malos}. Revisa con 'ver' y revierte.")
        anotar(f"{nombre}  {slug}  " + ", ".join(f"{c}={corto(v)}" for c, v in dif.items()))
        print("  ✓ aplicado y verificado")
        total += len(dif)
    return total


def cmd_ver(key, _args):
    ini = json.loads(ESTADO_INICIAL.read_text(encoding="utf-8"))["workspaces"] if ESTADO_INICIAL.exists() else {}
    ini = {w["slug"]: w for w in ini.values() if "slug" in w}
    for slug in os.environ.get("RAG_ESPACIOS", "rag-eval").split(","):  # espacios separados por comas
        w = leer(key, slug)
        print(f"\n[{slug}]")
        for c in CAMPOS:
            marca = "" if slug not in ini or iguales(ini[slug].get(c), w.get(c)) else "   ← distinto del original"
            print(f"  {c:<21} {corto(w.get(c))}{marca}")


def cmd_aplicar(key, args):
    exp = Path(args.experimento)
    d = json.loads(exp.read_text(encoding="utf-8"))
    cambios = {c: valor(v) for c, v in d["cambios"].items()}
    fuera = [c for c in cambios if c not in CAMPOS]
    if fuera:
        sys.exit(f"Campos no previstos (no se podrían revertir con 'revertir'): {fuera}")
    print(f"Experimento {exp.stem}: {d.get('descripcion', '')}")
    if not args.simular:
        if not args.sin_respaldo:
            ok, detalle = respaldo_reciente()
            print(f"Respaldo: {detalle}")
            if not ok:
                sys.exit("Falta un respaldo reciente. Corre primero:\n"
                         f"  ssh {SERVIDOR} 'sudo systemctl start respaldo-config.service'")
        foto = {slug: leer(key, slug) for slug in d["workspaces"]}
        destino = RESULTADOS / f"{datetime.now():%Y%m%d-%H%M}_config_antes_{exp.stem}.json"
        destino.write_text(json.dumps({"workspaces": foto}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Configuración anterior guardada en {destino.relative_to(ROOT)}")
    n = cambiar(key, exp.stem, {slug: cambios for slug in d["workspaces"]}, args.simular)
    print("\n(simulación: no se cambió nada)" if args.simular else f"\nListo: {n} campos cambiados.")


def cmd_revertir(key, args):
    origen = Path(args.a) if args.a else ESTADO_INICIAL
    ws = json.loads(origen.read_text(encoding="utf-8"))["workspaces"]
    objetivo = {w["slug"]: {c: w.get(c) for c in CAMPOS} for w in ws.values() if "slug" in w}
    print(f"Revirtiendo a {origen.relative_to(ROOT) if origen.is_relative_to(ROOT) else origen}")
    n = cambiar(key, f"revertir({origen.name})", objetivo, args.simular)
    print("\n(simulación: no se cambió nada)" if args.simular else f"\nListo: {n} campos restaurados.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="accion", required=True)
    sub.add_parser("ver", help="muestra la configuración actual y marca lo que difiere del original")
    p = sub.add_parser("aplicar", help="aplica un experimento de experimentos/*.json")
    p.add_argument("experimento")
    p.add_argument("--simular", action="store_true", help="muestra qué cambiaría, sin cambiar nada")
    p.add_argument("--sin-respaldo", action="store_true", help="no exige un respaldo reciente")
    p = sub.add_parser("revertir", help="vuelve a la configuración original (o a la de --a)")
    p.add_argument("--a", help="foto de configuración a restaurar (por defecto, resultados/estado_inicial.json)")
    p.add_argument("--simular", action="store_true")
    args = ap.parse_args()

    if args.accion != "ver" and not getattr(args, "simular", False) and corrida_en_curso():
        sys.exit("Hay una corrida de rag_eval.py en curso: cambiar la configuración ahora falsearía sus resultados.")
    key = api_key()
    {"ver": cmd_ver, "aplicar": cmd_aplicar, "revertir": cmd_revertir}[args.accion](key, args)


if __name__ == "__main__":
    main()
