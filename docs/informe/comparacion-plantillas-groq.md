# Comparación de fuentes de propuestas: Plantillas vs. Groq

Mismas 6 funciones de `sciref` y los mismos 13 mutantes del catálogo. Corridas: `templates-01`, `groq-01`.

## Resumen

| Indicador | Plantillas | Groq |
| --- | --- | --- |
| Propuestas | 48 | 42 |
| Válidas | 46 | 42 |
| Validez (todas las propuestas) | 95,8 % (46/48) | 100,0 % (42/42) |
| Validez sin semillas defectuosas | 100,0 % (46/46) | 100,0 % (42/42) |
| Pruebas ejecutadas · aprobadas | 46 · 46 | 42 · 42 |
| Cobertura de líneas | 100,0 % | 98,1 % |
| Cobertura de ramas | 100,0 % | 96,7 % |
| Mutantes detectados | 100,0 % (12/12) | 83,3 % (10/12) |
| Mutantes sobrevivientes | — | M02, M11 |
| Mutantes equivalentes | M03 | M03 |
| Mutantes inválidos | — | — |

## Motivos de rechazo

| Motivo | Plantillas | Groq |
| --- | --- | --- |
| SYNTAX_ERROR | 1 | 0 |
| TAUTOLOGICAL_ASSERTION | 1 | 0 |

## Por función

| Función | Propuestas válidas · Plantillas | Propuestas válidas · Groq | Mutantes detectados · Plantillas | Mutantes detectados · Groq |
| --- | --- | --- | --- | --- |
| `weighted_mean` | 8/9 | 7/7 | 2/2 | 1/2 |
| `clamp` | 7/8 | 6/6 | 2/2 | 2/2 |
| `normalize_minmax` | 6/6 | 7/7 | 2/2 | 2/2 |
| `moving_average` | 7/7 | 7/7 | 2/2 | 2/2 |
| `threshold_crossings` | 7/7 | 7/7 | 2/2 | 1/2 |
| `validate_range` | 11/11 | 8/8 | 2/2 | 2/2 |

## Mutante por mutante

| Mutante | Función | Plantillas | Groq |
| --- | --- | --- | --- |
| M01 | `weighted_mean` | KILLED | KILLED |
| M02 | `weighted_mean` | KILLED | **SURVIVED** |
| M03 | `clamp` | EQUIVALENT | EQUIVALENT |
| M04 | `clamp` | KILLED | KILLED |
| M05 | `clamp` | KILLED | KILLED |
| M06 | `normalize_minmax` | KILLED | KILLED |
| M07 | `normalize_minmax` | KILLED | KILLED |
| M08 | `moving_average` | KILLED | KILLED |
| M09 | `moving_average` | KILLED | KILLED |
| M10 | `threshold_crossings` | KILLED | KILLED |
| M11 | `threshold_crossings` | KILLED | **SURVIVED** |
| M12 | `validate_range` | KILLED | KILLED |
| M13 | `validate_range` | KILLED | KILLED |

## Modelo y configuración registrados

| Parámetro | Plantillas | Groq |
| --- | --- | --- |
| Fuente | Plantillas Jinja2 (deterministas) | Groq (API compatible con OpenAI) |
| Modelo | — | openai/gpt-oss-120b |
| Temperatura | — | 0.0 |
| Endpoint | — | https://api.groq.com/openai/v1 |
| Llamadas a la API | — | 6 |
| Llamadas fallidas | — | 0 |
| Tokens totales | — | 7517 |
| Fecha de las llamadas (UTC) | — | 2026-11-25 |
| Semilla | 42 | — |

Notas: la validez y las propuestas por función incluyen las semillas defectuosas (en el denominador); la tasa de mutación es detectados / (detectados + sobrevivientes) y deja aparte los mutantes equivalentes e inválidos; la cobertura es solo la de `sciref`.
