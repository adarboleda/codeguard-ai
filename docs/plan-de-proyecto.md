# CodeGuard AI — Plan de Proyecto

## 1. Resumen, alcance y supuestos

CodeGuard AI se construye en 12 días (17/11 → 28/11/2026) como una herramienta CLI en Python que genera pruebas pytest desde contratos YAML, las filtra, las ejecuta con cobertura de líneas y ramas, las enfrenta a 13 mutantes controlados y emite alertas estáticas para `eval` y `shell=True`. Todo se exporta a JSON, CSV y HTML y se reproduce con un solo comando.

**Criterio de éxito (lo que verá el tribunal):** un evaluador elige una función, ve su contrato, genera sus pruebas, las ejecuta, revisa la cobertura y comprueba que fallan ante una versión mutada. Una demo con todo en verde y ningún defecto detectado **no aprueba**.

**Metas cuantitativas que nos fijamos** (por encima del mínimo de la guía):

| Indicador | Mínimo de la guía | Meta del equipo |
| --- | --- | --- |
| Funciones de referencia | 6 en ≥ 2 módulos | 6 en 3 módulos |
| Pruebas propuestas automáticamente | 18 | 26–30 (incluye 2 rotas a propósito para PA 03) |
| Validez de propuestas | ≥ 85 % | ≥ 90 % |
| Cobertura de líneas / ramas | ≥ 70 % / ≥ 70 % | ≥ 90 % / ≥ 85 % |
| Mutantes evaluados | 12 (objetivo 8 detectados) | 13 (12 válidos + 1 equivalente justificado), ≥ 10 detectados |
| Reglas estáticas | 2 patrones | 2 reglas propias (AST) + contraste con Bandit |

**Extensión opcional con LLM (Grok de xAI), a cargo de Abner:** una segunda fuente de propuestas que se compara con las plantillas sobre las mismas 6 funciones y los mismos 13 mutantes. Está apagada por defecto y el pipeline obligatorio funciona completo sin ella, sin clave y sin red. Si no funciona el **27/11 a las 12:00**, se descarta y se presenta como trabajo futuro (sección 2.4).

**Fuera de alcance (lo decimos explícitamente en la defensa):** entrenar o afinar modelos, panel web, base de datos, extensión de VS Code, escaneo de repositorios ajenos, certificación OWASP.

**Supuestos confirmados (17/11):**

- Equipo de **tres** integrantes (Abner, Christian, Marcelo), autorizado; la defensa se reparte entre los tres.
- Entrega oficial el **martes 1/12/2026** y defensa el **jueves 3/12/2026**. Cierre interno el **sábado 28/11** con `v1.0`; del 29/11 al 1/12 quedan 3 días de colchón para imprevistos y ensayos.
- Abner crea y configura el repositorio (CG-01, CG-02) el primer día.

* [ ] Acordar el canal del equipo (WhatsApp/Discord) y el horario fijo del daily de 15 min.

## 2. Arquitectura

CodeGuard es un pipeline de seis etapas desacopladas que se comunican solo por artefactos en disco (`out/<run_id>/`), así cada etapa se puede ejecutar, probar y defender por separado, y cualquier corrida se repite con el mismo `run_config.json`.

&#91;embedded content: pipeline de CodeGuard · 6 etapas + escaneo estático\]

Solo las propuestas que superan el filtro llegan a ejecución; los mutantes se evalúan solo si esa suite pasa en verde sobre el código original, y los avisos estáticos se reportan en una sección separada.

### 2.1 Capas (Clean Architecture ligera)

| Capa | Contenido | Regla |
| --- | --- | --- |
| `domain/` | Modelos inmutables (`@dataclass(frozen=True)`): `FunctionContract`, `ContractCase`, `TestProposal`, `ValidationVerdict`, `Mutant`, `MutantResult`, `Finding`, `RunMetrics` | Sin E/S, sin pytest, sin YAML. 100 % testeable. |
| `application/` | Casos de uso: `GenerateTests`, `ValidateProposals`, `RunSuite`, `EvaluateMutants`, `ScanStatic`, `BuildReport`, `RunPipeline` | Orquesta; depende de interfaces (`Protocol`), no de implementaciones. |
| `ports/` | `SpecRepository`, `ProposalSource`, `TestRunner`, `Workspace`, `ReportWriter`, `StaticRule` | Contratos de los adaptadores. |
| `adapters/` | `YamlSpecRepository`, `TemplateProposalSource` (Jinja2), `PytestSubprocessRunner`, `TempWorkspace`, `Json/Csv/HtmlReportWriter`, reglas AST | Toda la E/S vive aquí. |
| `cli/` | Comandos Typer | Solo parsea argumentos y llama casos de uso. |

**Patrones y principios que se defienden ante el tribunal:**

- **Strategy** — `ProposalSource`: hoy plantillas deterministas; mañana un LLM se conecta sin tocar el resto y pasa por el mismo filtro.
- **Chain of Responsibility** — el validador aplica reglas en orden (sintaxis → importación → referencia a función → aserciones útiles → recolección pytest); la primera que falla da el motivo de rechazo.
- **Registry** — reglas estáticas (`CG001`, `CG002`) registradas por decorador; añadir una regla no modifica el escáner (Open/Closed).
- **Inversión de dependencias** — los casos de uso reciben adaptadores por constructor; en las pruebas del propio CodeGuard se inyectan dobles.
- **Inmutabilidad del código base** — el paquete de referencia nunca se escribe: toda ejecución ocurre en una copia `tempfile.TemporaryDirectory`, con `timeout` por proceso.

### 2.2 Estructura del repositorio

```text
codeguard-ai/
├─ pyproject.toml            # deps fijadas + config ruff, mypy, pytest, coverage
├─ uv.lock                   # versiones exactas (RF 08)
├─ Makefile                  # make all = experimento completo
├─ README.md
├─ .github/workflows/ci.yml  # lint + tests + pipeline completo
├─ src/codeguard/
│  ├─ domain/  application/  ports/  adapters/  cli/
│  └─ templates/             # plantillas Jinja2 de pruebas y del reporte HTML
├─ reference/sciref/         # paquete bajo estudio (NUNCA se modifica)
│  ├─ numeric.py  signals.py  validation.py
├─ specs/contracts.yaml      # contratos + tabla de casos con oráculo independiente
├─ specs/seeds_defective.yaml# 2 propuestas rotas a propósito (PA 03)
├─ mutants/catalog.yaml      # 13 mutantes: id, familia, original, reemplazo, entrada testigo
├─ samples/security/         # insecure_*.py y safe_*.py sintéticos
├─ tests/                    # pruebas del propio CodeGuard (no se miden en la cobertura objetivo)
├─ out/<run_id>/             # generado: propuestas, ledger, junit, coverage, mutantes, hallazgos, reportes
└─ docs/informe/  docs/presentacion/
```

### 2.3 Conjunto de referencia (6 funciones, 3 módulos)

| Módulo | Función | Contrato resumido | Casos límite / inválidos |
| --- | --- | --- | --- |
| `numeric` | `weighted_mean(values, weights)` | Σ(w·v) / Σw | Longitudes distintas, lista vacía, peso negativo o Σw = 0 → `ValueError` |
| `numeric` | `clamp(x, lo, hi)` | Devuelve lo si x < lo, hi si x > hi, si no x | x == lo, x == hi; lo > hi → `ValueError` |
| `numeric` | `normalize_minmax(values)` | (v − min) / (max − min) en \[0, 1\] | Todos iguales → lista de 0.0; vacía → `ValueError` |
| `signals` | `moving_average(values, window)` | Media de cada ventana; longitud n − window + 1 | window == n, window == 1; window < 1 o > n → `ValueError` |
| `signals` | `threshold_crossings(values, threshold)` | Índices i con values\[i−1\] < threshold ≤ values\[i\] | Valor igual al umbral, serie de 0 o 1 elementos → `[]` |
| `validation` | `validate_range(value, lo, hi, inclusive=True)` | True si value está en el rango (cerrado o abierto) | value == lo/hi en ambos modos; NaN → `ValueError`; no numérico o `bool` → `TypeError` |

Los valores esperados de `contracts.yaml` se calculan a mano o en hoja de cálculo por quien **no** escribió la función, nunca llamando a la implementación (evita el oráculo circular). Floats se comparan con `pytest.approx(rel=1e-9)`.

### 2.4 Extensión LLM con Grok (opcional)

Grok entra como `GrokProposalSource`, una segunda implementación del puerto `ProposalSource`. Sus pruebas pasan por el mismo validador, el mismo ejecutor y los mismos mutantes que las de plantillas, así que se pueden comparar con las mismas métricas.

**Reglas de diseño:**

1. **Apagado por defecto.** Se activa solo con `codeguard generate --source grok`; `codeguard all` usa plantillas. Ninguna prueba ni paso de la CI principal llama a Grok.
2. **Caja negra.** El prompt lleva solo la firma, el docstring y el contrato de `contracts.yaml`; nunca el código de la implementación. Así Grok no copia la lógica que debe probar.
3. **El LLM no es el oráculo.** Si Grok inventa un valor esperado incorrecto, la prueba falla sobre el código original y el validador la rechaza con motivo `WRONG_EXPECTATION`. Esas propuestas cuentan en el denominador de validez.
4. **Cliente.** SDK oficial `openai` con `base_url="https://api.x.ai/v1"`, que xAI documenta como compatible; la clave se lee de `XAI_API_KEY`. El modelo se fija en `CODEGUARD_LLM_MODEL` después de revisar los disponibles en la consola de xAI.
5. **Reproducible sin red (modo replay).** Cada respuesta cruda se guarda en `out/<run_id>/llm/` junto con modelo, temperatura (0), prompt y fecha. Con `--source grok --replay <run_id>` se regeneran las mismas pruebas sin llamar a la API, así el evaluador reproduce el experimento sin clave.
6. **Límites de cuota y tiempo.** Máximo 1 llamada por función y corrida (6 en total), timeout de 60 s y 2 reintentos; la cuota gratuita de Grok es de unos 200 000 tokens diarios y una corrida usa del orden de 20 000 (6 llamadas de \~3 000 tokens, a medir en la primera corrida), lo que deja margen para unas 9 corridas por día. Si la llamada falla o se agota la cuota, se registra en el ledger y el pipeline sigue.

**Manejo de secretos:**

- **Local:** la clave va en `.env` (incluido en `.gitignore`); se sube solo `.env.example` con `XAI_API_KEY=` vacío. Se carga con `python-dotenv`.
- **GitHub:** la clave se guarda en *Settings → Secrets and variables → Actions* como secreto `XAI_API_KEY`, y el modelo como variable `CODEGUARD_LLM_MODEL`. Solo la usa un workflow aparte, `llm-experiment.yml`, que se lanza a mano (`workflow_dispatch`) y nunca corre en PR; así la CI de cada push no gasta la cuota diaria ni falla si Grok no responde.
- **Prevención de fugas:** hook de pre-commit con gitleaks que bloquea cualquier commit con una clave. Si una clave llega a subirse, se revoca en la consola de xAI y se crea otra; borrarla del historial no basta.
- **Logs:** la clave nunca se imprime; los registros guardan solo el nombre del modelo y los parámetros.

## 3. Tecnologías

Todo el núcleo usa Python y herramientas libres que funcionan sin red ni credenciales; las versiones exactas quedan fijadas en `uv.lock` el día 18/11 y no se cambian después del 26/11.

| Área | Herramienta | Uso en CodeGuard | Por qué |
| --- | --- | --- | --- |
| Lenguaje | Python 3.12 | Todo el sistema | Requerido por la guía; `ast` y `tomllib` en la biblioteca estándar |
| Entorno y lock | uv (alternativa: pip + pip-tools) | Entorno virtual y `uv.lock` | Reproducibilidad exacta y rápida (RF 08) |
| Pruebas | pytest 8.x | Ejecutar suites generadas y las del propio CodeGuard | Estándar recomendado por la guía y la HSF |
| Cobertura | coverage.py 7.x + pytest-cov | Líneas y ramas (`--cov-branch`) limitadas a `reference/sciref` | Cobertura de ramas separada de líneas (RF 04) |
| Resultados | JUnit XML de pytest | Parsear aprobados, fallidos, errores, tiempos y qué prueba mató a cada mutante | Formato estable, sin plugins extra |
| Análisis de código | `ast` (stdlib) | Validador de propuestas, reglas `CG001`/`CG002`, aplicación de mutantes | Sin dependencias; explicable línea a línea |
| Seguridad (contraste) | Bandit 1.8.x | Comparar nuestras alertas con B307 (`eval`) y B602 (`shell=True`) | Referencia externa para hablar de falsos positivos |
| Especificaciones | PyYAML + pydantic 2 | Leer y validar `contracts.yaml` y `catalog.yaml` con errores comprensibles | RF 01: falla claro si falta un campo |
| Plantillas | Jinja2 3.x | Generar archivos `test_*.py` y el reporte HTML | Generación determinista, sin copiar y pegar (RF 02) |
| CLI | Typer | `codeguard generate / validate / run / mutate / scan / report / all` | Ayuda automática para el evaluador externo |
| Calidad del código | ruff (lint + formato), mypy `--strict` en `domain/` y `application/`, pre-commit | Bloquear código sucio antes del commit | Clean code verificable |
| Integración continua | GitHub Actions | Lint + pruebas + `make all` en cada PR; sube `out/` como artefacto | Evidencia de reproducción (PA 10) |
| Gestión | GitHub Projects (tablero) + Issues + Milestones | Backlog, sprints y trazabilidad commit ↔ historia | Todo queda en el repo (E1) |
| Documentación | Markdown (README), informe exportado a PDF, diapositivas | E2, E9, E10 |  |

**Tecnologías de la extensión LLM (opcional):**

| Herramienta | Uso |
| --- | --- |
| Grok (API de xAI) | Proponer pruebas desde el contrato; modelo fijado en `CODEGUARD_LLM_MODEL` |
| SDK `openai` para Python | Cliente con `base_url="https://api.x.ai/v1"` |
| python-dotenv | Leer `XAI_API_KEY` desde `.env` local |
| GitHub Secrets and variables | `XAI_API_KEY` (secreto) y `CODEGUARD_LLM_MODEL` (variable) para `llm-experiment.yml` |
| gitleaks (hook de pre-commit) | Bloquear commits que contengan claves |

**Decisiones descartadas y su razón** (preguntas típicas del tribunal): *mutmut* — genera miles de mutantes no controlados y requiere WSL en Windows; usamos un catálogo curado de 13 con entrada testigo. *Hypothesis* — útil, pero sus casos no salen del contrato y complican la trazabilidad; queda como trabajo futuro. *LLM como núcleo* — la guía lo deja opcional y exige que el sistema funcione sin credenciales; por eso Grok es una extensión apagada por defecto y con modo replay.

## 4. Metodología

Usamos **Scrum ligero en 4 sprints cortos** (Sprint 0 de 2 días y tres sprints de 4, 4 y 2 días), con tablero Kanban en GitHub Projects y revisión cruzada obligatoria en cada PR. La revisión cruzada no es burocracia: es la forma de que los tres puedan explicar el sistema completo ante el tribunal.

### 4.1 Roles

| Rol | Responsable | Qué hace |
| --- | --- | --- |
| Product Owner / integrador | Christian | Prioriza el backlog contra RF y PA de la guía; integra el pipeline; decide qué entra al freeze |
| Scrum Master / QA | Abner | Conduce el daily, cuida el tablero, el repositorio y la CI, vigila que nadie quede bloqueado más de medio día |
| Responsable de evidencias y documentación | Marcelo | Mantiene la matriz RF/PA ↔ evidencia, coordina informe y diapositivas |

Los tres son desarrolladores; los roles solo añaden una responsabilidad de coordinación.

### 4.2 Ceremonias

| Ceremonia | Cuándo | Duración | Salida |
| --- | --- | --- | --- |
| Planning | Inicio de cada sprint (17/11, 19/11, 23/11, 27/11) | 30 min | Historias del sprint asignadas en el tablero |
| Daily | Todos los días a hora fija (presencial o mensaje) | 15 min | Qué hice, qué haré, qué me bloquea |
| Review + demo | Cierre de sprint (22/11, 26/11, 28/11) | 30 min | Demo del pipeline y tag de versión |
| Retro | Tras cada review | 15 min | 1 cosa a mantener, 1 a cambiar |

### 4.3 Flujo de trabajo en Git (GitHub Flow)

1. `main` protegida: solo entra por PR con CI en verde y **1 aprobación de otro integrante**.
2. Una rama por historia: `feat/CG-07-validator-assertions`, `fix/CG-15-timeout`, `docs/CG-24-readme`.
3. Commits con Conventional Commits: `feat(validator): reject tautological asserts (CG-07)`.
4. PR pequeños (< 300 líneas) con descripción: qué historia cierra, cómo probarlo, evidencia.
5. Tags: `v0.1` (22/11), `v0.9` feature freeze (26/11), `v1.0` entrega (28/11). La versión final identificable exigida en E1 es `v1.0`.
6. Nunca se suben `.env`, claves ni `out/` pesados; `out/` final se adjunta como artefacto del release.

### 4.4 Buenas prácticas de código

- Funciones de ≤ 30 líneas, nombres en inglés y descriptivos, type hints en todo, docstrings con contrato.
- El propio CodeGuard se prueba con pytest (TDD en `domain/` y en las reglas del validador y del escáner): meta ≥ 80 % de cobertura de `src/codeguard`, medida aparte de la cobertura objetivo.
- Sin números mágicos: timeouts, tolerancias y rutas en `codeguard.toml` y copiados a `run_config.json` en cada corrida.
- Errores explícitos: excepciones propias (`SpecError`, `WorkspaceError`) con mensaje accionable, nunca `except: pass`.

### 4.5 Definition of Done (por historia)

- [ ] Código en `main` vía PR revisado por otro integrante.
- [ ] ruff y mypy sin errores; CI en verde.
- [ ] Pruebas unitarias del componente escritas y pasando.
- [ ] Comando CLI o paso del `Makefile` que lo ejecuta.
- [ ] Evidencia generada en `out/` y anotada en la matriz RF/PA.
- [ ] README actualizado si cambia cómo se usa.

## 5. Product backlog

33 historias (CG-01 a CG-33) cubren los 8 RF, las 10 PA, los 10 entregables y la extensión con Grok (CG-31 a CG-33); suman 98 puntos individuales (Abner 34, Christian 31, Marcelo 33) más 2 historias compartidas. Cada historia es un Issue en GitHub con su ID; el nombre de la rama y del commit lo citan.

### 5.1 Historias por sprint

| ID | Sprint | Historia (como… quiero…) | Criterio de aceptación | RF / PA | Pts | Resp. |
| --- | --- | --- | --- | --- | --- | --- |
| CG-01 | S0 | Crear y configurar el repo: `pyproject`, `uv.lock`, ruff, mypy, pre-commit, protección de `main` | `uv sync` + `pre-commit run -a` limpios en las 3 máquinas | RF 08 / E1 | 2 | Abner |
| CG-02 | S0 | CI en GitHub Actions | Cada PR corre lint + pruebas; badge en README | RF 08 / PA 10 | 2 | Abner |
| CG-32 | S0 | Manejo de secretos | `.env` en `.gitignore`, `.env.example` vacío, hook gitleaks activo, secreto `XAI_API_KEY` y variable `CODEGUARD_LLM_MODEL` creados en GitHub; un commit de prueba con una clave falsa es bloqueado | RF 08 / PA 09 | 2 | Abner |
| CG-03 | S0 | Modelos de dominio inmutables | Dataclasses frozen con pruebas; mypy strict pasa | Base | 3 | Christian |
| CG-04 | S0 | `contracts.yaml` con ≥ 4 casos por función (normal, frontera, inválido) y oráculo independiente | Valores calculados a mano; revisados por Abner | RF 01 / PA 01 / E3 | 5 | Marcelo |
| CG-05 | S0 | Paquete `sciref`: 6 funciones en 3 módulos con docstrings de contrato | Implementa la tabla 2.3; hash SHA-256 de la versión base guardado | RF 01 / E3 | 3 | Christian |
| CG-06 | S1 | Cargar y validar especificaciones; `codeguard list` | Lista 6 funciones y sus casos; error claro si falta un campo o la firma no existe | RF 01 / PA 01 | 3 | Christian |
| CG-07 | S1 | Generador por plantillas Jinja2 | `codeguard generate` crea ≥ 26 propuestas (≥ 1 por clase y función) sin edición manual | RF 02 / PA 02 / E4 | 5 | Christian |
| CG-08 | S1 | Semillas defectuosas y trazabilidad | 1 propuesta con sintaxis rota y 1 tautológica entran al denominador; cada prueba guarda id de caso de origen | RF 02-03 / PA 03 | 2 | Christian |
| CG-09 | S1 | Regla de sintaxis e importación | `ast.parse` + `compile`; rechaza con motivo `SYNTAX_ERROR` / `IMPORT_ERROR` | RF 03 / PA 03 | 3 | Abner |
| CG-10 | S1 | Regla de correspondencia | Verifica que llama a la función objetivo real y que los argumentos encajan con `inspect.signature().bind` | RF 03 | 3 | Abner |
| CG-11 | S1 | Regla de aserciones útiles | Rechaza: sin `assert`/`pytest.raises`, `assert True`, `assert x == x`, comparación entre constantes, prueba que solo llama sin verificar | RF 03 / PA 03 | 5 | Abner |
| CG-12 | S1 | Ledger de propuestas | `ledger.jsonl`: entrada, fuente (plantilla o Grok), archivo, estado, motivo, versión final; métricas propuestas vs. válidas | RF 03 / E4 | 2 | Abner |
| CG-13 | S1 | Catálogo de 13 mutantes | `catalog.yaml` con id, familia, operación, entrada testigo y salida esperada vs. mutada (tabla 5.2) | RF 05 / E6 | 5 | Marcelo |
| CG-14 | S1 | Aplicador de mutantes en copia temporal | Cada mutante vive en su propio directorio temporal; el hash de `sciref` original no cambia | RF 05, RF 08 / PA 09 | 3 | Marcelo |
| CG-15 | S1 | Reglas estáticas `CG001` (eval/exec no literal) y `CG002` (subprocess con `shell=True`, `os.system`) | Detecta los 4 ejemplos inseguros, no señala los 4 seguros; reporta archivo, línea, regla, fragmento, recomendación, severidad | RF 06 / PA 08 / E8 | 5 | Marcelo |
| CG-16 | S2 | Ejecutor pytest en subproceso con timeout | Registra aprobados, fallidos, errores y tiempos desde JUnit XML; timeout configurable | RF 04 / PA 04 | 5 | Abner |
| CG-17 | S2 | Cobertura de líneas y ramas | Solo mide `reference/sciref`; reporte por módulo en JSON + HTML de coverage | RF 04 / PA 05 / E5 | 3 | Abner |
| CG-18 | S2 | Evaluación de mutantes | Exige línea base verde; clasifica cada mutante en `KILLED`, `SURVIVED`, `EQUIVALENT`, `INVALID` (import/timeout no cuenta como detección) y guarda la prueba que lo mató | RF 05 / PA 06-07 / E7 | 5 | Marcelo |
| CG-19 | S2 | Contraste con Bandit | Tabla nuestras alertas vs. B307/B602; falsos positivos y límites documentados | RF 06 | 2 | Marcelo |
| CG-20 | S2 | Exportar JSON y CSV | `results.json`, `mutants.csv`, `findings.csv`, `ledger.csv` | RF 07 / E5-E7 | 3 | Marcelo |
| CG-21 | S2 | Reporte HTML | Secciones separadas: pruebas funcionales / mutación / avisos estáticos | RF 07 | 3 | Christian |
| CG-22 | S2 | Métricas y tiempos por fase | Validez, cobertura, tasa de mutación con denominador explícito, tiempo de generación / validación / ejecución | Sección 8 guía | 3 | Christian |
| CG-23 | S2 | CLI completa y `codeguard all` | Un comando reproduce todo; guarda `run_config.json` con versiones, semilla, timeouts y hash | RF 07-08 / PA 10 | 3 | Christian |
| CG-24 | S2 | Endurecimiento de ejecución | Copias temporales, límite de tiempo, verificación de hash antes/después, sin secretos en el repo | RF 08 / PA 09 | 3 | Christian |
| CG-31 | S2 | Fuente de propuestas con Grok | `GrokProposalSource` con prompt de caja negra (solo contrato), temperatura 0, timeout 60 s, 6 llamadas por corrida; respuestas crudas guardadas y modo `--replay` sin red; todas sus propuestas pasan por el validador | Extensión (sección 4 guía) | 5 | Abner |
| CG-25 | S2 | Pruebas del propio CodeGuard | ≥ 80 % de cobertura en `src/codeguard` (Grok simulado con un doble, sin red) | Calidad | 5 | Los tres |
| CG-26 | S3 | README completo | Objetivo, instalación, comandos, formato de entradas, reproducción paso a paso; cómo activar Grok con `.env` y cómo reproducirlo con `--replay` | E2 / PA 10 | 2 | Christian |
| CG-33 | S3 | Comparación plantillas vs. Grok | Tabla con validez, motivos de rechazo, cobertura y mutantes detectados de cada fuente sobre las mismas funciones y mutantes; modelo y configuración registrados | Sección 8 guía / E9 | 2 | Abner |
| CG-27 | S3 | Informe técnico 4–6 páginas | Metodología, resultados reales, métricas, decisiones, límites, relación con CERN/HSF (como inspiración, no colaboración) | E9 | 5 | Los tres |
| CG-28 | S3 | Presentación y guion de demo | 12–15 min; demo: prueba generada, ejecución, mutante detectado, reporte de cobertura y alertas | E10 | 3 | Marcelo |
| CG-29 | S3 | Ensayo de reproducción en limpio | Alguien clona en otra máquina, sin `.env`, y reproduce con el README sin ayuda | PA 10 | 2 | Marcelo |
| CG-30 | S3 | Release `v1.0` | Tag, notas de versión y `out/` final adjunto (incluye respuestas de Grok para replay) | E1 | 1 | Christian |

### 5.2 Catálogo inicial de mutantes (CG-13)

| ID | Función | Familia | Cambio | Entrada testigo → original vs. mutante |
| --- | --- | --- | --- | --- |
| M01 | `weighted_mean` | Cálculo numérico | Divide entre `len(values)` en vez de Σw | `[1, 3]`, `[1, 3]` → 2.5 vs. 5.0 |
| M02 | `weighted_mean` | Validación | Omite el chequeo de peso negativo | `[1, 2]`, `[-1, 2]` → `ValueError` vs. 3.0 |
| M03 | `clamp` | Condición lógica | `x < lo` → `x <= lo` | **Equivalente**: con x == lo ambos devuelven lo; se reporta aparte |
| M04 | `clamp` | Condición lógica | Devuelve `lo` cuando x > hi | `clamp(15, 0, 10)` → 10 vs. 0 |
| M05 | `clamp` | Validación | Omite `lo > hi → ValueError` | `clamp(5, 10, 0)` → `ValueError` vs. valor |
| M06 | `normalize_minmax` | Excepción | Elimina la rama "todos iguales" | `[5, 5, 5]` → `[0, 0, 0]` vs. `ZeroDivisionError` |
| M07 | `normalize_minmax` | Cálculo numérico | Divide entre `max` en vez de `max − min` | `[2, 4]` → `[0, 1]` vs. `[0, 0.5]` |
| M08 | `moving_average` | Frontera / índice | `range(n - window)` en vez de `n - window + 1` | `[1, 2, 3]`, 2 → `[1.5, 2.5]` vs. `[1.5]` |
| M09 | `moving_average` | Frontera | `window > n` → `window >= n` | `[1, 2, 3]`, 3 → `[2.0]` vs. `ValueError` |
| M10 | `threshold_crossings` | Condición lógica | `threshold <= v[i]` → `threshold < v[i]` | `[0, 5]`, 5 → `[1]` vs. `[]` |
| M11 | `threshold_crossings` | Índice | El bucle empieza en 0 (compara con `v[-1]`) | `[5, 0]`, 3 → `[]` vs. `[0]` |
| M12 | `validate_range` | Condición lógica | Invierte el modo `inclusive` | `(10, 0, 10, True)` → True vs. False |
| M13 | `validate_range` | Validación | Omite el chequeo de NaN | `(nan, 0, 1)` → `ValueError` vs. False |

M03 es equivalente a propósito: demuestra que distinguimos mutantes equivalentes y no los contamos como éxito ni fracaso. Quedan 12 mutantes válidos (≥ 2 por función).

## 6. Calendario

El producto queda completo el **sábado 28/11** con el tag `v1.0`; del 29/11 al 2/12 solo se ensaya y se corrigen detalles, sin funcionalidades nuevas. Cada día tiene un hito verificable para que un retraso se detecte en 24 h, no al final.

| Fecha | Sprint | Abner | Christian | Marcelo | Hito del día |
| --- | --- | --- | --- | --- | --- |
| Mar 17/11 | S0 | Crear el repo en GitHub, proteger `main`, crear el tablero; crear la clave de xAI | Kickoff (los 3, 1 h): leer la guía, aprobar este plan, acordar firmas de las 6 funciones; crear Issues CG-01…33 | Plantilla de la matriz RF/PA ↔ evidencia | Repo y tablero creados |
| Mié 18/11 | S0 | CG-01 configuración del repo + lock · CG-02 CI · CG-32 secretos | CG-05 paquete `sciref` · CG-03 modelos de dominio | CG-04 `contracts.yaml` con oráculo a mano | CI verde; 6 funciones y contratos en `main`; secreto `XAI_API_KEY` configurado |
| Jue 19/11 | S1 | CG-09 regla sintaxis/importación | CG-06 cargador de specs + `codeguard list` | CG-13 mutantes M01–M07 | PA 01 demostrable |
| Vie 20/11 | S1 | CG-10 regla de correspondencia · CG-12 ledger | CG-07 generador Jinja2 (≥ 26 propuestas) | CG-13 mutantes M08–M13 · CG-14 aplicador | PA 02 demostrable |
| Sáb 21/11 | S1 | CG-11 regla de aserciones útiles | CG-08 semillas defectuosas + trazabilidad | CG-15 reglas `CG001`/`CG002` + 8 ejemplos | PA 03 y PA 08 demostrables |
| Dom 22/11 | S1 | Revisión de PR pendientes | Integración generate → validate (media jornada) | Revisión de PR pendientes | Review S1 + tag `v0.1` |
| Lun 23/11 | S2 | CG-16 ejecutor pytest + timeout | CG-23 CLI completa + `run_config.json` | CG-18 evaluación de mutantes | PA 04 demostrable |
| Mar 24/11 | S2 | CG-17 cobertura líneas/ramas | CG-22 métricas y tiempos por fase · CG-24 (inicio) | CG-18 (cierre) · CG-19 contraste Bandit | PA 05, PA 06, PA 07 demostrables |
| Mié 25/11 | S2 | CG-31 `GrokProposalSource` en rama aparte, con `--replay` | CG-21 reporte HTML · CG-24 endurecimiento (cierre) | CG-20 exportación JSON/CSV | PA 09 demostrable |
| Jue 26/11 | S2 | CG-25 pruebas propias · primera corrida real con Grok | CG-25 pruebas propias · primera corrida completa | CG-25 pruebas propias · recopilar resultados reales | **Feature freeze**: review S2 + tag `v0.9` (núcleo obligatorio completo) |
| Vie 27/11 | S3 | **12:00 decisión Grok: se integra o se descarta** · CG-33 comparación · informe: validación, ejecución, cobertura, LLM | CG-26 README · informe: arquitectura y generador | CG-28 diapositivas · informe: mutación, seguridad, límites | Borrador del informe (CG-27) completo |
| Sáb 28/11 | S3 | Congelar en `out/` las respuestas de Grok para replay · revisión final del informe | CG-30 release `v1.0` | CG-29 ensayo de reproducción en limpio · informe y diapositivas finales | **Entrega interna completa** |
| Dom 29/11 | Colchón | Ensayo de defensa 1 (los 3) |  |  | Lista de preguntas del tribunal |
| Lun 30/11 | Colchón | Correcciones menores; ensayo 2 cronometrado |  |  | Presentación ≤ 15 min |
| Mar 1/12 | Colchón / entrega | Entrega oficial del repositorio y resultados |  |  | **Entrega oficial** |
| Mié 2/12 | — | Ensayo final con la demo en la máquina de la defensa |  |  | Demo probada |
| Jue 3/12 | Defensa | Presentación y defensa ante el tribunal (los 3) |  |  | **Defensa** |

Regla de bloqueo: si una historia no está en PR al final de su día, se avisa en el daily y el integrador reasigna o recorta alcance (primero lo opcional: Bandit, HTML elaborado).

## 7. Repartición del trabajo

El trabajo se divide por etapas del pipeline, con carga equilibrada (Abner 34, Christian 31, Marcelo 33 puntos) y una separación deliberada: quien escribe las funciones (Christian) no escribe el oráculo ni los mutantes (Marcelo), y quien valida las pruebas (Abner) no las genera con plantillas. Abner crea y configura el repositorio, la CI y los secretos desde el primer día, y lleva la extensión con Grok; para compensar, el endurecimiento de ejecución (CG-24) pasa a Christian y el ensayo en limpio (CG-29) a Marcelo.

|  | Abner | Christian | Marcelo |
| --- | --- | --- | --- |
| **Área** | Repositorio y secretos, calidad de pruebas, ejecución, extensión Grok | Núcleo, generación e integración | Mutación, seguridad y evidencias |
| **Rol extra** | Scrum Master / QA | Product Owner / integrador | Documentación y evidencias |
| **RF a cargo** | RF 03, RF 04, RF 08 (repo, CI, secretos) + LLM opcional | RF 01, RF 02, RF 07 (CLI + HTML), RF 08 (endurecimiento) | RF 05, RF 06, RF 07 (JSON/CSV) |
| **Historias** | CG-01, 02, 09, 10, 11, 12, 16, 17, 31, 32, 33 | CG-03, 05, 06, 07, 08, 21, 22, 23, 24, 26, 30 | CG-04, 13, 14, 15, 18, 19, 20, 28, 29 |
| **Puntos** | 34 | 31 | 33 |
| **Entregables que lidera** | E1 repositorio y CI, E5 pytest y cobertura, comparación plantillas vs. Grok | E2 README, E3 paquete, E4 especificaciones y propuestas | E6 mutantes, E7 informe de detección, E8 seguridad, E10 presentación |
| **Revisa los PR de** | Christian | Marcelo | Abner (incluida la integración con Grok) |
| **Sección del informe (E9)** | Validación, ejecución, cobertura, reproducibilidad, extensión LLM | Introducción, relación con CERN/HSF, arquitectura, generador | Mutación, análisis estático, límites y conclusiones |
| **En la defensa (≈ 5 min c/u)** | Filtro de validación, demo: rechazo con motivo + ejecución + cobertura; resultado de Grok frente a plantillas | Problema, arquitectura, demo: contrato → prueba generada | Demo: mutante detectado y no detectado, alertas estáticas, métricas y límites |

Compartido por los tres: CG-25 (pruebas propias de CodeGuard, cada uno las de sus módulos) y CG-27 (informe, cada uno su sección; Marcelo unifica estilo).

**Todos deben poder explicar el sistema completo.** Para lograrlo, además de la revisión cruzada de PR, el 26/11 y el 29/11 cada integrante explica en 3 minutos un módulo que **no** escribió, y los otros dos le hacen preguntas como si fueran el tribunal.

## 8. Riesgos, defensa y checklist final

### 8.1 Riesgos

| Riesgo | Impacto | Mitigación |
| --- | --- | --- |
| Oráculo circular (esperados calculados con la propia función) | Alto: invalida el experimento | Esperados a mano por Marcelo, revisados por Abner; regla en la DoD |
| Fuga de la clave `XAI_API_KEY` al repositorio | Alto | `.env` en `.gitignore`, hook gitleaks, secreto en GitHub; si se filtra, revocar en la consola de xAI y crear otra |
| Grok consume el tiempo del núcleo obligatorio | Alto | Se trabaja en rama aparte desde el 25/11; decisión de corte el 27/11 a las 12:00 |
| Respuestas de Grok no repetibles, cuota diaria agotada o API caída | Medio | Temperatura 0, 6 llamadas por corrida, respuestas guardadas y modo `--replay`; el pipeline nunca depende de la API |
| Integración tardía de etapas | Alto | Etapas comunicadas solo por archivos en `out/`; integración parcial el 22/11 |
| Un integrante se atrasa o enferma | Medio | Daily + regla de bloqueo; revisión cruzada hace que otro conozca su código |
| Diferencias Windows / Linux (rutas, subprocesos) | Medio | `pathlib` en todo; CI en Ubuntu y Windows; ensayo en limpio el 28/11 |
| Mutante que "muere" por error de importación o timeout | Medio: infla la tasa | Clasificarlo `INVALID`, nunca `KILLED` |
| Cifras maquilladas (borrar propuestas fallidas) | Alto en la defensa | El ledger conserva todas, de plantillas y de Grok; el denominador incluye las 2 semillas rotas |
| La demo falla en vivo | Alto | Ensayar en la máquina de la defensa (2/12); tener `out/` de `v1.0` y capturas de respaldo; la parte de Grok se muestra en modo replay |

### 8.2 Preguntas probables del tribunal

- ¿Por qué la cobertura sola no demuestra que las pruebas sirven? → Mostrar un mutante que sobrevive con cobertura alta.
- ¿Cómo evitaron el oráculo circular? → Tabla de casos calculada a mano por otra persona.
- ¿Qué es un mutante equivalente? → M03 y por qué no se cuenta.
- ¿Por qué `shell=True` no siempre es una vulnerabilidad? → Solo si parte del comando viene de entrada no confiable; por eso las alertas son indicios para revisión humana.
- ¿Qué no puede resolver CodeGuard? → Funciones sin contrato, efectos secundarios, código de terceros, cobertura OWASP.
- ¿Grok genera mejores pruebas que las plantillas? → Responder solo con la tabla de CG-33 (validez, cobertura, mutantes detectados); el LLM no reemplaza al oráculo y sus pruebas pasan el mismo filtro.
- ¿Cómo protegieron la clave de la API? → `.env` ignorado, GitHub Secrets, gitleaks y workflow manual; mostrar que el repo no contiene la clave.
- ¿Se puede reproducir sin la clave? → Sí: `codeguard all` usa plantillas y `--replay` regenera las pruebas de Grok desde las respuestas guardadas.

### 8.3 Checklist de entrega (28/11)

- [ ] E1 — Repositorio con historial limpio y tag `v1.0`
- [ ] E2 — README con reproducción completa (`make all`)
- [ ] E3 — Paquete `sciref`: 6 funciones, 3 módulos, contratos
- [ ] E4 — Especificaciones, ≥ 26 propuestas, validadas y ledger de rechazos
- [ ] E5 — Resultados de pytest y cobertura de líneas y ramas solo de `sciref`
- [ ] E6 — 13 mutantes con id, diferencia y entrada testigo
- [ ] E7 — Informe de detección por función, tasa con denominador y análisis de sobrevivientes
- [ ] E8 — Alertas `CG001`/`CG002` con ejemplos seguros e inseguros
- [ ] E9 — Informe técnico de 4 a 6 páginas
- [ ] E10 — Diapositivas y guion de demo
- [ ] PA 01–PA 10 verificadas una por una en la matriz de evidencias
- [ ] Ensayo de reproducción en limpio aprobado (CG-29)

* [ ] Extensión Grok: integrada con su tabla comparativa y respuestas para replay, o descartada y documentada como trabajo futuro
* [ ] Revisión final: ninguna clave en el historial de Git (`gitleaks detect` limpio)
