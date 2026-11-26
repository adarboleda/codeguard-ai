# Contraste de CG001/CG002 con Bandit (CG-19)

Comparamos nuestras reglas estáticas con Bandit 1.8.6 (versión fijada en `pyproject.toml`) sobre
los ejemplos de `samples/security/` y sobre el código de `src/` y `reference/`. Las alertas de
Bandit se obtuvieron con `bandit -r <ruta> -f json`; las nuestras, con `codeguard.adapters.static`.

## 1. Ejemplos inseguros (deben alertar)

| Ejemplo | Línea | Nuestra regla | Bandit | Coincide |
| --- | --- | --- | --- | --- |
| `insecure_eval.py` | 5 | CG001 `eval` con argumento no literal | B307 `eval` (MEDIUM) | Sí |
| `insecure_exec.py` | 6 | CG001 `exec` con argumento no literal | B102 `exec_used` (MEDIUM) | Sí |
| `insecure_os_system.py` | 7 | CG002 `os.system` | B605 shell (HIGH) | Sí |
| `insecure_shell_true.py` | 7 | CG002 `subprocess.run` con `shell=True` | B602 `shell=True` (HIGH) | Sí |
| `insecure_shell_true.py` | 3 | — (no marcamos imports) | B404 import de subprocess (LOW) | No, ruido de Bandit |

Resultado: las 4 alertas esperadas aparecen en ambos lados, con la misma línea.

## 2. Ejemplos seguros (no deben alertar)

| Ejemplo | Línea | Nuestra regla | Bandit | Lectura |
| --- | --- | --- | --- | --- |
| `safe_eval_literal.py` | 5 | sin alerta | B307 `eval` (MEDIUM) | **Falso positivo de Bandit**: `eval("1 + 1")` usa un literal fijo |
| `safe_exec_literal.py` | 5 | sin alerta | B102 `exec` (MEDIUM) | **Falso positivo de Bandit**: `exec("VALUE = 42")` usa un literal fijo |
| `safe_subprocess_list.py` | 3 | sin alerta | B404 import (LOW) | Ruido: el import no es un riesgo por sí mismo |
| `safe_subprocess_list.py` | 7 | sin alerta | B603 sin shell (LOW), B607 ruta parcial (LOW) | Ruido: la lista de argumentos sin shell es el uso recomendado |
| `safe_os_path.py` | — | sin alerta | sin alerta | Coincide |

Resultado: Bandit emite 6 alertas sobre los ejemplos seguros, todas de severidad MEDIUM o LOW.
Nuestras reglas no emiten ninguna. Las dos MEDIUM son falsos positivos claros porque el argumento
es un literal, que es justo lo que CG001 distingue.

## 3. Código de `src/` y `reference/`

Bandit emite 6 alertas sobre el código del proyecto. Nuestras reglas emiten **0**.

| Archivo | Línea | Bandit | Lectura |
| --- | --- | --- | --- |
| `src/codeguard/adapters/execution/junit.py` | 3 | B405 import de `xml.etree` (LOW) | Ruido. El XML lo genera pytest, no es entrada no confiable |
| `src/codeguard/adapters/execution/junit.py` | 19 | B314 `ElementTree.parse` (MEDIUM) | Ruido en nuestro caso: el XML es de la corrida, no de un usuario |
| `src/codeguard/adapters/execution/pytest_runner.py` | 16 | B404 import de subprocess (LOW) | Ruido |
| `src/codeguard/adapters/execution/pytest_runner.py` | 86 | B603 sin shell (LOW) | Ruido: lista de argumentos, sin `shell=True` |
| `src/codeguard/adapters/validation/import_rule.py` | 12 | B404 import de subprocess (LOW) | Ruido |
| `src/codeguard/adapters/validation/import_rule.py` | 70 | B603 sin shell (LOW) | Ruido: lista de argumentos, sin `shell=True` |

Ninguna de estas alertas es un riesgo de ejecución de comandos del proyecto.

## 4. Límites de nuestras reglas (falsos negativos verificados)

Probamos un archivo de control fuera del repositorio con llamadas que nuestras reglas no ven:

| Llamada | Bandit | CG001/CG002 |
| --- | --- | --- |
| `from subprocess import run` y `run(cmd, shell=True)` | B602 (HIGH) | **No** |
| `from os import system` y `system(cmd)` | B605 (HIGH) | **No** |
| `import os as o` y `o.system(cmd)` | B605 (HIGH) | **No** |
| `eval(payload)` | B307 (MEDIUM) | Sí (CG001) |

Causa: CG002 solo reconoce los nombres `os` y `subprocess` escritos tal cual, y CG001 solo
reconoce `eval` y `exec` como nombres directos. Estos son falsos negativos reales y están
documentados en el docstring de `src/codeguard/adapters/static/rules.py`. Hoy no se corrigen;
si se quiere cubrir, hay que resolver los alias de import en el escáner.

## 5. Conclusión

- En los 4 ejemplos inseguros, nuestras reglas y Bandit coinciden con la misma línea.
- En los ejemplos seguros, Bandit da 2 falsos positivos MEDIUM (`eval`/`exec` con literal) y
  4 alertas LOW de ruido; nuestras reglas no dan ninguna.
- En el código del proyecto, Bandit da 6 alertas LOW/MEDIUM que son ruido; nuestras reglas dan 0.
- Limitación principal de nuestras reglas: no siguen alias ni importaciones directas (sección 4).
  Bandit sí las sigue. Por eso CG001/CG002 son un complemento, no un reemplazo.

Bandit está en `pyproject.toml` como dependencia, pero ni el CI ni los hooks de pre-commit lo
ejecutan. Este documento registra la comparación; no hay ninguna puerta automática con Bandit.
