#!/usr/bin/env python3
"""Buscador de enlaces de invitación públicos en varias plataformas.

El script usa dorks de búsqueda en DuckDuckGo (u otros backends de ``ddgs``)
para localizar enlaces públicos de WhatsApp, Signal, Microsoft Teams, Discord
y Telegram. Los resultados se pueden exportar a CSV, JSON o NDJSON.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import logging
import os
import random
import re
import sys
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import httpx
from rich.align import Align
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

try:
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException
except ImportError:  # pragma: no cover - compatibilidad con duckduckgo_search
    from duckduckgo_search import DDGS  # type: ignore[no-redef]

    try:
        from duckduckgo_search.exceptions import (  # type: ignore[no-redef]
            DuckDuckGoSearchException as DDGSException,
        )
    except ImportError:
        DDGSException = Exception  # type: ignore[assignment,misc]

    RatelimitException = DDGSException  # type: ignore[assignment,misc]
    TimeoutException = DDGSException  # type: ignore[assignment,misc]


__version__ = "1.0.0"
USER_AGENT = f"sc-what/{__version__} (+https://github.com/BENDER35/sc_what)"
DEFAULT_CACHE_TTL = 60 * 60
VALIDATION_CACHE_TTL = 24 * 60 * 60
MAX_QUERY_LENGTH = 200
MAX_DEEP_BYTES = 1_000_000

console = Console()
error_console = Console(stderr=True)

TELEGRAM_BLACKLIST = frozenset(
    {"durov", "telegram", "setlanguage", "addstickers", "addtheme", "botfather"}
)


@dataclass(frozen=True)
class Platform:
    """Configuración de una plataforma de mensajería."""

    key: str
    name: str
    dorks: tuple[str, ...]
    patterns: tuple[re.Pattern[str], ...]
    hosts: frozenset[str]
    color: str
    blacklist: frozenset[str] = frozenset()


PLATFORMS: dict[str, Platform] = {
    "whatsapp": Platform(
        key="whatsapp",
        name="WhatsApp",
        dorks=("site:chat.whatsapp.com",),
        patterns=(
            re.compile(
                r"(?<![\w./-])(?:https?://)?(?:www\.)?chat\.whatsapp\.com/"
                r"(?:invite/)?[A-Za-z0-9_-]{10,}",
                re.IGNORECASE,
            ),
        ),
        hosts=frozenset({"chat.whatsapp.com"}),
        color="green",
    ),
    "signal": Platform(
        key="signal",
        name="Signal",
        dorks=("site:signal.group",),
        patterns=(
            re.compile(
                r"(?<![\w./-])(?:https?://)?(?:www\.)?signal\.group/"
                r"[#A-Za-z0-9_\-+/=]+",
                re.IGNORECASE,
            ),
        ),
        hosts=frozenset({"signal.group"}),
        color="blue",
    ),
    "teams": Platform(
        key="teams",
        name="Microsoft Teams",
        dorks=(
            "site:teams.microsoft.com/l/community",
            "site:teams.microsoft.com/l/meetup-join",
            "site:teams.live.com",
        ),
        patterns=(
            re.compile(
                r"(?<![\w./-])(?:https?://)?(?:www\.)?teams\.microsoft\.com/"
                r"l/(?:community|meetup-join)/[^\s<>\"']+",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?<![\w./-])(?:https?://)?(?:www\.)?teams\.live\.com/"
                r"meet/[^\s<>\"']+",
                re.IGNORECASE,
            ),
        ),
        hosts=frozenset({"teams.microsoft.com", "teams.live.com"}),
        color="magenta",
    ),
    "discord": Platform(
        key="discord",
        name="Discord",
        dorks=(
            "site:discord.gg",
            "site:discord.com/invite",
            "site:discordapp.com/invite",
        ),
        patterns=(
            re.compile(
                r"(?<![\w./-])(?:https?://)?(?:www\.)?"
                r"(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9_-]+",
                re.IGNORECASE,
            ),
        ),
        hosts=frozenset({"discord.gg", "discord.com", "discordapp.com"}),
        color="purple",
    ),
    "telegram": Platform(
        key="telegram",
        name="Telegram",
        dorks=("site:t.me", "site:telegram.me", "site:telegram.dog"),
        patterns=(
            re.compile(
                r"(?<![\w./-])(?:https?://)?(?:www\.)?"
                r"(?:t\.me|telegram\.me|telegram\.dog)/"
                r"(?:joinchat/|\+)?[A-Za-z0-9_-]{5,}",
                re.IGNORECASE,
            ),
        ),
        hosts=frozenset({"t.me", "telegram.me", "telegram.dog"}),
        blacklist=TELEGRAM_BLACKLIST,
        color="cyan",
    ),
}


@dataclass
class GroupLink:
    """Un enlace de invitación encontrado."""

    platform: str
    title: str
    link: str
    description: str = ""
    source_url: str = ""
    valid: bool | None = None
    member_count: int | None = None
    queries: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "title": self.title,
            "link": self.link,
            "description": self.description,
            "source_url": self.source_url,
            "valid": self.valid,
            "member_count": self.member_count,
            "queries": self.queries,
            "sources": self.sources,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GroupLink:
        valid = data.get("valid")
        if valid not in (True, False, None):
            valid = None
        member_count = data.get("member_count")
        try:
            member_count = int(member_count) if member_count is not None else None
        except (TypeError, ValueError):
            member_count = None
        return cls(
            platform=str(data.get("platform") or ""),
            title=str(data.get("title") or ""),
            link=str(data.get("link") or ""),
            description=str(data.get("description") or ""),
            source_url=str(data.get("source_url") or ""),
            valid=valid,
            member_count=member_count,
            queries=[str(item) for item in (data.get("queries") or [])],
            sources=[str(item) for item in (data.get("sources") or [])],
        )


@dataclass
class PlatformResult:
    key: str
    items: list[GroupLink]
    error: str | None = None
    elapsed: float = 0.0
    source_pages: set[str] = field(default_factory=set)


@dataclass
class SearchReport:
    results: dict[str, list[GroupLink]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    source_pages: dict[str, set[str]] = field(default_factory=dict)
    interrupted: bool = False
    elapsed: float = 0.0


@dataclass
class ValidationResult:
    valid: bool | None
    member_count: int | None = None
    title: str | None = None


class Cache:
    """Caché JSON sencilla y atómica para búsquedas y validaciones."""

    def __init__(self, path: Path | None, ttl: int = DEFAULT_CACHE_TTL):
        self.path = path
        self.ttl = ttl
        self._lock = threading.Lock()
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path or not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def make_key(self, **kwargs: Any) -> str:
        payload = json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any:
        with self._lock:
            entry = self._data.get(key)
            if not isinstance(entry, dict):
                return None
            ttl = int(entry.get("ttl", self.ttl))
            if time.time() - float(entry.get("ts", 0)) > ttl:
                del self._data[key]
                return None
            return entry.get("value")

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            self._data[key] = {
                "ts": time.time(),
                "ttl": self.ttl if ttl is None else ttl,
                "value": value,
            }
            self._save()


def default_cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "group_finder" / "cache.json"


def resolve_ddg_redirect(url: str) -> str:
    """Resuelve los enlaces de redirección de DuckDuckGo."""
    if "duckduckgo.com/l/" in url:
        query = parse_qs(urlparse(url).query)
        target = query.get("uddg", [""])[0]
        if target:
            return unquote(target)
    return url


def normalize_url(raw: str, platform: Platform) -> str | None:
    """Normaliza y valida una URL para una plataforma concreta."""
    url = html.unescape(raw.strip())
    url = url.rstrip(".,;:!?)]}>'\"")
    if url.startswith("//"):
        url = "https:" + url
    elif not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url

    parsed = urlparse(url)
    host = parsed.netloc.lower().split("@")[-1].split(":")[0].removeprefix("www.")
    if host not in platform.hosts:
        return None

    path = parsed.path.strip("/")

    if platform.key == "whatsapp":
        match = re.fullmatch(r"(?:invite/)?([A-Za-z0-9_-]{10,})", path)
        if not match:
            return None
        return f"https://chat.whatsapp.com/{match.group(1)}"

    if platform.key == "signal":
        fragment = parsed.fragment.strip()
        if not fragment or not re.fullmatch(r"[A-Za-z0-9_\-+/=]+", fragment):
            return None
        return f"https://signal.group/#{fragment}"

    if platform.key == "teams":
        if host == "teams.microsoft.com":
            if not path.startswith(("l/community/", "l/meetup-join/")):
                return None
        elif host == "teams.live.com":
            if not path.startswith("meet/"):
                return None
        else:
            return None
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))

    if platform.key == "discord":
        match = re.fullmatch(r"(?:invite/)?([A-Za-z0-9_-]{2,})", path)
        if not match:
            return None
        return f"https://discord.gg/{match.group(1)}"

    if platform.key == "telegram":
        first = path.split("/", 1)[0].lower()
        if first in platform.blacklist:
            return None
        if path.startswith(("s/", "share/", "iv/", "proxy", "socks")):
            return None
        match = re.fullmatch(r"joinchat/([A-Za-z0-9_-]{5,})", path)
        if match:
            return f"https://t.me/+{match.group(1)}"
        match = re.fullmatch(r"\+([A-Za-z0-9_-]{5,})", path)
        if match:
            return f"https://t.me/+{match.group(1)}"
        match = re.fullmatch(r"([A-Za-z0-9_]{5,32})", path)
        if match:
            return f"https://t.me/{match.group(1)}"
        return None

    return None


def extract_links(text: str, platform: Platform) -> set[str]:
    """Extrae y normaliza enlaces de un texto."""
    text = html.unescape(text or "")
    found: set[str] = set()
    for pattern in platform.patterns:
        for match in pattern.findall(text):
            url = normalize_url(match, platform)
            if url:
                found.add(url)
    return found


def extract_from_item(item: dict[str, Any], platform: Platform) -> tuple[set[str], str, str, str]:
    title = str(item.get("title") or "")
    href = resolve_ddg_redirect(str(item.get("href") or item.get("url") or ""))
    body = str(item.get("body") or item.get("description") or "")
    links = (
        extract_links(href, platform)
        | extract_links(title, platform)
        | extract_links(body, platform)
    )
    return links, title, href, body


def build_query(platform: Platform, query: str, exact: bool) -> str:
    """Construye una consulta con los dorks agrupados correctamente."""
    term = f'"{query}"' if exact else query
    dorks = " OR ".join(f"({dork})" for dork in platform.dorks)
    return f"({dorks}) {term}"


def is_excluded(*texts: str | None, patterns: Sequence[str]) -> bool:
    if not patterns:
        return False
    haystack = " ".join(str(text).lower() for text in texts if text)
    return any(pattern in haystack for pattern in patterns)


def is_platform_url(url: str, platform: Platform) -> bool:
    host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    return host.removeprefix("www.") in platform.hosts


def add_item(
    items: dict[str, GroupLink],
    platform: Platform,
    link: str,
    title: str,
    description: str,
    source_url: str,
    query: str | None,
) -> None:
    existing = items.get(link)
    if existing:
        if not existing.title and title:
            existing.title = title
        if len(description) > len(existing.description):
            existing.description = description
        if query and query not in existing.queries:
            existing.queries.append(query)
        if source_url and source_url not in existing.sources:
            existing.sources.append(source_url)
        return

    items[link] = GroupLink(
        platform=platform.key,
        title=title or link,
        link=link,
        description=description,
        source_url=source_url,
        queries=[query] if query else [],
        sources=[source_url] if source_url else [],
    )


def run_search(query: str, page: int, args: argparse.Namespace) -> list[dict[str, Any]]:
    """Ejecuta una búsqueda con reintentos y backoff exponencial."""
    last_error: BaseException | None = None
    attempts = args.retries + 1

    for attempt in range(attempts):
        try:
            with DDGS(timeout=args.timeout, proxy=args.proxy) as ddgs:
                results = ddgs.text(
                    query,
                    max_results=args.max_results,
                    region=args.region,
                    safesearch=args.safesearch,
                    timelimit=args.timelimit,
                    backend=args.backend,
                    page=page,
                )
            return list(results or [])
        except RatelimitException as exc:
            last_error = exc
            logging.warning("Rate limit en el intento %d/%d: %s", attempt + 1, attempts, exc)
        except TimeoutException as exc:
            last_error = exc
            logging.warning("Timeout en el intento %d/%d: %s", attempt + 1, attempts, exc)
        except DDGSException as exc:
            if "no results" in str(exc).lower():
                return []
            last_error = exc
            logging.warning(
                "Error de búsqueda en el intento %d/%d: %s",
                attempt + 1,
                attempts,
                exc,
            )
        except Exception as exc:  # pragma: no cover - errores de red inesperados
            last_error = exc
            logging.warning(
                "Error inesperado en el intento %d/%d: %s",
                attempt + 1,
                attempts,
                exc,
            )

        if attempt < args.retries:
            delay = args.delay * (2**attempt) + random.uniform(0, 0.5)
            time.sleep(delay)

    if last_error is not None:
        raise last_error
    raise DDGSException("La búsqueda no devolvió resultados")


def search_platform(
    platform: Platform,
    query: str,
    args: argparse.Namespace,
    cache: Cache | None,
) -> PlatformResult:
    """Busca y extrae enlaces de una plataforma para una consulta."""
    start = time.monotonic()
    items: dict[str, GroupLink] = {}
    source_pages: set[str] = set()
    exclude_patterns = [
        pattern.strip().lower() for pattern in (args.exclude or "").split(",") if pattern.strip()
    ]

    try:
        for page in range(1, args.pages + 1):
            cache_key = None
            raw_results: list[dict[str, Any]] | None = None
            if cache:
                cache_key = cache.make_key(
                    kind="search",
                    platform=platform.key,
                    query=query,
                    page=page,
                    exact=args.exact,
                    max_results=args.max_results,
                    region=args.region,
                    safesearch=args.safesearch,
                    timelimit=args.timelimit,
                    backend=args.backend,
                )
                raw_results = cache.get(cache_key)

            if raw_results is None:
                raw_results = run_search(build_query(platform, query, args.exact), page, args)
                if cache and cache_key:
                    cache.set(cache_key, raw_results)

            if not isinstance(raw_results, list):
                raw_results = []

            for item in raw_results:
                if not isinstance(item, dict):
                    continue
                links, title, href, body = extract_from_item(item, platform)

                if (
                    href.startswith(("http://", "https://"))
                    and not is_platform_url(href, platform)
                    and not is_excluded(href, title, body, patterns=exclude_patterns)
                ):
                    source_pages.add(href)

                if not links or is_excluded(href, title, body, patterns=exclude_patterns):
                    continue

                for link in links:
                    add_item(items, platform, link, title, body, href, query)

    except KeyboardInterrupt:
        raise
    except Exception as exc:
        return PlatformResult(
            key=platform.key,
            items=list(items.values()),
            error=f"{type(exc).__name__}: {exc}",
            elapsed=time.monotonic() - start,
            source_pages=source_pages,
        )

    return PlatformResult(
        key=platform.key,
        items=list(items.values()),
        elapsed=time.monotonic() - start,
        source_pages=source_pages,
    )


def merge_platform_result(report: SearchReport, result: PlatformResult) -> None:
    if result.error:
        report.errors[result.key] = result.error
    report.source_pages.setdefault(result.key, set()).update(result.source_pages)

    bucket = report.results.setdefault(result.key, [])
    index = {item.link: item for item in bucket}
    for item in result.items:
        existing = index.get(item.link)
        if existing is None:
            bucket.append(item)
            index[item.link] = item
            continue
        if not existing.title and item.title:
            existing.title = item.title
        if len(item.description) > len(existing.description):
            existing.description = item.description
        for query in item.queries:
            if query not in existing.queries:
                existing.queries.append(query)
        for source in item.sources:
            if source not in existing.sources:
                existing.sources.append(source)


def update_task_done(
    progress: Progress,
    task: Any,
    platform: Platform,
    query: str,
    result: PlatformResult,
) -> None:
    if result.error:
        description = f"[red]{platform.name}[/] · {query} · error"
    else:
        description = (
            f"[{platform.color}]{platform.name}[/] · {query} · {len(result.items)} enlaces"
        )
    progress.update(task, description=description, total=1, completed=1)


def search_all(
    queries: Sequence[str],
    platforms: Sequence[Platform],
    args: argparse.Namespace,
    cache: Cache | None,
    report: SearchReport,
    progress: Progress,
) -> None:
    total = len(queries) * len(platforms)
    overall = progress.add_task("[bold]Progreso total[/]", total=total)

    if args.workers <= 1:
        for query in queries:
            for platform in platforms:
                task = progress.add_task(
                    f"[{platform.color}]{platform.name}[/] · {query}", total=None
                )
                result = search_platform(platform, query, args, cache)
                update_task_done(progress, task, platform, query, result)
                merge_platform_result(report, result)
                progress.advance(overall)
        return

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for query in queries:
            for platform in platforms:
                task = progress.add_task(
                    f"[{platform.color}]{platform.name}[/] · {query}", total=None
                )
                future = executor.submit(search_platform, platform, query, args, cache)
                futures[future] = (platform, query, task)

        for future in as_completed(futures):
            platform, query, task = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # pragma: no cover - protección extra
                result = PlatformResult(
                    key=platform.key,
                    items=[],
                    error=f"{type(exc).__name__}: {exc}",
                )
            update_task_done(progress, task, platform, query, result)
            merge_platform_result(report, result)
            progress.advance(overall)


def robots_allowed(client: httpx.Client, url: str, robots_cache: dict[str, bool]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    netloc = parsed.netloc
    if netloc in robots_cache:
        return robots_cache[netloc]

    allowed = True
    try:
        response = client.get(f"{parsed.scheme}://{netloc}/robots.txt", timeout=5)
        if response.status_code == 200:
            parser = RobotFileParser()
            parser.parse(response.text.splitlines())
            allowed = parser.can_fetch("sc-what", url)
    except httpx.HTTPError:
        allowed = True
    robots_cache[netloc] = allowed
    return allowed


def extract_page_title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()


def deep_search(
    report: SearchReport,
    args: argparse.Namespace,
    progress: Progress,
) -> None:
    """Visita páginas de resultados para encontrar enlaces fuera del snippet."""
    exclude_patterns = [
        pattern.strip().lower() for pattern in (args.exclude or "").split(",") if pattern.strip()
    ]
    robots_cache: dict[str, bool] = {}

    with httpx.Client(
        timeout=args.timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for platform_key, source_pages in report.source_pages.items():
            platform = PLATFORMS.get(platform_key)
            if platform is None:
                continue
            urls = [
                url
                for url in sorted(source_pages)
                if not is_platform_url(url, platform)
                and not is_excluded(url, patterns=exclude_patterns)
            ][: args.deep_limit]
            if not urls:
                continue

            task = progress.add_task(
                f"[{platform.color}]Profundizando en {platform.name}[/]",
                total=len(urls),
            )
            items: dict[str, GroupLink] = {}
            for url in urls:
                if not robots_allowed(client, url, robots_cache):
                    logging.debug("robots.txt bloquea %s", url)
                    progress.advance(task)
                    continue
                try:
                    response = client.get(url)
                except httpx.HTTPError as exc:
                    logging.debug("Error al descargar %s: %s", url, exc)
                    progress.advance(task)
                    continue

                if response.status_code != 200:
                    progress.advance(task)
                    continue
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type and "text" not in content_type:
                    progress.advance(task)
                    continue

                page_text = response.text[:MAX_DEEP_BYTES]
                title = extract_page_title(page_text) or url
                links = extract_links(page_text, platform)
                for link in links:
                    if is_excluded(url, title, patterns=exclude_patterns):
                        continue
                    add_item(items, platform, link, title, "", url, None)

                if args.deep_delay:
                    time.sleep(args.deep_delay)
                progress.advance(task)

            result = PlatformResult(
                key=platform.key,
                items=list(items.values()),
                elapsed=0.0,
                source_pages=set(),
            )
            merge_platform_result(report, result)


def parse_member_count(raw: str) -> int | None:
    match = re.search(r"([\d][\d.,\s]*)\s*([KMB])?(?![A-Za-z])", raw, re.IGNORECASE)
    if not match:
        return None

    number = re.sub(r"\s", "", match.group(1))
    suffix = (match.group(2) or "").upper()
    if suffix:
        try:
            value = float(number.replace(",", "."))
        except ValueError:
            return None
        multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
        return int(value * multipliers[suffix])

    digits = re.sub(r"[^\d]", "", number)
    return int(digits) if digits else None


def validate_one(
    item: GroupLink,
    args: argparse.Namespace,
    cache: Cache | None,
) -> ValidationResult:
    cache_key = None
    if cache:
        cache_key = cache.make_key(kind="validate", platform=item.platform, link=item.link)
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            return ValidationResult(
                valid=cached.get("valid"),
                member_count=cached.get("member_count"),
                title=cached.get("title"),
            )

    if args.validate_delay:
        time.sleep(args.validate_delay)

    result = ValidationResult(valid=None)
    try:
        with httpx.Client(
            timeout=args.timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            if item.platform == "discord":
                code = item.link.rstrip("/").rsplit("/", 1)[-1]
                response = client.get(
                    f"https://discord.com/api/v10/invites/{code}?with_counts=true"
                )
                if response.status_code == 404:
                    result = ValidationResult(valid=False)
                elif response.status_code == 200:
                    data = response.json()
                    guild = data.get("guild") or {}
                    result = ValidationResult(
                        valid=True,
                        member_count=data.get("approximate_member_count"),
                        title=guild.get("name"),
                    )

            elif item.platform == "telegram":
                path = urlparse(item.link).path.strip("/")
                response = client.get(f"https://t.me/{path}")
                text = response.text[:MAX_DEEP_BYTES]
                lowered = text.lower()
                if response.status_code == 404 or "invite link is invalid" in lowered:
                    result = ValidationResult(valid=False)
                elif response.status_code == 200 and "tgme_page_extra" in text:
                    extra = re.search(
                        r'<div class="tgme_page_extra">(.*?)</div>',
                        text,
                        re.IGNORECASE | re.DOTALL,
                    )
                    raw_extra = ""
                    if extra:
                        raw_extra = html.unescape(re.sub(r"<[^>]+>", " ", extra.group(1)))
                    result = ValidationResult(
                        valid=True, member_count=parse_member_count(raw_extra)
                    )
                elif response.status_code == 200 and "tgme_page_title" in text:
                    result = ValidationResult(valid=True)

            elif item.platform == "whatsapp":
                response = client.get(item.link)
                text = response.text[:MAX_DEEP_BYTES].lower()
                if (
                    response.status_code == 404
                    or "invite link revoked" in text
                    or "chat not found" in text
                ):
                    result = ValidationResult(valid=False)
                elif response.status_code == 200 and "group chat" in text:
                    result = ValidationResult(valid=True)

            elif item.platform == "signal":
                response = client.get(item.link)
                if response.status_code == 404:
                    result = ValidationResult(valid=False)
                elif response.status_code == 200:
                    result = ValidationResult(valid=True)

    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        logging.debug("No se pudo validar %s: %s", item.link, exc)
        return ValidationResult(valid=None)

    if cache and cache_key:
        cache.set(
            cache_key,
            {
                "valid": result.valid,
                "member_count": result.member_count,
                "title": result.title,
            },
            ttl=VALIDATION_CACHE_TTL,
        )
    return result


def validate_links(
    report: SearchReport,
    args: argparse.Namespace,
    cache: Cache | None,
    progress: Progress,
) -> None:
    links = [item for items in report.results.values() for item in items]
    if not links:
        return

    task = progress.add_task("[bold]Validando enlaces[/]", total=len(links))
    with ThreadPoolExecutor(max_workers=args.validate_workers) as executor:
        futures = {executor.submit(validate_one, item, args, cache): item for item in links}
        for future in as_completed(futures):
            item = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # pragma: no cover - protección extra
                logging.debug("Error validando %s: %s", item.link, exc)
                progress.advance(task)
                continue

            item.valid = result.valid
            item.member_count = result.member_count
            if result.title and not item.title:
                item.title = result.title
            progress.advance(task)

    for platform_key, items in report.results.items():
        filtered = []
        for item in items:
            if item.valid is False:
                continue
            if (
                args.min_members
                and item.member_count is not None
                and item.member_count < args.min_members
            ):
                continue
            if args.require_members and item.member_count is None:
                continue
            filtered.append(item)
        report.results[platform_key] = filtered


def csv_safe(value: Any) -> str:
    """Evita inyección de fórmulas al abrir el CSV en una hoja de cálculo."""
    if value is None:
        return ""
    text = str(value).replace("\x00", "")
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def format_valid(value: bool | None) -> str:
    if value is True:
        return "sí"
    if value is False:
        return "no"
    return "desconocido"


CSV_HEADER = [
    "Plataforma",
    "Título",
    "Enlace",
    "Descripción",
    "Fuente",
    "Consultas",
    "Validado",
    "Miembros",
]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def save_json(report: SearchReport, path: Path, meta: dict[str, Any]) -> None:
    payload = {
        "meta": meta,
        "results": {
            platform: [item.to_dict() for item in items]
            for platform, items in report.results.items()
        },
    }
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def save_ndjson(report: SearchReport, path: Path) -> None:
    lines = []
    for platform, items in report.results.items():
        for item in items:
            payload = item.to_dict()
            payload["platform"] = platform
            lines.append(json.dumps(payload, ensure_ascii=False))
    atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def read_existing_csv(path: Path, delimiter: str) -> tuple[list[list[str]], set[str]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle, delimiter=delimiter))
    if not rows:
        return [], set()
    body = rows[1:] if rows[0] and rows[0][0].lower() in {"plataforma", "platform"} else rows
    links = {row[2] for row in body if len(row) > 2 and row[2]}
    return body, links


def save_csv(
    report: SearchReport,
    path: Path,
    delimiter: str,
    existing_rows: list[list[str]] | None = None,
    existing_links: set[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    existing_links = existing_links or set()

    with open(tmp, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(CSV_HEADER)
        for row in existing_rows or []:
            writer.writerow(row)
        for platform, items in report.results.items():
            platform_name = PLATFORMS[platform].name
            for item in items:
                if item.link in existing_links:
                    continue
                writer.writerow(
                    [
                        csv_safe(platform_name),
                        csv_safe(item.title),
                        csv_safe(item.link),
                        csv_safe(item.description),
                        csv_safe(item.source_url),
                        csv_safe("; ".join(item.queries)),
                        csv_safe(format_valid(item.valid)),
                        item.member_count if item.member_count is not None else "",
                    ]
                )
    tmp.replace(path)


def merge_existing_json(report: SearchReport, path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    results = data.get("results", {}) if isinstance(data, dict) else {}
    if not isinstance(results, dict):
        return
    for platform, rows in results.items():
        if not isinstance(rows, list):
            continue
        bucket = report.results.setdefault(str(platform), [])
        index = {item.link: item for item in bucket}
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = GroupLink.from_dict(row)
            if item.link and item.link not in index:
                bucket.append(item)
                index[item.link] = item


def merge_existing_ndjson(report: SearchReport, path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        platform = str(row.get("platform") or "")
        if not platform:
            continue
        bucket = report.results.setdefault(platform, [])
        index = {item.link: item for item in bucket}
        item = GroupLink.from_dict(row)
        if item.link and item.link not in index:
            bucket.append(item)
            index[item.link] = item


def build_meta(
    report: SearchReport,
    queries: Sequence[str],
    platforms: Sequence[Platform],
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "queries": list(queries),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": __version__,
        "platforms": [platform.key for platform in platforms],
        "engine": args.backend,
        "region": args.region,
        "safesearch": args.safesearch,
        "timelimit": args.timelimit,
        "validated": args.validate,
        "elapsed_seconds": round(report.elapsed, 2),
        "counts": {
            platform.key: len(report.results.get(platform.key, [])) for platform in platforms
        },
        "errors": report.errors,
    }


def resolve_base_path(args: argparse.Namespace) -> Path:
    base = Path(args.output)
    if args.output_dir:
        base = Path(args.output_dir) / base.name
    if base.suffix.lower() in {".csv", ".json", ".ndjson"}:
        base = base.with_suffix("")
    if args.timestamp:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = base.with_name(f"{base.name}_{stamp}")
    return base


def emit_stdout(report: SearchReport, meta: dict[str, Any], args: argparse.Namespace) -> None:
    output_format = "json" if args.format == "both" else args.format
    if output_format == "json":
        payload = {
            "meta": meta,
            "results": {
                platform: [item.to_dict() for item in items]
                for platform, items in report.results.items()
            },
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return

    if output_format == "ndjson":
        for platform, items in report.results.items():
            for item in items:
                line_payload: dict[str, Any] = item.to_dict()
                line_payload["platform"] = platform
                sys.stdout.write(json.dumps(line_payload, ensure_ascii=False) + "\n")
        return

    writer = csv.writer(sys.stdout, delimiter=args.csv_delimiter)
    writer.writerow(CSV_HEADER)
    for platform, items in report.results.items():
        platform_name = PLATFORMS[platform].name
        for item in items:
            writer.writerow(
                [
                    csv_safe(platform_name),
                    csv_safe(item.title),
                    csv_safe(item.link),
                    csv_safe(item.description),
                    csv_safe(item.source_url),
                    csv_safe("; ".join(item.queries)),
                    csv_safe(format_valid(item.valid)),
                    item.member_count if item.member_count is not None else "",
                ]
            )


def save_outputs(
    report: SearchReport,
    args: argparse.Namespace,
    queries: Sequence[str],
    platforms: Sequence[Platform],
) -> list[Path]:
    meta = build_meta(report, queries, platforms, args)
    if args.stdout:
        emit_stdout(report, meta, args)
        return []

    base = resolve_base_path(args)
    formats = ["csv", "json"] if args.format == "both" else [args.format]
    saved: list[Path] = []

    for output_format in formats:
        path = base.with_suffix(f".{output_format}")
        if path.exists() and not (args.force or args.append):
            raise FileExistsError(f"{path} ya existe; usa --force, --append o --timestamp")

        if output_format == "csv":
            existing_rows: list[list[str]] = []
            existing_links: set[str] = set()
            if args.append and path.exists():
                existing_rows, existing_links = read_existing_csv(path, args.csv_delimiter)
            save_csv(
                report,
                path,
                args.csv_delimiter,
                existing_rows=existing_rows,
                existing_links=existing_links,
            )
        elif output_format == "json":
            if args.append and path.exists():
                merge_existing_json(report, path)
            save_json(report, path, meta)
        elif output_format == "ndjson":
            if args.append and path.exists():
                merge_existing_ndjson(report, path)
            save_ndjson(report, path)

        saved.append(path)

    return saved


def display_summary(report: SearchReport, args: argparse.Namespace) -> None:
    table = Table(title="Resumen de grupos encontrados", title_style="bold magenta")
    table.add_column("Plataforma", justify="left", style="bold")
    table.add_column("Grupos encontrados", justify="right", style="green")

    total = 0
    for platform, items in report.results.items():
        info = PLATFORMS[platform]
        count = len(items)
        table.add_row(Text(info.name), Text(str(count)))
        total += count

    table.add_section()
    table.add_row(Text("Total"), Text(str(total)))
    console.print(table)

    if report.errors:
        errors = Table(title="Errores", title_style="bold red", box=None)
        errors.add_column("Plataforma", style="bold")
        errors.add_column("Error")
        for platform, message in report.errors.items():
            errors.add_row(Text(PLATFORMS[platform].name), Text(message))
        console.print(errors)

    limit = None if args.full else args.limit_display
    for platform, items in report.results.items():
        if not items:
            continue
        info = PLATFORMS[platform]
        console.print(f"\n[bold {info.color}]--- Detalles de {info.name} ({len(items)}) ---[/]")

        detail_table = Table(show_header=True, header_style=f"bold {info.color}", box=None)
        detail_table.add_column("Título", width=35)
        detail_table.add_column("Enlace", style="underline cyan")
        detail_table.add_column("Miembros", justify="right")

        visible = items if limit is None else items[:limit]
        for item in visible:
            title = item.title[:32] + "..." if len(item.title) > 32 else item.title
            if re.fullmatch(r"https?://[^\s\]]+", item.link):
                link_text = Text(item.link, style=f"link {item.link}")
            else:
                link_text = Text(item.link)
            members = str(item.member_count) if item.member_count is not None else "—"
            detail_table.add_row(Text(title), link_text, Text(members))

        console.print(detail_table)
        if limit is not None and len(items) > limit:
            console.print(
                f"[italic grey50]... y {len(items) - limit} resultados más "
                "guardados en los archivos de salida.[/]"
            )

    console.print(f"[grey50]Tiempo total: {report.elapsed:.2f} s · versión {__version__}[/]")
    if report.interrupted:
        console.print("[bold yellow]Búsqueda interrumpida; resultados parciales.[/]")


def setup_logging(args: argparse.Namespace) -> None:
    level = logging.DEBUG if args.verbose else logging.WARNING if args.quiet else logging.INFO
    handlers: list[logging.Handler] = []
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    if not args.quiet:
        handlers.append(
            RichHandler(
                console=console,
                show_path=False,
                show_time=args.verbose,
                markup=False,
            )
        )
    if not handlers:
        handlers.append(logging.NullHandler())
    logging.basicConfig(level=level, format="%(message)s", handlers=handlers, force=True)
    for logger_name in ("ddgs", "httpx", "httpcore", "urllib3", "primp"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"'{value}' no es un entero") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("el valor debe ser mayor que 0")
    return number


def non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"'{value}' no es un entero") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("el valor no puede ser negativo")
    return number


def non_negative_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"'{value}' no es un número") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("el valor no puede ser negativo")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="group-finder",
        description=(
            "Buscador de enlaces de invitación públicos para WhatsApp, Signal, "
            "Microsoft Teams, Discord y Telegram usando dorks de búsqueda."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            '  group-finder "python"\n'
            '  group-finder "gaming" -p telegram,discord -m 20\n'
            '  group-finder "cripto" -p whatsapp -o cripto -f json\n'
            "  group-finder --query-file consultas.txt --validate --min-members 100\n"
            '  group-finder "python" --deep --validate --stdout -f ndjson\n'
        ),
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Palabra clave o término de búsqueda (ej. 'cripto', 'gaming')",
    )
    parser.add_argument(
        "--query-file",
        help="Archivo con una consulta por línea (ignora líneas vacías y #)",
    )
    parser.add_argument(
        "-p",
        "--platforms",
        default="all",
        help=(
            "Plataformas separadas por comas (whatsapp, signal, teams, discord, "
            "telegram) o 'all' (por defecto)"
        ),
    )
    parser.add_argument(
        "-m",
        "--max-results",
        type=positive_int,
        default=50,
        help="Límite máximo de resultados por página y plataforma (por defecto 50)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="results",
        help="Nombre base del archivo de salida (por defecto 'results')",
    )
    parser.add_argument(
        "--output-dir",
        help="Carpeta donde guardar los resultados",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["csv", "json", "both", "ndjson"],
        default="both",
        help="Formato de salida (csv, json, both o ndjson). Por defecto 'both'.",
    )
    parser.add_argument(
        "--csv-delimiter",
        default=",",
        help="Delimitador del CSV (por defecto ','; usa ';' para Excel en español)",
    )
    parser.add_argument(
        "--exact",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Buscar la consulta como frase exacta (por defecto sí)",
    )
    parser.add_argument(
        "--region",
        default="us-en",
        help="Región de búsqueda, por ejemplo 'es-es' (por defecto 'us-en')",
    )
    parser.add_argument(
        "--safesearch",
        choices=["on", "moderate", "off"],
        default="moderate",
        help="Filtrado de contenido (por defecto 'moderate')",
    )
    parser.add_argument(
        "--timelimit",
        choices=["d", "w", "m", "y"],
        default=None,
        help="Limitar resultados por antigüedad: d, w, m o y",
    )
    parser.add_argument(
        "--backend",
        default="auto",
        help="Backend(s) de ddgs separados por comas (por defecto 'auto')",
    )
    parser.add_argument(
        "--retries",
        type=non_negative_int,
        default=3,
        help="Reintentos por búsqueda (por defecto 3)",
    )
    parser.add_argument(
        "--delay",
        type=non_negative_float,
        default=1.0,
        help="Espera base entre reintentos en segundos (por defecto 1.0)",
    )
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=10,
        help="Timeout de red en segundos (por defecto 10)",
    )
    parser.add_argument(
        "--proxy",
        default=None,
        help="Proxy HTTP/SOCKS, por ejemplo 'socks5://127.0.0.1:9050'",
    )
    parser.add_argument(
        "--workers",
        type=positive_int,
        default=1,
        help="Búsquedas concurrentes (por defecto 1, secuencial)",
    )
    parser.add_argument(
        "--pages",
        type=positive_int,
        default=1,
        help="Páginas de resultados por consulta y plataforma (por defecto 1)",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Visitar las páginas de resultados para buscar más enlaces",
    )
    parser.add_argument(
        "--deep-limit",
        type=non_negative_int,
        default=10,
        help="Máximo de páginas a visitar por plataforma con --deep (por defecto 10)",
    )
    parser.add_argument(
        "--deep-delay",
        type=non_negative_float,
        default=1.0,
        help="Espera entre páginas visitadas con --deep (por defecto 1.0)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Comprobar si los enlaces siguen vivos (Discord, Telegram, WhatsApp, Signal)",
    )
    parser.add_argument(
        "--min-members",
        type=non_negative_int,
        default=0,
        help="Filtrar grupos con menos miembros cuando se conozca el dato",
    )
    parser.add_argument(
        "--require-members",
        action="store_true",
        help="Descartar enlaces cuyo número de miembros no se pueda obtener",
    )
    parser.add_argument(
        "--validate-workers",
        type=positive_int,
        default=3,
        help="Validaciones concurrentes (por defecto 3)",
    )
    parser.add_argument(
        "--validate-delay",
        type=non_negative_float,
        default=0.5,
        help="Espera entre validaciones en segundos (por defecto 0.5)",
    )
    parser.add_argument(
        "--cache-dir",
        help="Carpeta de caché (por defecto ~/.cache/group_finder)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Desactivar la caché de búsquedas y validaciones",
    )
    parser.add_argument(
        "--cache-ttl",
        type=non_negative_int,
        default=DEFAULT_CACHE_TTL,
        help="TTL de la caché de búsquedas en segundos (por defecto 3600)",
    )
    parser.add_argument(
        "--exclude",
        default="",
        help="Dominios o palabras a excluir, separados por comas",
    )
    parser.add_argument(
        "--limit-display",
        type=positive_int,
        default=15,
        help="Resultados a mostrar por plataforma (por defecto 15)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Mostrar todos los resultados en la terminal",
    )
    parser.add_argument(
        "--timestamp",
        action="store_true",
        help="Añadir fecha y hora al nombre de los archivos",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Añadir a los archivos existentes sin duplicar enlaces",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sobrescribir archivos existentes",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Escribir los resultados a stdout en vez de a archivos",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Ocultar progreso y resumen; solo mostrar errores",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Mostrar información de depuración",
    )
    parser.add_argument(
        "--log-file",
        help="Guardar logs en un archivo",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Desactivar colores en la terminal",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar las consultas que se ejecutarían sin buscar",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def resolve_queries(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[str]:
    queries: list[str] = []
    if args.query and args.query.strip():
        queries.append(args.query.strip())

    if args.query_file:
        path = Path(args.query_file)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            parser.error(f"No se pudo leer {path}: {exc}")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                queries.append(line)

    queries = list(dict.fromkeys(re.sub(r'"', " ", query).strip() for query in queries))
    queries = [query for query in queries if query]

    if not queries:
        parser.error("Debes indicar una consulta o usar --query-file")

    for query in queries:
        if len(query) > MAX_QUERY_LENGTH:
            parser.error(f"La consulta es demasiado larga ({len(query)} > {MAX_QUERY_LENGTH})")
    return queries


def resolve_platforms(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[Platform]:
    raw = args.platforms.strip().lower()
    if raw == "all":
        return list(PLATFORMS.values())

    keys = list(dict.fromkeys(key.strip() for key in raw.split(",") if key.strip()))
    invalid = [key for key in keys if key not in PLATFORMS]
    if invalid:
        parser.error(
            f"Plataforma(s) no válida(s): {', '.join(invalid)}. Opciones: {', '.join(PLATFORMS)}"
        )
    if not keys:
        parser.error("Debes indicar al menos una plataforma")
    return [PLATFORMS[key] for key in keys]


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.append and args.force:
        parser.error("--append y --force son mutuamente excluyentes")
    if args.timestamp and args.append:
        parser.error("--timestamp y --append no tienen sentido juntos")
    if args.min_members and not args.validate:
        parser.error("--min-members requiere --validate")
    if args.require_members and not args.validate:
        parser.error("--require-members requiere --validate")
    if len(args.csv_delimiter) != 1:
        parser.error("--csv-delimiter debe ser un único carácter")
    if not args.output.strip():
        parser.error("--output no puede estar vacío")
    if not args.region.strip():
        parser.error("--region no puede estar vacío")
    if not args.backend.strip():
        parser.error("--backend no puede estar vacío")


def print_dry_run(
    queries: Sequence[str], platforms: Sequence[Platform], args: argparse.Namespace
) -> None:
    table = Table(title="Consultas que se ejecutarían", title_style="bold magenta")
    table.add_column("Consulta")
    table.add_column("Plataforma")
    table.add_column("Query")
    for query in queries:
        for platform in platforms:
            table.add_row(
                Text(query),
                Text(platform.name),
                Text(build_query(platform, query, args.exact)),
            )
    console.print(table)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    global console, error_console
    console = Console(no_color=args.no_color)
    error_console = Console(stderr=True, no_color=args.no_color)
    setup_logging(args)

    queries = resolve_queries(args, parser)
    platforms = resolve_platforms(args, parser)
    validate_args(args, parser)

    if not args.quiet:
        welcome = Text()
        welcome.append("Buscador de Grupos Multiplataforma\n", style="bold magenta")
        welcome.append("Consultas: ", style="")
        welcome.append(", ".join(queries), style="bold yellow")
        welcome.append("\nPlataformas: ", style="")
        welcome.append(", ".join(platform.name for platform in platforms), style="bold cyan")
        console.print(Panel(Align.center(welcome), subtitle=f"v{__version__}"))

    if args.dry_run:
        print_dry_run(queries, platforms, args)
        return 0

    cache = None
    if not args.no_cache:
        cache_path = Path(args.cache_dir) / "cache.json" if args.cache_dir else default_cache_path()
        cache = Cache(cache_path, ttl=args.cache_ttl)

    report = SearchReport(
        results={platform.key: [] for platform in platforms},
        source_pages={platform.key: set() for platform in platforms},
    )
    start = time.monotonic()

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        disable=args.quiet,
    )

    with progress:
        try:
            search_all(queries, platforms, args, cache, report, progress)
            if args.deep:
                deep_search(report, args, progress)
            if args.validate:
                validate_links(report, args, cache, progress)
        except KeyboardInterrupt:
            report.interrupted = True
            console.print("[bold yellow]Interrumpido; se guardarán los resultados parciales.[/]")
        except Exception as exc:  # pragma: no cover - último recurso
            logging.exception("Error inesperado")
            error_console.print(Text("Error inesperado: ", style="bold red"), Text(str(exc)))
            return 1
        finally:
            report.elapsed = time.monotonic() - start

    if not args.quiet:
        display_summary(report, args)

    try:
        saved = save_outputs(report, args, queries, platforms)
    except FileExistsError as exc:
        error_console.print(Text(str(exc), style="bold red"))
        return 1
    except OSError as exc:
        error_console.print(Text(f"No se pudieron guardar los resultados: {exc}", style="bold red"))
        return 1

    if saved and not args.quiet:
        console.print(
            Text(
                "✓ Resultados guardados en: " + ", ".join(str(path) for path in saved),
                style="bold green",
            )
        )

    if report.interrupted:
        return 130
    if report.errors and len(report.errors) == len(platforms):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
