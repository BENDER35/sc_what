# sc_what — Buscador de Grupos Multiplataforma 🔍💬

Buscador de enlaces de invitación **públicos** para grupos de **WhatsApp, Signal, Microsoft Teams, Discord y Telegram** usando dorks de búsqueda a través de [`ddgs`](https://pypi.org/project/ddgs/) (DuckDuckGo y otros backends).

> **Repositorio principal:** <https://github.com/BENDER35/sc_what>
> **Mirror / copia de seguridad:** <https://gitlab.com/BENDER_5000/sc_what>

---

## Características

- 🎯 Dorks agrupados correctamente (`OR` con paréntesis) para que la consulta se aplique a todas las ramas.
- 🧩 Extracción y normalización de enlaces por plataforma, incluyendo:
  - WhatsApp (`chat.whatsapp.com/<código>`)
  - Signal (`signal.group/#<token>`)
  - Teams (`teams.microsoft.com/l/...` y `teams.live.com/meet/...`)
  - Discord (`discord.gg`, `discord.com/invite`, `discordapp.com/invite`)
  - Telegram (`t.me/<usuario>`, `t.me/joinchat/<hash>`, `t.me/+<hash>`)
- 🛡️ Filtros para evitar falsos positivos (bots, enlaces de compartir, stickers, canales `t.me/s/`, etc.).
- 🔁 Reintentos con backoff exponencial y manejo específico de rate limits/timeouts.
- 🌍 Opciones de región, `safesearch`, límite temporal y backend de búsqueda.
- 🧠 Caché local de búsquedas y validaciones para no repetir peticiones.
- 🕵️ Modo `--deep` para visitar páginas de resultados y encontrar enlaces fuera del snippet.
- ✅ Validación opcional de enlaces vivos y filtrado por número de miembros (`--validate`, `--min-members`).
- 🎨 Interfaz de terminal con `rich`: progreso, tablas, enlaces clicables y resumen de errores.
- 💾 Exportación a CSV, JSON o NDJSON, con metadatos, escritura atómica y protección contra inyección de fórmulas.
- 🧪 Tests con `pytest`, lint con `ruff` y tipado con `mypy`.
- 🔄 Mirror automático GitHub → GitLab y releases en zip en ambos repositorios.

---

## Requisitos

- **Python 3.10 o superior** (`ddgs 9.x` no soporta 3.8/3.9).
- No necesita claves de API para el backend por defecto.

---

## Instalación

```bash
git clone https://github.com/BENDER35/sc_what.git
cd sc_what

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
```

Para desarrollo:

```bash
pip install -e ".[dev]"
```

También puedes usar solo el archivo `group_finder.py` si ya tienes las dependencias:

```bash
pip install -r requirements.txt
python group_finder.py --help
```

---

## Uso rápido

```bash
# Todas las plataformas, salida CSV + JSON
group-finder "python"

# Solo Telegram y Discord, máximo 20 resultados
group-finder "gaming" -p telegram,discord -m 20

# WhatsApp, salida JSON con nombre personalizado
group-finder "cripto" -p whatsapp -o cripto -f json

# Varias consultas desde un archivo
group-finder --query-file consultas.txt

# Validar enlaces y filtrar grupos con menos de 100 miembros
group-finder "python" --validate --min-members 100

# Búsqueda profunda + salida NDJSON por stdout
group-finder "python" --deep --stdout -f ndjson

# Ver qué consultas se ejecutarían sin hacer red
group-finder "python" --dry-run
```

Si no usas el entry point instalado:

```bash
python group_finder.py "python"
```

---

## Opciones principales

| Opción | Descripción |
|---|---|
| `query` | Consulta de búsqueda (opcional si usas `--query-file`). |
| `--query-file` | Archivo con una consulta por línea. Ignora líneas vacías y `#`. |
| `-p, --platforms` | `all` o lista separada por comas: `whatsapp,signal,teams,discord,telegram`. |
| `-m, --max-results` | Resultados máximos por página y plataforma (por defecto `50`). |
| `-o, --output` | Nombre base de salida (por defecto `results`). |
| `--output-dir` | Carpeta de salida. |
| `-f, --format` | `csv`, `json`, `both` o `ndjson` (por defecto `both`). |
| `--csv-delimiter` | Delimitador del CSV; usa `;` para Excel en español. |
| `--exact / --no-exact` | Buscar como frase exacta (por defecto sí). |
| `--region` | Región de búsqueda, por ejemplo `es-es` (por defecto `us-en`). |
| `--safesearch` | `on`, `moderate` u `off`. |
| `--timelimit` | `d`, `w`, `m` o `y`. |
| `--backend` | Backend(s) de `ddgs`, por ejemplo `duckduckgo,brave,bing`. |
| `--retries` | Reintentos por búsqueda (por defecto `3`). |
| `--delay` | Espera base entre reintentos (por defecto `1.0` s). |
| `--timeout` | Timeout de red en segundos (por defecto `10`). |
| `--proxy` | Proxy HTTP/SOCKS. |
| `--workers` | Búsquedas concurrentes (por defecto `1`). |
| `--pages` | Páginas de resultados por consulta y plataforma. |
| `--deep` | Visitar páginas de resultados para buscar más enlaces. |
| `--deep-limit` | Máximo de páginas a visitar por plataforma. |
| `--deep-delay` | Espera entre páginas visitadas. |
| `--validate` | Comprobar si los enlaces siguen vivos. |
| `--min-members` | Filtrar grupos con menos miembros (si se conoce el dato). |
| `--require-members` | Descartar enlaces sin número de miembros. |
| `--validate-workers` | Validaciones concurrentes (por defecto `3`). |
| `--validate-delay` | Espera entre validaciones. |
| `--cache-dir` | Carpeta de caché (por defecto `~/.cache/group_finder`). |
| `--no-cache` | Desactivar caché. |
| `--cache-ttl` | TTL de la caché de búsquedas en segundos. |
| `--exclude` | Dominios o palabras a excluir, separados por comas. |
| `--limit-display` | Resultados a mostrar por plataforma (por defecto `15`). |
| `--full` | Mostrar todos los resultados en terminal. |
| `--timestamp` | Añadir fecha y hora al nombre de los archivos. |
| `--append` | Añadir a archivos existentes sin duplicar enlaces. |
| `--force` | Sobrescribir archivos existentes. |
| `--stdout` | Escribir resultados a stdout. |
| `--quiet` | Ocultar progreso y resumen; solo errores. |
| `--verbose` | Información de depuración. |
| `--log-file` | Guardar logs en archivo. |
| `--no-color` | Desactivar colores. |
| `--dry-run` | Mostrar consultas sin ejecutar búsquedas. |
| `--version` | Mostrar versión. |

---

## Formatos de salida

### JSON

```json
{
  "meta": {
    "queries": ["python"],
    "generated_at": "2026-11-08T10:00:00+00:00",
    "version": "1.0.0",
    "platforms": ["whatsapp", "telegram"],
    "engine": "auto",
    "region": "us-en",
    "validated": true,
    "elapsed_seconds": 12.34,
    "counts": { "whatsapp": 1, "telegram": 2 },
    "errors": {}
  },
  "results": {
    "whatsapp": [
      {
        "platform": "whatsapp",
        "title": "Grupo de Python",
        "link": "https://chat.whatsapp.com/XXXXXXXXXXXX",
        "description": "Comunidad de Python en español",
        "source_url": "https://ejemplo.com/grupos",
        "valid": true,
        "member_count": null,
        "queries": ["python"],
        "sources": ["https://ejemplo.com/grupos"]
      }
    ]
  }
}
```

### CSV

Columnas: `Plataforma`, `Título`, `Enlace`, `Descripción`, `Fuente`, `Consultas`, `Validado`, `Miembros`.

El CSV se guarda en **UTF-8 con BOM** para que Excel muestre bien los acentos. Los valores que empiezan por `=`, `+`, `-` o `@` se prefijan con `'` para evitar inyección de fórmulas.

### NDJSON

Una línea JSON por enlace, con el campo `platform` incluido. Ideal para pipelines.

---

## Validación de enlaces

`--validate` intenta comprobar si el enlace sigue vivo:

| Plataforma | Método |
|---|---|
| Discord | API pública `https://discord.com/api/v10/invites/<code>?with_counts=true`. |
| Telegram | Página pública `https://t.me/<usuario>` y extracción del número de miembros. |
| WhatsApp | Página pública del enlace; detecta enlaces revocados o chats inexistentes. |
| Signal | Comprobación básica de respuesta HTTP. |
| Teams | Se deja como `desconocido` (normalmente requiere autenticación). |

La validación es opcional, tiene caché de 24 h y respeta un límite de concurrencia. **No entra en los grupos ni envía mensajes.**

---

## Búsqueda profunda

Con `--deep`, el script visita hasta `--deep-limit` páginas de resultados por plataforma (por ejemplo, directorios de grupos) y extrae enlaces que no aparecían en el snippet de búsqueda.

- Respeta `robots.txt`.
- Limita el tamaño de página a ~1 MB.
- Usa `--deep-delay` para no saturar los servidores.
- Solo visita páginas `http(s)` que no sean ya enlaces de la plataforma.

---

## Caché

Por defecto se guarda en `~/.cache/group_finder/cache.json`:

- Búsquedas: TTL configurable con `--cache-ttl` (1 h por defecto).
- Validaciones: TTL de 24 h.

Usa `--no-cache` para desactivarla o `--cache-dir` para cambiarla.

---

## Desarrollo

```bash
pip install -e ".[dev]"

ruff check .
ruff format --check .
mypy group_finder.py
pytest --cov=group_finder --cov-report=term-missing
```

### Estructura

```text
.
├── group_finder.py          # Script principal
├── tests/
│   ├── test_extract.py      # Extracción y normalización de URLs
│   ├── test_output.py       # CSV/JSON, atomicidad y sanitización
│   ├── test_cli.py          # Argumentos y validaciones
│   └── test_search.py       # Búsqueda con DDGS mockeado
├── .github/workflows/
│   ├── ci.yml               # Lint, tipos y tests
│   ├── mirror.yml           # Mirror GitHub → GitLab
│   └── release.yml          # Release en GitHub con zip
├── .gitlab-ci.yml           # Tests y release en GitLab
├── pyproject.toml
└── README.md
```

---

## Releases y mirror

- **GitHub** es el repositorio principal.
- **GitLab** es la copia de seguridad. El workflow `.github/workflows/mirror.yml` hace `git push --mirror` a GitLab en cada push a `main` y en cada tag.
- Al crear un tag `v*`:
  - GitHub Actions genera `sc_what-<tag>.zip` y crea la release en GitHub.
  - GitLab CI genera el mismo zip y crea la release en GitLab (requiere la variable `GITLAB_RELEASE_TOKEN` con scope `api`).

### Crear una release manualmente

```bash
git tag -a v1.0.0 -m "v1.0.0"
git push origin v1.0.0

# GitHub
gh release create v1.0.0 dist/sc_what-1.0.0.zip --generate-notes

# GitLab (subida de asset + release)
# Ver .gitlab-ci.yml para el flujo automatizado
```

---

## Aviso legal y uso responsable

Este proyecto está pensado para **descubrir enlaces de invitación públicos** con fines de investigación, documentación o moderación de comunidades.

- Respeta los **Términos de Servicio** de DuckDuckGo y de cada plataforma.
- No automatices el ingreso en grupos, el envío de mensajes ni el spam.
- No recopiles datos personales innecesarios.
- Los enlaces pueden caducar, ser revocados o llevar a contenido no deseado.
- Usa `--safesearch` y los filtros disponibles según tu caso.
- El autor no se responsabiliza del uso que se haga del software.

---

## Licencia

MIT. Consulta [LICENSE](LICENSE).
