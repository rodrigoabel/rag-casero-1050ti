#!/usr/bin/env bash
# Crea en Ollama una variante «solo texto» de un modelo: el mismo Modelfile sin el proyector de visión
# (la segunda línea FROM) y, si se pide, con todas las capas en la GPU (PARAMETER num_gpu 99).
#
# Por qué: Qwen 3.5 y Gemma 4 traen un proyector de visión (y de audio, en Gemma) de hasta ~1 GB que Ollama
# carga aunque solo se use texto. AnythingLLM no envía imágenes al modelo de respuesta, así que no se pierde
# nada. Además, el ajuste automático de Ollama deja ~1 GB libre; con num_gpu 99 se usa toda la GPU.
# Si el modelo no cabe con num_gpu 99, Ollama falla al cargarlo: vuelve a crearlo sin --gpu.
#
# Uso (en el equipo donde corre Ollama):
#   bash experimentos/crear_variante_texto.sh <modelo_base> <nombre_nuevo> [--gpu] [--simular]
# Ejemplo (el modelo de respuesta elegido en estas pruebas):
#   ollama pull gemma4:e4b
#   bash experimentos/crear_variante_texto.sh gemma4:e4b gemma4:e4b-texto-gpu --gpu
set -euo pipefail
BASE="${1:?falta el modelo base}"
NUEVO="${2:?falta el nombre del modelo nuevo}"
shift 2
GPU=0
SIMULAR=0
for a in "$@"; do
    case "$a" in
        --gpu) GPU=1 ;;
        --simular) SIMULAR=1 ;;
        *) echo "Opción desconocida: $a" >&2; exit 1 ;;
    esac
done

MF=$(mktemp)
trap 'rm -f "$MF"' EXIT
ollama show --modelfile "$BASE" | awk '/^FROM /{n++; if (n > 1) next} {print}' > "$MF"
if [ "$GPU" = 1 ]; then
    echo "PARAMETER num_gpu 99" >> "$MF"
fi
ANTES=$(ollama show --modelfile "$BASE" | grep -c '^FROM ' || true)
echo "Líneas FROM: $ANTES en $BASE, $(grep -c '^FROM ' "$MF") en $NUEVO."
if [ "$ANTES" -lt 2 ]; then
    echo "Aviso: $BASE no tiene una segunda línea FROM (proyector); la variante solo cambiará num_gpu." >&2
fi
if [ "$SIMULAR" = 1 ]; then
    grep -E '^(FROM|DRAFT|ADAPTER|PARAMETER|RENDERER|PARSER) ' "$MF"
    exit 0
fi
ollama create "$NUEVO" -f "$MF"
echo "Listo. Compruébalo con: ollama run $NUEVO 'hola' && ollama ps   (PROCESSOR debe decir 100% GPU)"
