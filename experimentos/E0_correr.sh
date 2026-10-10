#!/usr/bin/env bash
# E0: instrucción agregada al final de la pregunta. No cambia nada en el servidor.
#
# En modo query, AnythingLLM busca los fragmentos con el mensaje COMPLETO (sufijo incluido),
# así que el sufijo puede cambiar tanto la búsqueda como el comportamiento del modelo.
# Por eso se mide en dos partes:
#   1. recuperacion --rapida con sufijo (sin modelo, ~1 min): ¿el sufijo empeora la búsqueda?
#   2. chat --rapida con sufijo, 2 repeticiones (~8 min): ¿mejoran las respuestas? ¿bajan las H15?
# y se compara contra las mismas preguntas de la línea base (la última carpeta *_base con chat.csv).
#
# Uso (desde la carpeta del proyecto):
#   bash experimentos/E0_correr.sh                       # base = la última resultados/*_base
#   bash experimentos/E0_correr.sh resultados/<base>     # base explícita
set -euo pipefail
cd "$(dirname "$0")/.."

SUFIJO=" Si no aparece, dilo. Copia la frase del documento que lo respalda."
EVAL="python3 -u herramientas/rag_eval.py"

if pgrep -f '^[^ ]*python[0-9.]* .*rag_eval\.py (completo|chat|recuperacion)' >/dev/null; then
    echo "Hay otra corrida de rag_eval.py en curso; espera a que termine (correrían en paralelo y se falsearían los tiempos)." >&2
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

echo; echo "== 1/2 Recuperación con sufijo (sin modelo)"
$EVAL recuperacion --rapida --etiqueta E0-cita-rec --sufijo "$SUFIJO" | tee "$TMP"
salida=$(cat "$TMP")
REC=$(carpeta_de "$salida")

echo; echo "== 2/2 Chat con sufijo (2 repeticiones)"
$EVAL chat --rapida --repeticiones 2 --etiqueta E0-cita --sufijo "$SUFIJO" | tee "$TMP"
salida=$(cat "$TMP")
CHAT=$(carpeta_de "$salida")

{
    echo "# E0: comparaciones"
    echo; echo "Sufijo: \"$SUFIJO\""
    echo; echo '```'
    $EVAL comparar "$BASE" "$REC"
    echo; echo "------------------------------------------------------------"
    $EVAL comparar "$BASE" "$CHAT"
    if [[ -d resultados/20261009-0049_humo ]]; then
        echo; echo "------------------------------------------------------------"
        echo "(Referencia: F3 rápida de la noche anterior, 1 repetición)"
        $EVAL comparar resultados/20261009-0049_humo "$CHAT"
    fi
    echo '```'
} > "$CHAT/comparacion.md"

echo; cat "$CHAT/comparacion.md"
echo; echo "Listo. Recuperación: $REC · Chat: $CHAT · Comparación: $CHAT/comparacion.md"
echo "Revisar a mano: CRS-10, FUN-01, PRO-09 (H15), CON-07 (puede quedar OK_CON_RUIDO por citar valores antiguos) y toda respuesta con cifras."
