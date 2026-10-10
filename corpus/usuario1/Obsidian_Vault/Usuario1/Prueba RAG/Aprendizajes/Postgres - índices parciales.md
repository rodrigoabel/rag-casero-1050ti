---
tags: [postgres, rendimiento, aprendizaje]
---
# Postgres: índices parciales

En Cóndor, la consulta de despachos pendientes era lenta porque la tabla `despachos` tiene 12 millones de filas
y solo una fracción pequeña está en estado pendiente. Se creó un índice parcial:

```sql
CREATE INDEX idx_despachos_pendientes
    ON despachos (fecha_creacion)
    WHERE estado = 'pendiente';
```

Resultado: la consulta bajó de 1,8 segundos a 40 milisegundos.

> [!tip] Cuándo usarlo
> Cuando las consultas filtran siempre por el mismo valor y ese valor es una fracción pequeña de la tabla.

> Documento FICTICIO generado para pruebas del RAG doméstico (octubre de 2026). No corresponde a hechos reales.
