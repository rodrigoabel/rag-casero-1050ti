#!/usr/bin/env python3
"""revision_e8.py - Revisión manual de las corridas de E8 con UN SOLO criterio para todas las variantes.

Cada regla es (ID, texto que debe contener la respuesta, veredicto manual, nota[, veredicto automático requerido]). Se aplica a todas las corridas
E8chat-* que se indiquen y escribe <carpeta>/revision_manual.csv, que luego leen puntaje_manual.py y los resúmenes.
Las reglas salen de revisar a mano las respuestas únicas de todas las variantes (9/10/2026).

Uso (desde la carpeta del proyecto): python3 herramientas/revision_e8.py resultados/<carpeta> [...]
"""
import csv
import json
import sys
from pathlib import Path

ART = "La pregunta ingenua no pide el detalle extra de la esperada, heredada de su par de la F3"
REGLAS = [
    # artefactos del banco E8: la respuesta completa a la pregunta ingenua
    ("ING-11", "214", "OK", f"{ART} (CLI-02 pide el porcentaje; aquí se pregunta cuánta gente: 214)"),
    ("ING-32", "12", "OK", f"{ART} (solo pregunta la capacidad)"),
    ("ING-13", "convertidores", "OK", f"{ART} (solo pregunta el área)"),
    ("ING-17", "1 de octubre de 2026", "OK", f"{ART} (solo pregunta cuándo)"),
    ("ING-26", "Peirce-Smith", "OK", f"{ART} (solo pregunta qué mantención)"),
    ("ING-01", "32 años", "OK", f"{ART} (solo pregunta cuánto dura)"),
    ("FORM-08a", "término anticipado", "OK", "Define bien el ITC; la esperada era el monto de la pregunta mejorada (criterio de la línea base)"),
    ("FORM-08a", "Ingreso Total de la Concesión", "OK", "Define bien la sigla; la esperada era el monto de la pregunta mejorada (criterio de la línea base)"),
    # respuestas a otra pregunta, con falso positivo del puntaje automático
    ("FORM-01a", "**Requisitos no funcionales:**", "FALLA", "La reformulación quitó «caché»: responde requisitos no funcionales y seguridad; el «15 minutos» que encontró el puntaje es el RPO, no el TTL de la caché (900 s)"),
    ("ING-18", "serviciabilidad", "FALLA", "La reformulación cambió «y el enps?» por los niveles de servicio y multas de la concesión; el puntaje encontró «12» en «12 meses»"),
    ("FORM-03a", "Verificar que el canal de colada", "PARCIAL", "Describe bien el procedimiento, pero no da el rango de temperatura buscado (criterio de E1e)", "FALLA"),
    ("ING-18", "endpoints principales", "FALLA", "La reformulación confundió «enps» con «endpoints»: responde los endpoints de Cóndor"),
    # contenido falso
    ("ING-43", "La facilitadora que firmó el acta", "ALUCINA", "La reformulación llevó «el informe de la concesión» al acta del taller: responde «Daniela Fuentes» (y la fecha de carga del archivo); el informe lo firma Sebastián Merino Lagos el 5/9/2026"),
    ("ING-02", "10 boletas bancarias de UF 25.000", "OK_CON_RUIDO", "Monto correcto, pero detalle falso: las 10 boletas de UF 25.000 son de la garantía de construcción (UF 250.000), no de la de explotación"),
    ("FORM-04a", "Puntaje promedio general**: 3,8", "OK_CON_RUIDO", "Resumen correcto, pero detalle falso: «puntaje promedio general 3,8» es el de Liderazgo; no hay promedio general"),
    ("ING-51", "conforme a lo acordado en el Convenio Complementario N° 1", "OK_CON_RUIDO", "Detalle falso: atribuye los 32 años al Convenio Complementario N° 1; el contrato adjudicado ya los fijó (el borrador de 2018 decía 30)"),
    ("ING-06", "vence en marzo de 2056", "ALUCINA", "Cifra de al lado: responde el vencimiento de la concesión (marzo de 2056) a una pregunta por el plazo para terminar las obras (48 meses)"),
    ("ING-04", "Ubicación principal", "OK_CON_RUIDO", "Detalle falso: presenta como condiciones del incumplimiento grave las multas por baches e informes y el sector de Caleta Brava (eso explica las 380 UTM acumuladas); la condición es superar 1.200 UTM en 12 meses"),
    ("ING-04", "Las multas deben ser acumuladas por el incumplimiento del índice", "OK_CON_RUIDO", "Detalle falso: restringe qué multas cuentan para el incumplimiento grave; cuentan todas las acumuladas"),
    ("ING-15", "turno de noche pasan desapercibidos", "ALUCINA", "Da una razón equivocada: los equipos no aparecen para resguardar el anonimato (grupos de menos de 5 personas), no por los turnos de noche"),
    ("ING-29", "5 años", "ALUCINA", "Falso para la pregunta del usuario: el reformulador la llevó al procedimiento del horno (registros: 5 años); los logs de auditoría de Cóndor se guardan 400 días"),
    ("ING-18", "Liderazgo: 4,1 (mejor)", "ALUCINA", "No da el eNPS (la reformulación lo quitó) y afirma «Liderazgo: 4,1 (mejor)»: 4,1 es la refinería; la dimensión Liderazgo tiene 3,8"),
    ("ING-12", "Comunicación interna:** Puntaje promedio de 3,1", "OK_CON_RUIDO", "Detalle falso: pone Comunicación interna (3,1) como segunda peor; es Carga de trabajo (2,9). Mezcla el 2,6 del área con la dimensión"),
    ("ING-19", "punto de fusión de la mata", "OK_CON_RUIDO", "Detalle falso: inventa «el punto de fusión de la mata (aproximadamente 1.220 °C)»"),
    ("FORM-06a", "10,8%", "OK_CON_RUIDO", "Detalle falso: «caída del 10,8 %» (de 96,1 a 95,2 son 0,9 puntos)"),
    ("FORM-06a", "0.8%", "OK_CON_RUIDO", "Detalle falso: «caída del 0,8 %» (de 96,1 a 95,2 son 0,9 puntos)"),
    ("FORM-05a", "km 47 hasta el final del tramo", "OK_CON_RUIDO", "Detalle falso: «142 km (km 47 hasta el final del tramo)»"),
    ("FORM-05a", "Fecha de publicación del decreto de adjudicación:** 10/9/2026", "PARCIAL", "Detalles falsos: fecha del decreto (es de 2019) y tarifas en UF (son en pesos)"),
    ("FORM-05a", "UF 2.300 x Factor", "OK_CON_RUIDO", "Detalle falso: tarifas en UF (son en pesos chilenos)"),
    ("FORM-05a", "no fue evento de fuerza mayor cubierto", "OK_CON_RUIDO", "Detalle falso: invierte la posición de la Concesionaria (sostiene que SÍ fue fuerza mayor no cubierta)"),
    ("FORM-05a", "vigencia desde PSP + 12 meses", "PARCIAL", "Falta la fecha de la PSP; detalle falso: «garantía de explotación: vigencia desde PSP + 12 meses» (es el plazo de la concesión + 12 meses)"),
]


def main():
    for c in sys.argv[1:]:
        d = Path(c)
        filas = list(csv.DictReader(open(d / "chat.csv", encoding="utf-8-sig"), delimiter=";"))
        # chat.csv corta la respuesta a 600 caracteres: el texto completo está en chat.jsonl, en el mismo orden
        completas = [json.loads(l)["respuesta_api"].get("textResponse") or "" for l in open(d / "chat.jsonl", encoding="utf-8")]
        assert len(completas) == len(filas), f"{d}: chat.jsonl y chat.csv no coinciden"
        out = []
        for x, texto in zip(filas, completas):
            for i, txt, v, nota, *solo_si in REGLAS:
                if solo_si and x["veredicto"] != solo_si[0]:
                    continue
                # se anota también si el veredicto no cambia pero hay contenido falso, para contarlo
                if x["id"] == i and txt in texto and (x["veredicto"] != v or "falso" in nota.lower()):
                    out.append({"id": x["id"], "rep": x["rep"], "veredicto_auto": x["veredicto"],
                                "veredicto_manual": v, "nota": nota})
                    break
        with open(d / "revision_manual.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["id", "rep", "veredicto_auto", "veredicto_manual", "nota"], delimiter=";")
            w.writeheader()
            w.writerows(out)
        print(f"{d.name}: {len(out)} veredictos manuales")


if __name__ == "__main__":
    main()
