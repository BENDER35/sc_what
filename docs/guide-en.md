# sc_what — Getting Started Guide 📚

## Welcome

This guide will help you use **sc_what**, a public invitation link searcher for WhatsApp, Signal, Teams, Discord, and Telegram. It's designed for users who want to discover public groups for research, documentation, or community moderation purposes.

---

## Quick Installation

```bash
# Clone the repository
git clone https://github.com/BENDER35/sc_what.git
cd sc_what

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package in development mode
pip install -e .
```

---

## Basic Usage

### First search

```bash
# Search for groups about "python" on all platforms
group-finder "python"

# Only Telegram and Discord, limit 20 results
group-finder "gaming" -p telegram,discord -m 20
```

### Most common options

| Option | What it does |
|---|---|
| `-p, --platforms` | Select platforms: `all`, `whatsapp`, `signal`, `teams`, `discord`, `telegram` |
| `-m, --max-results` | Maximum results per page and platform (default 50) |
| `-o, --output` | Output base filename (default `results`) |
| `-f, --format` | Output format: `csv`, `json`, `both`, `ndjson` |
| `--exact / --no-exact` | Search for exact phrase (default yes) |
| `--validate` | Check if links are still active |
| `--min-members` | Filter groups with at least N members (requires `--validate`) |
| `--deep` | Visit result pages to find more links |
| `--dry-run` | Show queries that would run without actually searching |

---

## Output Formats

### CSV (default) + JSON

Results are saved in `results.csv` and `results.json` (or with the name you specify with `-o`).

- CSV uses **UTF-8 with BOM** so Excel displays accents correctly.
- Values starting with `=`, `+`, `-` or `@` are prefixed with `'` to prevent spreadsheet formula injection.
- Columns: `Platform`, `Title`, `Link`, `Description`, `Source`, `Queries`, `Validated`, `Members`.

### JSON

Structure with metadata (`meta`) and results per platform. Includes query info, search engine, region, safesearch, timing, and counts.

### NDJSON

One JSON line per found link. Ideal for data processing pipelines.

---

## Link Validation

With `--validate`, sc_what checks if links are still active:

| Platform | Method |
|---|---|
| **Discord** | Public API `https://discord.com/api/v10/invites/<code>?with_counts=true` |
| **Telegram** | Public page `https://t.me/<username>`; member count extraction |
| **WhatsApp** | Public link page; detects revoked chats or non-existent chats |
| **Signal** | Basic HTTP response check |
| **Teams** | Marked as `unknown` (usually requires authentication) |

Validation has a 24-hour cache and respects the concurrent limit (`--validate-workers`). **It does not enter groups or send messages.**

---

## Deep Search (`--deep`)

With `--deep`, sc_what visits up to `--deep-limit` result pages per platform and extracts links that didn't appear in the initial search snippet.

- Respects `robots.txt`.
- Limits page size to ~1 MB.
- Uses `--deep-delay` (in seconds) to avoid overloading servers.
- Only visits `http(s)` pages that aren't already platform links.

---

## Caching

- Searches are saved in `~/.cache/group_finder/cache.json` by default.
- TTL configurable with `--cache-ttl` (1 hour default).
- Validations have a 24-hour TTL.
- Use `--no-cache` to disable or `--cache-dir` to change the directory.

---

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Lint and formatting
ruff check .
ruff format --check .

# Types and tests
mypy group_finder.py
pytest --cov=group_finder --cov-report=term-missing
```

### Project Structure

```text
.
├── group_finder.py          # Main script
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

## Legal Notice and Responsible Use

- This project is intended for **discovering public invitation links**.
- Respect the **Terms of Service** of DuckDuckGo and each platform.
- Do not automate joining groups, sending messages, or spam.
- Do not collect unnecessary personal data.
- Links may expire or be revoked.
- Use `--safesearch` and available filters.
- The author is not responsible for how the software is used.

## License

MIT. See the [LICENSE](LICENSE) file included with the project.