#!/usr/bin/env python3
"""reformular.py - E8: reescribe las preguntas con otro modelo antes de buscarlas en el RAG.

Lee preguntas/preguntas.json y pide a un modelo que reescriba cada pregunta con las reglas de GUIA_PREGUNTAS.md
y, si se usa --mapa, con el mapa de temas del espacio (experimentos/E8_mapa_<workspace>.md: títulos y secciones,
sin contenido de los documentos). Guarda un JSON que rag_eval.py usa con --reformuladas.
No cambia nada en el servidor: solo consulta el modelo.

Motores:
  ollama : qwen3.5:2b del servidor, el mismo que usa AnythingLLM, con su mismo contexto (16384) para no recargarlo.
  openai : cualquier API compatible con OpenAI (llama-local del PC u OpenCode Go). Si pide clave, va en la
           variable de entorno REFORMULADOR_API_KEY, nunca en la línea de comandos.

Uso (desde la carpeta del proyecto):
  python3 herramientas/reformular.py --fase E8,F4 --variante ingenua --mapa --salida experimentos/E8_qwen2b_mapa.json
  python3 herramientas/reformular.py --fase F2-F3 --mapa --salida experimentos/E8_qwen2b_mapa_F3.json
  python3 herramientas/reformular.py --motor openai --url http://localhost:8080/v1 --modelo <nombre> --fase E8 ...
  python3 herramientas/rag_eval.py recuperacion --fase E8,F4 --ws-mirag rag-eval \\
      --reformuladas experimentos/E8_qwen2b_mapa.json --etiqueta E8-qwen2b-mapa
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREGUNTAS = ROOT / "preguntas" / "preguntas.json"
MAPAS = {"mirag": ROOT / "experimentos" / "E8_mapa_mirag.md", "obsidian": ROOT / "experimentos" / "E8_mapa_obsidian.md"}
# mapas generados automáticamente desde los documentos del workspace (título + títulos de sección), como el bot
MAPAS_AUTO = {"mirag": ROOT / "experimentos" / "E8_mapa_auto_mirag.md", "obsidian": ROOT / "experimentos" / "E8_mapa_auto_obsidian.md"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def contexto_fecha(hoy: date) -> str:
    # lo calcula el programa, no el modelo: un 2B se equivoca con «el trimestre pasado»
    mes_ant = date(hoy.year - (hoy.month == 1), (hoy.month - 2) % 12 + 1, 1)
    t = (hoy.month - 1) // 3  # trimestre actual, base 0
    t_ant, a_ant = (t - 1) % 4 + 1, hoy.year - (t == 0)
    return (f"Hoy es {DIAS[hoy.weekday()]} {hoy.day} de {MESES[hoy.month - 1]} de {hoy.year}. "
            f"El mes pasado es {MESES[mes_ant.month - 1]} de {mes_ant.year}; el trimestre pasado, "
            f"el {['primer', 'segundo', 'tercer', 'cuarto'][t_ant - 1]} trimestre (Q{t_ant}) de {a_ant}; "
            f"el año pasado, {hoy.year - 1}.")


def sistema(con_mapa: bool, hoy: date, version: str = "v1") -> str:
    if version == "v2":
        return sistema_v2(con_mapa, hoy)
    if version == "v3":
        return sistema_v3(con_mapa, hoy)
    reglas = [
        "Conserva exactamente lo que el usuario quiere saber. No agregues datos, cifras, nombres ni supuestos que "
        "el usuario no dio.",
        "Si la pregunta da por cierto un dato (por ejemplo, una cifra), no lo afirmes: pregunta por ese dato de "
        "forma neutra.",
        ("Si el mapa de documentos muestra a qué documento o sección se refiere la pregunta, nombra ese documento "
         "con su título tal como aparece en el mapa. Si no está claro, no nombres ningún documento.")
        if con_mapa else "Si la pregunta nombra un documento o un tema, mantenlo.",
        "Usa términos completos y precisos: desarrolla las siglas y corrige la ortografía.",
        "Cambia las fechas relativas por fechas absolutas. " + contexto_fecha(hoy),
        "Si la pregunta ya es clara y completa, cámbiala lo menos posible.",
        "Escribe una sola pregunta, en español, completa y breve. No agregues instrucciones de formato ni frases "
        "como «si no aparece, dilo».",
        "Responde solo con la pregunta reescrita, sin comillas ni explicaciones.",
    ]
    return ("Tu tarea es reescribir la pregunta de un usuario para buscarla en sus documentos. Con la pregunta "
            "reescrita se buscan los fragmentos más parecidos y otro modelo responde con ellos.\n\nReglas:\n"
            + "\n".join(f"{i}. {r}" for i, r in enumerate(reglas, 1)))


def sistema_v2(con_mapa: bool, hoy: date) -> str:
    # v2, conservadora: corrige los fallos de v1 en E8 (documento equivocado, preguntas concretas que se vuelven
    # generales y siglas desarrolladas al azar) sin ejemplos con datos
    reglas = [
        "Conserva las palabras del usuario: nombres, cifras, términos técnicos y siglas. Puedes corregir la "
        "ortografía y completar la frase.",
        "Pregunta exactamente por lo mismo. No la amplíes a un tema general ni la reemplaces por el título de una "
        "sección.",
        "Si la pregunta da por cierto un dato (por ejemplo, una cifra), no lo afirmes: pregunta por ese dato de "
        "forma neutra.",
        ("Agrega el nombre de un documento del mapa solo si las palabras de la pregunta coinciden claramente con el "
         "título o las secciones de un único documento. Si hay dudas, no agregues ningún documento.")
        if con_mapa else "No agregues nombres de documentos.",
        "No desarrolles una sigla si su significado no aparece en el mapa.",
        "Cambia las fechas relativas por fechas absolutas. " + contexto_fecha(hoy),
        "Escribe una sola pregunta, en español. No agregues instrucciones de formato ni frases como «si no aparece, "
        "dilo».",
        "Responde solo con la pregunta reescrita, sin comillas ni explicaciones.",
    ]
    return ("Tu tarea es completar la pregunta de un usuario para buscarla en sus documentos, cambiándola lo menos "
            "posible. Con la pregunta completada se buscan los fragmentos más parecidos y otro modelo responde con "
            "ellos.\n\nReglas:\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(reglas, 1)))


def sistema_v3(con_mapa: bool, hoy: date) -> str:
    # v3: v2 (conservar palabras, no ampliar, no inventar siglas) + v1 (decir explícitamente qué dato se pide)
    # + una regla más estricta para nombrar documentos. Diseñada viendo los errores de v1 y v2 en E8: se comprueba
    # con las preguntas E8b, que ninguna versión vio
    reglas = [
        "Conserva todas las palabras clave del usuario: nombres, cifras, siglas y términos técnicos deben aparecer "
        "tal cual en la pregunta completada. Puedes corregir la ortografía.",
        "Si la pregunta es corta o vaga, conviértela en una pregunta completa que diga qué dato se pide (un valor, "
        "un plazo, un motivo, una fecha, una persona), sin cambiar de tema.",
        "Pregunta por lo mismo que el usuario: no la amplíes a todo un tema ni la reemplaces por el título de una "
        "sección.",
        "Si la pregunta da por cierto un dato (por ejemplo, una cifra), no lo afirmes: pregunta por ese dato de "
        "forma neutra.",
        ("Agrega el nombre de un documento solo si una palabra clave del usuario aparece, tal cual o como sinónimo "
         "evidente, en el título o en las secciones de un único documento del mapa. Si esa palabra podría estar en "
         "varios documentos, o si dudas, no agregues ningún documento.")
        if con_mapa else "No agregues nombres de documentos.",
        "No desarrolles una sigla si su significado no aparece en el mapa.",
        "Cambia las fechas relativas por fechas absolutas. " + contexto_fecha(hoy),
        "Escribe una sola pregunta, en español. No agregues instrucciones de formato ni frases como «si no aparece, "
        "dilo».",
        "Responde solo con la pregunta completada, sin comillas ni explicaciones.",
    ]
    return ("Tu tarea es completar la pregunta de un usuario para buscarla en sus documentos. Con la pregunta "
            "completada se buscan los fragmentos más parecidos y otro modelo responde con ellos.\n\nReglas:\n"
            + "\n".join(f"{i}. {r}" for i, r in enumerate(reglas, 1)))


def mensaje(q, con_mapa: bool, auto: bool = False) -> str:
    mapa = (MAPAS_AUTO if auto else MAPAS).get(q["workspace"])
    previo = mapa.read_text(encoding="utf-8").strip() + "\n\n" if con_mapa and mapa and mapa.exists() else ""
    return previo + "Pregunta del usuario: " + q["pregunta"]


def post(url, body, cabeceras, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **cabeceras})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def llamar(args, sis, msg) -> str:
    mensajes = [{"role": "system", "content": sis}, {"role": "user", "content": msg}]
    if args.motor == "ollama":
        js = post(f"{args.url}/api/chat", {
            "model": args.modelo, "messages": mensajes, "stream": False, "think": False,
            # mismo num_ctx que AnythingLLM (ollama ps: 16384) para que Ollama no recargue el modelo entre ambos
            "options": {"temperature": args.temperatura, "top_p": 0.8, "presence_penalty": 0, "num_ctx": 16384,
                        "num_predict": 200}}, {}, args.timeout)
        return js["message"]["content"]
    clave = os.environ.get("REFORMULADOR_API_KEY", "")
    js = post(f"{args.url}/chat/completions", {
        "model": args.modelo, "messages": mensajes, "temperature": args.temperatura, "max_tokens": 400,
        "chat_template_kwargs": {"enable_thinking": False}},
        {"Authorization": f"Bearer {clave}"} if clave else {}, args.timeout)
    return js["choices"][0]["message"]["content"]


def limpiar(texto: str) -> str:
    t = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S).strip()
    lineas = [l.strip() for l in t.splitlines() if l.strip()]
    t = lineas[0] if lineas else ""
    t = re.sub(r"^(pregunta( reescrita)?|reescrita)\s*:\s*", "", t, flags=re.I)
    return t.strip(" \"'«»“”")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--motor", choices=["ollama", "openai"], default="ollama")
    ap.add_argument("--url", help="por defecto, Ollama del servidor (http://localhost:11434)")
    ap.add_argument("--modelo", default="qwen3.5:2b")
    ap.add_argument("--mapa", action="store_true", help="agrega el mapa de temas del espacio")
    ap.add_argument("--mapa-auto", action="store_true", help="usa el mapa generado de los documentos (E8_mapa_auto_*)")
    ap.add_argument("--fase", help="fases separadas por coma (E8, F4, F2-F3)")
    ap.add_argument("--ids", help="IDs separados por coma")
    ap.add_argument("--variante", help="solo esa variante (ingenua o mejorada)")
    ap.add_argument("--reglas", choices=["v1", "v2", "v3"], default="v1", help="v2: conservadora; v3: v2 + dato explícito")
    ap.add_argument("--temperatura", type=float, default=0.2)
    ap.add_argument("--hoy", default="2026-10-09", help="fecha de referencia de las preguntas (AAAA-MM-DD)")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    args.url = (args.url or ("http://localhost:11434" if args.motor == "ollama" else "")).rstrip("/")
    if not args.url:
        sys.exit("--url es obligatorio con --motor openai")

    P = json.loads(PREGUNTAS.read_text(encoding="utf-8"))
    if args.ids:
        ids = {i.strip() for i in args.ids.split(",")}
        P = [q for q in P if q["id"] in ids]
    if args.fase:
        P = [q for q in P if q["fase"] in set(args.fase.split(","))]
    if args.variante:
        P = [q for q in P if q.get("variante") == args.variante]
    if not P:
        sys.exit("No hay preguntas con esos filtros.")

    hoy = date.fromisoformat(args.hoy)
    sis = sistema(args.mapa, hoy, args.reglas)
    salida = {"meta": {"fecha": datetime.now().isoformat(timespec="seconds"), "motor": args.motor,
                       "modelo": args.modelo, "url": args.url, "mapa": args.mapa, "mapa_auto": args.mapa_auto, "reglas": args.reglas, "hoy": args.hoy,
                       "temperatura": args.temperatura, "sistema": sis}, "preguntas": {}}
    seguidos = 0
    for n, q in enumerate(P, 1):
        t0 = time.time()
        try:
            crudo = llamar(args, sis, mensaje(q, args.mapa, args.mapa_auto))
            nueva, error, seguidos = limpiar(crudo), "", 0
        except Exception as e:  # una pregunta fallida no detiene la corrida: queda la original y se anota
            crudo, nueva, error, seguidos = "", "", str(e)[:200], seguidos + 1
            if seguidos >= 3:  # el modelo no está disponible: no escribir un archivo con las originales
                sys.exit(f"3 errores seguidos ({error}); no se escribe {args.salida}")
        dt = time.time() - t0
        salida["preguntas"][q["id"]] = {"workspace": q["workspace"], "original": q["pregunta"],
                                        "reformulada": nueva or q["pregunta"], "crudo": crudo,
                                        "segundos": round(dt, 2), "error": error}
        print(f"[{n}/{len(P)}] {q['id']:<9} {dt:4.1f}s  {q['pregunta']}\n{'':17}-> {nueva or '(sin cambio: ' + error + ')'}")
    Path(args.salida).write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    seg = sorted(v["segundos"] for v in salida["preguntas"].values())
    print(f"\n{len(seg)} preguntas -> {args.salida} · mediana {seg[len(seg) // 2]:.1f} s · máxima {seg[-1]:.1f} s")


if __name__ == "__main__":
    main()
