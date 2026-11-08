# sc_what — Guía Didáctica 📚

## Bienvenido/a

Esta guía te ayudará a usar **sc_what**, el buscador de enlaces de invitación públicos para WhatsApp, Signal, Teams, Discord y Telegram. Está diseñada para usuarios que quieren descubrir grupos públicos con fines de investigación, documentación o moderación de comunidades.

---

## Instalación rápida

```bash
# Clonar el repositorio
git clone https://github.com/BENDER35/sc_what.git
cd sc_what

# Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar el paquete en modo desarrollo
pip install -e .
```

---

## Uso básico

### Primera búsqueda

```bash
# Buscar grupos sobre "python" en todas las plataformas
group-finder "python"

# Solo Telegram y Discord, límite 20 resultados
group-finder "gaming" -p telegram,discord -m 20
```

### Opciones más comunes

| Opción | Qué hace |
|---|---|
| `-p, --platforms` | Selecciona plataformas: `all`, `whatsapp`, `signal`, `teams`, `discord`, `telegram` |
| `-m, --max-results` | Máximo de resultados por página y plataforma (por defecto 50) |
| `-o, --output` | Nombre base de los archivos de salida (por defecto `results`) |
| `-f, --format` | Formato de salida: `csv`, `json`, `both`, `ndjson` |
| `--exact / --no-exact` | Buscar la consulta como frase exacta (por defecto sí) |
| `--validate` | Comprobar si los enlaces siguen vivos |
| `--min-members` | Filtrar grupos con al menos N miembros (requiere `--validate`) |
| `--deep` | Visitar páginas de resultados para encontrar más enlaces |
| `--dry-run` | Mostrar las consultas que se ejecutarían sin buscar de verdad |

---

## Formatos de salida

### CSV (predeterminado + JSON)

Los resultados se guardan en archivos `results.csv` y `results.json` (o con el nombre que indiques con `-o`).

- El CSV usa **UTF-8 con BOM** para que Excel muestre bien los acentos.
- Los valores que empiezan por `=`, `+`, `-` o `@` se prefijan con `'` para evitar inyección de fórmulas en hojas de cálculo.
- Columnas: `Plataforma`, `Título`, `Enlace`, `Descripción`, `Fuente`, `Consultas`, `Validado`, `Miembros`.

### JSON

Estructura con metadatos (`meta`) y resultados por plataforma. Incluye información de la consulta, motor de búsqueda, región, safesearch, tiempos y recuentos.

### NDJSON

Una línea JSON por cada enlace encontrado. Ideal para pipelines de procesamiento de datos.

---

## Validación de enlaces

Con `--validate`, sc_what comprueba si los enlaces siguen activos:

| Plataforma | Método |
|---|---|
| **Discord** | API pública `https://discord.com/api/v10/invites/<code>?with_counts=true` |
| **Telegram** | Página pública `https://t.me/<usuario>`; extracción del número de miembros |
| **WhatsApp** | Página pública del enlace; detecta si el chat fue revocado o no existe |
| **Signal** | Comprobación básica de la respuesta HTTP |
| **Teams** | Se marca como `desconocido` (normalmente requiere autenticación) |

La validación tiene caché de 24 horas y respeta un límite de concurrentes (`--validate-workers`). **No entra en los grupos ni envía mensajes.**

---

## Búsqueda profunda (`--deep`)

Con `--deep`, sc_what visita hasta `--deep-limit` páginas de resultados por plataforma y extrae enlaces que no aparecían en el fragmento de búsqueda inicial.

- Respeta `robots.txt`.
- Limita el tamaño de página a ~1 MB.
- Usa `--deep-delay` (en segundos) para no saturar los servidores.
- Solo visita páginas `http(s)` que no sean ya enlaces de la plataforma.

---

## Caché

- Las búsquedas se guardan en `~/.cache/group_finder/cache.json` por defecto.
- TTL configurable con `--cache-ttl` (1 hora por defecto).
- Las validaciones tienen TTL de 24 horas.
- Usa `--no-cache` para desactivarla o `--cache-dir` para cambiarla.

---

## Desarrollo

```bash
# Instalar dependencias de desarrollo
pip install -e ".[dev]"

# Lint y formato
ruff check .
ruff format --check .

# Tipos y tests
mypy group_finder.py
pytest --cov=group_finder --cov-report=term-missing
```

### Estructura del proyecto

```text
.
├── group_finder.py          # Script principal
├── tests/
│   ├── test_extract.py
│   ├── test_output.py
│   ├── test_cli.py
│   └── test_search.py
├── .github/workflows/
│   ├── ci.yml
│   ├── mirror.yml
│   └── release.yml
├── .gitlab-ci.yml
├── pyproject.toml
├── README.md
└── docs/
    ├── guide-es.md
    └── guide-en.md
```

---

## Aviso legal y uso responsable

- Este proyecto está pensado para **descubrir enlaces de invitación públicos**.
- Respeta los **Términos de Servicio** de DuckDuckGo y de cada plataforma.
- No automates el ingreso en grupos, envío de mensajes ni spam.
- No recopiles datos personales innecesarios.
- Los enlaces pueden caducar o ser revocados.
- Usa `--safesearch` y los filtros disponibles.
- El autor no se responsabiliza del uso que se haga del software.

## Licencia

MIT. Consulta el archivo [LICENSE](LICENSE) que viene con el proyecto.