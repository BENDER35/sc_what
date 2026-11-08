# Changelog

Todas las novedades relevantes de este proyecto se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el versionado usa [Semantic Versioning](https://semver.org/lang/es/).

## [1.0.0] - 2026-11-08

### Añadido

- Extracción y normalización de enlaces para WhatsApp, Signal, Teams, Discord y Telegram.
- Soporte para `t.me/+hash`, `t.me/joinchat/<hash>`, `discordapp.com/invite` y enlaces sin esquema.
- Dorks agrupados con paréntesis para que la consulta se aplique a todas las ramas del `OR`.
- Reintentos con backoff exponencial y manejo específico de rate limits y timeouts.
- Opciones `--region`, `--safesearch`, `--timelimit`, `--backend`, `--pages`, `--proxy` y `--timeout`.
- Caché local de búsquedas y validaciones.
- Modo `--deep` para visitar páginas de resultados respetando `robots.txt`.
- Validación opcional de enlaces vivos y filtrado por `--min-members`.
- Salida CSV, JSON y NDJSON con metadatos, escritura atómica y protección contra inyección de fórmulas.
- Opciones `--append`, `--force`, `--timestamp`, `--output-dir` y `--stdout`.
- Interfaz Rich con progreso, resumen de errores y enlaces clicables.
- Tests con `pytest`, lint con `ruff`, tipado con `mypy` y CI en GitHub/GitLab.
- Mirror automático GitHub → GitLab y releases en zip en ambos repositorios.

### Corregido

- Los dorks con `OR` ya no devuelven resultados sin filtrar por la consulta.
- Las regex de Teams, Signal y Telegram ya no truncan ni pierden enlaces válidos.
- La blacklist de Telegram compara rutas exactas y evita falsos positivos.
- `-o archivo.csv` ya no genera `archivo.csv.csv`.
- Los valores `None` de `ddgs` ya no rompen la extracción.
- El CSV se guarda con BOM para Excel y se sanitizan las fórmulas.
- Se elimina el `warnings.filterwarnings("ignore")` global.
