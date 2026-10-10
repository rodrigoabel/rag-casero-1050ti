---
tipo: adr
estado: aceptada
fecha: 2026-04-22
decidido_por: Marcela Ibáñez y Tomás Rivas
tags: [adr, condor, arquitectura]
---
# ADR-007: Colas con RabbitMQ

## Contexto
El [[Proyecto Cóndor]] necesita mensajería asíncrona entre los servicios de lotes, certificados y despachos.
El cliente exige que todo el sistema funcione en sus propios servidores (on-premise), sin servicios de nube pública.

## Alternativas evaluadas
| Opción   | A favor                         | En contra                               |
|----------|---------------------------------|-----------------------------------------|
| RabbitMQ | Simple, conocido por el equipo  | Menor rendimiento a gran escala         |
| Kafka    | Altísimo rendimiento            | Operación compleja para un equipo chico |
| AWS SQS  | Administrado                    | Es nube pública: no cumple on-premise   |

## Decisión
Usar **RabbitMQ** por ser simple de operar, conocido por el equipo y compatible con el requisito on-premise.

> [!warning] Cuándo revisar esta decisión
> No usar Kafka hasta superar los 5.000 mensajes por segundo de forma sostenida.

## Consecuencias
Se acepta un techo de rendimiento menor a cambio de simplicidad operativa.

> Documento FICTICIO generado para pruebas del RAG doméstico (octubre de 2026). No corresponde a hechos reales.
