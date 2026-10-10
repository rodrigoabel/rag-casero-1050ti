#!/usr/bin/env bash
# E1a y E1b: prompt del sistema en español contra H15, rechazo en español y temperatura 0,2.
# CAMBIA LA CONFIGURACIÓN DEL SERVIDOR (workspaces prueba y notas-obsidian): correr solo con la
# confirmación del usuario. Durante la corrida (~20 min) el RAG real de usuario1 (web y Telegram)
# responde con el prompt del experimento.
#
# Pasos: respaldo -> E1a -> chat --rapida x2 -> E1b -> chat --rapida x2 -> revertir -> comparar.
# Revierte a la configuración original al terminar, si algo falla o si se interrumpe (Ctrl+C).
# El prompt no afecta la búsqueda (no entra en el vector-search), así que basta con medir el chat.
#
# Uso (desde la carpeta del proyecto):
#   bash experimentos/E1_correr.sh                       # base = la última resultados/*_base
#   bash experimentos/E1_correr.sh resultados/<base>
set -euo pipefail
cd "$(dirname "$0")/.."

EVAL="python3 -u herramientas/rag_eval.py"
CONFIG="python3 -u herramientas/rag_config.py"

if pgrep -f '^[^ ]*python[0-9.]* .*rag_eval\.py (completo|chat|recuperacion)' >/dev/null; then
    echo "Hay otra corrida de rag_eval.py en curso; espera a que termine." >&2
    exit 1
fi

BASE="${1:-}"
if [[ -z "$BASE" ]]; then
    for d in $(ls -d resultados/*_base 2>/dev/null | sort -r); do
        if [[ -f "$d/chat.csv" ]]; then BASE="$d"; break; fi
    done
fi
[[ -f "$BASE/chat.csv" ]] || { echo "No encuentro una línea base con chat.csv en resultados/*_base" >&2; exit 1; }
echo "Línea base: $BASE"

# la salida se guarda en un temporal: «tee /dev/stderr» reabre y trunca el log cuando stderr es un archivo
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

carpeta_de() { grep -m1 -o 'resultados/[^ ]*' <<<"$1" | sed 's#.*/resultados/#resultados/#'; }

revertir() {
    echo; echo "== Revirtiendo a la configuración original"
    $CONFIG revertir || echo "!! FALLÓ LA REVERSIÓN: revisa con 'python3 herramientas/rag_config.py ver'" >&2
}

echo; echo "== Respaldo previo"
ssh -o ConnectTimeout=5 "${RAG_SERVIDOR_SSH:-usuario@servidor}" 'sudo systemctl start respaldo-config.service && systemctl show respaldo-config.service -p Result'

trap 'revertir; rm -f "$TMP"' EXIT

echo; echo "== E1a"
$CONFIG aplicar experimentos/E1a.json
$EVAL chat --rapida --repeticiones 2 --etiqueta E1a | tee "$TMP"
salida=$(cat "$TMP")
E1A=$(carpeta_de "$salida")

echo; echo "== E1b"
$CONFIG aplicar experimentos/E1b.json
$EVAL chat --rapida --repeticiones 2 --etiqueta E1b | tee "$TMP"
salida=$(cat "$TMP")
E1B=$(carpeta_de "$salida")

trap 'rm -f "$TMP"' EXIT
revertir

E0=$(ls -d resultados/*_E0-cita 2>/dev/null | sort -r | head -1 || true)
SALIDA="resultados/$(date +%Y%m%d-%H%M)_E1_comparacion.md"
{
    echo "# E1: comparaciones"
    echo; echo "Base: $BASE · E1a: $E1A · E1b: $E1B${E0:+ · E0: $E0}"
    echo; echo '```'
    $EVAL comparar "$BASE" "$E1A"
    echo; echo "------------------------------------------------------------"
    $EVAL comparar "$BASE" "$E1B"
    echo; echo "------------------------------------------------------------"
    $EVAL comparar "$E1A" "$E1B"
    if [[ -n "$E0" ]]; then
        echo; echo "------------------------------------------------------------"
        echo "(E0: misma petición de copiar la frase, pero en la pregunta)"
        $EVAL comparar "$E0" "$E1B"
    fi
    echo '```'
} > "$SALIDA"

echo; cat "$SALIDA"
echo; echo "Listo. E1a: $E1A · E1b: $E1B · Comparación: $SALIDA"
echo "La configuración volvió a la original. Revisar a mano CRS-10, FUN-01, PRO-09 y las respuestas con cifras;"
echo "en E1b, la línea 'Respaldo:' puede contener cifras que engañen al puntaje automático."
