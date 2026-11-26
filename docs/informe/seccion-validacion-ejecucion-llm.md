# Validación, ejecución, cobertura, reproducibilidad y extensión con LLM

*Sección de Abner Arboleda. Cifras reales de las corridas `templates-01` (26/11/2026), `groq-01` (25/11) y `groq-02` (26/11); los comandos para reproducirlas están al final. La comparación completa está en [comparacion-plantillas-groq.md](comparacion-plantillas-groq.md).*

## 1. El filtro de validación

Una propuesta de prueba, venga de una plantilla o de un modelo de lenguaje, es solo un candidato. Antes de ejecutarse pasa por una cadena de reglas y la primera que falla fija el motivo del rechazo:

| Orden | Regla | Rechaza si… | Motivo |
| --- | --- | --- | --- |
| 1 | Error de generación | la llamada al modelo falló y solo queda un marcador | `GENERATION_ERROR` |
| 2 | Sintaxis | no pasa `ast.parse` ni `compile` | `SYNTAX_ERROR` |
| 3 | Importación | no se importa en un subproceso aislado, con copia temporal y tiempo límite | `IMPORT_ERROR` |
| 4 | Correspondencia | no llama a la función objetivo, o con argumentos que no encajan con su firma | `TARGET_NOT_CALLED`, `INVALID_SIGNATURE` |
| 5 | Aserciones útiles | no verifica el resultado: sin `assert`, `assert True`, `assert x == x`, constantes comparadas | `NO_ASSERTION`, `TAUTOLOGICAL_ASSERTION` |
| 6 | Valores esperados | (solo propuestas del modelo) falla sobre el código original: calculó mal el resultado | `WRONG_EXPECTATION`, `COLLECTION_ERROR` |

Ninguna propuesta se descarta en silencio: `ledger.jsonl` guarda todas, con fuente, estado, motivo y SHA-256 del código, y las semillas defectuosas entran en el denominador de la validez.

Con plantillas se generaron **48 propuestas** (46 desde los casos del contrato y 2 semillas defectuosas a propósito) y **46 resultaron válidas (95,8 %)**, por encima de la meta del 90 % y del mínimo del 85 %. Las dos rechazadas son las semillas: una con sintaxis rota y otra con `assert True`. Sin contarlas, la validez es del 100 %. Damos ambas cifras porque el 95,8 % mide que el filtro detecta lo que debe, no que el generador sea perfecto. Los valores esperados salen de un oráculo hecho a mano (`contracts.yaml`, calculado sin ejecutar `sciref` y revisado por otra persona), así que el experimento no es circular.

El filtro también se equivocó una vez. La primera validación de `groq-01` rechazó 1 de 42 pruebas correctas: comprobaba que `normalize_minmax` no modifica su entrada y la regla solo miraba el resultado. La corregimos (una variable pasada a la función también cuenta como observada), con pruebas de regresión; tras el cambio, 42/42.

## 2. Ejecución y cobertura

Solo las propuestas válidas llegan a `pytest`. Se copian con el paquete bajo estudio a una carpeta temporal y se ejecutan en un subproceso con tiempo límite (60 s, configurable en `codeguard.toml`); el resultado se lee del JUnit XML. `reference/sciref` nunca se escribe y su SHA-256 se verifica antes y después. **Con plantillas se ejecutaron 46 pruebas y pasaron las 46**; una corrida completa de `codeguard all` (generar, validar, ejecutar, 13 mutantes y análisis estático) tarda menos de minuto y medio.

La cobertura se mide con `pytest-cov` solo sobre `sciref` y solo sobre la suite base, con líneas y ramas por separado. Con plantillas: **100 % de líneas y 100 % de ramas** (54 sentencias y 30 ramas), frente a la meta del 90 % / 85 %. Pero la cobertura no basta, y los datos lo muestran: la suite de `groq-02` también alcanza el 100 % de ambas y aun así deja sobrevivir dos mutantes (apartado 4). Ejecutar una línea no es comprobar su resultado.

## 3. Reproducibilidad

- **Un comando.** `codeguard all` (o `make all`) repite el experimento y guarda `run_config.json` con la semilla (42), las versiones (Python 3.12.3, pytest 8.4.2…), los tiempos límite y el SHA-256 de cada archivo de `sciref`. Las versiones exactas de las 51 dependencias están en `uv.lock`.
- **Determinista.** Dos ejecuciones de `generate` con plantillas producen los mismos 49 archivos, byte a byte. `generate` se niega a reutilizar un `run_id`: una revisión detectó que dejaba archivos de la corrida anterior mezclados con el manifiesto nuevo.
- **Verificable.** La CI ejecuta lint, tipos y pruebas en Ubuntu y Windows, exige un 80 % de cobertura de `src/codeguard` y busca secretos con gitleaks, con una regla propia para claves de Groq.
- **Sin red ni credenciales.** El pipeline obligatorio no las necesita; la clave de la API solo vive en `.env` (ignorado por git) y en los secretos de GitHub.

## 4. Extensión con un modelo de lenguaje: plantillas frente a Groq

**Diseño.** `GroqProposalSource` implementa el mismo puerto que las plantillas (patrón Strategy), de modo que sus pruebas pasan por el mismo filtro, ejecutor y mutantes. El *prompt* es de caja negra: lleva la firma, el docstring y el contrato, nunca el código ni los valores esperados. Se usa `openai/gpt-oss-120b` con temperatura 0, una llamada por función (6 por corrida), 60 s de tiempo límite y 2 reintentos. Cada respuesta cruda se guarda en `out/<run_id>/llm/` con modelo, temperatura, *prompt*, fecha y tokens. El modelo no es el oráculo: la regla 6 rechaza lo que falle sobre el código original.

**Resultados** sobre las mismas 6 funciones y los mismos 13 mutantes:

| Indicador | Plantillas (`templates-01`) | Groq (`groq-01`) |
| --- | --- | --- |
| Propuestas · válidas | 48 · 46 | 42 · 42 |
| Validez (todas las propuestas) | 95,8 % (46/48) | 100,0 % (42/42) |
| Cobertura de líneas · ramas | 100,0 % · 100,0 % | 98,1 % · 96,7 % |
| Mutantes detectados | **100,0 % (12/12)** | **83,3 % (10/12)** |
| Mutantes sobrevivientes | — | M02, M11 |
| Mutante equivalente (aparte) | M03 | M03 |
| Tokens por corrida | — | 7.517 |

Una segunda llamada real (`groq-02`) dio 43 propuestas, 41 válidas (95,3 %), 100 % de líneas y ramas, 10/12 mutantes y 7.749 tokens.

**Qué aprendimos.**

1. **Detectando defectos ganan las plantillas:** 12/12 frente a 10/12 en las dos corridas de Groq. En validez y cobertura son comparables.
2. **Los mutantes que Groq no detecta son los mismos en ambas corridas: puntos ciegos, no azar.** M02 (omitir la comprobación de peso negativo): Groq usa pesos `[1, -1]`, de suma 0, y el original y el mutante lanzan `ValueError` por otra razón; el caso del oráculo `[-1, 2]` sí la aísla. M11 (el bucle empieza en 0): Groq solo prueba series ascendentes y el mutante solo se delata con una bajada (`[5, 0]`, umbral 3).
3. **Hay que verificar al modelo.** En `groq-02` calculó mal dos valores esperados de `threshold_crossings` (`[3]` en lugar de `[2]`); la regla 6 los rechazó con `WRONG_EXPECTATION` y siguen en el denominador.
4. **Con temperatura 0 el resultado no es repetible:** solo 8 de los 42 archivos de `groq-01` coinciden con los de `groq-02`. Por eso se guardan las respuestas: `--replay` regenera exactamente las mismas 42 pruebas sin clave ni red.
5. **Coste bajo:** unos 7.500 tokens y 20 s por corrida, frente a los 20.000 estimados al planificar.

**Decisión (27/11).** `--replay` funciona y las pruebas pasan el validador, así que la extensión se integra, apagada por defecto. No sustituye a las plantillas ni al oráculo: es una segunda fuente de casos, filtrada con las mismas reglas.

## 5. Límites

- **Muestra pequeña.** Un modelo, un *prompt* y dos corridas. Con 12 mutantes válidos cada uno pesa 8,3 puntos: 83,3 % frente a 100 % son dos mutantes, no una estadística general.
- **Catálogo acotado.** Los resultados valen para 13 mutantes elegidos a mano sobre 6 funciones pequeñas.
- **Validez en parte por construcción.** La de las plantillas se apoya en un oráculo hecho a mano y en plantillas deterministas.
- **Heurística estática.** La regla de aserciones analiza el código sin ejecutarlo y puede equivocarse, como ocurrió una vez.
- **Dependencia del proveedor.** `--replay` conserva las pruebas, no el comportamiento del modelo.

## Cómo reproducir las cifras

```bash
uv run codeguard all --run-id templates-01
uv run codeguard generate --source groq --run-id groq-01     # requiere GROQ_API_KEY en .env
uv run codeguard validate --run-id groq-01
uv run codeguard run --run-id groq-01
uv run codeguard mutate --run-id groq-01
uv run codeguard compare --templates templates-01 --groq groq-01

# sin clave ni red, con las respuestas guardadas:
uv run codeguard generate --source groq --replay groq-01 --run-id groq-01-replay
```
