#!/usr/bin/env bash
# E6: mide el modelo de respuesta que tenga asignado rag-eval (chatModel), con las mismas corridas que las
# referencias del 2b: completo x2 (F3 y F4, como 20261009-1156_base-E3-rageval), ingenuas E8,F4 x2
# (como *_E8chat-ingenua) y E8b x3 (como 20261009-1551_E8bchat-ingenua).
# No cambia la configuración: antes hay que aplicar el experimento con rag_config.py.
# Las preguntas de Obsidian van a notas-obsidian, que sigue con el 2b: se comparan solo las filas de rag-eval.
#
# Uso (desde la carpeta del proyecto):  bash experimentos/E6_medir.sh <etiqueta>   p. ej. qwen4b
set -euo pipefail
cd "$(dirname "$0")/.."
ET="${1:?falta la etiqueta del modelo}"
EVAL="python3 -u herramientas/rag_eval.py"

if pgrep -f '^[^ ]*python[0-9.]* .*rag_eval\.py (completo|chat|recuperacion)' >/dev/null; then
    echo "Hay otra corrida de rag_eval.py en curso; espera a que termine." >&2
    exit 1
fi

$EVAL completo --ws-mirag rag-eval --repeticiones 2 --etiqueta "E6-${ET}-rageval"
$EVAL chat --fase E8,F4 --ws-mirag rag-eval --repeticiones 2 --etiqueta "E6-${ET}-E8chat-ingenua"
$EVAL chat --fase E8b --ws-mirag rag-eval --repeticiones 3 --etiqueta "E6-${ET}-E8bchat-ingenua"
echo "E6 ${ET}: listo $(date '+%H:%M')"
