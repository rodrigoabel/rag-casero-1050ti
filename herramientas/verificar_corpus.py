#!/usr/bin/env python3
"""
verificar_corpus.py - Comprueba, ANTES de subir nada al servidor, que cada respuesta esperada
sobrevive a la conversión que hará mirag-sync (mismas librerías y versiones que el servidor).

Uso (desde la carpeta del proyecto):
    .venv/bin/python herramientas/verificar_corpus.py

Además deja en vista_previa_conversion/ el texto exacto que "verá" el RAG de cada documento,
para que puedas revisar cómo quedaron tablas, notas del orador, gráficos, etc.

Conversión replicada (ver /usr/local/bin/mirag_sync.py en el servidor):
    Mi_RAG/office/*.docx|pptx   -> MarkItDown
    Mi_RAG/pdf/*.pdf            -> pymupdf4llm.to_markdown
    Mi_RAG/pdf_imagenes/*.pdf   -> páginas con < 100 caracteres de texto se pasan por OCR (tesseract, spa, 200 ppp)
    Mi_RAG/*.docx (raíz)        -> lo procesa AnythingLLM directamente; aquí se APROXIMA con MarkItDown
    *.md                        -> texto tal cual
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import pymupdf
import pymupdf4llm
from markitdown import MarkItDown

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus"
VISTA = ROOT / "vista_previa_conversion"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.replace(" ", " ").replace(" ", " "))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", s)


def clave(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(s))


def contiene(texto_n: str, kw: str) -> bool:
    k = norm(kw).strip()
    if re.fullmatch(r"[\d.,]+", k):  # número: no confundir 4 con 4471 ni 2 con 2,7
        return re.search(rf"(?<![\d.,]){re.escape(k)}(?!\d|[.,]\d)", texto_n) is not None
    return k in texto_n


def convertir(f: Path, md: MarkItDown) -> tuple[str, str]:
    rel = f.relative_to(CORPUS).as_posix()
    if f.suffix == ".md":
        return f.read_text(encoding="utf-8"), "texto"
    if "/pdf_imagenes/" in rel and not shutil.which("tesseract"):
        guardado = ROOT / "herramientas" / "ocr_servidor" / f"{f.stem}.txt"
        if guardado.exists():  # OCR hecho en el servidor el 9/10/2026 (tesseract 5.5, spa, 200 ppp)
            return guardado.read_text(encoding="utf-8"), "OCR del servidor (guardado)"
    if "/pdf_imagenes/" in rel:
        doc = pymupdf.open(str(f))
        partes, metodo = [], "pymupdf4llm"
        for i, page in enumerate(doc):
            if len(page.get_text().strip()) > 100:
                partes.append(pymupdf4llm.to_markdown(doc, pages=[i]))
            elif shutil.which("tesseract"):
                pix = page.get_pixmap(dpi=200)
                with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
                    pix.save(tmp.name)
                    r = subprocess.run(["tesseract", tmp.name, "stdout", "-l", "spa"], capture_output=True, text=True)
                partes.append(f"\n\n### Página {i + 1} (OCR)\n\n" + r.stdout.strip())
                metodo = "OCR local"
            else:
                partes.append(f"\n\n### Página {i + 1} (OCR PENDIENTE: sin capa de texto)\n\n")
                metodo = "OCR_PENDIENTE"
        return "\n\n---\n\n".join(partes), metodo
    if f.suffix == ".pdf":
        return pymupdf4llm.to_markdown(str(f)), "pymupdf4llm"
    if f.suffix in (".docx", ".pptx", ".xlsx"):
        metodo = "MarkItDown" if "/office/" in rel else "MarkItDown (aprox. al parser de AnythingLLM)"
        return md.convert(str(f)).text_content, metodo
    return "", "no soportado"


def main():
    preguntas = json.loads((ROOT / "preguntas" / "preguntas.json").read_text(encoding="utf-8"))
    md = MarkItDown()
    if VISTA.exists():
        shutil.rmtree(VISTA)

    textos, metodos = {}, {}
    for f in sorted(CORPUS.rglob("*")):
        if not f.is_file():
            continue
        txt, metodo = convertir(f, md)
        rel = f.relative_to(CORPUS)
        textos[rel.as_posix()] = txt
        metodos[rel.as_posix()] = metodo
        out = VISTA / rel.with_suffix(rel.suffix + ".md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"<!-- Conversión: {metodo} | {len(txt)} caracteres -->\n\n{txt}", encoding="utf-8")

    print("== Conversión de documentos")
    for rel, txt in textos.items():
        print(f"  {len(txt):6d} car.  {metodos[rel]:<45} {rel}")

    def fuentes_de(q):
        base = "cambios/" if q["fase"] == "F6" and q["tipo"] == "actualizacion" else ("usuario2/" if q["workspace"] == "usuario2" else "usuario1/")
        fuentes = q["fuente_esperada"] if isinstance(q["fuente_esperada"], list) else [q["fuente_esperada"]]
        rels = []
        for fu in fuentes:
            k = clave(fu)
            enc = [r for r in textos if r.startswith(base) and k in clave(Path(r).stem)]
            if not enc:
                return []  # falta alguna de las fuentes
            rels += enc
        return rels

    print("\n== Comprobación pregunta por pregunta (¿la respuesta está en el texto convertido?)")
    problemas = 0
    for q in preguntas:
        if q["espera_rechazo"] and not q["evidencia"]:
            continue
        rels = fuentes_de(q)
        if not rels:
            print(f"  ✗ {q['id']}: no se encontró el archivo fuente '{q['fuente_esperada']}'")
            problemas += 1
            continue
        t = norm(" ".join(textos[r] for r in rels))
        if any(metodos[r] == "OCR_PENDIENTE" for r in rels):
            print(f"  ? {q['id']}: depende de OCR (no hay tesseract local; verificar en el servidor)")
            continue
        falta_ev = [e for e in q["evidencia"] if not contiene(t, e)]
        falta_req = [] if q["tipo"] in ("calculo", "idioma") else \
            [g for g in q["requeridas"] if not any(contiene(t, k) for k in g)]
        if falta_ev or falta_req:
            problemas += 1
            print(f"  ✗ {q['id']}: falta evidencia {falta_ev} / requeridas {falta_req}  ({', '.join(rels)})")
    print(f"\nProblemas: {problemas} de {len(preguntas)} preguntas.")
    print(f"Vista previa del texto convertido en: {VISTA}")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
